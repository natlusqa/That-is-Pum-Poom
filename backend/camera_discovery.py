"""
Smart Camera Auto-Discovery Module.

Discovers ALL surveillance devices on the network using multiple methods:
1. ONVIF WS-Discovery (multicast probe — industry standard)
2. ARP table scan (find active hosts)
3. Port scan (RTSP 554/8554, HTTP 80/8080)
4. RTSP stream verification with OpenCV (proves the stream works)
5. Multi-credential brute-force (common defaults)
6. Multi-path brute-force (Hikvision, Dahua, XMEye, Reolink, etc.)
"""

import socket
import struct
import threading
import logging
import subprocess
import re
import time
import ipaddress
import uuid
from typing import List, Dict, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger('surveillance.discovery')

# ── Common camera credentials ────────────────────────────────────────────
DEFAULT_CREDENTIALS = [
    ('admin', ''),
    ('admin', 'admin'),
    ('admin', '12345'),
    ('admin', 'admin123'),
    ('admin', '123456'),
    ('admin', '888888'),
    ('admin', '666666'),
    ('root', ''),
    ('root', 'root'),
    ('root', 'pass'),
    ('user', 'user'),
    ('', ''),
]

# ── Common RTSP paths by manufacturer ────────────────────────────────────
RTSP_PATHS = [
    # Generic / ONVIF
    '/stream',
    '/live',
    '/media/video1',
    '/video1',
    # Hikvision
    '/Streaming/Channels/101',
    '/Streaming/Channels/1',
    '/streaming/channels/101',
    # Dahua
    '/cam/realmonitor?channel=1&subtype=0',
    '/cam/realmonitor?channel=1&subtype=1',
    # XMEye / iCSee / Saphena-style
    '/user={user}_password={pass}_channel=1_stream=0.sdp',
    '/user={user}&password={pass}&channel=1&stream=0.sdp?',
    # Reolink
    '/h264Preview_01_main',
    '/h264Preview_01_sub',
    # AXIS
    '/axis-media/media.amp',
    '/mjpg/video.mjpg',
    # Foscam
    '/videoMain',
    '/videoSub',
    # Amcrest / Dahua v2
    '/live',
    # RTSP generic fallback
    '/0',
    '/1',
    '/11',
    '/12',
]

RTSP_PORTS = [554, 8554, 9200, 8553]
HTTP_PORTS = [80, 8080, 8000, 8888, 81, 9000]

# ── ONVIF WS-Discovery ──────────────────────────────────────────────────

ONVIF_PROBE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
               xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery"
               xmlns:wsdp="http://schemas.xmlsoap.org/ws/2006/02/devprof"
               xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <soap:Header>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
    <wsa:MessageID>urn:uuid:{msg_id}</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
  </soap:Header>
  <soap:Body>
    <wsd:Probe>
      <wsd:Types>dn:NetworkVideoTransmitter</wsd:Types>
    </wsd:Probe>
  </soap:Body>
</soap:Envelope>"""

WS_DISCOVERY_ADDR = '239.255.255.250'
WS_DISCOVERY_PORT = 3702


def _onvif_discover(timeout: float = 4.0) -> List[str]:
    """Send WS-Discovery multicast probe and collect ONVIF device IPs."""
    discovered_ips: Set[str] = set()

    try:
        msg = ONVIF_PROBE_TEMPLATE.format(msg_id=uuid.uuid4()).encode('utf-8')

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)

        # Send to multicast group
        sock.sendto(msg, (WS_DISCOVERY_ADDR, WS_DISCOVERY_PORT))

        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                data, addr = sock.recvfrom(65535)
                ip = addr[0]
                if ip not in ('0.0.0.0', '127.0.0.1'):
                    discovered_ips.add(ip)
                    logger.debug(f"ONVIF WS-Discovery: found device at {ip}")
            except socket.timeout:
                break
            except Exception:
                continue

        sock.close()
    except Exception as e:
        logger.debug(f"ONVIF WS-Discovery error: {e}")

    return list(discovered_ips)


# ── Network utilities ────────────────────────────────────────────────────

def _get_local_networks() -> List[str]:
    """Detect all local network subnets this machine is connected to."""
    networks = set()

    try:
        # Windows: ipconfig
        result = subprocess.run(['ipconfig'], capture_output=True, text=True, timeout=10)
        # Find IPv4 addresses and subnet masks
        lines = result.stdout.split('\n')
        ip_addr = None
        for line in lines:
            if 'IPv4' in line or 'IP Address' in line:
                match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                if match:
                    ip_addr = match.group(1)
            elif 'Subnet Mask' in line or 'Маска подсети' in line:
                match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                if match and ip_addr:
                    mask = match.group(1)
                    try:
                        net = ipaddress.IPv4Network(f"{ip_addr}/{mask}", strict=False)
                        if not net.is_loopback and net.num_addresses <= 65536:
                            networks.add(str(net))
                    except Exception:
                        pass
                    ip_addr = None
    except Exception:
        pass

    if not networks:
        try:
            # Fallback: try linux-style
            result = subprocess.run(['ip', '-4', 'addr'], capture_output=True, text=True, timeout=10)
            for match in re.finditer(r'inet (\d+\.\d+\.\d+\.\d+/\d+)', result.stdout):
                net = ipaddress.IPv4Network(match.group(1), strict=False)
                if not net.is_loopback and net.num_addresses <= 65536:
                    networks.add(str(net))
        except Exception:
            pass

    if not networks:
        # Ultimate fallback
        networks.add('192.168.1.0/24')

    return list(networks)


def _get_arp_hosts() -> Set[str]:
    """Get all known hosts from ARP table."""
    hosts = set()
    try:
        result = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=10)
        for match in re.finditer(r'(\d+\.\d+\.\d+\.\d+)', result.stdout):
            ip = match.group(1)
            if not ip.endswith('.255') and not ip.endswith('.0') and ip != '255.255.255.255':
                hosts.add(ip)
    except Exception:
        pass
    return hosts


def _ping_sweep(network: str, timeout: float = 0.5) -> Set[str]:
    """Fast ping sweep to find active hosts."""
    alive = set()
    try:
        net = ipaddress.IPv4Network(network, strict=False)
        hosts = list(net.hosts())
    except Exception:
        return alive

    def ping_host(ip_str):
        try:
            # Windows ping
            result = subprocess.run(
                ['ping', '-n', '1', '-w', str(int(timeout * 1000)), ip_str],
                capture_output=True, text=True, timeout=timeout + 2
            )
            if result.returncode == 0:
                return ip_str
        except Exception:
            pass
        return None

    # Parallel ping with limited threads
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(ping_host, str(ip)): str(ip) for ip in hosts[:254]}
        for future in as_completed(futures, timeout=30):
            try:
                result = future.result()
                if result:
                    alive.add(result)
            except Exception:
                pass

    return alive


def _check_port(ip: str, port: int, timeout: float = 1.5) -> bool:
    """Check if a TCP port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


