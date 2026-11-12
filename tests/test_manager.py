"""Manager rule rendering and instance rebuild without privileged host mutations."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
sys.path.insert(0,str(Path(__file__).parents[1]))
import manager
from common import render_config


def test_firewall_preserves_foreign_rules_and_opens_all_input_chains(monkeypatch):
    rules={'nftables':[
        {'chain':{'family':'inet','table':'filter','name':'input','hook':'input','policy':'drop'}},
        {'chain':{'family':'ip6','table':'filter6','name':'incoming','hook':'input','policy':'drop'}},
        {'rule':{'family':'inet','table':'filter','chain':'input','handle':9,'comment':'ssh-existing'}},
        {'rule':{'family':'inet','table':'filter','chain':'input','handle':10,'comment':'mihomo-panel:tcp'}}]}
    commands=[]
    def run(args,**kwargs):
        commands.append((args,kwargs))
        return subprocess.CompletedProcess(args,0,json.dumps(rules),'')
    monkeypatch.setattr(manager,'run',run)
    monkeypatch.setenv('PANEL_PORT','18080');monkeypatch.setenv('PANEL_FIREWALL','1')
    manager.firewall({'svc-0123456789ab':{'port':40099}})
    text=commands[-1][1]['input']
    assert 'flush' not in text and 'handle 9' not in text and 'handle 10' in text
    assert 'inet filter input tcp dport { 18080, 40099 }' in text
    assert 'ip6 filter6 incoming udp dport { 40099 }' in text
    assert 'udp dport { 18080' not in text
    assert commands[-2][0]==['nft','-c','-f','-']


def test_manual_firewall_mode_cleans_only_our_rules(monkeypatch):
    commands=[]
    def run(args,**kwargs):
        commands.append((args,kwargs));return subprocess.CompletedProcess(args,0,'{"nftables":[]}','')
    monkeypatch.setattr(manager,'run',run);monkeypatch.setenv('FIREWALL_MODE','off')
    manager.firewall({'svc-0123456789ab':{'port':40099}})
    assert 'dport' not in commands[-1][1]['input']
    assert 'flush' not in commands[-1][1]['input']


def test_service_paths_reject_arbitrary_identifiers():
    for slug in ['../../root','svc-123','x.service','svc-0123456789ab;id']:
        with pytest.raises(ValueError):manager.paths(slug)


def test_instance_unit_has_no_shell_and_project_core(monkeypatch,tmp_path):
    monkeypatch.setattr(manager,'MIHOMO_BIN','/opt/mihomo-panel/core/mihomo')
    text=manager.unit_text('mihomo-svc-0123456789ab',tmp_path/'config',tmp_path/'data')
    assert 'ExecStart=/opt/mihomo-panel/core/mihomo ' in text
    assert 'User=mihomo-svc-0123456789ab' in text
    assert '/bin/sh' not in text and 'NoNewPrivileges=yes' in text


def test_panel_port_setting_is_reserved(monkeypatch):
    monkeypatch.setenv('PANEL_PORT','18080')
    proxy={'name':'node','type':'vless','server':'example.com','port':443,'uuid':'00000000-0000-4000-8000-000000000001'}
    with pytest.raises(ValueError):render_config(18080,'user','x'*24,proxy)
    assert render_config(8080,'user','x'*24,proxy)['socks-port']==8080


def test_legacy_restore_creates_missing_systemd_unit(monkeypatch,tmp_path):
    """Imported legacy IDs must get a unit on a fresh destination machine."""
    from types import SimpleNamespace
    monkeypatch.setattr(manager,'CONFIG_DIR',tmp_path/'config')
    monkeypatch.setattr(manager,'INSTANCE_DATA',tmp_path/'data')
    monkeypatch.setattr(manager,'UNIT_DIR',tmp_path/'units')
    monkeypatch.setattr(manager,'REGISTRY',tmp_path/'services.json')
    (tmp_path/'data').mkdir();(tmp_path/'units').mkdir()
    monkeypatch.setattr(manager.pwd,'getpwnam',lambda name:SimpleNamespace(pw_uid=0,pw_gid=0))
    monkeypatch.setattr(manager.os,'chown',lambda *args:None)
    def atomic(path,content,*args,**kwargs):Path(path).write_text(content)
    monkeypatch.setattr(manager,'atomic',atomic)
    commands=[]
    def run(args,**kwargs):commands.append(args);return subprocess.CompletedProcess(args,0,'','')
    monkeypatch.setattr(manager,'run',run)
    monkeypatch.setattr(manager,'status',lambda slug:{'ActiveState':'inactive','UnitFileState':'disabled'})
    monkeypatch.setattr(manager,'check_free',lambda port:None)
    monkeypatch.setattr(manager,'firewall',lambda data:None)
    manager.save_registry({'india':{'port':40099}})
    proxy={'name':'node','type':'vless','server':'example.com','port':443,'uuid':'00000000-0000-4000-8000-000000000001'}
    manager.apply({'id':'india','port':40099,'username':'user','password':'x'*24,'proxy':proxy,'enabled':False})
    unit=tmp_path/'units/mihomo-india.service'
    assert unit.exists() and 'User=mihomo-india' in unit.read_text()
    assert ['systemctl','daemon-reload'] in commands
