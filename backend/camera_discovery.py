"""
Smart Camera Auto-Discovery v3 — fast, tested, deadline-aware.

Real-world timing (measured on actual hardware):
  Wrong credentials → OpenCV fails in 0.15 s  (FAST)
  Right credentials → OpenCV succeeds in 2.3 s
  ARP table        → 0.02 s
  TCP port probe   → 0.5 s per host
  ONVIF multicast  → 4 s total

Strategy:
  1. Find hosts with RTSP ports open       (ARP + port probe, ~5 s)
  2. RTSP DESCRIBE fingerprint             (Server header → manufacturer, ~0.2 s)
  3. Smart-ordered OpenCV sequential probe (wrong fails in 0.15 s, right in 2.3 s)
     → 100 combos worst case = ~17 s per camera

Total: ≤ 60 s typical, ≤ 5 min absolute max.
"""

import socket
import threading
import logging
import subprocess
import re
import time
import ipaddress
import uuid
import os
from typing import List, Dict, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

logger = logging.getLogger('surveillance.discovery')

DEADLINE_SEC = 280  # 4 min 40 s hard cap

# ══════════════════════════════════════════════════════════════════════════
# COMBO DATABASE
#
# Key insight: on failure OpenCV returns in ~0.15 s, on success ~2.3 s.
# So we can afford to try 100+ combos sequentially — wrong ones are cheap.
# Order matters: most-likely first → finds camera in 1-3 attempts.
# ══════════════════════════════════════════════════════════════════════════

# Statistically ordered: covers ~95 % of IP cameras worldwide.
# Each tuple: (username, password, path)
TOP_COMBOS: List[Tuple[str, str, str]] = [
    # — Generic / XMEye / Chinese DVR (world's most common) —
    ('admin', '',       '/stream'),
    ('admin', 'admin',  '/stream'),
    ('admin', '',       '/0'),
    ('admin', '',       '/1'),
    ('admin', '',       '/live'),
    ('admin', '',       '/ch1/main/av_stream'),
    ('admin', '',       '/media/video1'),
    # — Hikvision (world #1 by market share) —
    ('admin', '',       '/Streaming/Channels/101'),
    ('admin', '12345',  '/Streaming/Channels/101'),
    ('admin', 'Hik12345','/Streaming/Channels/101'),
    ('admin', 'hik12345','/Streaming/Channels/101'),
    ('admin', '12345',  '/Streaming/Channels/102'),
    ('admin', '',       '/Streaming/Channels/102'),
    ('admin', '',       '/ISAPI/Streaming/channels/101'),
    # — Dahua / Amcrest (world #2) —
    ('admin', 'admin',  '/cam/realmonitor?channel=1&subtype=0'),
    ('admin', '',       '/cam/realmonitor?channel=1&subtype=0'),
    ('admin', '888888', '/cam/realmonitor?channel=1&subtype=0'),
    ('admin', '666666', '/cam/realmonitor?channel=1&subtype=0'),
    ('admin', 'dahua',  '/cam/realmonitor?channel=1&subtype=0'),
    ('admin', 'admin',  '/cam/realmonitor?channel=1&subtype=1'),
    ('admin', '1',      '/cam/realmonitor?channel=1&subtype=0'),
    # — Reolink —
    ('admin', '',       '/h264Preview_01_main'),
    ('admin', '',       '/h264Preview_01_sub'),
    ('admin', '',       '/Preview_01_main'),
    # — AXIS —
    ('root',  '',       '/axis-media/media.amp'),
    ('root',  'root',   '/axis-media/media.amp'),
    ('root',  'pass',   '/axis-media/media.amp'),
    ('root',  '',       '/live.sdp'),
    # — Foscam —
    ('admin', '',       '/videoMain'),
    ('admin', 'admin',  '/videoMain'),
    # — Samsung / Hanwha —
    ('admin', '4321',   '/profile1/media.smp'),
    ('admin', 'admin4321','/profile1/media.smp'),
    # — TP-Link / Tapo —
    ('admin', 'admin',  '/stream1'),
    ('admin', '',       '/stream1'),
    # — Uniview —
    ('admin', '123456', '/media/video1'),
    ('admin', 'admin1234','/unicast/c1/s0/live'),
    # — Ubiquiti —
    ('ubnt',  'ubnt',   '/live'),
    ('ubnt',  'ubnt',   '/s0'),
    # — Bosch —
    ('admin', 'admin',  '/rtsp_tunnel'),
    ('service','service','/video?inst=1'),
    # — Vivotek —
    ('root',  'icatch99','/live.sdp'),
    ('root',  '',        '/live.sdp'),
    # — Grandstream —
    ('admin', 'admin',  '/0'),
    ('admin', '',       '/live/ch0'),
    # — Mobotix —
    ('admin', 'meinsm', '/mobotix.h264'),
    # — ACTi —
    ('Admin', '123456', '/cgi-bin/cmd/encoder?GET_STREAM'),
    ('admin', '12345678','/cgi-bin/cmd/encoder?GET_STREAM'),
    # — Pelco —
    ('admin', 'admin',  '/stream1'),
    # — GeoVision —
    ('admin', 'admin',  '/CH001.sdp'),
    # — Wanscam —
    ('admin', '',       '/live/ch00_0'),
    ('admin', 'admin',  '/11'),
    # — XMEye with embedded creds —
    ('admin', '',       '/user={user}_password={pass}_channel=1_stream=0.sdp'),
    ('admin', '',       '/user={user}&password={pass}&channel=1&stream=0.sdp?'),
]

