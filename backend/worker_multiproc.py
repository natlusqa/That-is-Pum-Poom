"""
Optimized Camera Worker — Threaded architecture with shared model.

Key optimizations vs original:
1. Threading (not multiprocessing) — all cameras share one model instance (~300MB RAM once)
2. Threaded frame grabber — always grabs latest frame, no RTSP buffer lag
3. Frame resize before inference — 2304x1296 → 960xN saves ~5x compute
4. Non-blocking detection publishing — fire-and-forget HTTP posts
5. Batch attendance logging — groups API calls every 2 seconds
6. API-based data — works with PostgreSQL backend (not SQLite)
"""

import os
import cv2
import numpy as np
import json
import time
import requests
import threading
import logging
import signal
import sys
from datetime import datetime, timezone, timedelta
from queue import Queue, Empty
from face_core import face_engine
from face_matching import build_face_matrix, match_face

# --- LOGGING ---
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s'
)
logger = logging.getLogger('worker')

# --- CONFIG ---
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost:5002')
INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
THRESHOLD = float(os.environ.get('FACE_THRESHOLD', '0.5'))
COOLDOWN = int(os.environ.get('FACE_COOLDOWN', '60'))
MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '10'))
FRAME_SKIP = int(os.environ.get('FRAME_SKIP', '3'))
PROCESS_WIDTH = int(os.environ.get('PROCESS_WIDTH', '960'))  # resize before inference
HEARTBEAT_INTERVAL = 30
FACE_RELOAD_INTERVAL = int(os.environ.get('FACE_RELOAD_INTERVAL', '30'))

# Timezone
ASTANA_TZ = timezone(timedelta(hours=5))


def get_astana_time():
    return datetime.now(ASTANA_TZ)


def api_headers():
    return {'X-Internal-Key': INTERNAL_API_KEY}


# --- THREADED FRAME GRABBER ---

class FrameGrabber:
    """
    Continuously reads frames in a background thread.
    Always returns the latest frame — no buffering delay.
    """

    def __init__(self, url, camera_name=''):
        self.url = url
        self.camera_name = camera_name
        self.frame = None
        self.ret = False
        self.stopped = False
        self.lock = threading.Lock()
        self.cap = None
        self.fps = 0
        self._frame_count = 0
        self._fps_time = time.time()

    def start(self):
        self.cap = self._create_capture()
        if self.cap is None or not self.cap.isOpened():
            logger.error(f"[{self.camera_name}] Failed to open stream: {str(self.url)[:60]}")
            return None
        # Read first frame
        self.ret, self.frame = self.cap.read()
        t = threading.Thread(target=self._update, daemon=True, name=f"grab-{self.camera_name}")
        t.start()
        logger.info(f"[{self.camera_name}] Frame grabber started")
        return self

    def _create_capture(self):
        """Create optimized VideoCapture"""
        cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        if cap.isOpened():
            # Minimize buffer — always get latest frame
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Use TCP for reliable RTSP (less frame corruption)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000)
        return cap

    def _update(self):
        """Continuously grab frames in background"""
        consecutive_fails = 0
        while not self.stopped:
            if self.cap is None or not self.cap.isOpened():
                logger.warning(f"[{self.camera_name}] Stream lost, reconnecting...")
                time.sleep(2)
                self.cap = self._create_capture()
                if self.cap is None or not self.cap.isOpened():
                    consecutive_fails += 1
                    if consecutive_fails > 10:
                        logger.error(f"[{self.camera_name}] Too many reconnect failures, stopping")
                        self.stopped = True
                        break
                    continue
                consecutive_fails = 0

            ret, frame = self.cap.read()
            if not ret:
                consecutive_fails += 1
                if consecutive_fails > 30:
                    # Force reconnect
                    logger.warning(f"[{self.camera_name}] {consecutive_fails} consecutive failures, forcing reconnect")
                    self.cap.release()
                    self.cap = None
                    consecutive_fails = 0
                continue

            consecutive_fails = 0
            with self.lock:
                self.ret = True
                self.frame = frame
            self._frame_count += 1

            # Calculate FPS every 5 seconds
            now = time.time()
            if now - self._fps_time >= 5.0:
                self.fps = self._frame_count / (now - self._fps_time)
                self._frame_count = 0
                self._fps_time = now

    def read(self):
        """Get latest frame (non-blocking)"""
        with self.lock:
            return self.ret, self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.stopped = True
        if self.cap:
            self.cap.release()


