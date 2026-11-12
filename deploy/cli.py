#!/usr/bin/env python3
"""Install, upgrade and move a single-machine Mihomo personal panel."""
import argparse
import base64
from contextlib import contextmanager
from dataclasses import dataclass
import datetime
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import pwd
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

SOURCE = Path(__file__).resolve().parents[1]
ITEMS = ('app.py','common.py','database.py','manager.py','probe.py','runtime.py','serve.py','initialize.py',
         'transfer.py','schema.sql','static','deploy','tests','VERSION','README.md','CHANGELOG.md',
         'requirements.txt','requirements-dev.txt','config.env.example','.gitignore',
         'install.sh','upgrade.sh','backup.sh','restore.sh','uninstall.sh','doctor.sh','build-release.py')
UNITS = ('mihomo-panel.service','mihomo-panel-manager.service')


@dataclass
class Layout:
    root: Path = Path('/')
    def path(self, name): return self.root/name.lstrip('/')
    @property
    def app(self): return self.path('/opt/mihomo-panel')
    @property
    def config(self): return self.path('/etc/mihomo-panel')
    @property
    def env(self): return self.config/'web.env'
    @property
    def data(self): return self.path('/var/lib/mihomo-panel')
    @property
    def state(self): return self.path('/var/lib/mihomo-panel-manager')
    @property
    def units(self): return self.path('/etc/systemd/system')
    @property
    def backups(self): return self.path('/var/backups/mihomo-panel')
    @property
    def database(self): return self.data/'panel.sqlite3'
    @property
    def python(self): return self.app/'venv/bin/python'


class Host:
    def run(self, args, *, env=None, check=True, capture=True):
        result=subprocess.run([str(x) for x in args],env=env,check=False,text=True,
                              stdout=subprocess.PIPE if capture else None,stderr=subprocess.PIPE if capture else None)
        if check and result.returncode:
            # Never print environment values or decrypted service specifications.
            raise RuntimeError('命令失败：'+str(args[0])+'\n'+(result.stderr or result.stdout or '')[-1800:])
        return result
    def running(self, unit):return self.run(['systemctl','is-active','--quiet',unit],check=False).returncode==0
    def check_port(self, env):
        family=socket.AF_INET6 if ':' in env['PANEL_BIND'] else socket.AF_INET
        with socket.socket(family) as sock:
            sock.bind((env['PANEL_BIND'],int(env['PANEL_PORT'])))
    def account(self):
        try:pwd.getpwnam('mihomo-panel')
        except KeyError:self.run(['useradd','--system','--user-group','--no-create-home','--home-dir','/var/lib/mihomo-panel','--shell','/usr/sbin/nologin','mihomo-panel'])
    def check_instances(self, ids, layout):
        registry=layout.state/'services.json'
        current=json.loads(registry.read_text()) if registry.exists() else {}
        for slug in ids:
            if slug in current:continue
            account='mihomo-'+slug
            try:pwd.getpwnam(account);exists=True
            except KeyError:exists=False
            if exists or (layout.units/(account+'.service')).exists() or layout.path('/etc/mihomo').joinpath(slug).exists() or layout.path('/var/lib').joinpath(account).exists():
                raise ValueError('实例名称已被其他服务使用，拒绝覆盖：'+slug)
    def permissions(self, layout):
        user=pwd.getpwnam('mihomo-panel')
        os.chown(layout.config,0,user.pw_gid)
        os.chown(layout.env,0,user.pw_gid)
        layout.env.chmod(0o640)
        os.chown(layout.data,user.pw_uid,user.pw_gid)
        for path in layout.data.glob('panel.sqlite3*'):
            os.chown(path,user.pw_uid,user.pw_gid);path.chmod(0o600)
    def health(self, env):
        bind=env['PANEL_BIND']
        host='[::1]' if ':' in bind else '127.0.0.1'
        if bind not in ('0.0.0.0','::','127.0.0.1','::1'):host=bind
        url=f'http://{host}:{env["PANEL_PORT"]}/healthz'
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(40):
            try:
                with opener.open(url,timeout=2) as r:
                    if r.status==200 and json.load(r).get('ok'):
                        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as manager:
                            manager.settimeout(2)
                            manager.connect(env.get('MANAGER_SOCKET','/run/mihomo-panel-manager/manager.sock'))
                            manager.sendall(b'{"op":"status"}\n')
                            with manager.makefile('rb') as stream:reply=json.loads(stream.readline(1048576))
                            if reply.get('ok') and all(self.running(unit) for unit in UNITS):return
            except (OSError,ValueError):pass
            time.sleep(.25)
        raise RuntimeError('面板健康检查未通过')