# Extended combos: extra creds × extra paths (tried if TOP_COMBOS fail)
EXTRA_CREDS = [
    ('admin', 'admin123'), ('admin', '123456'), ('admin', 'password'),
    ('admin', '1234'), ('admin', 'pass'), ('admin', 'admin123456'),
    ('root', '12345'), ('root', 'admin'), ('user', 'user'), ('', ''),
    ('Qwerty123', 'Qwerty888'),
]

EXTRA_PATHS = [
    '/stream2', '/video1', '/video2', '/live/ch1',
    '/streaming/channels/101', '/Streaming/Channels/1',
    '/Streaming/Channels/201', '/h264/ch1/main/av_stream',
    '/ch1/sub/av_stream', '/cam/realmonitor?channel=2&subtype=0',
    '/h265Preview_01_main', '/media/video2',
    '/live1.sdp', '/live2.sdp', '/profile2/media.smp',
    '/stream/main', '/stream/sub', '/s1',
    '/mjpg/video.mjpg', '/12',
    '/user={user}&password={pass}&channel=20&stream=0.sdp?',
]

# ── RTSP Server header → manufacturer mapping ───────────────────────────

SERVER_FINGERPRINTS = [
    (re.compile(r'Hikvision|DNVRS|hikv', re.I),   'hikvision'),
    (re.compile(r'Dahua|DH-', re.I),               'dahua'),
    (re.compile(r'Reolink', re.I),                  'reolink'),
    (re.compile(r'AXIS', re.I),                     'axis'),
    (re.compile(r'H264DVR|XMEye|DVR', re.I),       'xmeye'),
    (re.compile(r'Foscam|IPCam', re.I),             'foscam'),
    (re.compile(r'Ubnt|UniFi', re.I),               'ubiquiti'),
    (re.compile(r'Samsung|Hanwha|Wisenet', re.I),   'samsung'),
    (re.compile(r'Bosch', re.I),                    'bosch'),
    (re.compile(r'Vivotek', re.I),                  'vivotek'),
    (re.compile(r'Grandstream', re.I),              'grandstream'),
    (re.compile(r'TP-LINK|Tapo', re.I),             'tplink'),
]

# Manufacturer → best combo indices in TOP_COMBOS (jump to these first)
MANUFACTURER_FAST_INDICES: Dict[str, List[int]] = {
    'xmeye':     [0, 1, 2, 3, 4, 5, 6],       # /stream, /0, /1, /live
    'hikvision': [7, 8, 9, 10, 11, 12, 13],    # /Streaming/Channels/*
    'dahua':     [14, 15, 16, 17, 18, 19, 20], # /cam/realmonitor*
    'reolink':   [21, 22, 23],                  # /h264Preview*
    'axis':      [24, 25, 26, 27],              # /axis-media*
    'foscam':    [28, 29],                       # /videoMain
    'samsung':   [30, 31],                       # /profile*
    'tplink':    [32, 33],                       # /stream1
    'ubiquiti':  [36, 37],                       # /live, /s0
    'bosch':     [38, 39],                       # /rtsp_tunnel
    'vivotek':   [40, 41],                       # /live.sdp
    'grandstream':[42, 43],                      # /0, /live/ch0
}

RTSP_PORTS = [554, 8554, 9200, 8553, 10554]
HTTP_PORTS = [80, 8080, 8000, 8888, 81]

# ── MAC OUI → manufacturer (top vendors) ────────────────────────────────