# --- CAMERA WORKER THREAD ---

class CameraWorker(threading.Thread):
    """
    Per-camera worker thread. Uses shared face_engine (no model duplication).
    """

    def __init__(self, camera_id, camera_url, camera_name,
                 face_data, log_queue, shutdown_event):
        super().__init__(daemon=True, name=f"cam-{camera_id}")
        self.camera_id = camera_id
        self.camera_url = camera_url
        self.camera_name = camera_name
        self.face_data = face_data  # shared dict with lock
        self.log_queue = log_queue
        self.shutdown_event = shutdown_event
        self.last_seen = {}
        self.frame_count = 0
        self.last_heartbeat = 0
        self.log = logging.getLogger(f"cam-{camera_id}")

    def run(self):
        self.log.info(f"Starting worker for '{self.camera_name}' ({str(self.camera_url)[:50]}...)")

        grabber = FrameGrabber(self.camera_url, self.camera_name)
        if grabber.start() is None:
            self.log.error(f"Cannot connect to camera '{self.camera_name}', worker exiting")
            return

        try:
            while not self.shutdown_event.is_set():
                ret, frame = grabber.read()
                if not ret or frame is None:
                    time.sleep(0.1)
                    continue

                self.frame_count += 1
                if self.frame_count % FRAME_SKIP != 0:
                    time.sleep(0.01)  # yield CPU
                    continue

                self._process_frame(frame)
                self._send_heartbeat()

        except Exception as e:
            self.log.error(f"Worker exception: {e}", exc_info=True)
        finally:
            grabber.stop()
            self.log.info(f"Worker stopped for '{self.camera_name}'")

    def _process_frame(self, frame):
        """Resize frame, detect faces, match against known faces"""
        try:
            # Resize for faster inference
            h, w = frame.shape[:2]
            if w > PROCESS_WIDTH:
                scale = PROCESS_WIDTH / w
                frame_small = cv2.resize(frame, None, fx=scale, fy=scale,
                                         interpolation=cv2.INTER_LINEAR)
            else:
                frame_small = frame
                scale = 1.0

            all_faces = face_engine.get_all_faces(frame_small)
            if not all_faces:
                return

            detection_data = []
            face_data = self.face_data  # thread-safe read

            for face_info in all_faces[:5]:
                match_result = self._recognize_face(face_info, face_data)

                # Scale bbox back to original coordinates
                bbox = face_info['bbox']
                if scale != 1.0:
                    bbox = [int(b / scale) for b in bbox]

                detection_data.append({
                    'bbox': bbox,
                    'name': match_result[0] if match_result else 'Unknown',
                    'confidence': match_result[1] if match_result else 0.0,
                    'det_score': face_info['det_score'],
                })

            # Publish detection events (non-blocking)
            if detection_data:
                self._publish_detections(detection_data, w, h)

        except Exception as e:
            self.log.error(f"Frame processing error: {e}")

    def _recognize_face(self, face_info, face_data):
        """Match face against known database"""
        v_cam = face_info['embedding']
        matrix = face_data.get('matrix')
        ids = face_data.get('ids', [])
        names = face_data.get('names', [])

        if matrix is None or matrix.shape[0] == 0:
            return None

        emp_id, name, sim = match_face(v_cam, matrix, ids, names, threshold=THRESHOLD)

        if emp_id is not None:
            now = get_astana_time()
            if emp_id not in self.last_seen or \
               (now - self.last_seen[emp_id]).total_seconds() >= COOLDOWN:

                log_entry = {
                    'employee_id': emp_id,
                    'camera_id': self.camera_id,
                    'timestamp': now.isoformat(),
                    'confidence': float(sim),
                    'event_type': 'check-in'
                }
                self.log_queue.put(log_entry)
                self.last_seen[emp_id] = now
                self.log.info(f"{name} detected (conf: {sim:.3f})")

            return name, float(sim)
        return None

    def _publish_detections(self, detection_data, frame_w, frame_h):
        """Send detection events to backend for WebSocket broadcast (non-blocking)"""
        def _send():
            try:
                requests.post(
                    f'{API_BASE_URL}/api/detections/publish',
                    json={
                        'camera_id': self.camera_id,
                        'faces': detection_data,
                        'frame_width': frame_w,
                        'frame_height': frame_h,
                        'timestamp': time.time()
                    },
                    headers=api_headers(),
                    timeout=2
                )
            except Exception:
                pass
        threading.Thread(target=_send, daemon=True).start()

    def _send_heartbeat(self):
        now = time.time()
        if now - self.last_heartbeat < HEARTBEAT_INTERVAL:
            return
        self.last_heartbeat = now

        def _beat():
            try:
                requests.post(
                    f"{API_BASE_URL}/api/cameras/{self.camera_id}/heartbeat",
                    headers=api_headers(),
                    timeout=5
                )
            except Exception:
                pass
        threading.Thread(target=_beat, daemon=True).start()