def read_env(path):
    values={}
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        key,sep,value=line.partition('=')
        if not sep or not re.fullmatch('[A-Z_][A-Z_0-9]*',key):raise ValueError('环境配置格式无效')
        if any(c in value for c in ('\n','\r','\0','"',"'",'\\')):raise ValueError('环境配置应为不带引号的单行值')
        values[key]=value
    return values


def write_env(path, env):
    content=''.join(f'{key}={value}\n' for key,value in sorted(env.items()))
    private_replace(path,content.encode(),0o640)


def private_replace(path, content, mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
    fd,temporary=tempfile.mkstemp(prefix='.panel-',dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def address(value):
    if not value:raise ValueError('首次安装需要 --public-ip，填写新服务器的公网 IP 或域名')
    try:ipaddress.ip_address(value);return value
    except ValueError:pass
    if len(value)>253 or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',value):raise ValueError('公网地址格式无效')
    return value


def configuration(layout, args):
    previous=read_env(layout.env) if layout.env.exists() else {}
    if layout.database.exists() and not previous.get('FERNET_KEY'):
        raise ValueError('数据库已存在但加密密钥缺失，请先恢复 web.env')
    env=dict(previous)
    if 'PANEL_BIND' not in env and layout.units.joinpath(UNITS[0]).exists():
        old=layout.units.joinpath(UNITS[0]).read_text()
        match=re.search(r'--host\s+([\w.:]+)',old)
        if match:env['PANEL_BIND']=match[1]
    env.update({key:str(value) for key,value in {
        'PUBLIC_IP':args.public_ip,'PANEL_BIND':args.bind,'PANEL_PORT':args.port,'PANEL_HOSTS':args.hosts,
        'COOKIE_SECURE':args.cookie_secure,'FIREWALL_MODE':args.firewall}.items() if value is not None})
    env.setdefault('PANEL_BIND','127.0.0.1');env.setdefault('PANEL_PORT','8080');env.setdefault('COOKIE_SECURE','0')
    env.setdefault('FIREWALL_MODE','auto')
    env['PUBLIC_IP']=address(env.get('PUBLIC_IP'))
    ipaddress.ip_address(env['PANEL_BIND'])
    if not 1024<=int(env['PANEL_PORT'])<=65535:raise ValueError('面板端口需在 1024–65535 之间')
    names=[name.strip() for name in env.get('PANEL_HOSTS','').split(',') if name.strip()]
    for name in names:address(name)
    env['PANEL_HOSTS']=','.join(dict.fromkeys(['localhost','127.0.0.1','::1',env['PUBLIC_IP'],*names]))
    env['PANEL_FIREWALL']='0' if ipaddress.ip_address(env['PANEL_BIND']).is_loopback else '1'
    env['DATABASE_PATH']=str(layout.database)
    env['MIHOMO_BIN']=str(layout.app/'core/mihomo')
    if not env.get('FERNET_KEY'):
        env['FERNET_KEY']=os.environ.get('FERNET_KEY') or base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    key=env['FERNET_KEY']
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}=',key) or len(base64.urlsafe_b64decode(key))!=32:
        raise ValueError('FERNET_KEY 必须是有效的 32 字节 Fernet 密钥')
    # An installation password is consumed once, never persisted in web.env.
    env.pop('ADMIN_PASSWORD',None)
    env['INITIAL_PASSWORD_FILE']=str(layout.config/'initial-admin.txt')
    # A changed web port must not take an existing proxy's port.
    if layout.database.exists():
        with sqlite3.connect(layout.database.resolve().as_uri()+'?mode=ro',uri=True) as db:
            if db.execute('SELECT 1 FROM services WHERE port=?',(int(env['PANEL_PORT']),)).fetchone():
                raise ValueError('面板端口已被代理服务使用')
    return previous,env


def preflight(host, args):
    if not Path('/run/systemd/system').is_dir():raise RuntimeError('需要使用 systemd 的 Linux 主机')
    distro=platform.freedesktop_os_release()
    if (distro.get('ID'),distro.get('VERSION_ID')) not in {('debian','12'),('ubuntu','24.04')}:
        raise RuntimeError('当前版本支持 Debian 12 和 Ubuntu 24.04')
    if platform.machine() not in ('x86_64','aarch64','arm64'):raise RuntimeError('当前版本支持 x86_64 和 ARM64')
    if not args.skip_packages:
        host.run(['apt-get','update'],capture=False)
        host.run(['apt-get','install','-y','python3-venv','python3-pip','ca-certificates','nftables','passwd'],
                 env={**os.environ,'DEBIAN_FRONTEND':'noninteractive'},capture=False)
    for program in ('systemctl','nft','useradd','runuser'):
        if not shutil.which(program):raise RuntimeError('缺少命令：'+program)
    if sqlite3.sqlite_version_info<(3,35):raise RuntimeError('SQLite 需要 3.35 或更新版本')


def download_core(stage, layout, host, core_file=None):
    metadata=json.loads((SOURCE/'deploy/core.json').read_text())
    arch={'arm64':'aarch64'}.get(platform.machine(),platform.machine())
    asset=metadata['assets'][arch]
    cache=layout.path('/var/cache/mihomo-panel');cache.mkdir(parents=True,exist_ok=True,mode=0o755)
    archive=Path(core_file) if core_file else cache/asset['file']
    if not archive.exists():
        direct=f'https://github.com/MetaCubeX/mihomo/releases/download/v{metadata["version"]}/{asset["file"]}'
        sources=[(direct,15)]
        if asset.get('api_id'):
            sources.append((f'https://api.github.com/repos/MetaCubeX/mihomo/releases/assets/{asset["api_id"]}',30))
        errors=[]
        for url,timeout in sources:
            fd,temporary=tempfile.mkstemp(dir=cache)
            try:
                request=urllib.request.Request(url,headers={'User-Agent':'mihomo-panel/1.0.0','Accept':'application/octet-stream'})
                with os.fdopen(fd,'wb') as out, urllib.request.urlopen(request,timeout=timeout) as source:
                    size=0
                    while chunk:=source.read(1024*1024):
                        size+=len(chunk)
                        if size>64*1024*1024:raise ValueError('下载文件超出预期大小')
                        out.write(chunk)
                if hashlib.sha256(Path(temporary).read_bytes()).hexdigest()!=asset['sha256']:
                    raise ValueError('下载校验失败')
                os.replace(temporary,archive)
                break
            except (OSError,ValueError) as exc:
                errors.append(type(exc).__name__)
            finally:Path(temporary).unlink(missing_ok=True)
        else:
            raise RuntimeError('官方内核下载失败（'+', '.join(errors)+'）；可提前下载对应文件并用 --core-file 指定')
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=asset['sha256']:
        raise ValueError('Mihomo 下载校验失败；请删除损坏的缓存后重试')
    folder=stage/'core';folder.mkdir()
    with gzip.open(archive,'rb') as source, (folder/'mihomo').open('wb') as target:
        shutil.copyfileobj(source,target)
    (folder/'mihomo').chmod(0o755)
    version=host.run([folder/'mihomo','-v']).stdout
    if metadata['version'] not in version:raise ValueError('Mihomo 版本校验失败')


def build_stage(layout, host, args):
    layout.app.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.mihomo-panel-stage-',dir=layout.app.parent))
    stage.chmod(0o755)
    try:
        for name in ITEMS:
            source=SOURCE/name
            if source.is_dir():shutil.copytree(source,stage/name,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
            else:shutil.copy2(source,stage/name)
        host.run(['python3','-m','venv',stage/'venv'],capture=False)
        host.run([stage/'venv/bin/python','-m','pip','install','--disable-pip-version-check','-r',stage/'requirements.txt'],capture=False)
        download_core(stage,layout,host,args.core_file)
        return stage
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise


def execution(env):
    return {**os.environ,**env,'PYTHONDONTWRITEBYTECODE':'1'}


def transfer(host, layout, action, env, path=None, python=None):
    args=[python or layout.python,SOURCE/'transfer.py',action]
    if path is not None:args.append(path)
    result=host.run(args,env=execution(env))
    if result.stdout:print(result.stdout.strip())
    return result


@contextmanager
def paused(host):
    running={unit:host.running(unit) for unit in UNITS}
    for unit in UNITS:host.run(['systemctl','stop',unit],check=False)
    try:yield running
    finally:
        # Start helper before web, only if it was running before this operation.
        for unit in reversed(UNITS):
            if running[unit]:host.run(['systemctl','start',unit],check=False)


def backup_path(layout, prefix):
    layout.backups.mkdir(parents=True,exist_ok=True,mode=0o700)
    return layout.backups/(prefix+'-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(3))


def restore_database(layout, source):
    for path in layout.data.glob('panel.sqlite3*'):path.unlink()
    private_replace(layout.database,(source/'panel.sqlite3').read_bytes())
    with sqlite3.connect(layout.database) as db:db.execute('DELETE FROM sessions')


def install(layout, host, args):
    previous,env=configuration(layout,args)
    existed=layout.app.exists()
    if args.command=='upgrade' and not existed:raise ValueError('尚未安装，请先运行 install.sh')
    if not existed or env['PANEL_PORT']!=previous.get('PANEL_PORT','8080'):
        host.check_port(env)
    preflight(host,args)
    stage=build_stage(layout,host,args)
    rollback=backup_path(layout,'before-upgrade')
    rollback.mkdir(mode=0o700)
    old_app=layout.app.with_name('.mihomo-panel-previous-'+secrets.token_hex(5))
    old_units={unit:(layout.units/unit).read_bytes() if (layout.units/unit).exists() else None for unit in UNITS}
    old_env=layout.env.read_bytes() if layout.env.exists() else None
    swapped=False
    rebuilt=False
    try:
        host.account()
        for path,mode in [(layout.config,0o750),(layout.data,0o750),(layout.state,0o700)]:
            path.mkdir(parents=True,exist_ok=True,mode=mode)
        with paused(host):
            if layout.database.exists():
                transfer(host,layout,'export',previous,rollback/'data',python=stage/'venv/bin/python')
            if existed:os.replace(layout.app,old_app)
            os.replace(stage,layout.app);swapped=True
            write_env(layout.env,env)
            transfer(host,layout,'initialize',env)
            host.permissions(layout)
            layout.units.mkdir(parents=True,exist_ok=True)
            for unit in UNITS:private_replace(layout.units/unit,(SOURCE/'deploy'/unit).read_bytes(),0o644)
            # Reinstall after a normal uninstall: data remains, units are rebuilt.
            registry=layout.state/'services.json'
            if not registry.exists() or not json.loads(registry.read_text()):
                with sqlite3.connect(layout.database) as db:
                    host.check_instances([row[0] for row in db.execute('SELECT id FROM services')],layout)
                rebuilt=True
                transfer(host,layout,'rebuild',env)
            host.run(['systemctl','daemon-reload'])
            host.run(['systemctl','enable',*reversed(UNITS)])
            host.run(['systemctl','start',*reversed(UNITS)])
            host.health(env)
        if old_app.exists():shutil.rmtree(old_app)
        print('安装完成。管理地址：'+env['PANEL_BIND']+':'+env['PANEL_PORT'])
        if Path(env['INITIAL_PASSWORD_FILE']).exists():
            print('初始密码文件：'+env['INITIAL_PASSWORD_FILE']+'（已有密码保持不变）')
        else:
            print('管理员账号：admin；首次密码由 ADMIN_PASSWORD 提供，已有密码保持不变')
        if (rollback/'data').exists():print('升级前备份：'+str(rollback/'data'))
    except BaseException:
        for unit in UNITS:host.run(['systemctl','stop',unit],check=False)
        if swapped:
            if rebuilt:
                transfer(host,layout,'clear',{**env,'PANEL_FIREWALL':'0'})
            shutil.rmtree(layout.app,ignore_errors=True)
            if old_app.exists():os.replace(old_app,layout.app)
        if old_env is not None:private_replace(layout.env,old_env,0o640)
        else:layout.env.unlink(missing_ok=True)
        for unit,data in old_units.items():
            if data is not None:private_replace(layout.units/unit,data,0o644)
            else:(layout.units/unit).unlink(missing_ok=True)
        if (rollback/'data').exists():restore_database(layout,rollback/'data')
        host.run(['systemctl','daemon-reload'],check=False)
        if existed:
            host.permissions(layout)
            host.run(['systemctl','start',*reversed(UNITS)],check=False)
        else:host.run(['systemctl','disable',*UNITS],check=False)
        raise
    finally:shutil.rmtree(stage,ignore_errors=True)


def backup(layout, host, destination):
    if destination.exists():raise ValueError('备份目录已存在，请换一个目录名')
    env=read_env(layout.env)
    with paused(host):transfer(host,layout,'export',env,destination)


def restore(layout, host, source, replace=False):
    env=read_env(layout.env)
    # Verify everything, including the encryption key, before stopping any service.
    transfer(host,layout,'validate',env,source)
    if layout.database.exists():
        with sqlite3.connect(layout.database) as db:
            populated=db.execute('SELECT count(*) FROM subscriptions').fetchone()[0] or db.execute('SELECT count(*) FROM services').fetchone()[0]
        if populated and not replace:raise ValueError('当前已有数据；覆盖恢复需明确加 --replace')
    with sqlite3.connect((source/'panel.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
        host.check_instances([row[0] for row in db.execute('SELECT id FROM services')],layout)
    previous_env=dict(env)
    saved=backup_path(layout,'before-restore')
    with paused(host):
        transfer(host,layout,'export',env,saved)
        try:
            transfer(host,layout,'clear',env)
            restore_database(layout,source)
            env['FERNET_KEY']=json.loads((source/'secrets.json').read_text())['fernet_key']
            write_env(layout.env,env);host.permissions(layout)
            transfer(host,layout,'rebuild',env)
            host.run(['systemctl','start',*reversed(UNITS)])
            host.health(env)
        except BaseException:
            for unit in UNITS:host.run(['systemctl','stop',unit],check=False)
            transfer(host,layout,'clear',env)
            restore_database(layout,saved)
            write_env(layout.env,previous_env);host.permissions(layout)
            transfer(host,layout,'rebuild',previous_env)
            raise
    print('恢复完成；保留目标机器的公网地址及面板设置。恢复前备份：'+str(saved))


def uninstall(layout, host, purge=False):
    env=read_env(layout.env)
    saved=backup_path(layout,'before-uninstall')
    with paused(host) as running:
        transfer(host,layout,'export',env,saved)
        env['PANEL_FIREWALL']='0'
        transfer(host,layout,'clear',env)
        # Do not restart units in paused() after a successful uninstall.
        running.update({unit:False for unit in UNITS})
        host.run(['systemctl','disable',*UNITS],check=False)
        for unit in UNITS:(layout.units/unit).unlink(missing_ok=True)
        host.run(['systemctl','daemon-reload'])
        host.run(['nft','delete','table','inet','mihomo_panel'],check=False)
        shutil.rmtree(layout.app)
        shutil.rmtree(layout.state,ignore_errors=True)
        if purge:
            shutil.rmtree(layout.data,ignore_errors=True);shutil.rmtree(layout.config,ignore_errors=True)
            host.run(['userdel','mihomo-panel'],check=False)
    print('已卸载；'+('已清除运行数据。' if purge else '数据库、密钥和管理员密码保留。')+'备份：'+str(saved))


def doctor(layout,host):
    env=read_env(layout.env)
    host.health(env)
    with sqlite3.connect(layout.database) as db:
        integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
        count=db.execute('SELECT count(*) FROM services').fetchone()[0]
    print(json.dumps({'version':(layout.app/'VERSION').read_text().strip(),'database':integrity,'services':count,
                      'web':host.running(UNITS[0]),'manager':host.running(UNITS[1])},ensure_ascii=False))


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    commands=result.add_subparsers(dest='command',required=True)
    for name in ('install','upgrade'):
        command=commands.add_parser(name)
        command.add_argument('--public-ip');command.add_argument('--bind');command.add_argument('--port',type=int)
        command.add_argument('--hosts');command.add_argument('--cookie-secure',choices=['0','1'])
        command.add_argument('--firewall',choices=['auto','off'])
        command.add_argument('--skip-packages',action='store_true');command.add_argument('--core-file',type=Path)
    command=commands.add_parser('backup');command.add_argument('destination',type=Path)
    command=commands.add_parser('restore');command.add_argument('source',type=Path);command.add_argument('--replace',action='store_true')
    command=commands.add_parser('uninstall');command.add_argument('--purge',action='store_true')
    commands.add_parser('doctor')
    return result


def main():
    args=parser().parse_args()
    if os.geteuid()!=0:raise SystemExit('请使用 sudo 或 root 运行')
    # Prevent concurrent install/restore/uninstall from racing each other.
    import fcntl
    lock=Path('/run/lock/mihomo-panel-deploy.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    layout,host=Layout(),Host()
    if args.command in ('install','upgrade'):install(layout,host,args)
    elif args.command=='backup':backup(layout,host,args.destination.resolve())
    elif args.command=='restore':restore(layout,host,args.source.resolve(),args.replace)
    elif args.command=='uninstall':uninstall(layout,host,args.purge)
    elif args.command=='doctor':doctor(layout,host)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('操作失败：'+str(exc),file=sys.stderr)
        sys.exit(1)
