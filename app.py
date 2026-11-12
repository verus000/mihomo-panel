import asyncio
from contextlib import asynccontextmanager
import datetime
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import urljoin, urlsplit, quote

from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
import sqlite3
from database import Database
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
import yaml

from common import credentials, normalize_proxy, region, render_config, validate_credentials
from probe import probe
from runtime import DATA_DIR, MANAGER_SOCKET, MIHOMO_BIN

ROOT = Path(__file__).parent
CIPHER = Fernet(os.environ['FERNET_KEY'].encode())
DB = Database(os.getenv('DATABASE_PATH', '/var/lib/mihomo-panel/panel.sqlite3'))
WRITE = threading.RLock()
PROBE_LOCK = threading.Semaphore(1)
LOGIN_LOCK = threading.Lock()
LOGIN_ATTEMPTS = {}
STOP = threading.Event()

def enc(value):
    return CIPHER.encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()

def dec(value):
    return json.loads(CIPHER.decrypt(value.encode()))

def password_hash(value, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest

def audit(db, action, detail):
    db.execute('INSERT INTO audit(action,detail) VALUES (?,?)', (action, detail[:500]))

def manager(op, **payload):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(70)
            sock.connect(MANAGER_SOCKET)
            sock.sendall((json.dumps({'op': op, **payload}) + '\n').encode())
            with sock.makefile('rb') as reader:
                result = json.loads(reader.readline(1048576))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(503, '服务管理进程暂时不可用，请稍后重试')
    if not result['ok']:
        raise HTTPException(400, result['error'])
    return result['result']

def require_admin(request: Request):
    token = request.cookies.get('panel_session', '')
    if not token:
        raise HTTPException(401, '请先登录')
    digest = hashlib.sha256(token.encode()).hexdigest()
    with DB.connection() as db:
        session = db.execute("SELECT 1 FROM sessions WHERE token_hash=? AND expires_at>strftime('%Y-%m-%dT%H:%M:%fZ','now')", (digest,)).fetchone()
    if not session:
        raise HTTPException(401, '登录已过期，请重新登录')

def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('请填写有效的 HTTP/HTTPS 订阅地址')
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
        raise ValueError('订阅地址必须指向公网服务器')

def fetch_subscription(url):
    with httpx.Client(timeout=httpx.Timeout(25, connect=10), trust_env=False, headers={'User-Agent': 'clash.meta'}) as client:
        for _ in range(5):
            validate_url(url)
            with client.stream('GET', url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers['location'])
                    continue
                if response.status_code != 200:
                    raise ValueError(f'订阅服务器返回 HTTP {response.status_code}')
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise ValueError('订阅超过 4 MB 限制')
                    chunks.append(chunk)
                document = yaml.safe_load(b''.join(chunks))
                if not isinstance(document, dict) or not isinstance(document.get('proxies'), list):
                    raise ValueError('需要包含 proxies 节点列表的 Clash YAML 订阅')
                if len(document['proxies']) > 3000:
                    raise ValueError('单订阅最多 3000 个节点')
                nodes, skipped = [], 0
                for raw in document['proxies']:
                    try:
                        node = normalize_proxy(raw)
                        if len(json.dumps(node)) > 65536:
                            raise ValueError('节点配置过大')
                        nodes.append(node)
                    except (ValueError, TypeError, OverflowError):
                        skipped += 1
                if not nodes:
                    raise ValueError('订阅中没有可导入的节点，已保留原节点')
                return nodes, skipped
    raise ValueError('订阅重定向次数过多')

def refresh_subscription(subscription_id):
    with WRITE:
        with DB.connection() as db:
            sub = db.execute('SELECT * FROM subscriptions WHERE id=?', (subscription_id,)).fetchone()
        if not sub or not sub['url_enc']:
            raise HTTPException(400, '此分类没有远程订阅地址')
        try:
            nodes, skipped = fetch_subscription(dec(sub['url_enc']))
            seen = {}
            with DB.connection(write=True) as db:
                db.execute('UPDATE nodes SET available=false WHERE subscription_id=?', (subscription_id,))
                for node in nodes:
                    key = node['name'] + '\0' + node['type']
                    index = seen.get(key, 0)
                    seen[key] = index + 1
                    identity = hashlib.sha256((key + '\0' + str(index)).encode()).hexdigest()
                    db.execute('''INSERT INTO nodes(subscription_id,identity,name,country,protocol,config_enc)
                        VALUES (?,?,?,?,?,?) ON CONFLICT(subscription_id,identity) DO UPDATE SET
                        name=excluded.name, country=CASE WHEN nodes.manual_country THEN nodes.country ELSE excluded.country END,
                        protocol=excluded.protocol, config_enc=excluded.config_enc, available=true, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''',
                        (subscription_id, identity, node['name'], region(node['name']), node['type'], enc(node)))
                db.execute("UPDATE subscriptions SET last_refresh=strftime('%Y-%m-%dT%H:%M:%fZ','now'), next_refresh=strftime('%Y-%m-%dT%H:%M:%fZ','now','+' || interval_hours || ' hours'), last_error=NULL WHERE id=?", (subscription_id,))
                audit(db, 'subscription.refresh', f'{sub["name"]}: {len(nodes)} 节点，跳过 {skipped}')
            return {'count': len(nodes), 'skipped': skipped}
        except Exception as exc:
            message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, yaml.YAMLError) else f'订阅更新失败：{type(exc).__name__}'
            # Never expose the token-bearing subscription URL in an exception.
            message = message.replace(dec(sub['url_enc']), '[订阅地址]')[:300]
            with DB.connection(write=True) as db:
                db.execute("UPDATE subscriptions SET last_error=?, next_refresh=strftime('%Y-%m-%dT%H:%M:%fZ','now','+15 minutes') WHERE id=?", (message, subscription_id))
            raise HTTPException(400, message)

