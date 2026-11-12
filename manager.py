"""Root-only local service manager. No shell commands and no TCP listener."""
import grp
import datetime
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import time
import yaml
from common import render_config
from runtime import MANAGER_STATE, MANAGER_SOCKET, CONFIG_DIR, INSTANCE_DATA, UNIT_DIR, MIHOMO_BIN

STATE = MANAGER_STATE
REGISTRY = STATE / 'services.json'
SOCKET = MANAGER_SOCKET

def run(args, check=True, timeout=25, **kwargs):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kwargs)
    if check and r.returncode:
        # Commands contain paths/units, never SOCKS or subscription secrets.
        raise ValueError((r.stderr.strip() or r.stdout.strip() or '操作失败')[-1800:])
    return r

def atomic(path, content, mode=0o600, gid=0):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.panel-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        os.fchown(fd, 0, gid)
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def registry():
    return json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}

def save_registry(data):
    atomic(REGISTRY, json.dumps(data, indent=2))

def paths(slug):
    if slug not in ('india', 'philippines') and not re.fullmatch(r'svc-[0-9a-f]{12}', slug):
        raise ValueError('无效的服务标识')
    account = 'mihomo-' + slug
    return account, CONFIG_DIR / slug, INSTANCE_DATA / account, account + '.service'

def status(slug):
    unit = paths(slug)[3]
    r = run(['systemctl', 'show', unit, '--property=ActiveState,SubState,MainPID,UnitFileState'], check=False)
    return dict(line.split('=', 1) for line in r.stdout.splitlines() if '=' in line)

def nft_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', value):
        raise ValueError('不支持的 nftables 表或链名称')
    return value


def firewall(data):
    automatic = os.getenv('FIREWALL_MODE', 'auto') != 'off'
    ports = sorted({int(v['port']) for v in data.values()}) if automatic else []
    panel = int(os.getenv('PANEL_PORT', '8080')) if automatic and os.getenv('PANEL_FIREWALL') == '1' else None
    rules = json.loads(run(['nft', '-j', 'list', 'ruleset']).stdout)['nftables']
    changes = []
    # Only remove rules marked as ours; all unrelated rules retain their order.
    for entry in rules:
        rule = entry.get('rule', {})
        if rule.get('comment', '').startswith('mihomo-panel:'):
            changes.append(f'delete rule {nft_name(rule["family"])} {nft_name(rule["table"])} {nft_name(rule["chain"])} handle {int(rule["handle"])}')
    own_table = any(x.get('table', {}).get('family')=='inet' and x['table']['name']=='mihomo_panel' for x in rules)
    if own_table:
        changes.append('delete table inet mihomo_panel')
    changes.append('table inet mihomo_panel {\n chain input { type filter hook input priority -10; policy accept; }\n}')
    targets = [('inet','mihomo_panel','input')]
    targets += [(c['family'],c['table'],c['name']) for x in rules if (c:=x.get('chain', {})).get('hook')=='input' and c.get('family') in ('inet','ip','ip6') and c.get('table')!='mihomo_panel']
    # Accept in every input base chain: accept in one chain cannot override a later drop.
    for family, table, chain in targets:
        for protocol, allowed in [('tcp',sorted(set(ports + ([panel] if panel else [])))),('udp',ports)]:
            if allowed:
                values=', '.join(str(v) for v in allowed)
                changes.append(f'insert rule {family} {nft_name(table)} {nft_name(chain)} {protocol} dport {{ {values} }} accept comment "mihomo-panel:{protocol}"')
    text='\n'.join(changes)+'\n'
    run(['nft', '-c', '-f', '-'], input=text)
    run(['nft', '-f', '-'], input=text)

def check_free(port):
    sockets = []
    try:
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            try:
                sock = socket.socket(socket.AF_INET6, kind)
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                address = ('::', port)
            except OSError:
                sock = socket.socket(socket.AF_INET, kind)
                address = ('0.0.0.0', port)
            sockets.append(sock)
            sock.bind(address)
    except OSError:
        raise ValueError(f'端口 {port} 的 TCP 或 UDP 已被占用')
    finally:
        for sock in sockets:
            sock.close()

def unit_text(account, folder, data_dir):
    return f'''[Unit]
Description=Mihomo managed SOCKS5 {account}
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
User={account}
Group={account}
WorkingDirectory={data_dir}
ExecStart={MIHOMO_BIN} -d {data_dir} -f {folder}/config.yaml
Restart=on-failure
RestartSec=5s
UMask=0027
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths={data_dir}
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
MemoryMax=160M
TasksMax=64
[Install]
WantedBy=multi-user.target
'''

def wait_running(slug, port):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if status(slug).get('ActiveState') == 'active':
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    return
            except OSError:
                pass
        time.sleep(.1)
    raise ValueError('服务未能正常监听，已尝试回退原配置')

