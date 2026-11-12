"""Administrator initialization uses secrets supplied outside the source tree."""
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from cryptography.fernet import Fernet
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def environment(tmp_path):
    env={key:value for key,value in os.environ.items() if key!='ADMIN_PASSWORD'}
    env.update(FERNET_KEY=Fernet.generate_key().decode(),DATABASE_PATH=str(tmp_path/'panel.sqlite3'),
               INITIAL_PASSWORD_FILE=str(tmp_path/'initial-admin.txt'),PYTHONDONTWRITEBYTECODE='1')
    return env


def initialize(env):
    return subprocess.run([sys.executable,str(ROOT/'initialize.py')],env=env,capture_output=True,text=True)


def stored_hash(env):
    with sqlite3.connect(env['DATABASE_PATH']) as db:
        row=db.execute("SELECT value FROM settings WHERE key='admin_hash'").fetchone()
        return row[0] if row else None


def matches(password,encoded):
    salt,digest=encoded.split(':')
    return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()==digest


def test_environment_password_is_hashed_without_plaintext_copy(environment):
    password='Only-for-tests: $ "quotes" and spaces'
    environment['ADMIN_PASSWORD']=password
    result=initialize(environment)
    assert result.returncode==0,result.stderr
    assert matches(password,stored_hash(environment))
    assert not Path(environment['INITIAL_PASSWORD_FILE']).exists()
    assert password not in result.stdout+result.stderr
    assert password.encode() not in Path(environment['DATABASE_PATH']).read_bytes()


@pytest.mark.parametrize('password',['too-short','x'*129,'test-password-with\nnewline'])
def test_invalid_password_does_not_create_administrator(environment,password):
    environment['ADMIN_PASSWORD']=password
    result=initialize(environment)
    assert result.returncode!=0
    assert 'ADMIN_PASSWORD' in result.stderr
    assert password not in result.stdout+result.stderr
    assert stored_hash(environment) is None
    assert not Path(environment['INITIAL_PASSWORD_FILE']).exists()


@pytest.mark.parametrize('empty',[False,True])
def test_unset_or_empty_environment_generates_private_password_file(environment,empty):
    if empty:environment['ADMIN_PASSWORD']=''
    result=initialize(environment)
    assert result.returncode==0,result.stderr
    path=Path(environment['INITIAL_PASSWORD_FILE'])
    assert path.stat().st_mode & 0o777==0o600
    values=dict(line.split('=',1) for line in path.read_text().splitlines())
    assert values['username']=='admin' and len(values['password'])>=24
    assert matches(values['password'],stored_hash(environment))
    assert values['password'] not in result.stdout+result.stderr


def test_existing_password_is_preserved_on_reinstall(environment):
    environment['ADMIN_PASSWORD']='First-password-only-for-tests'
    assert initialize(environment).returncode==0
    original=stored_hash(environment)
    environment['ADMIN_PASSWORD']='Another-password-only-for-tests'
    assert initialize(environment).returncode==0
    assert stored_hash(environment)==original
