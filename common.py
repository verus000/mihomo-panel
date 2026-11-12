"""Shared validation and deterministic Mihomo configuration rendering."""
import copy
import os
import re
import secrets

SUPPORTED = {'vless', 'vmess', 'trojan', 'ss', 'ssr', 'hysteria', 'hysteria2', 'tuic', 'socks5', 'http', 'snell', 'anytls'}
FIELDS = {
    'name', 'type', 'server', 'port', 'uuid', 'password', 'username', 'cipher', 'alterId',
    'udp', 'tls', 'skip-cert-verify', 'servername', 'sni', 'network', 'flow', 'packet-encoding',
    'client-fingerprint', 'fingerprint', 'alpn', 'reality-opts', 'ws-opts', 'grpc-opts',
    'http-opts', 'h2-opts', 'xhttp-opts', 'encryption', 'encryption-mode',
    'plugin', 'plugin-opts', 'obfs', 'obfs-password', 'obfs-param', 'protocol', 'protocol-param',
    'up', 'down', 'up-speed', 'down-speed', 'auth', 'auth-str', 'recv-window', 'recv-window-conn',
    'disable-mtu-discovery', 'fast-open', 'reduce-rtt', 'request-timeout', 'heartbeat-interval',
    'congestion-controller', 'udp-relay-mode', 'max-udp-relay-packet-size', 'version',
    'udp-over-tcp', 'udp-over-tcp-version', 'tfo', 'ip-version', 'max-open-streams',
}
REGIONS = [
    ('香港', ['香港', 'hong kong', 'hongkong', '🇭🇰']), ('台湾', ['台湾', 'taiwan', '🇹🇼']),
    ('新加坡', ['新加坡', 'singapore', '🇸🇬']), ('日本', ['日本', 'japan', 'tokyo', '🇯🇵']),
    ('韩国', ['韩国', 'korea', '🇰🇷']), ('印度', ['印度', 'india', 'mumbai', '🇮🇳']),
    ('菲律宾', ['菲律宾', 'philippine', 'manila', '🇵🇭']), ('美国', ['美国', 'united states', '🇺🇸']),
    ('英国', ['英国', 'united kingdom', '🇬🇧']), ('德国', ['德国', 'germany', '🇩🇪']),
    ('法国', ['法国', 'france', '🇫🇷']), ('加拿大', ['加拿大', 'canada', '🇨🇦']),
    ('澳大利亚', ['澳大利亚', '澳洲', 'australia', '🇦🇺']), ('马来西亚', ['马来西亚', 'malaysia', '🇲🇾']),
    ('泰国', ['泰国', 'thailand', '🇹🇭']), ('越南', ['越南', 'vietnam', '🇻🇳']),
    ('印度尼西亚', ['印度尼西亚', '印尼', 'indonesia', '🇮🇩']), ('俄罗斯', ['俄罗斯', 'russia', '🇷🇺']),
    ('荷兰', ['荷兰', 'netherlands', '🇳🇱']), ('土耳其', ['土耳其', 'turkey', '🇹🇷']),
    ('巴西', ['巴西', 'brazil', '🇧🇷']), ('中国大陆', ['中国大陆', 'china', '🇨🇳']),
]

def region(name):
    value = name.lower()
    # Longer names must win, e.g. 印度尼西亚 before 印度.
    matches = [(len(word), label) for label, words in REGIONS for word in words if word in value]
    return max(matches)[1] if matches else '其他'

def credentials():
    return {'username': 'socks_' + secrets.token_hex(4), 'password': secrets.token_urlsafe(24)}

def validate_credentials(username, password):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', username):
        raise ValueError('用户名限 1–64 位英文、数字、点、下划线或短横线')
    if not isinstance(password, str) or not 16 <= len(password.encode()) <= 128 or any(c.isspace() or c == ':' for c in password):
        raise ValueError('密码需为 16–128 字节，不能包含空白或冒号')

def normalize_proxy(raw):
    if not isinstance(raw, dict) or raw.get('type') not in SUPPORTED:
        raise ValueError('不支持的节点协议')
    if not isinstance(raw.get('name'), str) or not raw['name'].strip() or len(raw['name']) > 256:
        raise ValueError('节点名称无效')
    if not isinstance(raw.get('server'), str) or not re.fullmatch(r'[A-Za-z0-9._:\-\[\]]{1,253}', raw['server']):
        raise ValueError('节点服务器地址无效')
    if isinstance(raw.get('port'), bool) or not 1 <= int(raw.get('port', 0)) <= 65535:
        raise ValueError('节点端口无效')
    result = {key: copy.deepcopy(value) for key, value in raw.items() if key in FIELDS}
    result['port'] = int(result['port'])
    result.setdefault('udp', True)
    # No file access, external processes, provider references, or dialer indirection.
    def safe_nested(value, depth=0):
        if depth > 10:
            raise ValueError('节点配置嵌套过深')
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str) or any(word in key.lower() for word in ('file', 'path', 'command', 'exec', 'private-key')):
                    raise ValueError('节点包含不允许的本地文件或执行选项')
                safe_nested(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                safe_nested(item, depth + 1)
        elif not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError('节点配置格式无效')
    # Path strings are legitimate in WS/HTTP options, but never interpreted as files.
    for key in ('reality-opts', 'plugin-opts'):
        if key in result:
            safe_nested(result[key])
    return result

def render_config(port, username, password, proxy):
    validate_credentials(username, password)
    if isinstance(port, bool) or not 1024 <= int(port) <= 65535 or int(port) == int(os.getenv('PANEL_PORT', '8080')):
        raise ValueError('服务端口需在 1024–65535 之间，不能占用面板端口')
    node = normalize_proxy(proxy)
    node['name'] = 'selected-node'
    return {'socks-port': int(port), 'allow-lan': True, 'bind-address': '*',
            'authentication': [username + ':' + password], 'mode': 'rule', 'log-level': 'info',
            'external-controller': '', 'ipv6': False, 'proxies': [node], 'rules': ['MATCH,selected-node']}
