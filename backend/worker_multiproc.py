import os
import cv2
import numpy as np
import sqlite3
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from multiprocessing import Process, Queue, Event
import logging
import signal
from face_core import face_engine
from face_matching import build_face_matrix, match_face

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# --- CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "surveillance.db")

THRESHOLD = float(os.environ.get('FACE_THRESHOLD', '0.5'))
COOLDOWN = int(os.environ.get('FACE_COOLDOWN', '60'))
MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '10'))
FRAME_SKIP = int(os.environ.get('FRAME_SKIP', '2'))
HEADLESS = os.environ.get('HEADLESS', 'False').lower() == 'true'
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost:5002')
HEARTBEAT_INTERVAL = 30  # seconds

# --- TIMEZONE CONFIGURATION ---
ASTANA_TZ = timezone(timedelta(hours=5))


def get_astana_time():
    """Returns current time in Astana (UTC+5)"""
    return datetime.now(ASTANA_TZ)


class CameraWorkerProcess(Process):
    """
    Process for handling a single camera.
    Gets camera config + all known employees in memory.
    """

    def __init__(self, camera_id, camera_url, known_face_matrix, known_ids, known_names,
                 log_queue, detection_queue, shutdown_event):
        super().__init__()
        self.camera_id = camera_id
        self.camera_url = camera_url
        self.known_face_matrix = known_face_matrix
        self.known_ids = known_ids
        self.known_names = known_names
        self.log_queue = log_queue
        self.detection_queue = detection_queue
        self.shutdown_event = shutdown_event

        self.last_seen = {}
        self.frame_count = 0
        self.face_engine = None
        self.last_heartbeat = 0
        self.logger = logging.getLogger(f"Camera-{camera_id}")

    def run(self):
        """Main video processing loop"""
        try:
            self.logger.info(f"Starting camera worker (URL: {str(self.camera_url)[:50]}...)")
            self.face_engine = face_engine.__class__()
            self.face_engine.load()

            cap = self._connect_camera()
            if cap is None:
                self.logger.error(f"Failed to connect to camera {self.camera_id}")
                return

            while not self.shutdown_event.is_set():
                ret, frame = cap.read()

                if not ret:
                    self.logger.warning("Frame read failed, reconnecting...")
                    cap.release()
                    time.sleep(2)
                    cap = self._connect_camera()
                    if cap is None:
                        break
                    continue

                self.frame_count += 1

                if self.frame_count % FRAME_SKIP != 0:
                    continue

                self._process_frame(frame)
                self._send_heartbeat()

            cap.release()
            self.logger.info(f"Camera {self.camera_id} worker stopped")

        except Exception as e:
            self.logger.error(f"Worker exception: {e}", exc_info=True)
        finally:
            if 'cap' in locals() and cap is not None:
                cap.release()

    def _connect_camera(self, retries=3):
        """Connect to camera with retry logic"""
        for attempt in range(retries):
            try:
                cap = cv2.VideoCapture(self.camera_url)
                if cap.isOpened():
                    self.logger.info(f"Connected to camera {self.camera_id}")
                    return cap
            except Exception as e:
                self.logger.debug(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(2)
        return None

    def _send_heartbeat(self):
        """Periodically update camera heartbeat via API"""
        now = time.time()
        if now - self.last_heartbeat < HEARTBEAT_INTERVAL:
            return
        self.last_heartbeat = now
        try:
            requests.post(
                f"{API_BASE_URL}/api/cameras/{self.camera_id}/heartbeat",
                timeout=5
            )
        except Exception:
            pass  # Non-critical

    def _process_frame(self, frame):
        """Process one frame: detection + recognition"""
        try:
            all_faces = self.face_engine.get_all_faces(frame)
            if not all_faces:
                return

            detection_data = []

            # Process top 5 faces
            for face_info in all_faces[:5]:
                match_result = self._recognize_face(face_info)
                detection_data.append({
                    'bbox': face_info['bbox'],
                    'name': match_result[0] if match_result else 'Unknown',
                    'confidence': match_result[1] if match_result else 0.0,
                    'det_score': face_info['det_score'],
                })

            # Publish detection events for bounding box overlay
            if detection_data and self.detection_queue is not None:
                try:
                    event_data = {
                        'camera_id': self.camera_id,
                        'faces': detection_data,
                        'frame_width': frame.shape[1],
                        'frame_height': frame.shape[0],
                        'timestamp': time.time()
                    }
                    self.detection_queue.put_nowait(event_data)

                    # Also send to Flask server for WebSocket broadcast
                    try:
                        requests.post(
                            f'{API_BASE_URL}/api/detections/publish',
                            json=event_data,
                            timeout=1
                        )
                    except Exception:
                        pass  # Non-critical, just skip if server is unavailable
                except Exception:
                    pass  # Queue full, skip

        except Exception as e:
            self.logger.error(f"Frame processing error: {e}")

    def _recognize_face(self, face_info):
        """Recognize a single face using vectorized matching"""
        v_cam = face_info['embedding']

        emp_id, name, sim = match_face(
            v_cam, self.known_face_matrix, self.known_ids, self.known_names,
            threshold=THRESHOLD
        )

        if emp_id is not None:
            now = get_astana_time()

            if emp_id not in self.last_seen or \
               (now - self.last_seen[emp_id]).total_seconds() >= COOLDOWN:

                log_entry = {
                    'employee_id': emp_id,
                    'camera_id': self.camera_id,
                    'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
                    'confidence': float(sim),
                    'event_type': 'check-in'
                }

                self.log_queue.put(log_entry)
                self.last_seen[emp_id] = now
                self.logger.info(f"{name} detected (conf: {sim:.3f}) - Logged at {log_entry['timestamp']}")

            return name, float(sim)

        return None


class AttendanceLogger(Process):
    """
    Dedicated process for writing attendance logs to the database.
    Prevents "database is locked" errors from concurrent writes.
    Uses a persistent connection and batch inserts.
    """
    def __init__(self, log_queue, shutdown_event):
        super().__init__()
        self.log_queue = log_queue
        self.shutdown_event = shutdown_event
        self.logger = logging.getLogger("Logger")

    def run(self):
        self.logger.info("Attendance Logger started")
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        batch = []
        last_flush = time.time()

        while not self.shutdown_event.is_set():
            try:
                try:
                    log_entry = self.log_queue.get(timeout=1)
                    batch.append(log_entry)
                except Exception:
                    pass

                # Flush batch every 5 entries or every 2 seconds
                if len(batch) >= 5 or (batch and time.time() - last_flush > 2):
                    self._flush_batch(conn, batch)
                    batch.clear()
                    last_flush = time.time()

            except Exception as e:
                self.logger.error(f"Logger error: {e}")

        # Flush remaining on shutdown
        if batch:
            self._flush_batch(conn, batch)
        conn.close()
        self.logger.info("Logger stopped")

    def _flush_batch(self, conn, batch):
        """Write a batch of log entries to the database"""
        try:
            cursor = conn.cursor()
            cursor.executemany(
                """INSERT INTO attendance_log
                   (employee_id, camera_id, timestamp, confidence, event_type)
                   VALUES (?, ?, ?, ?, ?)""",
                [(
                    e['employee_id'], e['camera_id'],
                    e['timestamp'], e['confidence'], e['event_type']
                ) for e in batch]
            )
            conn.commit()
        except Exception as e:
            self.logger.error(f"Batch DB write failed: {e}")


class MultiCameraOrchestrator:
    """Main process: manages worker processes and configuration."""
    def __init__(self):
        self.workers = {}  # camera_id -> (worker, camera_url)
        self.log_queue = Queue()
        self.detection_queue = Queue(maxsize=100)
        self.shutdown_event = Event()
        self.logger_process = None
        self.logger = logging.getLogger("Orchestrator")

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        self.logger.info("Shutdown signal received, stopping workers...")
        self.shutdown_event.set()

    def load_cameras_from_db(self):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10)
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, protocol, ip_address, port, username, password, path, connection_type, dvr_url
                   FROM camera WHERE active=1 AND face_recognition_enabled=1"""
            )
            cameras = []
            for row in cursor.fetchall():
                cam_id, protocol, ip, port, user, pwd, path, conn_type, dvr_url = row

                if conn_type == 'dvr' and dvr_url:
                    cameras.append((cam_id, dvr_url))
                    continue

                if protocol == 'local':
                    try:
                        url = int(path) if path else 0
                    except Exception:
                        url = path or 0
                    cameras.append((cam_id, url))
                    continue
                if protocol == 'file':
                    cameras.append((cam_id, path))
                    continue

                creds = f"{user}:{pwd}@" if user and pwd else (f"{user}@" if user else "")
                url = f"{protocol}://{creds}{ip}:{port}{path}"
                cameras.append((cam_id, url))
            conn.close()
            return cameras
        except Exception as e:
            self.logger.error(f"Failed to load cameras: {e}")
            return []

    def load_known_faces(self):
        """Load known faces and pre-build normalized matrix for vectorized matching"""
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10)
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, face_encoding FROM employee WHERE active=1")
            raw_faces = []
            for emp_id, name, encoding in cursor.fetchall():
                if encoding:
                    try:
                        vec = np.array(json.loads(encoding), dtype=np.float32)
                        if vec.shape[0] == 512:
                            raw_faces.append((emp_id, name, vec))
                    except Exception:
                        pass
            conn.close()

            matrix, ids, names = build_face_matrix(raw_faces)
            self.logger.info(f"Loaded {len(ids)} known faces (matrix shape: {matrix.shape})")
            return matrix, ids, names
        except Exception as e:
            self.logger.error(f"Failed to load known faces: {e}")
            return np.empty((0, 512), dtype=np.float32), [], []

    def _spawn_worker(self, camera_id, camera_url, face_matrix, face_ids, face_names):
        """Create and start a camera worker process"""
        worker = CameraWorkerProcess(
            camera_id, camera_url, face_matrix, face_ids, face_names,
            self.log_queue, self.detection_queue, self.shutdown_event
        )
        worker.start()
        self.workers[camera_id] = (worker, camera_url)
        self.logger.info(f"Worker started for camera {camera_id}")
        return worker

    def run(self):
        try:
            self.logger.info("Starting Multi-Camera Orchestrator")
            face_engine.load()

            cameras = self.load_cameras_from_db()
            face_matrix, face_ids, face_names = self.load_known_faces()

            if not cameras:
                self.logger.warning("No cameras configured. Exiting.")
                return
            if len(face_ids) == 0:
                self.logger.warning("No known faces loaded. System will detect but not recognize.")

            # Start attendance logger process
            self.logger_process = AttendanceLogger(self.log_queue, self.shutdown_event)
            self.logger_process.start()

            num_workers = min(len(cameras), MAX_WORKERS)
            self.logger.info(f"Starting {num_workers} camera workers")

            for camera_id, camera_url in cameras[:num_workers]:
                self._spawn_worker(camera_id, camera_url, face_matrix, face_ids, face_names)

            # Monitor loop with auto-respawn
            while not self.shutdown_event.is_set():
                for cam_id, (worker, cam_url) in list(self.workers.items()):
                    if not worker.is_alive() and not self.shutdown_event.is_set():
                        self.logger.warning(f"Worker for camera {cam_id} died — respawning...")
                        self._spawn_worker(cam_id, cam_url, face_matrix, face_ids, face_names)
                time.sleep(5)

            self.logger.info("Waiting for workers to finish...")
            all_processes = [w for w, _ in self.workers.values()]
            if self.logger_process:
                all_processes.append(self.logger_process)

            for proc in all_processes:
                proc.join(timeout=5)
                if proc.is_alive():
                    self.logger.warning(f"Force terminating {proc.name}")
                    proc.terminate()

            self.logger.info("All workers stopped. Goodbye!")

        except Exception as e:
            self.logger.error(f"Orchestrator error: {e}", exc_info=True)
        finally:
            self.shutdown_event.set()
            for cam_id, (worker, _) in self.workers.items():
                if worker.is_alive():
                    worker.terminate()
            if self.logger_process and self.logger_process.is_alive():
                self.logger_process.terminate()


def main():
    orchestrator = MultiCameraOrchestrator()
    orchestrator.run()


if __name__ == "__main__":
    main()
