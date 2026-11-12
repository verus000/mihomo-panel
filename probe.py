import datetime
import json
import os
import socket
import struct
import time
from urllib.parse import quote
import httpx

def exact(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise OSError('SOCKS5 连接提前关闭')
        data += chunk
    return data

def udp_query(port, username, password):
    with socket.create_connection(('127.0.0.1', port), 3) as control:
        control.settimeout(3)
        control.sendall(b'\x05\x01\x02')
        if exact(control, 2) != b'\x05\x02':
            raise OSError('SOCKS5 未选择密码认证')
        user, secret = username.encode(), password.encode()
        control.sendall(b'\x01' + bytes([len(user)]) + user + bytes([len(secret)]) + secret)
        if exact(control, 2) != b'\x01\x00':
            raise OSError('SOCKS5 密码认证失败')
        control.sendall(b'\x05\x03\x00\x01' + b'\x00' * 6)
        header = exact(control, 4)
        if header[:2] != b'\x05\x00' or header[3] not in (1, 4):
            raise OSError('UDP ASSOCIATE 失败')
        tail = exact(control, 6 if header[3] == 1 else 18)
        relay = struct.unpack('!H', tail[-2:])[0]
        txid = os.urandom(2)
        dns = txid + b'\x01\x00\x00\x01' + b'\x00' * 6 + b'\x07example\x03com\x00\x00\x01\x00\x01'
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.settimeout(8)
            udp.sendto(b'\x00\x00\x00\x01' + socket.inet_aton('1.1.1.1') + struct.pack('!H', 53) + dns, ('127.0.0.1', relay))
            packet, _ = udp.recvfrom(4096)
        if packet[:3] != b'\x00\x00\x00':
            raise OSError('UDP 返回头无效')
        offset = 10 if packet[3] == 1 else 22 if packet[3] == 4 else 5 + packet[4] + 2
        answer = packet[offset:]
        if len(answer) < 12 or answer[:2] != txid or not (answer[2] & 128) or answer[3] & 15 or struct.unpack('!H', answer[6:8])[0] < 1:
            raise OSError('DNS 返回内容无效')

def probe(port, username, password, with_udp=True):
    start = time.monotonic()
    result = {'tcp': False, 'udp': None, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    proxy = f'socks5h://{quote(username, safe="")}:{quote(password, safe="")}@127.0.0.1:{port}'
    failures = []
    with httpx.Client(proxy=proxy, timeout=12, trust_env=False) as client:
        for _ in range(2):
            try:
                response = client.get('https://ipinfo.io/json')
                response.raise_for_status()
                data = response.json()
                if not data.get('ip'):
                    raise ValueError('查询未返回出口 IP')
                result.update(tcp=True, ip=data['ip'], country=data.get('country', ''), city=data.get('city', ''))
                break
            except Exception as exc:
                failures.append(type(exc).__name__ + ': ' + str(exc))
    if not result['tcp']:
        result['error'] = '; '.join(failures)[-600:]
    elif failures:
        result['warning'] = '首次 TCP 请求失败，重试成功'
    if with_udp:
        for attempt in range(2):
            try:
                udp_query(port, username, password)
                result['udp'] = True
                if attempt:
                    result['udp_warning'] = '首次 UDP 请求超时或失败，重试成功'
                break
            except Exception as exc:
                result['udp'] = False
                result['udp_error'] = type(exc).__name__ + ': ' + str(exc)
        if result['udp']:
            result.pop('udp_error', None)
    result['duration_ms'] = round((time.monotonic() - start) * 1000)
    # Do not return credentials in errors from HTTP client implementations.
    return json.loads(json.dumps(result).replace(password, '[redacted]'))