MAC_OUI_MAP = {
    'c0:56:e3': 'hikvision', '44:19:b6': 'hikvision', '54:c4:15': 'hikvision',
    'bc:ad:28': 'hikvision', 'e0:ab:fe': 'hikvision', '68:0a:e2': 'hikvision',
    'c4:2f:90': 'hikvision', '28:57:be': 'hikvision', '38:af:29': 'hikvision',
    'a4:14:37': 'hikvision', '74:da:88': 'hikvision', '80:65:e9': 'hikvision',
    '3c:ef:8c': 'dahua', 'a0:bd:1d': 'dahua', '40:2c:76': 'dahua',
    'b0:c7:de': 'dahua', 'e0:50:8b': 'dahua', '3c:e3:6b': 'dahua',
    'f8:4d:fc': 'dahua', '14:a7:8b': 'dahua', '9c:8e:cd': 'dahua',
    'ec:71:db': 'reolink', 'b4:6d:c2': 'reolink', 'd4:5f:5b': 'reolink',
    '00:40:8c': 'axis', 'b8:a4:4f': 'axis', 'd8:a3:7c': 'axis',
    '24:5a:4c': 'ubiquiti', '44:d9:e7': 'ubiquiti', 'fc:ec:da': 'ubiquiti',
    '50:c7:bf': 'tplink', '60:a4:b7': 'tplink', '78:44:76': 'tplink',
    'c0:56:27': 'foscam', '00:02:d1': 'vivotek', '24:28:fd': 'uniview',
    '00:04:13': 'bosch', '00:0b:82': 'grandstream',
}

# ══════════════════════════════════════════════════════════════════════════
# ONVIF WS-Discovery
# ══════════════════════════════════════════════════════════════════════════

_ONVIF_PROBE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
               xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery"
               xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <soap:Header>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
    <wsa:MessageID>urn:uuid:{msg_id}</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
  </soap:Header>
  <soap:Body>
    <wsd:Probe><wsd:Types>dn:NetworkVideoTransmitter</wsd:Types></wsd:Probe>
  </soap:Body>
