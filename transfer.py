"""Private, portable backups. Invoked by deploy/cli.py with the panel paused."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

from cryptography.fernet import Fernet
from common import normalize_proxy, render_config
from database import Database

FORMAT = 1
MEMBERS = ('panel.sqlite3', 'secrets.json', 'services.json')


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def check_database(path, key):
    cipher = Fernet(key.encode())
    def decrypt(value):
        return json.loads(cipher.decrypt(value.encode()))
    # Open read-only; never initialize or alter a backup during validation.
    db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA user_version').fetchone()[0] > 1:
            raise ValueError('备份数据库版本比当前程序新')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('数据库完整性或外键校验失败')
        admin = db.execute("SELECT value FROM settings WHERE key='admin_hash'").fetchone()
        if not admin or not re.fullmatch(r'[0-9a-f]{32}:[0-9a-f]{128}', admin[0]):
            raise ValueError('管理员密码记录无效')
        for sub in db.execute('SELECT url_enc FROM subscriptions'):
            if sub[0] and not isinstance(decrypt(sub[0]), str):
                raise ValueError('订阅链接格式无效')
        for node in db.execute('SELECT config_enc FROM nodes'):
            normalize_proxy(decrypt(node[0]))
        specs=[]
        for row in db.execute('SELECT * FROM services ORDER BY port'):
            if row['id'] not in ('india','philippines') and not re.fullmatch(r'svc-[0-9a-f]{12}',row['id']):
                raise ValueError('服务标识无效')
            password=decrypt(row['password_enc'])
            proxy=decrypt(row['snapshot_enc'])
            render_config(row['port'], row['username'], password, proxy)
            specs.append({'id':row['id'],'port':row['port'],'username':row['username'],
                          'password':password,'proxy':proxy,'enabled':bool(row['enabled'])})
        return specs
    finally:
        db.close()


def export(destination):
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    fd=os.open(destination/'panel.sqlite3',os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
    os.close(fd)
    with sqlite3.connect(Path(os.environ['DATABASE_PATH']).resolve().as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(destination/'panel.sqlite3') as target:
        source.backup(target)
    specs=check_database(destination/'panel.sqlite3',os.environ['FERNET_KEY'])
    private_write(destination/'secrets.json',{'fernet_key':os.environ['FERNET_KEY']})
    # Generate the portable registry from the same database snapshot.
    private_write(destination/'services.json',{s['id']:{'port':s['port']} for s in specs})
    private_write(destination/'manifest.json',{'format':FORMAT,'version':Path(__file__).with_name('VERSION').read_text().strip(),
        'sha256':{name:hashlib.sha256((destination/name).read_bytes()).hexdigest() for name in MEMBERS}})
    print('备份完成：'+str(destination))


def validate(destination):
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError('备份必须是本机普通目录')
    for name in (*MEMBERS,'manifest.json'):
        path=destination/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>100*1024*1024:
            raise ValueError('备份文件缺失或格式无效：'+name)
    manifest=json.loads((destination/'manifest.json').read_text())
    if manifest['format'] != FORMAT or set(manifest['sha256']) != set(MEMBERS):
        raise ValueError('不支持的备份格式')
    for name in MEMBERS:
        if hashlib.sha256((destination/name).read_bytes()).hexdigest()!=manifest['sha256'][name]:
            raise ValueError('备份文件校验失败：'+name)
    key=json.loads((destination/'secrets.json').read_text())['fernet_key']
    specs=check_database(destination/'panel.sqlite3',key)
    expected={s['id']:{'port':s['port']} for s in specs}
    if json.loads((destination/'services.json').read_text())!=expected:
        raise ValueError('服务登记与数据库不一致')
    return key,specs


def rebuild():
    import manager
    specs=check_database(Path(os.environ['DATABASE_PATH']),os.environ['FERNET_KEY'])
    manager.STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    if manager.registry():
        raise ValueError('重建前需要先清空现有实例登记')
    # Older installations used these two legacy IDs; retain their credentials and ports.
    legacy={s['id']:{'port':s['port']} for s in specs if s['id'] in ('india','philippines')}
    manager.save_registry(legacy)
    for spec in specs:
        manager.apply(spec)
    manager.firewall(manager.registry())
    print('已重建 '+str(len(specs))+' 个服务')


def clear():
    import manager
    for slug in list(manager.registry()):
        manager.dispatch({'op':'delete','id':slug})
    manager.firewall({})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['export','validate','rebuild','clear','initialize'])
    parser.add_argument('path',nargs='?',type=Path)
    args=parser.parse_args()
    if args.action in ('export','validate') and not args.path:parser.error('需要备份目录')
    if args.action=='export':export(args.path)
    elif args.action=='validate':
        _,specs=validate(args.path)
        print('备份校验通过：'+str(len(specs))+' 个服务')
    elif args.action=='rebuild':rebuild()
    elif args.action=='clear':clear()
    elif args.action=='initialize':import initialize
