import os
import time
import cv2
import multiprocessing as mp
import numpy as np
import json
import logging
from datetime import datetime, timezone, timedelta 

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# Import Flask app and models
from app import app, db, Camera, Employee, AttendanceLog
from face_core import face_engine

logger = logging.getLogger(__name__)

ASTANA_TZ = timezone(timedelta(hours=5))

def get_astana_time():
    """Returns current time in Astana (UTC+5)"""
    return datetime.now(ASTANA_TZ)

def _get_font(size=20):
    """Get a truetype font, fallback to default if not available"""
    font_paths = [
        '/Library/Fonts/Arial Unicode.ttf',
        '/Library/Fonts/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/System/Library/Fonts/SFNSDisplay.ttf'
    ]
    for p in font_paths:
        try:
            if os.path.exists(p):
                return ImageFont.truetype(p, size=size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def draw_text_unicode(frame, text, position, color=(255, 255, 255), size=20):
    """Draw unicode text onto an OpenCV BGR frame using PIL"""
    x, y = position
    if PIL_AVAILABLE:
        try:
            img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img_pil)
            font = _get_font(size=size)
            rgb = (int(color[2]), int(color[1]), int(color[0]))
            if font:
                draw.text((x, y), text, font=font, fill=rgb)
            else:
                draw.text((x, y), text, fill=rgb)
            frame[:] = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            return
        except Exception:
            pass
    try:
        cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    except Exception:
        pass


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "surveillance.db")


def _load_camera(camera_id):
    """Load camera configuration from database"""
    with app.app_context():
        return Camera.query.get(camera_id)


def _load_known_faces():
    """Load all active employees with face encodings from database"""
    known_faces = []
    try:
        with app.app_context():
            employees = Employee.query.filter_by(active=True).all()
            for emp in employees:
                if emp.face_encoding:
                    try:
                        vec = np.array(json.loads(emp.face_encoding), dtype=np.float32)
                        if vec.shape[0] == 512:
                            known_faces.append((emp.id, emp.name, vec))
                    except Exception as e:
                        logger.warning(f"Failed to load encoding for {emp.name}: {e}")
            logger.info(f"📦 Loaded {len(known_faces)} faces from database")
    except Exception as e:
        logger.error(f"❌ DB Load Error: {e}")
    return known_faces


def _log_attendance(employee_id, camera_id, confidence):
    """Log attendance detection to database using Astana time"""
    try:
        with app.app_context():
            log = AttendanceLog(
                employee_id=employee_id,
                camera_id=camera_id,
                timestamp=get_astana_time(),  # CHANGED: Use Astana time
                confidence=confidence,
                event_type='check-in'
            )
            db.session.add(log)
            db.session.commit()
            db.session.refresh(log)
            logger.info(f"✅ LOGGED: Employee {employee_id} (confidence: {confidence:.3f})")
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Log Error: {e}")


def _detect_and_log_attendance(frame, camera, known_faces, last_seen_cache):
    """Detect faces in frame and log attendance if match found"""
    try:
        faces = face_engine.model.get(frame)
        if not faces:
            return
        
        for face in faces:
            v_cam = face.embedding
            best_match = None
            best_similarity = 0.5  # Confidence threshold
            
            # Compare with known faces using cosine similarity
            for emp_id, emp_name, v_db in known_faces:
                sim = np.dot(v_cam, v_db) / (np.linalg.norm(v_cam) * np.linalg.norm(v_db))
                if sim > best_similarity:
                    best_similarity = sim
                    best_match = (emp_id, emp_name)
            
            # Log if found match
            if best_match:
                emp_id, emp_name = best_match
                # Avoid logging same person multiple times within 1 minute
                now = get_astana_time() # CHANGED: Current time in Astana
                
                # Check cache. Ensure cache stores aware datetimes to avoid "offset-naive vs offset-aware" errors
                if emp_id not in last_seen_cache or (now - last_seen_cache[emp_id]).total_seconds() > 60:
                    _log_attendance(emp_id, camera.id, best_similarity)
                    last_seen_cache[emp_id] = now  # CHANGED: Store Astana time in cache
    except Exception as e:
        logger.error(f"❌ Detection Error: {e}")


def _camera_loop(camera_id, reconnect_delay=2.0, frame_delay=0.1):
    """Main loop for camera stream processing"""
    camera = _load_camera(camera_id)
    if camera is None or not camera.active:
        logger.warning(f"Camera {camera_id} is not active or not found")
        return

    known_faces = _load_known_faces()
    last_seen_cache = {}
    
    url = camera.get_stream_url()
    logger.info(f"🎥 Starting camera {camera.name} (ID: {camera_id})")
    logger.info(f"   Stream URL: {url[:50]}...")
    
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    
    consecutive_failures = 0
    max_consecutive_failures = 10

    while True:
        ret, frame = cap.read()
        if not ret:
            consecutive_failures += 1
            if consecutive_failures > max_consecutive_failures:
                logger.error(f"Camera {camera.name}: Too many consecutive failures, exiting")
                break
            logger.warning(f"Camera {camera.name}: Failed to read frame, reconnecting...")
            time.sleep(reconnect_delay)
            cap.release()
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            continue
        
        consecutive_failures = 0
        _detect_and_log_attendance(frame, camera, known_faces, last_seen_cache)
        time.sleep(frame_delay)