</soap:Envelope>"""


def _expired(deadline: float) -> bool:
    return time.time() >= deadline


def _onvif_discover(timeout: float = 4.0) -> List[str]:
    ips: Set[str] = set()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        for _ in range(3):
            msg = _ONVIF_PROBE.format(msg_id=uuid.uuid4()).encode()
            sock.sendto(msg, ('239.255.255.250', 3702))
            time.sleep(0.15)
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, addr = sock.recvfrom(65535)
                ip = addr[0]
                if ip not in ('0.0.0.0', '127.0.0.1'):
                    ips.add(ip)
                for m in re.finditer(r'http[s]?://(\d+\.\d+\.\d+\.\d+)', data.decode('utf-8', errors='ignore')):
                    if m.group(1) not in ('0.0.0.0', '127.0.0.1'):
                        ips.add(m.group(1))
            except socket.timeout:
                break
            except Exception:
                continue
        sock.close()
    except Exception:
        pass
    return list(ips)


def _ssdp_discover(timeout: float = 3.0) -> List[str]:
    ips: Set[str] = set()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        for st in ['urn:schemas-upnp-org:device:MediaServer:1', 'ssdp:all']:
            msg = (f"M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
                   f"MAN: \"ssdp:discover\"\r\nMX: 2\r\nST: {st}\r\n\r\n").encode()
            sock.sendto(msg, ('239.255.255.250', 1900))
            time.sleep(0.1)
        end = time.time() + timeout
        while time.time() < end:
            try:
                _, addr = sock.recvfrom(4096)
                if addr[0] not in ('0.0.0.0', '127.0.0.1'):
                    ips.add(addr[0])
            except socket.timeout:
                break
            except Exception:
                continue
        sock.close()
    except Exception:
        pass
    return list(ips)


# ══════════════════════════════════════════════════════════════════════════
# Network helpers
# ══════════════════════════════════════════════════════════════════════════

def _get_local_ips() -> Set[str]:
    """Get ALL IP addresses assigned to this machine (to exclude from scan).
    Prevents scanning ourselves (go2rtc, Docker networks, VPN, etc.)."""
    local: Set[str] = {'127.0.0.1'}
    try:
        r = subprocess.run(['ipconfig'], capture_output=True, text=True, timeout=5)
        for m in re.finditer(r'IPv4[^:]*:\s*(\d+\.\d+\.\d+\.\d+)', r.stdout):
            local.add(m.group(1))
        # Also match generic "IP Address" lines
        for m in re.finditer(r'IP Address[^:]*:\s*(\d+\.\d+\.\d+\.\d+)', r.stdout):
            local.add(m.group(1))
    except Exception:
        pass
    try:
        r = subprocess.run(['ip', '-4', 'addr'], capture_output=True, text=True, timeout=5)
        for m in re.finditer(r'inet (\d+\.\d+\.\d+\.\d+)', r.stdout):
            local.add(m.group(1))
    except Exception:
        pass
    # Also try hostname resolution
    try:
        local.add(socket.gethostbyname(socket.gethostname()))
    except Exception:
        pass
    logger.info(f"Local IPs (excluded from scan): {local}")
    return local


def _get_local_networks() -> List[str]:
    networks: set = set()
    try:
        r = subprocess.run(['ipconfig'], capture_output=True, text=True, timeout=5)
        ip_addr = None
        for line in r.stdout.split('\n'):
            if 'IPv4' in line or 'IP Address' in line:
                m = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                if m:
                    ip_addr = m.group(1)
            elif ('Subnet Mask' in line or 'Маска подсети' in line) and ip_addr:
                m = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                if m:
                    try:
                        net = ipaddress.IPv4Network(f"{ip_addr}/{m.group(1)}", strict=False)
                        if not net.is_loopback and net.num_addresses <= 65536:
                            networks.add(str(net))
                    except Exception:
                        pass
                ip_addr = None
    except Exception:
        pass
    if not networks:
        try:
            r = subprocess.run(['ip', '-4', 'addr'], capture_output=True, text=True, timeout=5)
            for m in re.finditer(r'inet (\d+\.\d+\.\d+\.\d+/\d+)', r.stdout):
                net = ipaddress.IPv4Network(m.group(1), strict=False)
                if not net.is_loopback and net.num_addresses <= 65536:
                    networks.add(str(net))
        except Exception:
            pass
    return list(networks) or ['192.168.1.0/24']


def _get_arp_hosts() -> Dict[str, Optional[str]]:
    """Returns {ip: mac_or_None}."""
    hosts: Dict[str, Optional[str]] = {}
    try:
        r = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=5)
        for line in r.stdout.split('\n'):
            ip_m = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
            if not ip_m:
                continue
            ip = ip_m.group(1)
            if ip.endswith('.255') or ip.endswith('.0') or ip == '255.255.255.255':
                continue
            mac_m = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', line)
            hosts[ip] = mac_m.group(0).lower().replace('-', ':') if mac_m else None
    except Exception:
        pass
    return hosts


def _tcp_port_open(ip: str, port: int, timeout: float = 0.6) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        ok = s.connect_ex((ip, port)) == 0
        s.close()
        return ok
    except Exception:
        return False


def _ping_sweep_fast(network: str, deadline: float) -> Set[str]:
    """Quick sweep: TCP connect to port 554 on all hosts (no subprocess ping)."""
    alive: Set[str] = set()
    try:
        hosts = list(ipaddress.IPv4Network(network, strict=False).hosts())[:254]
    except Exception:
        return alive

    def probe(ip_str):
        if _expired(deadline):
            return None
        for port in (554, 80, 8554):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.4)
                if s.connect_ex((ip_str, port)) == 0:
                    s.close()
                    return ip_str
                s.close()
            except Exception:
                pass
        return None

    with ThreadPoolExecutor(max_workers=80) as pool:
        futs = {pool.submit(probe, str(h)): str(h) for h in hosts}
        tl = max(1, deadline - time.time())
        for f in as_completed(futs, timeout=min(15, tl)):
            try:
                r = f.result()
                if r:
                    alive.add(r)
            except Exception:
                pass
    return alive


# ══════════════════════════════════════════════════════════════════════════
# RTSP fingerprint (DESCRIBE without auth → Server header)
# ══════════════════════════════════════════════════════════════════════════

def _rtsp_fingerprint(ip: str, port: int = 554) -> Optional[str]:
    """Send DESCRIBE without auth, parse Server header → manufacturer."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((ip, port))
        url = f'rtsp://{ip}:{port}/'
        req = f'DESCRIBE {url} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n'
        s.sendall(req.encode())
        resp = b''
        end = time.time() + 2
        while time.time() < end:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
                if b'\r\n\r\n' in resp:
                    break
            except socket.timeout:
                break
        s.close()
        text = resp.decode('utf-8', errors='ignore')
        # Parse Server header
        server_m = re.search(r'Server:\s*(.+?)[\r\n]', text, re.I)
        if server_m:
            server_val = server_m.group(1).strip()
            for pattern, mfr in SERVER_FINGERPRINTS:
                if pattern.search(server_val):
                    return mfr
            return f'unknown:{server_val[:40]}'
    except Exception:
        pass
    return None


