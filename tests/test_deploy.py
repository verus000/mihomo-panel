"""Exercise deployment in isolated directories, never touching host services."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest
from cryptography.fernet import Fernet

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('deployment',ROOT/'deploy/cli.py')
deploy=importlib.util.module_from_spec(spec);sys.modules[spec.name]=deploy;spec.loader.exec_module(deploy)


class FakeHost:
    def __init__(self):self.active=set();self.commands=[];self.fail_health=False;self.enabled=set()
    def running(self,unit):return unit in self.active
    def account(self):pass
    def check_port(self,env):pass
    def check_instances(self,ids,layout):pass
    def permissions(self,layout):
        layout.env.chmod(0o640)
        for path in layout.data.glob('panel.sqlite3*'):path.chmod(0o600)
    def health(self,env):
        if self.fail_health:self.fail_health=False;raise RuntimeError('模拟新版本启动失败')
        assert set(deploy.UNITS)<=self.active
        with sqlite3.connect(env['DATABASE_PATH']) as db:assert db.execute("SELECT value FROM settings WHERE key='admin_hash'").fetchone()
    def run(self,args,*,env=None,check=True,capture=True):
        args=[str(x) for x in args];self.commands.append(args)
        if args[0]=='systemctl' and args[1] in ('start','stop','enable','disable'):
            collection=self.active if args[1] in ('start','stop') else self.enabled
            for unit in args[2:]:
                if args[1] in ('start','enable'):collection.add(unit)
                else:collection.discard(unit)
        if len(args)>2 and args[1].endswith('/transfer.py'):
            action=args[2]
            if action in ('initialize','export','validate'):
                result=subprocess.run([sys.executable,*args[1:]],env=env,text=True,capture_output=True)
                if check and result.returncode:raise RuntimeError(result.stderr)
                return result
            registry=Path(env['DATABASE_PATH']).parents[1]/'mihomo-panel-manager/services.json'
            registry.parent.mkdir(parents=True,exist_ok=True)
            if action=='clear':registry.write_text('{}')
            elif action=='rebuild':
                with sqlite3.connect(env['DATABASE_PATH']) as db:
                    registry.write_text(json.dumps({row[0]:{'port':row[1]} for row in db.execute('SELECT id,port FROM services')}))
        return subprocess.CompletedProcess(args,0,'','')


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    layout=deploy.Layout(tmp_path/'machine')
    host=FakeHost()
    monkeypatch.setattr(deploy,'preflight',lambda *args:None)
    def stage(layout,host,args):
        layout.app.parent.mkdir(parents=True,exist_ok=True)
        path=layout.app.parent/'.stage'
        path.mkdir()
        for item in deploy.ITEMS:
            source=ROOT/item
            if source.is_dir():shutil.copytree(source,path/item,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
            else:shutil.copy2(source,path/item)
        (path/'venv/bin').mkdir(parents=True)
        (path/'venv/bin/python').symlink_to(sys.executable)
        (path/'core').mkdir();(path/'core/mihomo').write_text('fake-core')
        return path
    monkeypatch.setattr(deploy,'build_stage',stage)
    return layout,host


def args(command='install',*options):
    return deploy.parser().parse_args([command,*options])


def seed(layout):
    env=deploy.read_env(layout.env);cipher=Fernet(env['FERNET_KEY'].encode())
    enc=lambda value:cipher.encrypt(json.dumps(value).encode()).decode()
    proxy={'name':'测试节点','type':'vless','server':'example.com','port':443,'uuid':'00000000-0000-4000-8000-000000000001','network':'tcp','tls':True}
    with sqlite3.connect(layout.database) as db:
        sub=db.execute('INSERT INTO subscriptions(name,url_enc) VALUES (?,?)',('测试订阅',enc('https://example.com/sub'))).lastrowid
        node=db.execute('INSERT INTO nodes(subscription_id,identity,name,country,tags,protocol,config_enc) VALUES (?,?,?,?,?,?,?)',(sub,'fixture','测试节点','其他','["常用"]','vless',enc(proxy))).lastrowid
        db.execute('INSERT INTO services(id,name,port,username,password_enc,node_id,snapshot_enc,enabled) VALUES (?,?,?,?,?,?,?,?)',('svc-0123456789ab','服务',40099,'user',enc('password-only-for-unit-test'),node,enc(proxy),False))
    layout.state.joinpath('services.json').write_text('{"svc-0123456789ab":{"port":40099}}')
    return env


def test_first_install_repeat_and_upgrade_preserve_data(isolated):
    layout,host=isolated
    deploy.install(layout,host,args('install','--public-ip','203.0.113.10'))
    assert layout.python.exists() and layout.database.stat().st_mode & 0o777==0o600
    first_password=(layout.config/'initial-admin.txt').read_bytes()
    original=seed(layout)
    deploy.install(layout,host,args('install'))
    assert deploy.read_env(layout.env)['FERNET_KEY']==original['FERNET_KEY']
    assert (layout.config/'initial-admin.txt').read_bytes()==first_password
    deploy.install(layout,host,args('upgrade','--port','18080'))
    assert deploy.read_env(layout.env)['PANEL_PORT']=='18080'
    with sqlite3.connect(layout.database) as db:assert db.execute('SELECT count(*) FROM services').fetchone()[0]==1
    assert len(list(layout.backups.glob('before-upgrade-*/data/manifest.json')))==2
    assert 'python /opt/mihomo-panel/serve.py' in layout.units.joinpath(deploy.UNITS[0]).read_text()


def test_upgrade_failure_restores_code_key_and_database(isolated):
    layout,host=isolated
    deploy.install(layout,host,args('install','--public-ip','203.0.113.10'))
    old=seed(layout)
    layout.app.joinpath('VERSION').write_text('old-version')
    host.fail_health=True
    with pytest.raises(RuntimeError,match='模拟新版本'):
        deploy.install(layout,host,args('upgrade','--port','18080'))
    assert layout.app.joinpath('VERSION').read_text()=='old-version'
    assert deploy.read_env(layout.env)==old
    with sqlite3.connect(layout.database) as db:assert db.execute('SELECT name FROM services').fetchone()[0]=='服务'
    assert set(deploy.UNITS)<=host.active


def test_backup_restore_other_machine_and_corrupt_rejection(isolated,tmp_path):
    layout,host=isolated
    deploy.install(layout,host,args('install','--public-ip','203.0.113.10'))
    original=seed(layout)
    backup=tmp_path/'backup';deploy.backup(layout,host,backup)
    target=deploy.Layout(tmp_path/'target');target_host=FakeHost()
    deploy.install(target,target_host,args('install','--public-ip','198.51.100.20','--port','18080'))
    deploy.restore(target,target_host,backup)
    env=deploy.read_env(target.env)
    assert env['PUBLIC_IP']=='198.51.100.20' and env['PANEL_PORT']=='18080'
    assert env['FERNET_KEY']==original['FERNET_KEY']
    assert json.loads(target.state.joinpath('services.json').read_text())=={'svc-0123456789ab':{'port':40099}}
    with sqlite3.connect(target.database) as db:
        assert db.execute('SELECT enabled FROM services').fetchone()[0]==0
        assert json.loads(db.execute('SELECT tags FROM nodes').fetchone()[0])==['常用']
        assert not db.execute('SELECT * FROM sessions').fetchall()
    with pytest.raises(ValueError,match='--replace'):deploy.restore(target,target_host,backup)
    backup.joinpath('secrets.json').write_text('{}')
    before=list(target_host.commands)
    with pytest.raises(RuntimeError):deploy.restore(target,target_host,backup,replace=True)
    assert target_host.commands[len(before):][0][2]=='validate'
    assert not any('stop' in command for command in target_host.commands[len(before):])


def test_restore_failure_rebuilds_previous_instances(isolated,tmp_path):
    layout,host=isolated
    deploy.install(layout,host,args('install','--public-ip','203.0.113.10'))
    original=seed(layout)
    backup=tmp_path/'backup';deploy.backup(layout,host,backup)
    host.fail_health=True
    with pytest.raises(RuntimeError):deploy.restore(layout,host,backup,replace=True)
    assert deploy.read_env(layout.env)==original
    assert set(deploy.UNITS)<=host.active
    assert json.loads(layout.state.joinpath('services.json').read_text())=={'svc-0123456789ab':{'port':40099}}


def test_uninstall_keeps_data_reinstall_and_purge(isolated):
    layout,host=isolated
    deploy.install(layout,host,args('install','--public-ip','203.0.113.10'))
    original=seed(layout)
    deploy.uninstall(layout,host)
    assert layout.database.exists() and layout.env.exists() and not layout.app.exists()
    assert not host.active and not host.enabled
    deploy.install(layout,host,args('install'))
    assert deploy.read_env(layout.env)['FERNET_KEY']==original['FERNET_KEY']
    assert json.loads(layout.state.joinpath('services.json').read_text())=={'svc-0123456789ab':{'port':40099}}
    deploy.uninstall(layout,host,purge=True)
    assert not layout.database.exists() and not layout.config.exists()
    assert len(list(layout.backups.glob('before-uninstall-*/manifest.json')))==2


def test_core_checksum_rejection_and_arch_selection(tmp_path,monkeypatch):
    import gzip,hashlib
    source=tmp_path/'source';source.joinpath('deploy').mkdir(parents=True)
    archive=tmp_path/'core.gz';archive.write_bytes(gzip.compress(b'not-a-real-core'))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    source.joinpath('deploy/core.json').write_text(json.dumps({'version':'1.19.32','assets':{'aarch64':{'file':'core.gz','sha256':digest}}}))
    monkeypatch.setattr(deploy,'SOURCE',source);monkeypatch.setattr(deploy.platform,'machine',lambda:'aarch64')
    host=FakeHost();host.run=lambda *args,**kwargs:subprocess.CompletedProcess(args,0,'Mihomo 1.19.32','')
    stage=tmp_path/'stage';stage.mkdir()
    deploy.download_core(stage,deploy.Layout(tmp_path/'root'),host,archive)
    assert stage.joinpath('core/mihomo').read_bytes()==b'not-a-real-core'
    archive.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='校验失败'):deploy.download_core(stage,deploy.Layout(tmp_path/'root'),host,archive)


@pytest.mark.parametrize('first_response',[TimeoutError('blocked'),b'not-the-asset'])
def test_download_falls_back_to_official_api(tmp_path,monkeypatch,first_response):
    import gzip,hashlib,io
    payload=gzip.compress(b'test-core')
    source=tmp_path/'source';source.joinpath('deploy').mkdir(parents=True)
    source.joinpath('deploy/core.json').write_text(json.dumps({'version':'1.19.32','assets':{'x86_64':{'file':'core.gz','sha256':hashlib.sha256(payload).hexdigest(),'api_id':123}}}))
    monkeypatch.setattr(deploy,'SOURCE',source);monkeypatch.setattr(deploy.platform,'machine',lambda:'x86_64')
    calls=[]
    def urlopen(request,timeout):
        calls.append(request.full_url)
        if len(calls)==1:
            if isinstance(first_response,Exception):raise first_response
            return io.BytesIO(first_response)
        return io.BytesIO(payload)
    monkeypatch.setattr(deploy.urllib.request,'urlopen',urlopen)
    host=FakeHost();host.run=lambda *args,**kwargs:subprocess.CompletedProcess(args,0,'Mihomo 1.19.32','')
    stage=tmp_path/'stage';stage.mkdir()
    deploy.download_core(stage,deploy.Layout(tmp_path/'root'),host)
    assert calls[0].startswith('https://github.com/')
    assert calls[1]=='https://api.github.com/repos/MetaCubeX/mihomo/releases/assets/123'
    assert stage.joinpath('core/mihomo').read_bytes()==b'test-core'


def test_missing_encryption_key_is_rejected_before_install(isolated):
    layout,host=isolated
    layout.data.mkdir(parents=True);layout.database.touch()
    with pytest.raises(ValueError,match='密钥缺失'):deploy.configuration(layout,args('install','--public-ip','203.0.113.10'))
    assert not host.commands


def test_install_accepts_secret_environment_without_persisting_password(isolated,monkeypatch):
    layout,host=isolated
    key=Fernet.generate_key().decode()
    password='Environment-password-only-for-tests'
    monkeypatch.setenv('ADMIN_PASSWORD',password)
    monkeypatch.setenv('FERNET_KEY',key)
    deploy.install(layout,host,args('install','--public-ip','203.0.113.10'))
    env=deploy.read_env(layout.env)
    assert env['FERNET_KEY']==key and 'ADMIN_PASSWORD' not in env
    assert password not in layout.env.read_text()
    assert not (layout.config/'initial-admin.txt').exists()
    monkeypatch.setenv('FERNET_KEY',Fernet.generate_key().decode())
    deploy.install(layout,host,args('upgrade'))
    assert deploy.read_env(layout.env)['FERNET_KEY']==key


def test_invalid_environment_key_is_rejected_before_host_changes(isolated,monkeypatch):
    layout,host=isolated
    monkeypatch.setenv('FERNET_KEY','invalid-key-only-for-tests')
    with pytest.raises(ValueError,match='FERNET_KEY'):
        deploy.install(layout,host,args('install','--public-ip','203.0.113.10'))
    assert not host.commands and not layout.app.exists()