def refresh_loop():
    while not STOP.wait(60):
        try:
            with DB.connection(write=True) as db:
                rows = db.execute("SELECT id FROM subscriptions WHERE enabled AND url_enc<>'' AND next_refresh<=strftime('%Y-%m-%dT%H:%M:%fZ','now')").fetchall()
                db.execute("DELETE FROM sessions WHERE expires_at<strftime('%Y-%m-%dT%H:%M:%fZ','now')")
                db.execute("DELETE FROM audit WHERE at<strftime('%Y-%m-%dT%H:%M:%fZ','now','-90 days')")
            for row in rows:
                if STOP.is_set():
                    return
                try:
                    refresh_subscription(row['id'])
                except Exception:
                    pass  # The precise failure is already persisted in subscriptions.last_error.
        except Exception:
            pass

@asynccontextmanager
async def lifespan(app):
    DB.initialize()
    STOP.clear()
    worker = threading.Thread(target=refresh_loop, daemon=True)
    worker.start()
    yield
    STOP.set()
    await asyncio.to_thread(worker.join, 30)

app = FastAPI(title='Mihomo 管理面板', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.getenv('PANEL_HOSTS', 'localhost,127.0.0.1').split(','))

@app.middleware('http')
async def security_headers(request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.headers.get('x-requested-with') != 'MihomoPanel':
        return JSONResponse({'detail': '请求来源校验失败'}, status_code=403)
    try:
        if int(request.headers.get('content-length', '0')) > 1048576:
            return JSONResponse({'detail': '请求过大'}, status_code=413)
    except ValueError:
        return JSONResponse({'detail': '请求长度无效'}, status_code=400)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response

@app.exception_handler(sqlite3.IntegrityError)
async def db_error(request, exc):
    return JSONResponse({'detail': '数据库操作失败，请检查名称或端口是否重复后重试'}, status_code=409)

@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'detail': str(exc)[:400]}, status_code=400)

class Login(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)

@app.post('/api/login')
def login(body: Login, request: Request, response: Response):
    key = request.client.host
    with LOGIN_LOCK:
        now = time.monotonic()
        attempts = [t for t in LOGIN_ATTEMPTS.get(key, []) if t > now - 60]
        if len(attempts) >= 5:
            raise HTTPException(429, '登录尝试过多，请一分钟后重试')
        LOGIN_ATTEMPTS[key] = attempts + [now]
    with DB.connection(write=True) as db:
        stored = db.execute("SELECT value FROM settings WHERE key='admin_hash'").fetchone()['value']
        valid = hmac.compare_digest(password_hash(body.password, stored.split(':')[0]), stored)
        if body.username != 'admin' or not valid:
            raise HTTPException(401, '用户名或密码错误')
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions VALUES (?,strftime('%Y-%m-%dT%H:%M:%fZ','now','+12 hours'))", (hashlib.sha256(token.encode()).hexdigest(),))
        audit(db, 'admin.login', '管理员登录')
    with LOGIN_LOCK:
        LOGIN_ATTEMPTS.pop(key, None)
    response.set_cookie('panel_session', token, httponly=True, samesite='strict', max_age=43200, secure=os.getenv('COOKIE_SECURE') == '1')
    return {'ok': True}