def _rtsp_probe_auth(ip: str, port: int = 554, path: str = '/') -> Dict[str, str]:
    """Probe RTSP endpoint and detect if authentication is required."""
    result = {'auth_required': False, 'status': ''}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((ip, port))
        if not path.startswith('/'):
            path = '/' + path
        url = f'rtsp://{ip}:{port}{path}'
        req = f'DESCRIBE {url} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n'
        s.sendall(req.encode())
        resp = b''
        end = time.time() + 2
        while time.time() < end:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
                if b'\r\n\r\n' in resp:
                    break
            except socket.timeout:
                break
        s.close()

        text = resp.decode('utf-8', errors='ignore')
        status_m = re.search(r'RTSP/\d\.\d\s+(\d+)', text, re.I)
        code = int(status_m.group(1)) if status_m else 0
        result['status'] = str(code) if code else ''
        if code in (401, 403):
            result['auth_required'] = True
    except Exception:
        pass
    return result


# ══════════════════════════════════════════════════════════════════════════
# OpenCV stream verification (the only reliable method)
# ══════════════════════════════════════════════════════════════════════════

def _verify_stream(url: str, timeout: int = 4) -> bool:
    """OpenCV RTSP verification with HARD thread-level timeout.
    Wrong creds: fails in ~0.15 s (fast!).
    Right creds: succeeds in ~2.3 s.
    Never hangs: daemon thread is abandoned after hard_limit.
    """
    hard_limit = timeout + 3  # absolute max wait

    result = [False]

    def _inner():
        import cv2
        try:
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout * 1000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout * 1000)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                cap.release()
                return
            ret, frame = cap.read()
            cap.release()
            result[0] = ret and frame is not None
        except Exception:
            pass

    t = threading.Thread(target=_inner, daemon=True)
    t.start()
    t.join(hard_limit)
    if t.is_alive():
        logger.warning(f"_verify_stream HARD TIMEOUT ({hard_limit}s): {url[:80]}")
    return result[0]


def _build_url(ip: str, port: int, path: str, user: str, passwd: str) -> str:
    actual = path.replace('{user}', user).replace('{pass}', passwd)
    if not actual.startswith('/'):
        actual = '/' + actual
    use_embedded_path_creds = ('user=' in actual and 'password=' in actual)
    creds = ''
    if user and not use_embedded_path_creds:
        creds = f"{quote(user, safe='')}:{quote(passwd, safe='')}@"
    return f"rtsp://{creds}{ip}:{port}{actual}"


def _make_result(ip, port, path, user, passwd, url, manufacturer=''):
    return {
        'ip_address': ip, 'port': port, 'protocol': 'rtsp',
        'path': path, 'username': user, 'password': passwd,
        'stream_url': url, 'name': f'Camera {ip}',
        'verified': True, 'connection_type': 'direct',
        'auth_required': False,
        'manufacturer': manufacturer,
    }


# ══════════════════════════════════════════════════════════════════════════
# SMART COMBO ORDERING
# ══════════════════════════════════════════════════════════════════════════

def _ordered_combos(manufacturer: Optional[str]) -> List[Tuple[str, str, str]]:
    """Return TOP_COMBOS reordered: manufacturer-specific first, then rest."""
    if manufacturer and manufacturer in MANUFACTURER_FAST_INDICES:
        fast_idx = MANUFACTURER_FAST_INDICES[manufacturer]
        result = [TOP_COMBOS[i] for i in fast_idx if i < len(TOP_COMBOS)]
        for i, combo in enumerate(TOP_COMBOS):
            if i not in fast_idx:
                result.append(combo)
        return result
    return list(TOP_COMBOS)


def _extended_combos(manufacturer: Optional[str]) -> List[Tuple[str, str, str]]:
    """Extra combos for when TOP_COMBOS all fail. Capped at ~100 combos."""
    seen: Set[Tuple[str, str, str]] = set(TOP_COMBOS)
    result: List[Tuple[str, str, str]] = []
    # Cross-product extra creds × extra paths
    for user, passwd in EXTRA_CREDS:
        for path in EXTRA_PATHS:
            combo = (user, passwd, path)
            if combo not in seen:
                seen.add(combo)
                result.append(combo)
                if len(result) >= 100:
                    return result
    return result


# ══════════════════════════════════════════════════════════════════════════
# MAIN DISCOVERY ENGINE v3
# ══════════════════════════════════════════════════════════════════════════