# --- ATTENDANCE LOGGER THREAD ---

class AttendanceLogger(threading.Thread):
    """Batches attendance logs and sends to API every 2 seconds"""

    def __init__(self, log_queue, shutdown_event):
        super().__init__(daemon=True, name="attendance-logger")
        self.log_queue = log_queue
        self.shutdown_event = shutdown_event
        self.log = logging.getLogger("logger")

    def run(self):
        self.log.info("Attendance logger started")
        batch = []
        last_flush = time.time()

        while not self.shutdown_event.is_set():
            try:
                entry = self.log_queue.get(timeout=1)
                batch.append(entry)
            except Empty:
                pass

            # Flush every 5 entries or every 2 seconds
            if len(batch) >= 5 or (batch and time.time() - last_flush > 2):
                self._flush(batch)
                batch = []
                last_flush = time.time()

        # Final flush
        if batch:
            self._flush(batch)
        self.log.info("Attendance logger stopped")

    def _flush(self, batch):
        try:
            resp = requests.post(
                f"{API_BASE_URL}/api/internal/worker/attendance",
                json=batch,
                headers=api_headers(),
                timeout=10
            )
            if resp.status_code == 200:
                self.log.debug(f"Flushed {len(batch)} attendance records")
            else:
                self.log.error(f"Attendance API error: {resp.status_code} {resp.text}")
        except Exception as e:
            self.log.error(f"Attendance flush failed: {e}")


# --- ORCHESTRATOR ---

