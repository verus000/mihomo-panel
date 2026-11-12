"""Create an empty installation without resetting an existing administrator."""
import os
from pathlib import Path
from app import DB, password_hash
import secrets

DB.initialize()
with DB.connection(write=True) as db:
    if not db.execute("SELECT 1 FROM settings WHERE key='admin_hash'").fetchone():
        supplied = os.environ.get('ADMIN_PASSWORD', '')
        password = supplied or secrets.token_urlsafe(24)
        if not 16 <= len(password) <= 128 or any(c in password for c in ('\n', '\r', '\0')):
            raise ValueError('ADMIN_PASSWORD 需为 16–128 个字符，不能包含换行或空字符')
        db.execute("INSERT INTO settings VALUES ('admin_hash',?)", (password_hash(password),))
        if supplied:
            print('管理员已创建，初始密码由 ADMIN_PASSWORD 环境变量提供')
        else:
            path=Path(os.environ['INITIAL_PASSWORD_FILE'])
            path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as stream:
                stream.write('username=admin\npassword='+password+'\n')
            print('管理员已创建，初始密码保存在 '+str(path))
    else:
        print('保留现有管理员密码及数据')