class SmartCameraDiscovery:
    """
    Fast camera auto-discovery (target: < 2 min typical, < 5 min max).

    Key insight from real hardware testing:
      - OpenCV fails on wrong creds in ~0.15 s
      - OpenCV succeeds on right creds in ~2.3 s
      - Cameras handle 1 RTSP session at a time (no parallel per camera)
      - But different cameras CAN be tested in parallel

    So: ordered sequential probe per camera, parallel across cameras.
    50 combos × 0.15 s = 7.5 s for misses + 2.3 s for hit = ~10 s per camera.
    """

    def __init__(self, callback=None, networks=None):
        self.callback = callback
        self._stop = False
        self._user_networks = networks
        self._ip_mfr: Dict[str, str] = {}

    def stop(self):
        self._stop = True

    def _report(self, stage: str, msg: str, pct: int):
        logger.info(f"[Discovery {pct}%] {stage}: {msg}")
        if self.callback:
            try:
                self.callback(stage, msg, pct)
            except Exception:
                pass

    def _stopped(self, deadline: float) -> bool:
        return self._stop or _expired(deadline)

    def discover(self) -> List[Dict]:
        deadline = time.time() + DEADLINE_SEC
        t_start = time.time()
        discovered: List[Dict] = []
        seen_keys: Set[Tuple[str, int, str]] = set()
        candidate_ips: Set[str] = set()

        # ── Phase 0: Detect our own IPs (exclude from scan) ─────────
        local_ips = _get_local_ips()

        # ── Phase 1: Discover network hosts (~8 s) ──────────────────
        self._report('network', 'Detecting local networks...', 2)
        networks = self._user_networks or _get_local_networks()
        self._report('network', f'Networks: {", ".join(networks)}', 4)

        if self._stopped(deadline):
            return discovered

        # ARP + ONVIF + SSDP — all in parallel
        self._report('discovery', 'ARP + ONVIF + SSDP multicast (parallel)...', 6)
        arp_hosts: Dict[str, Optional[str]] = {}
        onvif_ips: List[str] = []
        ssdp_ips: List[str] = []

        with ThreadPoolExecutor(max_workers=3) as pool:
            f_arp = pool.submit(_get_arp_hosts)
            f_onvif = pool.submit(_onvif_discover, 4.0)
            f_ssdp = pool.submit(_ssdp_discover, 3.0)
            try:
                arp_hosts = f_arp.result(timeout=6)
            except Exception:
                pass
            try:
                onvif_ips = f_onvif.result(timeout=6)
            except Exception:
                pass
            try:
                ssdp_ips = f_ssdp.result(timeout=6)
            except Exception:
                pass

        # MAC → manufacturer
        for ip, mac in arp_hosts.items():
            if mac:
                oui = mac[:8].lower()
                mfr = MAC_OUI_MAP.get(oui)
                if mfr:
                    self._ip_mfr[ip] = mfr

        candidate_ips.update(arp_hosts.keys())
        candidate_ips.update(onvif_ips)
        candidate_ips.update(ssdp_ips)

        # Build set of IPs that belong to our detected networks
        net_objects = []
        for n in networks:
            try:
                net_objects.append(ipaddress.IPv4Network(n, strict=False))
            except Exception:
                pass

        def _in_our_networks(ip_str: str) -> bool:
            try:
                addr = ipaddress.IPv4Address(ip_str)
                return any(addr in net for net in net_objects)
            except Exception:
                return False

        # Filter: remove broadcasts, loopback, OUR OWN IPs,
        # multicast (224-239.x.x.x), and IPs outside our networks
        # (unless found via ONVIF/SSDP which proves reachability)
        onvif_ssdp_set = set(onvif_ips) | set(ssdp_ips)
        candidate_ips = {ip for ip in candidate_ips
                         if not ip.endswith('.255') and not ip.endswith('.0')
                         and ip != '127.0.0.1'
                         and ip not in local_ips
                         and not ip.startswith('224.')
                         and not ip.startswith('239.')
                         and (_in_our_networks(ip) or ip in onvif_ssdp_set)}

        self._report('discovery',
                      f'ARP:{len(arp_hosts)} ONVIF:{len(onvif_ips)} SSDP:{len(ssdp_ips)} | '
                      f'{len(self._ip_mfr)} by MAC | excluded {len(local_ips)} local IPs',
                      14)

        if self._stopped(deadline):
            return discovered

        # ── Phase 2: TCP port sweep to find RTSP hosts (~5-8 s) ─────
        self._report('ports', 'Scanning RTSP ports on all candidates...', 16)

        # First: check RTSP ports on ARP/ONVIF/SSDP hosts (fast, few hosts)
        rtsp_targets: List[Tuple[str, int]] = []

        def check_rtsp(ip):
            if _expired(deadline):
                return []
            found = []
            for port in RTSP_PORTS:
                if _tcp_port_open(ip, port, timeout=0.6):
                    found.append((ip, port))
            return found

        with ThreadPoolExecutor(max_workers=40) as pool:
            futs = {pool.submit(check_rtsp, ip): ip for ip in candidate_ips}
            tl = max(1, deadline - time.time())
            for f in as_completed(futs, timeout=min(15, tl)):
                try:
                    rtsp_targets.extend(f.result())
                except Exception:
                    pass

        self._report('ports', f'{len(rtsp_targets)} RTSP ports found on known hosts', 24)

        # Also sweep full network for hosts not in ARP (e.g. cameras that haven't talked yet)
        if not self._stopped(deadline):
            self._report('sweep', 'Quick sweep for hidden cameras...', 26)
            for net in networks:
                if self._stopped(deadline):
                    break
                new_hosts = _ping_sweep_fast(net, deadline)
                new_hosts -= candidate_ips  # only hosts we didn't already scan
                new_hosts -= local_ips      # never scan ourselves
                if new_hosts:
                    self._report('sweep', f'{len(new_hosts)} new hosts on {net}', 30)
                    with ThreadPoolExecutor(max_workers=40) as pool:
                        futs = {pool.submit(check_rtsp, ip): ip for ip in new_hosts}
                        tl = max(1, deadline - time.time())
                        for f in as_completed(futs, timeout=min(15, tl)):
                            try:
                                rtsp_targets.extend(f.result())
                            except Exception:
                                pass
                    candidate_ips.update(new_hosts)

        # Deduplicate
        rtsp_targets = list(set(rtsp_targets))
        # Prioritize ONVIF devices
        onvif_set = set(onvif_ips)
        rtsp_targets.sort(key=lambda x: (0 if x[0] in onvif_set else 1, x[1]))

        self._report('ports', f'Total: {len(rtsp_targets)} RTSP endpoints to verify', 34)

        if self._stopped(deadline) or not rtsp_targets:
            # Also check HTTP-only devices
            if not rtsp_targets:
                self._report('done',
                              f'No RTSP ports found. Elapsed: {time.time()-t_start:.0f}s', 100)
            return discovered

        # ── Phase 3: RTSP fingerprint (~0.2 s per camera) ───────────
        self._report('fingerprint', 'Identifying camera brands (RTSP Server header)...', 36)
        ip_ports: Dict[str, List[int]] = {}
        for ip, port in rtsp_targets:
            ip_ports.setdefault(ip, []).append(port)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = {}
            for ip, ports in ip_ports.items():
                futs[pool.submit(_rtsp_fingerprint, ip, ports[0])] = ip
            for f in as_completed(futs, timeout=min(10, max(1, deadline - time.time()))):
                try:
                    ip = futs[f]
                    mfr = f.result()
                    if mfr and ip not in self._ip_mfr:
                        self._ip_mfr[ip] = mfr
                except Exception:
                    pass

        for ip, mfr in self._ip_mfr.items():
            if ip in ip_ports:
                logger.info(f"Fingerprint: {ip} => {mfr}")

        self._report('fingerprint', f'{len(self._ip_mfr)} cameras identified', 40)

        if self._stopped(deadline):
            return discovered

        # ── Phase 4: Smart OpenCV verification (~10-30 s) ────────────
        target_list = ', '.join(f"{ip}:{ports[0]}" for ip, ports in ip_ports.items())
        self._report('verify',
                      f'Testing {len(ip_ports)} cameras: [{target_list}]', 42)
        logger.info(f"Phase 4 targets: {target_list}")

        total_cameras = len(ip_ports)
        done_count = [0]
        combo_counter = [0]  # tracks attempts across all cameras

        def probe_camera(ip: str, ports: List[int]) -> List[Dict]:
            """Sequential smart-ordered combo probe for one camera, returns multiple channels/paths."""
            if self._stopped(deadline):
                return []

            mfr = self._ip_mfr.get(ip)
            # Clean manufacturer name (remove 'unknown:' prefix)
            mfr_clean = mfr if mfr and not mfr.startswith('unknown:') else None

            logger.info(f"Probing {ip} (mfr={mfr_clean or '?'}) ports={ports}")
            found: List[Dict] = []
            found_paths: Set[Tuple[int, str]] = set()
            max_per_ip = 12
            # Phase A: Top combos (ordered by manufacturer)
            combos = _ordered_combos(mfr_clean)
            for idx, (user, passwd, path) in enumerate(combos):
                if self._stopped(deadline):
                    break
                for port in ports:
                    if len(found) >= max_per_ip:
                        break
                    url = _build_url(ip, port, path, user, passwd)
                    combo_counter[0] += 1
                    # Update progress every 5 attempts
                    if combo_counter[0] % 5 == 0:
                        pct = 42 + min(int((combo_counter[0] / max(total_cameras * 20, 1)) * 45), 45)
                        self._report('verify',
                                      f'Testing {ip}:{port} combo #{idx+1}...',
                                      min(pct, 88))
                    t0 = time.time()
                    ok = _verify_stream(url, timeout=4)
                    dt = time.time() - t0
                    if ok:
                        logger.info(f"HIT {ip}:{port} combo #{idx+1} in {dt:.2f}s: {user}@{path}")
                        actual_path = path.replace('{user}', user).replace('{pass}', passwd)
                        key = (port, actual_path)
                        if key not in found_paths:
                            found_paths.add(key)
                            found.append(_make_result(ip, port, actual_path, user, passwd, url,
                                                      mfr_clean or ''))
                    elif dt > 3:
                        logger.warning(f"Slow reject ({dt:.1f}s): {ip}:{port} {user}@{path}")
                if len(found) >= max_per_ip:
                    break

            if self._stopped(deadline):
                return found

            # Phase B: Extended combos (if top combos failed)
            ext = _extended_combos(mfr_clean)
            for idx, (user, passwd, path) in enumerate(ext):
                if self._stopped(deadline):
                    break
                for port in ports:
                    if len(found) >= max_per_ip:
                        break
                    url = _build_url(ip, port, path, user, passwd)
                    combo_counter[0] += 1
                    if combo_counter[0] % 10 == 0:
                        pct = 87 + min(int((idx / max(len(ext), 1)) * 8), 8)
                        self._report('verify',
                                      f'Extended probe {ip}:{port} #{idx+1}...',
                                      min(pct, 95))
                    if _verify_stream(url, timeout=3):
                        actual_path = path.replace('{user}', user).replace('{pass}', passwd)
                        key = (port, actual_path)
                        if key not in found_paths:
                            found_paths.add(key)
                            found.append(_make_result(ip, port, actual_path, user, passwd, url,
                                                      mfr_clean or ''))
                if len(found) >= max_per_ip:
                    break

            if found:
                return found

            # If no combo matched, check if endpoint is protected by auth.
            for auth_port in ports:
                auth_probe = _rtsp_probe_auth(ip, auth_port, '/')
                if not auth_probe.get('auth_required'):
                    continue
                actual_path = '/stream'
                return [{
                    'ip_address': ip,
                    'port': auth_port,
                    'protocol': 'rtsp',
                    'path': actual_path,
                    'username': '',
                    'password': '',
                    'stream_url': f'rtsp://{ip}:{auth_port}{actual_path}',
                    'name': f'Camera {ip}',
                    'verified': False,
                    'auth_required': True,
                    'connection_type': 'direct',
                    'manufacturer': mfr_clean or '',
                }]

            logger.info(f"No match for {ip}:{ports} after all combos")
            return []

        # Parallel across different cameras (1 worker per camera)
        workers = min(total_cameras, 5)  # max 5 cameras in parallel
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {}
            for ip, ports in ip_ports.items():
                futs[pool.submit(probe_camera, ip, ports)] = ip

            tl = max(1, deadline - time.time())
            for f in as_completed(futs, timeout=tl):
                done_count[0] += 1
                pct = 90 + int((done_count[0] / max(len(futs), 1)) * 7)
                try:
                    results = f.result() or []
                    if results:
                        for result in results:
                            key = (
                                result.get('ip_address', ''),
                                int(result.get('port', 0)),
                                result.get('path', '/stream') or '/stream',
                            )
                            if key in seen_keys:
                                continue
                            seen_keys.add(key)
                            discovered.append(result)
                            mfr_tag = f" [{result.get('manufacturer','')}]" if result.get('manufacturer') else ''
                            if result.get('verified'):
                                self._report('verify',
                                              f"FOUND{mfr_tag}: {result['stream_url']}",
                                              min(pct, 97))
                            elif result.get('auth_required'):
                                self._report('verify',
                                              f"AUTH REQUIRED{mfr_tag}: {result['ip_address']}:{result['port']}",
                                              min(pct, 97))
                    else:
                        ip_name = futs[f]
                        self._report('verify',
                                      f'No stream on {ip_name}',
                                      min(pct, 97))
                except Exception as e:
                    logger.error(f"probe_camera error: {e}")
                    pass

        elapsed = time.time() - t_start
        verified_count = len([r for r in discovered if r.get('verified')])
        auth_required_count = len([r for r in discovered if r.get('auth_required') and not r.get('verified')])
        self._report('done',
                      f'Done in {elapsed:.0f}s. Found {verified_count} verified and {auth_required_count} auth-required cameras.', 100)
        return discovered


# ── Legacy wrapper ───────────────────────────────────────────────────────

class CameraDiscovery:
    def __init__(self, network="192.168.1.0/24", timeout=2):
        self.network = network
        self.found_cameras: List[Dict] = []

    def scan(self, max_workers=10):
        s = SmartCameraDiscovery()
        self.found_cameras = s.discover()
        return self.found_cameras

    def get_discovered(self):
        return self.found_cameras