class WorkerOrchestrator:
    """
    Main controller: loads config from API, manages camera threads.
    Single model instance shared across all threads.
    """

    def __init__(self):
        self.workers = {}
        self.log_queue = Queue()
        self.shutdown_event = threading.Event()
        self.face_data = {'matrix': np.empty((0, 512), dtype=np.float32), 'ids': [], 'names': []}
        self.log = logging.getLogger("orchestrator")

    def _signal_handler(self, signum, frame):
        self.log.info("Shutdown signal received")
        self.shutdown_event.set()

    def load_cameras(self):
        """Load camera list from backend API"""
        try:
            resp = requests.get(
                f"{API_BASE_URL}/api/internal/worker/cameras",
                headers=api_headers(),
                timeout=10
            )
            if resp.status_code != 200:
                self.log.error(f"Failed to load cameras: HTTP {resp.status_code}")
                return []
            return resp.json()
        except Exception as e:
            self.log.error(f"Failed to load cameras: {e}")
            return []

    def load_faces(self):
        """Load known face embeddings from backend API"""
        try:
            resp = requests.get(
                f"{API_BASE_URL}/api/internal/worker/faces",
                headers=api_headers(),
                timeout=10
            )
            if resp.status_code != 200:
                self.log.error(f"Failed to load faces: HTTP {resp.status_code}")
                return

            faces_json = resp.json()
            raw_faces = []
            for f in faces_json:
                try:
                    vec = np.array(json.loads(f['encoding']), dtype=np.float32)
                    if vec.shape[0] == 512:
                        raw_faces.append((f['id'], f['name'], vec))
                except Exception:
                    pass

            matrix, ids, names = build_face_matrix(raw_faces)
            self.face_data = {'matrix': matrix, 'ids': ids, 'names': names}
            self.log.info(f"Loaded {len(ids)} known faces")
        except Exception as e:
            self.log.error(f"Failed to load faces: {e}")

    def _face_reload_loop(self):
        """Periodically reload face database"""
        while not self.shutdown_event.is_set():
            time.sleep(FACE_RELOAD_INTERVAL)
            if self.shutdown_event.is_set():
                break
            self.load_faces()

    def run(self):
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.log.info("=" * 60)
        self.log.info("  Surveillance AI Worker — Starting")
        self.log.info(f"  API: {API_BASE_URL}")
        self.log.info(f"  Threshold: {THRESHOLD}, Cooldown: {COOLDOWN}s, FrameSkip: {FRAME_SKIP}")
        self.log.info(f"  Process Width: {PROCESS_WIDTH}px")
        self.log.info("=" * 60)

        # Load face recognition model (once, shared by all threads)
        self.log.info("Loading face recognition model...")
        t0 = time.time()
        face_engine.load()
        self.log.info(f"Model loaded in {time.time() - t0:.1f}s")

        # Wait for backend to be ready
        self._wait_for_backend()

        # Load cameras from API
        cameras = self.load_cameras()
        if not cameras:
            self.log.warning("No cameras with face recognition enabled. Exiting.")
            return

        # Load known faces
        self.load_faces()

        # Start attendance logger
        att_logger = AttendanceLogger(self.log_queue, self.shutdown_event)
        att_logger.start()

        # Start face reload thread
        face_reloader = threading.Thread(target=self._face_reload_loop, daemon=True, name="face-reload")
        face_reloader.start()

        # Start camera workers
        num_workers = min(len(cameras), MAX_WORKERS)
        self.log.info(f"Starting {num_workers} camera workers")

        for cam in cameras[:num_workers]:
            worker = CameraWorker(
                camera_id=cam['id'],
                camera_url=cam['stream_url'],
                camera_name=cam['name'],
                face_data=self.face_data,
                log_queue=self.log_queue,
                shutdown_event=self.shutdown_event
            )
            worker.start()
            self.workers[cam['id']] = worker

        # Monitor loop
        self.log.info("All workers started. Monitoring...")
        try:
            while not self.shutdown_event.is_set():
                self.shutdown_event.wait(timeout=5)

                # Check worker health
                for cam_id, worker in list(self.workers.items()):
                    if not worker.is_alive() and not self.shutdown_event.is_set():
                        self.log.warning(f"Worker for camera {cam_id} died, respawning...")
                        cam_info = next((c for c in cameras if c['id'] == cam_id), None)
                        if cam_info:
                            new_worker = CameraWorker(
                                camera_id=cam_info['id'],
                                camera_url=cam_info['stream_url'],
                                camera_name=cam_info['name'],
                                face_data=self.face_data,
                                log_queue=self.log_queue,
                                shutdown_event=self.shutdown_event
                            )
                            new_worker.start()
                            self.workers[cam_id] = new_worker
        except KeyboardInterrupt:
            self.log.info("Keyboard interrupt received")
            self.shutdown_event.set()

        self.log.info("Shutting down workers...")
        self.shutdown_event.set()

        # Wait for threads to finish
        for worker in self.workers.values():
            worker.join(timeout=5)

        self.log.info("All workers stopped. Goodbye!")

    def _wait_for_backend(self, max_wait=60):
        """Wait for backend API to be available"""
        start = time.time()
        while time.time() - start < max_wait:
            try:
                resp = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
                if resp.status_code == 200:
                    self.log.info("Backend API is ready")
                    return
            except Exception:
                pass
            self.log.info("Waiting for backend API...")
            time.sleep(3)
        self.log.warning("Backend API not responding, proceeding anyway")


def main():
    orchestrator = WorkerOrchestrator()
    orchestrator.run()


if __name__ == "__main__":
    main()