@app.post('/api/logout', dependencies=[Depends(require_admin)])
def logout(request: Request, response: Response):
    with DB.connection(write=True) as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(request.cookies['panel_session'].encode()).hexdigest(),))
    response.delete_cookie('panel_session')
    return {'ok': True}

class PasswordChange(BaseModel):
    current: str = Field(max_length=256)
    password: str = Field(min_length=16, max_length=128)

@app.post('/api/admin/password', dependencies=[Depends(require_admin)])
def change_password(body: PasswordChange):
    with DB.connection(write=True) as db:
        old = db.execute("SELECT value FROM settings WHERE key='admin_hash'").fetchone()['value']
        if not hmac.compare_digest(password_hash(body.current, old.split(':')[0]), old):
            raise HTTPException(400, '当前密码不正确')
        db.execute("UPDATE settings SET value=? WHERE key='admin_hash'", (password_hash(body.password),))
        db.execute('DELETE FROM sessions')
        audit(db, 'admin.password', '更新管理员密码')
    return {'ok': True}

@app.get('/api/state', dependencies=[Depends(require_admin)])
def state():
    with DB.connection() as db:
        subs = db.execute('''SELECT s.id,s.name,s.enabled,s.interval_hours,s.last_refresh,s.next_refresh,s.last_error,
            (s.url_enc<>'') AS remote, count(n.id) FILTER (WHERE n.available) AS node_count
            FROM subscriptions s LEFT JOIN nodes n ON n.subscription_id=s.id GROUP BY s.id ORDER BY s.id''').fetchall()
        nodes = db.execute('''SELECT n.id,n.subscription_id,n.name,n.country,n.tags,n.protocol,n.available,s.name AS subscription
            FROM nodes n JOIN subscriptions s ON s.id=n.subscription_id ORDER BY n.country,n.name,n.id''').fetchall()
        services = db.execute('''SELECT v.id,v.name,v.port,v.username,v.node_id,v.enabled,v.last_probe,v.updated_at,
            n.name AS node_name,n.country,n.available,s.name AS subscription,v.snapshot_enc,n.config_enc
            FROM services v JOIN nodes n ON n.id=v.node_id JOIN subscriptions s ON s.id=n.subscription_id ORDER BY v.port''').fetchall()
        events = db.execute('SELECT at,action,detail FROM audit ORDER BY id DESC LIMIT 30').fetchall()
    for service in services:
        service['update_available'] = dec(service.pop('snapshot_enc')) != dec(service.pop('config_enc'))
    try:
        statuses = manager('status')
    except Exception:
        statuses = {}
    for service in services:
        service['status'] = statuses.get(service['id'], {})
    return {'public_ip': os.getenv('PUBLIC_IP', ''), 'subscriptions': subs, 'nodes': nodes, 'services': services, 'events': events}

class SubscriptionInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(default='', max_length=4096)
    enabled: bool = True
    interval_hours: int = Field(default=24, ge=1, le=168)

@app.post('/api/subscriptions', dependencies=[Depends(require_admin)])
def add_subscription(body: SubscriptionInput):
    validate_url(body.url)
    with WRITE, DB.connection(write=True) as db:
        row = db.execute('INSERT INTO subscriptions(name,url_enc,enabled,interval_hours) VALUES (?,?,?,?) RETURNING id',
            (body.name.strip(), enc(body.url), body.enabled, body.interval_hours)).fetchone()
        audit(db, 'subscription.create', body.name)
    try:
        result = refresh_subscription(row['id'])
    except HTTPException as exc:
        return {'id': row['id'], 'warning': exc.detail}
    return {'id': row['id'], **result}

@app.put('/api/subscriptions/{sub_id}', dependencies=[Depends(require_admin)])
def edit_subscription(sub_id: int, body: SubscriptionInput):
    if body.url:
        validate_url(body.url)
    with WRITE, DB.connection(write=True) as db:
        old = db.execute('SELECT * FROM subscriptions WHERE id=?', (sub_id,)).fetchone()
        if not old:
            raise HTTPException(404, '订阅不存在')
        db.execute('UPDATE subscriptions SET name=?,url_enc=?,enabled=?,interval_hours=? WHERE id=?',
            (body.name.strip(), enc(body.url) if body.url else old['url_enc'], body.enabled, body.interval_hours, sub_id))
        audit(db, 'subscription.edit', body.name)
    return {'ok': True}

