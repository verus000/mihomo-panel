"""SQLite transactions, scheduling and backend data behavior, without live services."""
import json
from pathlib import Path
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))
from database import Database


@pytest.fixture
def store(tmp_path):
    db = Database(tmp_path/'panel.sqlite3')
    db.initialize()
    return db


def test_rollback_foreign_keys_and_private_file(store):
    assert store.path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(RuntimeError):
        with store.connection(write=True) as db:
            db.execute("INSERT INTO subscriptions(name) VALUES ('rollback')")
            raise RuntimeError('abort')
    with store.connection() as db:
        assert not db.execute('SELECT * FROM subscriptions').fetchall()
    with pytest.raises(sqlite3.IntegrityError):
        with store.connection(write=True) as db:
            db.execute("INSERT INTO nodes(subscription_id,identity,name,country,protocol,config_enc) VALUES (99,'x','x','x','vless','x')")
    with pytest.raises(sqlite3.OperationalError):
        with store.connection() as db:
            db.execute("INSERT INTO settings VALUES ('read-only','x')")


def test_wal_readers_and_concurrent_writes(store):
    with store.connection(write=True) as db:
        db.execute("INSERT INTO settings VALUES ('counter','0')")
    def increment():
        for _ in range(10):
            with store.connection(write=True) as db:
                db.execute("UPDATE settings SET value=cast(value as integer)+1 WHERE key='counter'")
    with store.connection() as reader:
        assert reader.execute("SELECT value FROM settings WHERE key='counter'").fetchone()['value']=='0'
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda _:increment(),range(3)))
        assert reader.execute("SELECT value FROM settings WHERE key='counter'").fetchone()['value']=='0'
    with store.connection() as db:
        assert db.execute("SELECT value FROM settings WHERE key='counter'").fetchone()['value']=='30'


def test_utc_expiry_and_subscription_schedule(store):
    with store.connection(write=True) as db:
        db.execute("INSERT INTO sessions VALUES ('old',strftime('%Y-%m-%dT%H:%M:%fZ','now','-1 minute')),('new',strftime('%Y-%m-%dT%H:%M:%fZ','now','+12 hours'))")
        db.execute("INSERT INTO subscriptions(name,interval_hours) VALUES ('s',3)")
        db.execute("UPDATE subscriptions SET next_refresh=strftime('%Y-%m-%dT%H:%M:%fZ','now','+' || interval_hours || ' hours')")
        valid=db.execute("SELECT token_hash FROM sessions WHERE expires_at>strftime('%Y-%m-%dT%H:%M:%fZ','now')").fetchall()
        assert valid==[{'token_hash':'new'}]
        assert not db.execute("SELECT id FROM subscriptions WHERE next_refresh<=strftime('%Y-%m-%dT%H:%M:%fZ','now')").fetchall()
        db.execute("INSERT INTO audit(at,action,detail) VALUES (strftime('%Y-%m-%dT%H:%M:%fZ','now','-91 days'),'old','old')")
        db.execute("DELETE FROM audit WHERE at<strftime('%Y-%m-%dT%H:%M:%fZ','now','-90 days')")
        assert not db.execute('SELECT * FROM audit').fetchall()