def apply(payload):
    slug = str(payload['id'])
    account, folder, data_dir, unit = paths(slug)
    old_registry = registry()
    old = old_registry.get(slug)
    if not old and slug in ('india', 'philippines'):
        raise ValueError('原有服务必须先导入')
    config = render_config(payload['port'], payload['username'], payload['password'], payload['proxy'])
    port = config['socks-port']
    if any(k != slug and v['port'] == port for k, v in old_registry.items()):
        raise ValueError('端口已被另一个服务使用')
    if not old or old['port'] != port or status(slug).get('ActiveState') != 'active':
        check_free(port)
    previous_status = status(slug) if old else {}
    config_file = folder / 'config.yaml'
    previous = config_file.read_text() if config_file.exists() else None
    unit_file = UNIT_DIR / unit
    previous_unit = unit_file.read_text() if unit_file.exists() else None
    created_account = False
    stage = folder / 'config.pending.yaml'
    try:
        try:
            user = pwd.getpwnam(account)
        except KeyError:
            run(['useradd', '--system', '--user-group', '--no-create-home', '--home-dir', str(data_dir), '--shell', '/usr/sbin/nologin', account])
            created_account = True
            user = pwd.getpwnam(account)
        folder.mkdir(mode=0o750, parents=True, exist_ok=True)
        os.chmod(folder, 0o750)
        os.chown(folder, 0, user.pw_gid)
        data_dir.mkdir(mode=0o750, exist_ok=True)
        os.chmod(data_dir, 0o750)
        os.chown(data_dir, user.pw_uid, user.pw_gid)
        atomic(stage, yaml.safe_dump(config, allow_unicode=True, sort_keys=False), 0o640, user.pw_gid)
        run(['runuser', '-u', account, '--', MIHOMO_BIN, '-t', '-d', str(data_dir), '-f', str(stage)], timeout=20)
        if previous:
            atomic(folder / 'config.previous.yaml', previous, 0o640, user.pw_gid)
        os.replace(stage, config_file)
        if not old or previous_unit is None:
            atomic(unit_file, unit_text(account, folder, data_dir), 0o644)
            run(['systemctl', 'daemon-reload'])
        new_registry = dict(old_registry)
        new_registry[slug] = {'port': port}
        save_registry(new_registry)
        firewall(new_registry)
        if payload.get('enabled', True):
            run(['systemctl', 'enable', unit])
            run(['systemctl', 'restart', unit])
            wait_running(slug, port)
        else:
            run(['systemctl', 'disable', '--now', unit])
        return {'status': status(slug)}
    except Exception:
        save_registry(old_registry)
        firewall(old_registry)
        if previous is not None:
            atomic(config_file, previous, 0o640, pwd.getpwnam(account).pw_gid)
            if previous_status.get('UnitFileState') == 'enabled':
                run(['systemctl', 'enable', unit], check=False)
            else:
                run(['systemctl', 'disable', unit], check=False)
            run(['systemctl', 'restart' if previous_status.get('ActiveState') == 'active' else 'stop', unit], check=False)
        else:
            run(['systemctl', 'disable', '--now', unit], check=False)
            if previous_unit is None:
                unit_file.unlink(missing_ok=True)
            shutil.rmtree(folder, ignore_errors=True)
            shutil.rmtree(data_dir, ignore_errors=True)
            if created_account:
                run(['userdel', account], check=False)
            run(['systemctl', 'daemon-reload'], check=False)
        raise
    finally:
        stage.unlink(missing_ok=True)

def dispatch(request):
    op = request.get('op')
    data = registry()
    if op == 'status':
        return {slug: status(slug) for slug in data}
    if op == 'apply':
        return apply(request)
    slug = str(request.get('id', ''))
    if slug not in data:
        raise ValueError('服务不存在')
    account, folder, data_dir, unit = paths(slug)
    if op == 'action':
        action = request.get('action')
        if action == 'start':
            run(['systemctl', 'enable', '--now', unit])
            wait_running(slug, data[slug]['port'])
        elif action == 'stop':
            run(['systemctl', 'disable', '--now', unit])
        elif action == 'restart':
            run(['systemctl', 'restart', unit])
            wait_running(slug, data[slug]['port'])
        else:
            raise ValueError('不支持的操作')
        return status(slug)
    if op == 'logs':
        args = ['journalctl', '-u', unit, '-n', '60', '--no-pager', '-o', 'cat']
        if request.get('since'):
            since = datetime.datetime.fromisoformat(request['since']).astimezone(datetime.timezone.utc)
            args += ['--since', since.strftime('%Y-%m-%d %H:%M:%S UTC')]
        return {'logs': run(args, check=False).stdout[-20000:]}
    if op == 'delete':
        run(['systemctl', 'disable', '--now', unit], check=False)
        del data[slug]
        save_registry(data)
        firewall(data)
        (UNIT_DIR / unit).unlink(missing_ok=True)
        run(['systemctl', 'daemon-reload'])
        shutil.rmtree(folder, ignore_errors=True)
        shutil.rmtree(data_dir, ignore_errors=True)
        run(['userdel', account], check=False)
        return {'deleted': True}
    raise ValueError('不支持的操作')

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        try:
            raw = self.rfile.readline(262145)
            if len(raw) > 262144:
                raise ValueError('管理请求过大')
            result = {'ok': True, 'result': dispatch(json.loads(raw))}
        except Exception as exc:
            result = {'ok': False, 'error': str(exc)[:2000]}
        self.wfile.write((json.dumps(result, ensure_ascii=False) + '\n').encode())

def main():
    STATE.mkdir(mode=0o700, exist_ok=True)
    firewall(registry())
    Path(SOCKET).unlink(missing_ok=True)
    with socketserver.UnixStreamServer(SOCKET, Handler) as server:
        os.chown(SOCKET, 0, grp.getgrnam('mihomo-panel').gr_gid)
        os.chmod(SOCKET, 0o660)
        server.serve_forever()

if __name__ == '__main__':
    main()
