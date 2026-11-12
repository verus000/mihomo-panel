import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
from common import credentials, normalize_proxy, region, render_config

PROXY = {'name':'测试', 'type':'vless', 'server':'example.com', 'port':443,
         'uuid':'00000000-0000-4000-8000-000000000001', 'network':'tcp', 'tls':True}

def test_independent_credentials():
    generated = [credentials() for _ in range(100)]
    assert len({v['username'] for v in generated}) == 100
    assert len({v['password'] for v in generated}) == 100
    assert all(len(v['password']) >= 32 for v in generated)

@pytest.mark.parametrize('username', ['../root','india:password','user\nname','用户'])
def test_rejects_unsafe_authentication(username):
    with pytest.raises(ValueError):
        render_config(40099, username, 'A'*24, PROXY)

def test_only_selected_proxy_and_no_controller():
    config = render_config(40099, 'some_user', 'A'*24, PROXY)
    assert config['external-controller'] == ''
    assert config['rules'] == ['MATCH,selected-node']
    assert config['proxies'][0]['name'] == 'selected-node'
    assert len(config['proxies']) == 1

def test_unsafe_subscription_options_removed():
    raw = {**PROXY, 'dialer-proxy':'DIRECT','interface-name':'lo','routing-mark':12,'certificate':'/etc/shadow'}
    node = normalize_proxy(raw)
    assert 'dialer-proxy' not in node
    assert 'certificate' not in node

def test_region_longest_match_wins():
    assert region('印度尼西亚-01') == '印度尼西亚'
    assert region('印度-01') == '印度'
    assert region('PH Philippines 01') == '菲律宾'

@pytest.mark.parametrize('port', [22,8080,65536])
def test_reserved_or_invalid_listen_ports(port):
    with pytest.raises(ValueError):
        render_config(port, 'some_user', 'A'*24, PROXY)