@pytest.fixture
def panel(store, monkeypatch):
    monkeypatch.setenv('FERNET_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('PANEL_HOSTS','testserver')
    import app
    monkeypatch.setattr(app,'DB',store)
    monkeypatch.setattr(app,'CIPHER',Fernet(Fernet.generate_key()))
    monkeypatch.setattr(app,'manager',lambda *args,**kwargs: {})
    proxy={'name':'测试印度','type':'vless','server':'example.com','port':443,'uuid':'00000000-0000-4000-8000-000000000001','network':'tcp','tls':True}
    monkeypatch.setattr(app,'fetch_subscription',lambda url:([proxy],0))
    monkeypatch.setattr(app,'validate_url',lambda url:None)
    with store.connection(write=True) as db:
        db.execute("INSERT INTO settings VALUES ('admin_hash',?)",(app.password_hash('test-password-for-sqlite'),))
    with TestClient(app.app,headers={'X-Requested-With':'MihomoPanel'}) as client:
        assert client.post('/api/login',json={'username':'admin','password':'test-password-for-sqlite'}).status_code==200
        yield client,app,proxy


def seed(client):
    response=client.post('/api/subscriptions',json={'name':'订阅','url':'https://example.com/sub','enabled':False})
    assert response.status_code==200,response.text
    state=client.get('/api/state').json()
    return response.json()['id'],state['nodes'][0]['id']


def test_subscription_refresh_json_classification_and_failures(panel):
    client,app,proxy=panel
    sub,node=seed(client)
    assert client.put(f'/api/nodes/{node}',json={'country':'自定义地区','tags':['常用','常用']}).status_code==200
    assert client.post(f'/api/subscriptions/{sub}/refresh',json={}).status_code==200
    state=client.get('/api/state').json()
    assert state['nodes'][0]['tags']==['常用']
    assert state['nodes'][0]['country']=='自定义地区'
    assert state['nodes'][0]['available'] is True
    app.fetch_subscription=lambda url: (_ for _ in ()).throw(ValueError('模拟失败'))
    assert client.post(f'/api/subscriptions/{sub}/refresh',json={}).status_code==400
    state=client.get('/api/state').json()
    assert state['nodes'][0]['available'] is True
    assert state['subscriptions'][0]['last_error']=='模拟失败'
    assert client.delete(f'/api/subscriptions/{sub}').status_code==200
    assert not client.get('/api/state').json()['nodes']


def test_service_credentials_probe_json_and_config_rollback(panel,monkeypatch):
    client,app,proxy=panel
    sub,node=seed(client)
    auth=client.post('/api/credentials/generate',json={}).json()
    body={'name':'测试服务','port':40299,'node_id':node,**auth,'enabled':False}
    created=client.post('/api/services',json=body)
    assert created.status_code==200,created.text
    slug=created.json()['id']
    credentials=client.post(f'/api/services/{slug}/credentials',json={}).json()
    assert credentials['password']==auth['password']
    assert client.delete(f'/api/subscriptions/{sub}').status_code==409
    assert client.post('/api/services',json=body).status_code==409
    assert client.put(f'/api/services/{slug}',json={**body,'name':'新名字','password':''}).status_code==200
    assert client.post(f'/api/services/{slug}/credentials',json={}).json()['password']==auth['password']
    result={'tcp':True,'udp':True,'ip':'203.0.113.1','country':'IN','at':'2026-10-23T00:00:00Z','duration_ms':100}
    monkeypatch.setattr(app,'probe',lambda *args,**kwargs:result)
    assert client.post(f'/api/services/{slug}/test',json={}).status_code==200
    assert client.get('/api/state').json()['services'][0]['last_probe']==result
    monkeypatch.setattr(app,'manager',lambda *args,**kwargs:(_ for _ in ()).throw(ValueError('配置无效')))
    assert client.put(f'/api/services/{slug}',json={**body,'name':'不应保存'}).status_code==400
    assert client.get('/api/state').json()['services'][0]['name']=='新名字'
    monkeypatch.setattr(app,'manager',lambda *args,**kwargs:{})
    assert client.post(f'/api/services/{slug}/action',json={'action':'start'}).status_code==200
    assert client.get('/api/state').json()['services'][0]['enabled'] is True
    assert client.delete(f'/api/services/{slug}').status_code==200
    assert client.delete(f'/api/subscriptions/{sub}').status_code==200


def test_expired_session_and_password_change(panel):
    client,app,_=panel
    with app.DB.connection(write=True) as db:
        db.execute("UPDATE sessions SET expires_at=strftime('%Y-%m-%dT%H:%M:%fZ','now','-1 minute')")
    assert client.get('/api/state').status_code==401
    assert client.post('/api/login',json={'username':'admin','password':'test-password-for-sqlite'}).status_code==200
    assert client.post('/api/admin/password',json={'current':'test-password-for-sqlite','password':'another-test-password'}).status_code==200
    assert client.get('/api/state').status_code==401
    assert client.post('/api/login',json={'username':'admin','password':'another-test-password'}).status_code==200