@app.post('/api/subscriptions/{sub_id}/refresh', dependencies=[Depends(require_admin)])
def refresh(sub_id: int):
    return refresh_subscription(sub_id)

@app.delete('/api/subscriptions/{sub_id}', dependencies=[Depends(require_admin)])
def delete_subscription(sub_id: int):
    with WRITE, DB.connection(write=True) as db:
        if db.execute('SELECT 1 FROM services v JOIN nodes n ON n.id=v.node_id WHERE n.subscription_id=? LIMIT 1', (sub_id,)).fetchone():
            raise HTTPException(409, '此订阅仍被服务使用，请先为这些服务更换节点')
        db.execute('DELETE FROM subscriptions WHERE id=?', (sub_id,))
        audit(db, 'subscription.delete', str(sub_id))
    return {'ok': True}

class NodeInput(BaseModel):
    country: str = Field(min_length=1, max_length=40)
    tags: list[str] = Field(default_factory=list, max_length=12)

@app.put('/api/nodes/{node_id}', dependencies=[Depends(require_admin)])
def edit_node(node_id: int, body: NodeInput):
    tags = list(dict.fromkeys(t.strip() for t in body.tags if t.strip()))
    if any(len(t) > 30 for t in tags):
        raise HTTPException(400, '每个标签最多 30 个字符')
    with WRITE, DB.connection(write=True) as db:
        if not db.execute('UPDATE nodes SET country=?,manual_country=true,tags=? WHERE id=? RETURNING id', (body.country, json.dumps(tags, ensure_ascii=False), node_id)).fetchone():
            raise HTTPException(404, '节点不存在')
    return {'ok': True}

@app.post('/api/credentials/generate', dependencies=[Depends(require_admin)])
def generate_credentials():
    return credentials()

class ServiceInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    port: int = Field(ge=1024, le=65535)
    username: str = Field(default='', max_length=64)
    password: str = Field(default='', max_length=128)
    node_id: int = Field(gt=0)
    enabled: bool = True

def save_service(body, slug=None):
    with WRITE, DB.connection(write=True) as db:
        old = db.execute('SELECT * FROM services WHERE id=?', (slug,)).fetchone() if slug else None
        if slug and not old:
            raise HTTPException(404, '服务不存在')
        node = db.execute('SELECT * FROM nodes WHERE id=?', (body.node_id,)).fetchone()
        if not node or (not node['available'] and (not old or old['node_id'] != node['id'])):
            raise HTTPException(400, '节点已从订阅移除，请选择其他节点')
        if db.execute('SELECT 1 FROM services WHERE port=? AND id<>?', (body.port, slug or '')).fetchone():
            raise HTTPException(409, '此端口已被其他服务使用')
        fresh = credentials()
        user = body.username or (old['username'] if old else fresh['username'])
        password = body.password or (dec(old['password_enc']) if old else fresh['password'])
        validate_credentials(user, password)
        selected = dec(node['config_enc']) if node['available'] else dec(old['snapshot_enc'])
        slug = slug or 'svc-' + secrets.token_hex(6)
        manager('apply', id=slug, port=body.port, username=user, password=password, proxy=selected, enabled=body.enabled)
        db.execute('''INSERT INTO services(id,name,port,username,password_enc,node_id,snapshot_enc,enabled)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,port=excluded.port,
            username=excluded.username,password_enc=excluded.password_enc,node_id=excluded.node_id,
            snapshot_enc=excluded.snapshot_enc,enabled=excluded.enabled,last_probe=NULL,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''',
            (slug, body.name.strip(), body.port, user, enc(password), body.node_id, enc(selected), body.enabled))
        audit(db, 'service.apply', f'{body.name}: {body.port} → {node["name"]}')
    return {'id': slug, 'username': user, 'password': password}

@app.post('/api/services', dependencies=[Depends(require_admin)])
def create_service(body: ServiceInput):
    return save_service(body)

@app.put('/api/services/{slug}', dependencies=[Depends(require_admin)])
def edit_service(slug: str, body: ServiceInput):
    return save_service(body, slug)

@app.post('/api/services/{slug}/credentials', dependencies=[Depends(require_admin)])
def service_credentials(slug: str):
    with DB.connection(write=True) as db:
        row = db.execute('SELECT port,username,password_enc FROM services WHERE id=?', (slug,)).fetchone()
        if not row:
            raise HTTPException(404, '服务不存在')
        audit(db, 'service.credentials', slug)
    password = dec(row.pop('password_enc'))
    host = os.getenv('PUBLIC_IP', '127.0.0.1')
    uri_host = '[' + host + ']' if ':' in host else host
    return {**row, 'host': host, 'password': password, 'uri': f'socks5://{quote(row["username"],safe="")}:{quote(password,safe="")}@{uri_host}:{row["port"]}'}

