"""Camera discovery module for automatic network scanning."""

import socket
import threading
import logging
from typing import List, Dict
import subprocess
import re

logger = logging.getLogger('surveillance')


class CameraDiscovery:
    """Automatic camera discovery in local network."""

    def __init__(self, network: str = "192.168.1.0/24", timeout: int = 2):
        """
        Initialize discovery scanner.

        Args:
            network: CIDR network to scan (default: 192.168.1.0/24)
            timeout: Connection timeout in seconds
        """
        self.network = network
        self.timeout = timeout
        self.found_cameras: List[Dict] = []
        self.rtsp_ports = [554, 8554, 9200]
        self.http_ports = [80, 8080, 8000]
        self.rtsp_paths = [
            '/stream',
            '/streaming/channels/101',
            '/streaming/channels/1',
            '/Streaming/Channels/101',
            '/Streaming/Channels/1',
            '/user=admin_password=_channel=1_stream=0.sdp',
            '/h264/ch1/main/av_stream',
            '/rtsp_tunnel',
        ]

    def _parse_network(self) -> List[str]:
        """Parse CIDR notation and return list of IPs."""
        try:
            import ipaddress
            network = ipaddress.ip_network(self.network, strict=False)
            return [str(ip) for ip in network.hosts()]
        except:
            logger.warning(f"Invalid network {self.network}, using default")
            # Fallback: scan 192.168.1.1-254
            return [f"192.168.1.{i}" for i in range(1, 255)]

    def _check_rtsp(self, ip: str, port: int) -> List[Dict]:
        """Check RTSP ports and paths."""
        cameras = []

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((ip, port))
            sock.close()

            if result == 0:
                # Port is open, try common paths
                for path in self.rtsp_paths:
                    camera_info = {
                        'ip_address': ip,
                        'port': port,
                        'protocol': 'rtsp',
                        'path': path,
                        'username': 'admin',
                        'password': '',
                        'stream_url': f'rtsp://admin:@{ip}:{port}{path}',
                        'connection_type': 'direct',
                    }
                    cameras.append(camera_info)
        except Exception as e:
            logger.debug(f"RTSP check failed for {ip}:{port}: {e}")

        return cameras

    def _check_http(self, ip: str, port: int) -> List[Dict]:
        """Check HTTP ports for MJPEG streams."""
        cameras = []

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((ip, port))
            sock.close()

            if result == 0:
                # Port is open
                camera_info = {
                    'ip_address': ip,
                    'port': port,
                    'protocol': 'http',
                    'path': '/snapshot.jpg',
                    'username': 'admin',
                    'password': '',
                    'stream_url': f'http://admin:@{ip}:{port}/snapshot.jpg',
                    'connection_type': 'direct',
                }
                cameras.append(camera_info)
        except Exception as e:
            logger.debug(f"HTTP check failed for {ip}:{port}: {e}")

        return cameras

    def _scan_host(self, ip: str) -> List[Dict]:
        """Scan single host for cameras."""
        cameras = []

        # Check RTSP ports
        for port in self.rtsp_ports:
            cameras.extend(self._check_rtsp(ip, port))

        # Check HTTP ports
        for port in self.http_ports:
            cameras.extend(self._check_http(ip, port))

        return cameras

    def scan(self, max_workers: int = 10) -> List[Dict]:
        """
        Scan network for cameras.

        Args:
            max_workers: Max concurrent threads

        Returns:
            List of discovered cameras with connection info
        """
        ips = self._parse_network()
        self.found_cameras = []

        logger.info(f"Starting camera discovery scan on {self.network}")

        # Use threading for parallel scanning
        threads = []
        results_lock = threading.Lock()
        results = []

        def scan_worker():
            while len(ips) > 0:
                try:
                    ip = ips.pop(0)
                    cameras = self._scan_host(ip)
                    if cameras:
                        with results_lock:
                            results.extend(cameras)
                        logger.debug(f"Found {len(cameras)} camera configs at {ip}")
                except IndexError:
                    break

        # Create worker threads
        for _ in range(min(max_workers, len(ips))):
            t = threading.Thread(target=scan_worker, daemon=True)
            t.start()
            threads.append(t)

        # Wait for all threads
        for t in threads:
            t.join()

        self.found_cameras = results
        logger.info(f"Discovery scan complete. Found {len(results)} camera stream endpoints")

        return results

    def get_discovered(self) -> List[Dict]:
        """Get list of discovered cameras."""
        return self.found_cameras