# ── RTSP Stream Verification ─────────────────────────────────────────────

def _verify_rtsp_stream(url: str, timeout: int = 8) -> bool:
    """Actually connect to RTSP stream with OpenCV to verify it works."""
    import cv2

    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout * 1000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout * 1000)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            cap.release()
            return False

        ret, frame = cap.read()
        cap.release()

        return ret and frame is not None
    except Exception:
        return False


def _build_rtsp_url(ip: str, port: int, path: str, user: str, passwd: str) -> str:
    """Build RTSP URL with credentials and path template substitution."""
    # Replace {user} and {pass} placeholders in path
    actual_path = path.replace('{user}', user).replace('{pass}', passwd)
    if not actual_path.startswith('/'):
        actual_path = '/' + actual_path

    if user:
        from urllib.parse import quote
        creds = f"{quote(user, safe='')}:{quote(passwd, safe='')}@"
    else:
        creds = ''

    return f"rtsp://{creds}{ip}:{port}{actual_path}"


# ── Main Discovery Engine ────────────────────────────────────────────────

class SmartCameraDiscovery:
    """
    One-click camera auto-discovery.

    Finds and verifies ALL surveillance cameras on all local networks.
    """

    def __init__(self, callback=None):
        self.callback = callback  # Progress callback: fn(stage, message, progress_pct)
        self._stop = False

    def stop(self):
        self._stop = True

    def _report(self, stage: str, message: str, progress: int):
        logger.info(f"[Discovery {progress}%] {stage}: {message}")
        if self.callback:
            try:
                self.callback(stage, message, progress)
            except Exception:
                pass

    def discover(self) -> List[Dict]:
        """
        Run full auto-discovery pipeline.

        Returns list of verified cameras:
        [
            {
                'ip_address': '192.168.1.10',
                'port': 554,
                'protocol': 'rtsp',
                'path': '/Streaming/Channels/101',
                'username': 'admin',
                'password': '',
                'stream_url': 'rtsp://admin:@192.168.1.10:554/Streaming/Channels/101',
                'name': 'Camera 192.168.1.10',
                'verified': True,
            }
        ]
        """
        verified_cameras: List[Dict] = []
        seen_ips: Set[str] = set()
        candidate_ips: Set[str] = set()

        # ── Stage 1: Detect local networks ───────────────────────────
        self._report('network', 'Detecting local networks...', 5)
        networks = _get_local_networks()
        self._report('network', f'Found networks: {", ".join(networks)}', 8)

        if self._stop:
            return verified_cameras

        # ── Stage 2: ONVIF WS-Discovery ──────────────────────────────
        self._report('onvif', 'Sending ONVIF WS-Discovery probe...', 10)
        onvif_ips = _onvif_discover(timeout=4.0)
        candidate_ips.update(onvif_ips)
        self._report('onvif', f'ONVIF found {len(onvif_ips)} devices', 18)

        if self._stop:
            return verified_cameras

        # ── Stage 3: ARP table ────────────────────────────────────────
        self._report('arp', 'Reading ARP table...', 20)
        arp_hosts = _get_arp_hosts()
        candidate_ips.update(arp_hosts)
        self._report('arp', f'ARP table has {len(arp_hosts)} hosts', 25)

        if self._stop:
            return verified_cameras

        # ── Stage 4: Ping sweep (for networks not in ARP) ────────────
        self._report('ping', 'Running ping sweep on local networks...', 28)
        for net in networks:
            if self._stop:
                break
            ping_hosts = _ping_sweep(net, timeout=0.5)
            candidate_ips.update(ping_hosts)
            self._report('ping', f'Ping sweep found {len(ping_hosts)} hosts on {net}', 35)

        # Filter out obviously non-camera IPs (broadcast, gateway typically .1)
        candidate_ips = {
            ip for ip in candidate_ips
            if not ip.endswith('.255') and not ip.endswith('.0')
            and ip != '127.0.0.1'
        }

        self._report('scan', f'Total candidate hosts: {len(candidate_ips)}', 38)

        if self._stop or not candidate_ips:
            return verified_cameras

        # ── Stage 5: Port scan for RTSP/HTTP ports ───────────────────
        self._report('ports', 'Scanning camera ports (554, 8554, 80, 8080)...', 40)
        hosts_with_camera_ports: List[Tuple[str, int]] = []

        def scan_host_ports(ip):
            open_ports = []
            for port in RTSP_PORTS + HTTP_PORTS:
                if self._stop:
                    break
                if _check_port(ip, port, timeout=1.5):
                    open_ports.append((ip, port))
            return open_ports

        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = {executor.submit(scan_host_ports, ip): ip for ip in candidate_ips}
            for future in as_completed(futures, timeout=120):
                try:
                    result = future.result()
                    hosts_with_camera_ports.extend(result)
                except Exception:
                    pass

        # Prioritize: ONVIF devices first, then RTSP ports, then HTTP
        onvif_set = set(onvif_ips)
        hosts_with_camera_ports.sort(key=lambda x: (
            0 if x[0] in onvif_set else 1,
            0 if x[1] in RTSP_PORTS else 1,
            x[1]
        ))

        self._report('ports', f'Found {len(hosts_with_camera_ports)} open camera ports', 55)

        if self._stop or not hosts_with_camera_ports:
            return verified_cameras

        # ── Stage 6: RTSP Stream Verification (the key step) ─────────
        self._report('verify', 'Verifying camera streams (this takes a moment)...', 58)

        total_to_check = len(hosts_with_camera_ports)
        checked = 0

        def try_camera(ip: str, port: int) -> Optional[Dict]:
            """Try all credential + path combinations for one ip:port."""
            if port in HTTP_PORTS:
                # HTTP cameras — just record as found, no RTSP verification
                return {
                    'ip_address': ip,
                    'port': port,
                    'protocol': 'http',
                    'path': '/',
                    'username': '',
                    'password': '',
                    'stream_url': f'http://{ip}:{port}/',
                    'name': f'HTTP Device {ip}:{port}',
                    'verified': False,
                    'connection_type': 'direct',
                }

            # RTSP — try credentials + paths
            for user, passwd in DEFAULT_CREDENTIALS:
                if self._stop:
                    return None
                for path in RTSP_PATHS:
                    if self._stop:
                        return None
                    url = _build_rtsp_url(ip, port, path, user, passwd)
                    if _verify_rtsp_stream(url, timeout=6):
                        return {
                            'ip_address': ip,
                            'port': port,
                            'protocol': 'rtsp',
                            'path': path.replace('{user}', user).replace('{pass}', passwd),
                            'username': user,
                            'password': passwd,
                            'stream_url': url,
                            'name': f'Camera {ip}',
                            'verified': True,
                            'connection_type': 'direct',
                        }
            return None

        # Group by IP to avoid double-checking
        ip_port_map: Dict[str, List[int]] = {}
        for ip, port in hosts_with_camera_ports:
            ip_port_map.setdefault(ip, []).append(port)

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {}
            for ip, ports in ip_port_map.items():
                if ip in seen_ips:
                    continue
                for port in ports:
                    futures[executor.submit(try_camera, ip, port)] = (ip, port)

            for future in as_completed(futures, timeout=300):
                checked += 1
                pct = 58 + int((checked / max(len(futures), 1)) * 37)
                try:
                    result = future.result()
                    if result and result['ip_address'] not in seen_ips:
                        if result.get('verified'):
                            seen_ips.add(result['ip_address'])
                            verified_cameras.append(result)
                            self._report(
                                'verify',
                                f"VERIFIED: {result['stream_url']}",
                                min(pct, 95)
                            )
                except Exception:
                    pass

        self._report('done', f'Discovery complete. Found {len(verified_cameras)} verified cameras.', 100)
        return verified_cameras


# ── Legacy compatibility wrapper ─────────────────────────────────────────

class CameraDiscovery:
    """Legacy discovery class (kept for backward compatibility)."""

    def __init__(self, network: str = "192.168.1.0/24", timeout: int = 2):
        self.network = network
        self.timeout = timeout
        self.found_cameras: List[Dict] = []

    def scan(self, max_workers: int = 10) -> List[Dict]:
        smart = SmartCameraDiscovery()
        results = smart.discover()
        self.found_cameras = results
        return results

    def get_discovered(self) -> List[Dict]:
        return self.found_cameras