class Action(BaseModel):
    action: str

@app.post('/api/services/{slug}/action', dependencies=[Depends(require_admin)])
def service_action(slug: str, body: Action):
    with WRITE, DB.connection(write=True) as db:
        if not db.execute('SELECT 1 FROM services WHERE id=?', (slug,)).fetchone():
            raise HTTPException(404, '服务不存在')
        result = manager('action', id=slug, action=body.action)
        if body.action in ('start', 'stop'):
            db.execute('UPDATE services SET enabled=? WHERE id=?', (body.action == 'start', slug))
        audit(db, 'service.' + body.action, slug)
    return result

@app.delete('/api/services/{slug}', dependencies=[Depends(require_admin)])
def delete_service(slug: str):
    with WRITE, DB.connection(write=True) as db:
        if not db.execute('SELECT 1 FROM services WHERE id=?', (slug,)).fetchone():
            raise HTTPException(404, '服务不存在')
        manager('delete', id=slug)
        db.execute('DELETE FROM services WHERE id=?', (slug,))
        audit(db, 'service.delete', slug)
    return {'ok': True}

@app.get('/api/services/{slug}/logs', dependencies=[Depends(require_admin)])
def logs(slug: str):
    return manager('logs', id=slug)

@app.post('/api/services/{slug}/test', dependencies=[Depends(require_admin)])
def test_service(slug: str):
    if not PROBE_LOCK.acquire(blocking=False):
        raise HTTPException(429, '另一个测试正在运行，请稍后重试')
    try:
        with DB.connection() as db:
            row = db.execute('SELECT * FROM services WHERE id=?', (slug,)).fetchone()
        if not row:
            raise HTTPException(404, '服务不存在')
        result = probe(row['port'], row['username'], dec(row['password_enc']))
        if not result['tcp'] or result.get('udp') is False:
            lines = manager('logs', id=slug, since=result['at'])['logs'].splitlines()
            result['upstream_errors'] = [line for line in lines if 'error:' in line and '127.0.0.1:' in line][-3:]
        with DB.connection(write=True) as db:
            db.execute('UPDATE services SET last_probe=? WHERE id=?', (json.dumps(result, ensure_ascii=False), slug))
            audit(db, 'service.test', f'{slug}: TCP={result["tcp"]}, UDP={result.get("udp")}')
        return result
    finally:
        PROBE_LOCK.release()

@app.post('/api/nodes/{node_id}/test', dependencies=[Depends(require_admin)])
def test_node(node_id: int):
    if not PROBE_LOCK.acquire(blocking=False):
        raise HTTPException(429, '另一个测试正在运行，请稍后重试')
    process = None
    try:
        with DB.connection() as db:
            node = db.execute('SELECT * FROM nodes WHERE id=? AND available', (node_id,)).fetchone()
        if not node:
            raise HTTPException(404, '节点不可用')
        with tempfile.TemporaryDirectory(prefix='node-test-', dir=DATA_DIR) as folder:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            auth = credentials()
            config = render_config(port, auth['username'], auth['password'], dec(node['config_enc']))
            config['allow-lan'], config['bind-address'] = False, '127.0.0.1'
            path = Path(folder) / 'config.yaml'
            path.write_text(yaml.safe_dump(config))
            path.chmod(0o600)
            with (Path(folder) / 'core.log').open('w+') as logfile:
                process = subprocess.Popen([MIHOMO_BIN, '-d', folder, '-f', str(path)], stdout=logfile, stderr=logfile)
                for _ in range(40):
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.1):
                            break
                    except OSError:
                        if process.poll() is not None:
                            raise HTTPException(400, '节点配置无法启动，请检查协议参数')
                        time.sleep(.1)
                result = probe(port, auth['username'], auth['password'], with_udp=False)
                process.terminate()
                process.wait(timeout=5)
                process = None
                if not result['tcp']:
                    logfile.seek(0)
                    result['upstream_errors'] = [line.strip() for line in logfile if 'error:' in line][-3:]
                return result
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait()
        PROBE_LOCK.release()

@app.get('/')
def index():
    return FileResponse(ROOT / 'static' / 'index.html')

app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

@app.get('/healthz')
def health():
    with DB.connection() as db:
        db.execute('SELECT 1').fetchone()
    return {'ok': True}