def _spawn_workers(camera_ids, max_workers):
    """Spawn worker processes for each camera"""
    processes = []
    for camera_id in camera_ids[:max_workers]:
        proc = mp.Process(target=_camera_loop, args=(camera_id,), daemon=True)
        proc.start()
        processes.append(proc)

    try:
        while True:
            for idx, proc in enumerate(processes):
                if not proc.is_alive():
                    camera_id = camera_ids[idx]
                    logger.warning(f"Process for camera {camera_id} died, respawning...")
                    new_proc = mp.Process(target=_camera_loop, args=(camera_id,), daemon=True)
                    new_proc.start()
                    processes[idx] = new_proc
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("Terminating all worker processes...")
        for proc in processes:
            proc.terminate()


def _local_camera_loop(camera_source=0, frame_delay=0.1):
    """
    Local camera loop for MacBook testing
    camera_source: 0 for webcam, or RTSP URL string
    """
    known_faces = _load_known_faces()
    last_seen_cache = {}
    last_reload_time = time.time()
    reload_interval = 10  # Reload employee list every 10 seconds
    
    logger.info(f"🎥 Opening camera: {camera_source}")
    cap = cv2.VideoCapture(camera_source)
    
    if not cap.isOpened():
        logger.error(f"❌ Failed to open camera: {camera_source}")
        return
    
    # Set resolution for webcam
    if isinstance(camera_source, int):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    logger.info(f"✅ Camera opened successfully")
    frame_count = 0
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Failed to read frame")
                time.sleep(0.5)
                continue
            
            frame_count += 1
            
            # Reload employee list every N seconds
            current_time = time.time()
            if current_time - last_reload_time > reload_interval:
                known_faces = _load_known_faces()
                last_reload_time = current_time
            
            # Process every 2nd frame to save resources
            if frame_count % 2 == 0:
                try:
                    faces = face_engine.model.get(frame)
                    if faces:
                        for face in faces:
                            v_cam = face.embedding
                            best_match = None
                            best_similarity = 0.5
                            
                            for emp_id, emp_name, v_db in known_faces:
                                sim = np.dot(v_cam, v_db) / (np.linalg.norm(v_cam) * np.linalg.norm(v_db))
                                if sim > best_similarity:
                                    best_similarity = sim
                                    best_match = (emp_id, emp_name)
                            
                            if best_match:
                                emp_id, emp_name = best_match
                                now = get_astana_time() # CHANGED: Current time in Astana
                                
                                if emp_id not in last_seen_cache or (now - last_seen_cache[emp_id]).total_seconds() > 60:
                                    logger.info(f"✅ DETECTED: {emp_name} (confidence: {best_similarity:.3f})")
                                    # Log to database with camera_id=1 (or default camera)
                                    _log_attendance(emp_id, camera_id=1, confidence=best_similarity)
                                    last_seen_cache[emp_id] = now # CHANGED: Update cache
                except Exception as e:
                    logger.error(f"❌ Detection Error: {e}")
            
            time.sleep(frame_delay)
    except KeyboardInterrupt:
        logger.info("⏹️  Camera stream interrupted")
    finally:
        cap.release()
        logger.info("Camera released")


def main():
    """Main entry point for worker process"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load face engine
    face_engine.load()
    logger.info("✅ Face recognition model loaded")
    
    # Check for LOCAL_MODE environment variable
    local_mode = os.getenv('LOCAL_MODE', 'false').lower() in ('true', '1', 'yes')
    
    if local_mode:
        # LOCAL MODE: Use MacBook camera
        logger.info('🎯 Running in LOCAL MODE (MacBook camera)')
        camera_source = int(os.getenv('CAMERA_SOURCE', '0'))
        _local_camera_loop(camera_source=camera_source)
    else:
        # PRODUCTION MODE: Use cameras from database
        with app.app_context():
            cameras = Camera.query.filter_by(active=True).all()
            camera_ids = [cam.id for cam in cameras]

        if not camera_ids:
            logger.error('❌ No active cameras found in database')
            return

        max_workers = int(os.getenv('MAX_WORKERS', '10'))
        max_workers = max(1, min(max_workers, len(camera_ids)))

        logger.info(f'🚀 Starting workers: {max_workers} processes (cameras: {len(camera_ids)})')
        _spawn_workers(camera_ids, max_workers)


if __name__ == '__main__':
    mp.set_start_method('spawn', force=True)
    main()