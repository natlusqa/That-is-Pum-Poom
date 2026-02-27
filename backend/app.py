import os
import logging
import json
import base64
import csv
import time
from datetime import datetime, timezone, timedelta
from functools import wraps
from io import StringIO, BytesIO
from urllib.parse import quote

import numpy as np
import jwt
from flask import Flask, request, jsonify, send_from_directory, send_file, Response, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from sqlalchemy import func, text
from werkzeug.security import generate_password_hash, check_password_hash
from dateutil import parser as date_parser
from collections import defaultdict, deque

from face_core import face_engine
from camera_discovery import SmartCameraDiscovery

# --- LOGGING ---
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger('surveillance')

# --- APP FACTORY ---
app = Flask(__name__, static_folder='../frontend/dist', static_url_path='')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- IN-MEMORY DETECTION EVENT STORE ---
# Store last N detection events per camera for late joiners
MAX_DETECTIONS_PER_CAMERA = 50
detection_events = defaultdict(lambda: deque(maxlen=MAX_DETECTIONS_PER_CAMERA))


def utc_now():
    """Timezone-aware UTC datetime (replaces deprecated utcnow())"""
    return datetime.now(timezone.utc)


# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "surveillance.db")

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-fallback-change-in-prod')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', f'sqlite:///{DB_PATH}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
}
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'instance', 'face_encodings')
app.config['RECORDINGS_FOLDER'] = os.path.join(BASE_DIR, 'instance', 'recordings')
app.config['SNAPSHOTS_FOLDER'] = os.path.join(BASE_DIR, 'instance', 'snapshots')

db = SQLAlchemy(app)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RECORDINGS_FOLDER'], exist_ok=True)
os.makedirs(app.config['SNAPSHOTS_FOLDER'], exist_ok=True)

# --- DATABASE MODELS ---


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Camera(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    connection_type = db.Column(db.String(20), default='direct')

    # Direct connection fields
    ip_address = db.Column(db.String(100))
    port = db.Column(db.Integer, default=554)
    username = db.Column(db.String(50))
    password = db.Column(db.String(50))
    protocol = db.Column(db.String(10), default='rtsp')
    path = db.Column(db.String(200), default='/stream')

    # DVR connection fields
    dvr_url = db.Column(db.String(500))

    location = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True, index=True)
    face_recognition_enabled = db.Column(db.Boolean, default=False)
    last_heartbeat = db.Column(db.DateTime, nullable=True)

    def get_stream_url(self):
        if self.connection_type == 'dvr' and self.dvr_url:
            return self.dvr_url

        creds = ""
        if self.username:
            creds = self.username
            creds = f"{creds}:{self.password or ''}"
            creds = f"{creds}@"

        path = self.path or ""
        if self.protocol == 'rtsp' and 'stream=' in path and '.sdp' in path and '?' not in path:
            path = f"{path}?"

        return f"{self.protocol}://{creds}{self.ip_address}:{self.port}{path}"

    def is_online(self):
        if not self.last_heartbeat:
            return False
        hb = self.last_heartbeat
        if hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        return (utc_now() - hb).total_seconds() < 120

    def to_dict(self, include_credentials=False):
        data = {
            'id': self.id,
            'name': self.name,
            'connection_type': self.connection_type,
            'ip_address': self.ip_address,
            'port': self.port,
            'username': self.username,
            'password': '****' if self.password else '',
            'protocol': self.protocol,
            'path': self.path,
            'dvr_url': self.dvr_url,
            'location': self.location,
            'active': self.active,
            'face_recognition_enabled': self.face_recognition_enabled,
            'is_online': self.is_online(),
        }
        if include_credentials:
            data['password'] = self.password
            data['stream_url'] = self.get_stream_url()
        return data


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    position = db.Column(db.String(100))
    department = db.Column(db.String(100), index=True)
    face_encoding = db.Column(db.Text)
    face_encoding_blob = db.Column(db.LargeBinary, nullable=True)
    photo_path = db.Column(db.String(200))
    active = db.Column(db.Boolean, default=True, index=True)


class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utc_now)


class AttendanceLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False, index=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('camera.id'), nullable=False, index=True)
    event_type = db.Column(db.String(20), nullable=False, default='check-in')
    timestamp = db.Column(db.DateTime, default=utc_now, index=True)
    confidence = db.Column(db.Float)

    employee = db.relationship('Employee', backref='attendance_logs')
    camera = db.relationship('Camera', backref='attendance_logs')


class AuditLog(db.Model):
    """Immutable append-only audit trail for all sensitive operations"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    username = db.Column(db.String(80))
    action = db.Column(db.String(50), nullable=False, index=True)
    resource_type = db.Column(db.String(50))
    resource_id = db.Column(db.String(50))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=utc_now, index=True)
    source = db.Column(db.String(20), default='web')  # 'web', 'telegram', 'api'


class Recording(db.Model):
    __tablename__ = 'recordings'
    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('camera.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=True)
    event_type = db.Column(db.String(50), default='face')  # face, motion, manual
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    file_path = db.Column(db.String(500), nullable=True)
    thumbnail_path = db.Column(db.String(500), nullable=True)
    file_size = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utc_now)

    camera = db.relationship('Camera', backref='recordings')
    employee = db.relationship('Employee', backref='recordings')


def log_audit(action, resource_type=None, resource_id=None, details=None,
              user_id=None, username=None, ip_address=None, source='web'):
    """Write an immutable audit log entry"""
    try:
        entry = AuditLog(
            user_id=user_id,
            username=username or 'system',
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details=details,
            ip_address=ip_address or (request.remote_addr if request else None),
            source=source
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        logger.error(f"Audit log failed: {e}")


# --- MEMORY CACHE ---
face_cache = {'vectors': [], 'ids': [], 'names': []}
DUPLICATE_FACE_THRESHOLD = float(os.environ.get('DUPLICATE_FACE_THRESHOLD', '0.7'))


def load_face_db_to_memory():
    """Updates face vector cache in memory from database"""
    try:
        employees = Employee.query.filter_by(active=True).all()
        face_cache['vectors'] = []
        face_cache['ids'] = []
        face_cache['names'] = []

        count = 0
        for emp in employees:
            vec = None
            # Prefer binary blob (faster)
            if emp.face_encoding_blob:
                try:
                    vec = np.frombuffer(emp.face_encoding_blob, dtype=np.float32)
                except Exception as e:
                    logger.warning(f"Failed to parse blob encoding for employee {emp.id}: {e}")
            # Fallback to JSON text
            if vec is None and emp.face_encoding:
                try:
                    vec = np.array(json.loads(emp.face_encoding), dtype=np.float32)
                except Exception as e:
                    logger.warning(f"Failed to parse JSON encoding for employee {emp.id}: {e}")

            if vec is not None and vec.shape[0] == 512:
                face_cache['vectors'].append(vec)
                face_cache['ids'].append(emp.id)
                face_cache['names'].append(emp.name)
                count += 1

        logger.info(f"Face cache updated: {count} faces loaded")
    except Exception as e:
        logger.error(f"Cache update failed: {e}")


def find_duplicate_employee_by_face(embedding):
    """Return existing employee with similar face embedding, if any."""
    try:
        employees = Employee.query.all()
        if not employees:
            return None
        query = np.array(embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query) + 1e-6

        best_sim = -1.0
        best_employee = None
        for employee in employees:
            vec = None
            if employee.face_encoding_blob:
                vec = np.frombuffer(employee.face_encoding_blob, dtype=np.float32)
            elif employee.face_encoding:
                try:
                    vec = np.array(json.loads(employee.face_encoding), dtype=np.float32)
                except Exception:
                    vec = None
            if vec is None or vec.shape[0] != 512:
                continue

            v = vec.astype(np.float32)
            sim = float(np.dot(query, v) / ((np.linalg.norm(v) + 1e-6) * query_norm))
            if sim > best_sim:
                best_sim = sim
                best_employee = employee

        if best_employee is not None and best_sim >= DUPLICATE_FACE_THRESHOLD:
            return {
                'id': best_employee.id,
                'name': best_employee.name,
                'employee_id': best_employee.employee_id,
                'active': bool(best_employee.active),
                'similarity': best_sim,
            }
        return None
    except Exception as e:
        logger.warning(f"Duplicate face check failed: {e}")
        return None


def generate_employee_id(department):
    """
    Generates IDs by department:
    - department id is prefix (1..., 2..., 3...)
    - sequence inside department starts from 001
    Example: Sales (id=1) => 1001, 1002; IT (id=2) => 2001, 2002.
    """
    if not department or not department.id:
        raise ValueError('Department is required to generate employee ID')

    prefix = str(department.id)
    max_seq = 0
    existing_ids = db.session.query(Employee.employee_id).filter(
        Employee.department == department.name
    ).all()

    for row in existing_ids:
        value = (row[0] or '').strip()
        if not value.startswith(prefix):
            continue
        rest = value[len(prefix):]
        if rest.isdigit():
            seq = int(rest)
            if seq > max_seq:
                max_seq = seq

    return f"{prefix}{max_seq + 1:03d}"


def ensure_department_exists(name):
    if not name:
        return None
    clean_name = name.strip()
    if not clean_name:
        return None
    department = Department.query.filter_by(name=clean_name).first()
    if not department:
        department = Department(name=clean_name, active=True)
        db.session.add(department)
    elif not department.active:
        department.active = True
    return department


# --- AUTH DECORATORS ---

def _extract_token():
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        return token[7:]
    return None


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = db.session.get(User, data['user_id'])
            if not current_user:
                return jsonify({'error': 'Invalid token'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(current_user, *args, **kwargs)
    return decorated


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(current_user, *args, **kwargs):
            if current_user.role not in roles:
                return jsonify({'error': 'Insufficient permissions'}), 403
            return f(current_user, *args, **kwargs)
        return decorated
    return decorator


# --- SHARED HELPERS ---

def _build_attendance_query(args):
    """Build filtered attendance query (shared between list/export/stats)"""
    query = AttendanceLog.query

    employee_id = args.get('employee_id', type=int)
    camera_id = args.get('camera_id', type=int)
    department = args.get('department', type=str)
    date_from = args.get('date_from', type=str)
    date_to = args.get('date_to', type=str)

    if employee_id:
        query = query.filter_by(employee_id=employee_id)
    if camera_id:
        query = query.filter_by(camera_id=camera_id)
    if department:
        query = query.join(Employee).filter(Employee.department == department)
    if date_from:
        try:
            dt_from = date_parser.parse(date_from)
            query = query.filter(AttendanceLog.timestamp >= dt_from)
        except Exception as e:
            logger.warning(f"Invalid date_from: {date_from}: {e}")
    if date_to:
        try:
            dt_to = date_parser.parse(date_to)
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            query = query.filter(AttendanceLog.timestamp <= dt_to)
        except Exception as e:
            logger.warning(f"Invalid date_to: {date_to}: {e}")

    return query


# --- API ROUTES ---

@app.route('/')
def serve():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    if path.startswith('api/'):
        return jsonify({'error': 'Not found'}), 404
    full_path = os.path.join(app.static_folder, path)
    if os.path.exists(full_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')


# --- HEALTH CHECK ---

@app.route('/api/health')
def health_check():
    try:
        db.session.execute(text('SELECT 1'))
        model_loaded = face_engine.model is not None
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'face_model': 'loaded' if model_loaded else 'not_loaded',
            'face_cache_size': len(face_cache['ids'])
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


# --- DETECTION EVENTS (for bounding box overlay) ---

@app.route('/api/detections/publish', methods=['POST'])
def publish_detection_event():
    """
    Called by worker to publish face detection events for real-time bounding box overlay.
    Expected JSON: {
        'camera_id': int,
        'faces': [{'bbox': [...], 'name': str, 'confidence': float, 'det_score': float}, ...],
        'frame_width': int,
        'frame_height': int,
        'timestamp': float
    }
    """
    try:
        data = request.get_json()
        if not data or 'camera_id' not in data:
            return jsonify({'error': 'Missing camera_id'}), 400

        camera_id = data['camera_id']

        # Store event in memory
        event = {
            'camera_id': camera_id,
            'faces': data.get('faces', []),
            'frame_width': data.get('frame_width', 0),
            'frame_height': data.get('frame_height', 0),
            'timestamp': data.get('timestamp', time.time())
        }
        detection_events[camera_id].append(event)

        # Broadcast to all clients connected to this camera detection room
        socketio.emit('detection', event, room=f'camera_{camera_id}', namespace='/detections')

        return jsonify({'status': 'published'}), 200
    except Exception as e:
        logger.error(f"Detection publish error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/detections/<int:camera_id>', methods=['GET'])
@token_required
def get_latest_detections(current_user, camera_id):
    """Get latest detection events for a camera"""
    try:
        events = list(detection_events.get(camera_id, []))
        return jsonify({'detections': events[-5:]})  # Return last 5 events
    except Exception as e:
        logger.error(f"Get detections error: {e}")
        return jsonify({'error': str(e)}), 500


# --- SOCKET.IO HANDLERS ---

@socketio.on('connect', namespace='/detections')
def handle_detection_connect(auth=None):
    logger.info(f"Detection WebSocket client connected: {request.sid}")
    emit('connect', {'data': 'Connected to detection server'})


@socketio.on('disconnect', namespace='/detections')
def handle_detection_disconnect():
    logger.info(f"Detection WebSocket client disconnected: {request.sid}")


@socketio.on('join_camera', namespace='/detections')
def handle_join_camera(data):
    """Client joins a specific camera detection room"""
    try:
        camera_id = data.get('camera_id')
        if not camera_id:
            emit('error', {'message': 'Missing camera_id'})
            return

        room = f'camera_{camera_id}'
        join_room(room)
        logger.info(f"Client {request.sid} joined room {room}")

        # Send last detection event if available
        recent_events = list(detection_events.get(camera_id, []))
        if recent_events:
            emit('detection', recent_events[-1])
    except Exception as e:
        logger.error(f"Join camera error: {e}")
        emit('error', {'message': str(e)})


@socketio.on('leave_camera', namespace='/detections')
def handle_leave_camera(data):
    """Client leaves a specific camera detection room"""
    try:
        camera_id = data.get('camera_id')
        if camera_id:
            room = f'camera_{camera_id}'
            leave_room(room)
            logger.info(f"Client {request.sid} left room {room}")
    except Exception as e:
        logger.error(f"Leave camera error: {e}")




@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    username = (data.get('username') or '').strip()
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(data.get('password', '')):
        token = jwt.encode({
            'user_id': user.id,
            'role': user.role,
            'exp': utc_now() + timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        log_audit(
            action='login_success',
            resource_type='user',
            resource_id=user.id,
            details=f'User "{user.username}" logged in',
            user_id=user.id,
            username=user.username,
            source='web'
        )
        return jsonify({'token': token, 'user': {'username': user.username, 'role': user.role}})

    log_audit(
        action='login_failed',
        resource_type='user',
        resource_id=None,
        details=f'Failed login attempt for username "{username}"',
        user_id=None,
        username=username or 'unknown',
        source='web'
    )
    return jsonify({'error': 'Invalid credentials'}), 401


# --- VIDEO STREAM ---

@app.route('/api/video/<int:camera_id>', methods=['GET'])
@token_required
def get_video_stream(current_user, camera_id):
    camera = Camera.query.get_or_404(camera_id)
    if not camera.active:
        return jsonify({'error': 'Camera is inactive'}), 404

    stream_url = camera.get_stream_url()
    if not stream_url:
        return jsonify({'error': 'Camera stream URL is not configured'}), 400

    src = f"ffmpeg:{stream_url}#video=mjpeg" if (camera.protocol or '').lower() == 'rtsp' else stream_url
    mjpeg_url = f"/go2rtc/api/stream.mjpeg?src={quote(src, safe='')}"
    return redirect(mjpeg_url, code=302)


# --- USERS ---

@app.route('/api/users', methods=['GET'])
@token_required
@role_required('admin', 'super_admin')
def get_users(current_user):
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'role': u.role,
        'created_at': u.created_at.isoformat() if u.created_at else None
    } for u in users])


@app.route('/api/users', methods=['POST'])
@token_required
@role_required('super_admin')
def create_user(current_user):
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'employee')

    if not username:
        return jsonify({'error': 'Username is required'}), 400
    if not password or len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if role not in ('super_admin', 'admin', 'hr', 'employee'):
        return jsonify({'error': 'Invalid role'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Пользователь с таким именем уже существует'}), 409

    new_user = User(username=username, role=role)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User created', 'id': new_user.id}), 201


@app.route('/api/users/<int:user_id>', methods=['PUT'])
@token_required
@role_required('super_admin')
def update_user(current_user, user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}

    if 'username' in data:
        username = data['username'].strip()
        if username != user.username:
            if User.query.filter_by(username=username).first():
                return jsonify({'error': 'Пользователь с таким именем уже существует'}), 409
            user.username = username

    if 'role' in data:
        role = data['role']
        if role not in ('super_admin', 'admin', 'hr', 'employee'):
            return jsonify({'error': 'Invalid role'}), 400
        user.role = role

    if 'password' in data and data['password']:
        password = data['password']
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        user.set_password(password)

    db.session.commit()
    return jsonify({'message': 'User updated'})


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@token_required
@role_required('super_admin')
def delete_user(current_user, user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot delete yourself'}), 400

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted'})


# --- EMPLOYEES ---

@app.route('/api/employees', methods=['POST'])
@token_required
@role_required('admin', 'super_admin', 'hr')
def add_employee(current_user):
    full_name = request.form.get('name')
    department = request.form.get('department', '').strip()
    position = request.form.get('position')

    file_bytes = None
    if 'photo' in request.files:
        file_bytes = request.files['photo'].read()
    elif request.json and 'photo' in request.json:
        try:
            file_bytes = base64.b64decode(request.json['photo'].split(',')[1])
            full_name = request.json.get('name')
            department = (request.json.get('department') or '').strip()
            position = request.json.get('position')
        except Exception as e:
            logger.warning(f"Failed to parse base64 photo: {e}")

    if not file_bytes:
        return jsonify({'error': 'No photo provided'}), 400

    if not department:
        return jsonify({'error': 'Укажите отдел сотрудника'}), 400

    department_obj = ensure_department_exists(department)
    db.session.flush()

    emp_id = generate_employee_id(department_obj)

    if Employee.query.filter_by(employee_id=emp_id).first():
        return jsonify({'error': 'Сотрудник с таким ID уже существует'}), 409

    try:
        embedding, bbox = face_engine.get_vector(file_bytes)

        if embedding is None:
            return jsonify({'error': 'No face detected in photo'}), 400

        if len(embedding) != 512:
            return jsonify({'error': f'Invalid face encoding length: {len(embedding)}'}), 400

        duplicate = find_duplicate_employee_by_face(embedding)
        if duplicate:
            status_text = 'активный' if duplicate.get('active') else 'неактивный'
            return jsonify({
                'error': f"Сотрудник с таким фото уже существует: {duplicate['name']} (ID: {duplicate['employee_id']}, {status_text})",
                'duplicate_employee_id': duplicate['id'],
                'similarity': round(float(duplicate['similarity']), 3)
            }), 409

        vector_json = json.dumps(embedding)
        vector_blob = np.array(embedding, dtype=np.float32).tobytes()

    except Exception as e:
        logger.error(f"Face detection error: {e}")
        return jsonify({'error': f'Face detection failed: {str(e)}'}), 500

    photo_filename = f"{emp_id}.jpg"
    photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
    with open(photo_path, 'wb') as f:
        f.write(file_bytes)

    employee = Employee(
        name=full_name,
        employee_id=emp_id,
        department=department,
        position=position,
        face_encoding=vector_json,
        face_encoding_blob=vector_blob,
        photo_path=photo_filename,
        active=True
    )
    db.session.add(employee)
    db.session.commit()

    load_face_db_to_memory()
    return jsonify({'message': 'Employee added', 'id': employee.id, 'employee_id': employee.employee_id}), 201


@app.route('/api/employees', methods=['GET'])
@token_required
def get_employees(current_user):
    include_inactive_raw = (request.args.get('include_inactive') or '').strip().lower()
    include_inactive = include_inactive_raw in ('1', 'true', 'yes', 'on')
    if include_inactive and current_user.role not in ('hr', 'admin', 'super_admin'):
        return jsonify({'error': 'Insufficient permissions'}), 403
    query = Employee.query
    if not include_inactive:
        query = query.filter_by(active=True)
    employees = query.all()
    return jsonify([{
        'id': e.id,
        'name': e.name,
        'employee_id': e.employee_id,
        'department': e.department,
        'position': e.position,
        'photo_path': e.photo_path,
        'active': e.active
    } for e in employees])


@app.route('/api/employees/<int:emp_id>', methods=['GET'])
@token_required
def get_employee(current_user, emp_id):
    employee = Employee.query.get_or_404(emp_id)
    return jsonify({
        'id': employee.id,
        'name': employee.name,
        'employee_id': employee.employee_id,
        'department': employee.department,
        'position': employee.position,
        'photo_path': employee.photo_path,
        'active': employee.active
    })


@app.route('/api/employees/photo/<path:filename>', methods=['GET'])
@token_required
def get_employee_photo(current_user, filename):
    safe_name = os.path.basename(filename)
    return send_from_directory(app.config['UPLOAD_FOLDER'], safe_name)


@app.route('/api/employees/<int:emp_id>', methods=['PUT'])
@token_required
@role_required('admin', 'super_admin', 'hr')
def update_employee(current_user, emp_id):
    employee = Employee.query.get_or_404(emp_id)
    data = request.get_json() or {}

    if 'name' in data:
        employee.name = data['name']
    if 'employee_id' in data:
        new_emp_id = data['employee_id']
        if new_emp_id != employee.employee_id:
            if Employee.query.filter_by(employee_id=new_emp_id).first():
                return jsonify({'error': 'Сотрудник с таким ID уже существует'}), 409
            employee.employee_id = new_emp_id
    if 'department' in data:
        employee.department = (data['department'] or '').strip()
        ensure_department_exists(employee.department)
    if 'position' in data:
        employee.position = data['position']
    if 'active' in data:
        employee.active = data['active']

    db.session.commit()
    load_face_db_to_memory()
    return jsonify({'message': 'Employee updated'})


@app.route('/api/employees/<int:emp_id>', methods=['DELETE'])
@token_required
@role_required('admin', 'super_admin', 'hr')
def delete_employee(current_user, emp_id):
    employee = Employee.query.get_or_404(emp_id)
    db.session.delete(employee)
    db.session.commit()
    load_face_db_to_memory()
    return jsonify({'message': 'Employee deleted'})


# --- DEPARTMENTS ---

@app.route('/api/departments', methods=['GET'])
@token_required
def get_departments(current_user):
    departments = Department.query.filter_by(active=True).order_by(Department.name.asc()).all()
    return jsonify([{
        'id': d.id,
        'name': d.name,
        'active': d.active,
        'created_at': d.created_at.isoformat() if d.created_at else None
    } for d in departments])


@app.route('/api/departments', methods=['POST'])
@token_required
@role_required('admin', 'super_admin', 'hr')
def create_department(current_user):
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Название отдела обязательно'}), 400

    existing = Department.query.filter_by(name=name).first()
    if existing:
        if not existing.active:
            existing.active = True
            db.session.commit()
        return jsonify({'id': existing.id, 'name': existing.name, 'message': 'Отдел уже существует'}), 200

    department = Department(name=name, active=True)
    db.session.add(department)
    db.session.commit()
    return jsonify({'id': department.id, 'name': department.name, 'message': 'Отдел создан'}), 201


# --- CAMERAS ---

@app.route('/api/cameras', methods=['POST'])
@token_required
@role_required('admin', 'super_admin')
def add_camera(current_user):
    data = request.get_json() or {}
    name = data.get('name', 'New Camera')
    connection_type = data.get('connection_type', 'direct')

    camera = Camera(
        name=name,
        connection_type=connection_type,
        location=data.get('location', ''),
        active=data.get('active', True),
        face_recognition_enabled=data.get('face_recognition_enabled', False)
    )

    if connection_type == 'direct':
        camera.ip_address = data.get('ip_address', '')
        camera.port = data.get('port', 554)
        camera.username = data.get('username', '')
        camera.password = data.get('password', '')
        camera.protocol = data.get('protocol', 'rtsp')
        camera.path = data.get('path', '/stream')
    elif connection_type == 'dvr':
        camera.dvr_url = data.get('dvr_url', '')

    db.session.add(camera)
    db.session.commit()
    return jsonify({'message': 'Camera created', 'id': camera.id}), 201


@app.route('/api/cameras', methods=['GET'])
@token_required
def get_cameras(current_user):
    cameras = Camera.query.filter_by(active=True).all()
    return jsonify([c.to_dict() for c in cameras])


@app.route('/api/cameras/<int:camera_id>', methods=['GET'])
@token_required
def get_camera(current_user, camera_id):
    camera = Camera.query.get_or_404(camera_id)
    return jsonify(camera.to_dict())


@app.route('/api/cameras/<int:camera_id>', methods=['PUT'])
@token_required
@role_required('admin', 'super_admin')
def update_camera(current_user, camera_id):
    camera = Camera.query.get_or_404(camera_id)
    data = request.get_json()

    for field in ['name', 'location', 'active', 'face_recognition_enabled',
                  'connection_type', 'ip_address', 'port', 'username',
                  'password', 'protocol', 'path', 'dvr_url']:
        if field in data:
            setattr(camera, field, data[field])

    db.session.commit()
    return jsonify({'message': 'Camera updated', 'id': camera.id})


@app.route('/api/cameras/<int:camera_id>', methods=['DELETE'])
@token_required
@role_required('admin', 'super_admin')
def delete_camera(current_user, camera_id):
    camera = Camera.query.get_or_404(camera_id)
    camera.active = False
    db.session.commit()
    return jsonify({'message': 'Camera deleted'})


@app.route('/api/cameras/<int:camera_id>/heartbeat', methods=['POST'])
def camera_heartbeat(camera_id):
    """Called by worker to update camera online status"""
    camera = Camera.query.get_or_404(camera_id)
    camera.last_heartbeat = utc_now()
    db.session.commit()
    return jsonify({'status': 'ok'})



# --- CAMERA AUTO-DISCOVERY ---

discovery_state = {
    'scanning': False,
    'stage': '',
    'message': '',
    'progress': 0,
    'results': [],
    'error': None,
}
_discovery_instance = None


def _discovery_callback(stage, message, progress):
    """Progress callback from SmartCameraDiscovery."""
    discovery_state['stage'] = stage
    discovery_state['message'] = message
    discovery_state['progress'] = progress


@app.route('/api/camera-discovery/scan', methods=['POST'])
@token_required
@role_required('admin', 'super_admin')
def start_camera_discovery(current_user):
    """One-click auto-discovery: finds ALL cameras on all local networks."""
    global _discovery_instance

    if discovery_state['scanning']:
        return jsonify({'error': 'Scan already in progress'}), 400

    # Accept user-specified network(s) from request body
    data = request.get_json(silent=True) or {}
    user_network = data.get('network', '').strip()
    user_networks = [user_network] if user_network else None

    discovery_state['scanning'] = True
    discovery_state['stage'] = 'starting'
    discovery_state['message'] = 'Initializing auto-discovery...'
    discovery_state['progress'] = 0
    discovery_state['results'] = []
    discovery_state['error'] = None

    def scan_in_background():
        global _discovery_instance
        try:
            _discovery_instance = SmartCameraDiscovery(
                callback=_discovery_callback,
                networks=user_networks
            )
            results = _discovery_instance.discover()
            discovery_state['results'] = results
            logger.info(f"Auto-discovery complete: {len(results)} verified cameras found")
        except Exception as e:
            logger.error(f"Auto-discovery failed: {e}")
            discovery_state['error'] = str(e)
            discovery_state['results'] = []
        finally:
            discovery_state['scanning'] = False
            _discovery_instance = None

    import threading
    thread = threading.Thread(target=scan_in_background, daemon=True)
    thread.start()

    return jsonify({'message': 'Auto-discovery started'}), 202


@app.route('/api/camera-discovery/stop', methods=['POST'])
@token_required
@role_required('admin', 'super_admin')
def stop_camera_discovery(current_user):
    """Stop a running auto-discovery scan."""
    global _discovery_instance
    if _discovery_instance:
        _discovery_instance.stop()
    discovery_state['scanning'] = False
    return jsonify({'message': 'Discovery stopped'})


@app.route('/api/camera-discovery/status', methods=['GET'])
@token_required
def get_discovery_status(current_user):
    """Get auto-discovery progress and results."""
    return jsonify({
        'scanning': discovery_state['scanning'],
        'stage': discovery_state['stage'],
        'message': discovery_state['message'],
        'progress': discovery_state['progress'],
        'found_count': len(discovery_state['results']),
        'results': discovery_state['results'],
        'error': discovery_state['error'],
    })


@app.route('/api/camera-discovery/add', methods=['POST'])
@token_required
@role_required('admin', 'super_admin')
def add_discovered_camera(current_user):
    """Add a single discovered camera to the system."""
    data = request.get_json()

    # Check for duplicate by IP + port
    existing = Camera.query.filter_by(
        ip_address=data.get('ip_address'),
        port=data.get('port', 554)
    ).first()
    if existing:
        return jsonify({'error': 'Camera already exists', 'id': existing.id}), 409

    camera = Camera(
        name=data.get('name', f"Camera {data.get('ip_address')}"),
        connection_type=data.get('connection_type', 'direct'),
        location=data.get('location', ''),
        ip_address=data.get('ip_address'),
        port=data.get('port', 554),
        username=data.get('username', ''),
        password=data.get('password', ''),
        protocol=data.get('protocol', 'rtsp'),
        path=data.get('path', '/stream'),
        active=True,
        face_recognition_enabled=data.get('face_recognition_enabled', True)
    )

    db.session.add(camera)
    db.session.commit()

    # Register stream in go2rtc with H.265->H.264 transcoding for browser MSE
    stream_url = camera.get_stream_url()
    if stream_url:
        try:
            import requests as http_requests
            go2rtc_host = os.environ.get('GO2RTC_HOST', 'localhost')
            go2rtc_port = os.environ.get('GO2RTC_PORT', '1984')
            base = f"http://{go2rtc_host}:{go2rtc_port}/api/streams"
            http_requests.put(base, params={'src': stream_url, 'name': f'camera_{camera.id}_raw'}, timeout=5)
            http_requests.put(base, params={
                'src': f'ffmpeg:camera_{camera.id}_raw#video=h264',
                'name': f'camera_{camera.id}'
            }, timeout=5)
        except Exception:
            pass

    return jsonify({
        'message': 'Camera added successfully',
        'id': camera.id,
        'name': camera.name
    }), 201


@app.route('/api/camera-discovery/add-all', methods=['POST'])
@token_required
@role_required('admin', 'super_admin')
def add_all_discovered_cameras(current_user):
    """Add ALL verified discovered cameras to the system at once."""
    results = discovery_state.get('results', [])
    verified = [r for r in results if r.get('verified')]

    if not verified:
        return jsonify({'error': 'No verified cameras to add'}), 400

    added = []
    skipped = []

    for cam in verified:
        existing = Camera.query.filter_by(
            ip_address=cam['ip_address'],
            port=cam['port']
        ).first()
        if existing:
            skipped.append(cam['ip_address'])
            continue

        camera = Camera(
            name=cam.get('name', f"Camera {cam['ip_address']}"),
            connection_type=cam.get('connection_type', 'direct'),
            location='',
            ip_address=cam['ip_address'],
            port=cam['port'],
            username=cam.get('username', ''),
            password=cam.get('password', ''),
            protocol=cam.get('protocol', 'rtsp'),
            path=cam.get('path', '/stream'),
            active=True,
            face_recognition_enabled=True
        )
        db.session.add(camera)
        added.append(cam['ip_address'])

    db.session.commit()

    return jsonify({
        'message': f'Added {len(added)} cameras, skipped {len(skipped)} duplicates',
        'added_count': len(added),
        'skipped_count': len(skipped),
        'added_ips': added,
        'skipped_ips': skipped,
    }), 201

# --- ATTENDANCE LOGS ---

@app.route('/api/attendance', methods=['GET'])
@token_required
def get_attendance_logs(current_user):
    query = _build_attendance_query(request.args)

    page = request.args.get('page', type=int, default=1)
    per_page = request.args.get('per_page', type=int, default=100)
    per_page = min(per_page, 500)

    pagination = query.order_by(AttendanceLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [{
            'id': log.id,
            'employee_id': log.employee_id,
            'employee_name': log.employee.name if log.employee else 'Unknown',
            'department': log.employee.department if log.employee else '',
            'camera_id': log.camera_id,
            'camera_name': log.camera.name if log.camera else 'Unknown',
            'event_type': log.event_type,
            'timestamp': log.timestamp.isoformat() if log.timestamp else None,
            'confidence': log.confidence
        } for log in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': pagination.page,
        'per_page': per_page
    })


@app.route('/api/attendance/export', methods=['GET'])
@token_required
def export_attendance(current_user):
    query = _build_attendance_query(request.args)
    out_format = request.args.get('format', 'csv').lower()

    MAX_EXPORT = 50000
    logs = query.order_by(AttendanceLog.timestamp.desc()).limit(MAX_EXPORT).all()

    rows = []
    for log in logs:
        rows.append({
            'ID': log.id,
            'Employee Name': log.employee.name if log.employee else 'Unknown',
            'Employee ID': log.employee.employee_id if log.employee else '',
            'Department': log.employee.department if log.employee else '',
            'Position': log.employee.position if log.employee else '',
            'Camera': log.camera.name if log.camera else 'Unknown',
            'Event Type': log.event_type,
            'Timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S') if log.timestamp else '',
            'Confidence': f"{log.confidence:.3f}" if log.confidence else ''
        })

    if out_format == 'xlsx':
        try:
            import pandas as pd
            df = pd.DataFrame(rows)
            bio = BytesIO()
            df.to_excel(bio, index=False, engine='openpyxl')
            bio.seek(0)
            return Response(
                bio.getvalue(),
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': 'attachment; filename=attendance_report.xlsx'}
            )
        except Exception as e:
            logger.error(f"Excel export failed: {e}")
            return jsonify({'error': f'Excel export failed: {str(e)}'}), 500

    if out_format == 'pdf':
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
            styles = getSampleStyleSheet()
            elements = [Paragraph("Attendance Report", styles['Title']), Spacer(1, 12)]

            table_data = [['ID', 'Name', 'Emp ID', 'Dept', 'Pos', 'Camera', 'Event', 'Time', 'Conf']]
            for r in rows:
                table_data.append([
                    str(r['ID']), str(r['Employee Name']), str(r['Employee ID']),
                    str(r['Department']), str(r['Position']), str(r['Camera']),
                    str(r['Event Type']), str(r['Timestamp']), str(r['Confidence'])
                ])

            table = Table(table_data, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
            doc.build(elements)
            buffer.seek(0)
            return Response(
                buffer.getvalue(),
                mimetype='application/pdf',
                headers={'Content-Disposition': 'attachment; filename=attendance_report.pdf'}
            )
        except Exception as e:
            logger.error(f"PDF export failed: {e}")
            return jsonify({'error': f'PDF export failed: {str(e)}'}), 500

    # CSV (default)
    output = StringIO()
    writer = csv.writer(output)
    headers = ['ID', 'Employee Name', 'Employee ID', 'Department', 'Position', 'Camera', 'Event Type', 'Timestamp', 'Confidence']
    writer.writerow(headers)
    for r in rows:
        writer.writerow([r[h] for h in headers])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=attendance_report.csv'}
    )


@app.route('/api/attendance/stats', methods=['GET'])
@token_required
def get_attendance_stats(current_user):
    """Attendance statistics using SQL aggregation (no loading all rows into memory)"""
    department = request.args.get('department', type=str)
    date_from = request.args.get('date_from', type=str)
    date_to = request.args.get('date_to', type=str)

    # Build base filter conditions
    filters = []
    if department:
        filters.append(Employee.department == department)
    if date_from:
        try:
            dt_from = date_parser.parse(date_from)
            filters.append(AttendanceLog.timestamp >= dt_from)
        except Exception as e:
            logger.warning(f"Invalid date_from in stats: {e}")
    if date_to:
        try:
            dt_to = date_parser.parse(date_to)
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            filters.append(AttendanceLog.timestamp <= dt_to)
        except Exception as e:
            logger.warning(f"Invalid date_to in stats: {e}")

    # Total count
    total_query = db.session.query(func.count(AttendanceLog.id)).join(Employee)
    for f in filters:
        total_query = total_query.filter(f)
    total_logs = total_query.scalar() or 0

    # Stats by employee (SQL aggregation)
    emp_query = db.session.query(
        Employee.name,
        func.count(AttendanceLog.id).label('total_checkins'),
        func.avg(AttendanceLog.confidence).label('avg_confidence')
    ).join(Employee)
    for f in filters:
        emp_query = emp_query.filter(f)
    emp_stats = emp_query.group_by(Employee.name).all()

    stats_by_employee = {}
    for name, count, avg_conf in emp_stats:
        stats_by_employee[name] = {
            'total_checkins': count,
            'avg_confidence': float(avg_conf) if avg_conf else 0
        }

    # Stats by camera (SQL aggregation)
    cam_query = db.session.query(
        Camera.name,
        func.count(AttendanceLog.id).label('detections')
    ).join(Camera)
    for f in filters:
        cam_query = cam_query.filter(f)
    cam_stats = cam_query.group_by(Camera.name).all()

    stats_by_camera = {}
    for name, count in cam_stats:
        stats_by_camera[name] = {'detections': count}

    return jsonify({
        'total_logs': total_logs,
        'by_employee': stats_by_employee,
        'by_camera': stats_by_camera
    })


# --- RECORDINGS ---

@app.route('/api/recordings', methods=['GET'])
@token_required
def get_recordings(current_user):
    """List recordings with optional filters (camera_id, date_from, date_to, event_type)"""
    query = Recording.query

    camera_id = request.args.get('camera_id', type=int)
    event_type = request.args.get('event_type', type=str)
    date_from = request.args.get('date_from', type=str)
    date_to = request.args.get('date_to', type=str)

    if camera_id:
        query = query.filter_by(camera_id=camera_id)
    if event_type:
        query = query.filter_by(event_type=event_type)
    if date_from:
        try:
            dt_from = date_parser.parse(date_from)
            query = query.filter(Recording.start_time >= dt_from)
        except Exception as e:
            logger.warning(f"Invalid date_from: {date_from}: {e}")
    if date_to:
        try:
            dt_to = date_parser.parse(date_to)
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            query = query.filter(Recording.start_time <= dt_to)
        except Exception as e:
            logger.warning(f"Invalid date_to: {date_to}: {e}")

    page = request.args.get('page', type=int, default=1)
    per_page = request.args.get('per_page', type=int, default=50)
    per_page = min(per_page, 200)

    pagination = query.order_by(Recording.start_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [{
            'id': rec.id,
            'camera_id': rec.camera_id,
            'camera_name': rec.camera.name if rec.camera else 'Unknown',
            'employee_id': rec.employee_id,
            'employee_name': rec.employee.name if rec.employee else None,
            'event_type': rec.event_type,
            'start_time': rec.start_time.isoformat() if rec.start_time else None,
            'end_time': rec.end_time.isoformat() if rec.end_time else None,
            'file_path': rec.file_path,
            'thumbnail_path': rec.thumbnail_path,
            'file_size': rec.file_size,
            'created_at': rec.created_at.isoformat() if rec.created_at else None,
        } for rec in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': pagination.page,
        'per_page': per_page
    })


@app.route('/api/recordings/<int:recording_id>/stream', methods=['GET'])
@token_required
def stream_recording(current_user, recording_id):
    """Stream the recording MP4 file"""
    recording = Recording.query.get_or_404(recording_id)

    if not recording.file_path:
        return jsonify({'error': 'Recording file not available'}), 404

    full_path = os.path.join(app.config['RECORDINGS_FOLDER'], recording.file_path)
    if not os.path.exists(full_path):
        return jsonify({'error': 'Recording file not found on disk'}), 404

    return send_file(full_path, mimetype='video/mp4', as_attachment=False)


@app.route('/api/recordings/<int:recording_id>/thumbnail', methods=['GET'])
@token_required
def get_recording_thumbnail(current_user, recording_id):
    """Return the thumbnail image for a recording"""
    recording = Recording.query.get_or_404(recording_id)

    if not recording.thumbnail_path:
        return jsonify({'error': 'Thumbnail not available'}), 404

    full_path = os.path.join(app.config['RECORDINGS_FOLDER'], recording.thumbnail_path)
    if not os.path.exists(full_path):
        return jsonify({'error': 'Thumbnail file not found on disk'}), 404

    return send_file(full_path, mimetype='image/jpeg')


@app.route('/api/recordings/<int:recording_id>', methods=['DELETE'])
@token_required
@role_required('admin', 'super_admin')
def delete_recording(current_user, recording_id):
    """Delete a recording (admin only). Removes the file from disk too."""
    recording = Recording.query.get_or_404(recording_id)

    # Delete recording file from disk
    if recording.file_path:
        file_full_path = os.path.join(app.config['RECORDINGS_FOLDER'], recording.file_path)
        if os.path.exists(file_full_path):
            try:
                os.remove(file_full_path)
            except Exception as e:
                logger.error(f"Failed to delete recording file {file_full_path}: {e}")

    # Delete thumbnail from disk
    if recording.thumbnail_path:
        thumb_full_path = os.path.join(app.config['RECORDINGS_FOLDER'], recording.thumbnail_path)
        if os.path.exists(thumb_full_path):
            try:
                os.remove(thumb_full_path)
            except Exception as e:
                logger.error(f"Failed to delete thumbnail file {thumb_full_path}: {e}")

    log_audit('delete_recording', 'recording', recording_id,
              f'Recording deleted by {current_user.username}',
              user_id=current_user.id, username=current_user.username)

    db.session.delete(recording)
    db.session.commit()
    return jsonify({'message': 'Recording deleted'})


@app.route('/api/recordings/timeline', methods=['GET'])
@token_required
def get_recordings_timeline(current_user):
    """Return timeline data for a given date range and camera"""
    camera_id = request.args.get('camera_id', type=int)
    date_from = request.args.get('date_from', type=str)
    date_to = request.args.get('date_to', type=str)

    query = Recording.query

    if camera_id:
        query = query.filter_by(camera_id=camera_id)
    if date_from:
        try:
            dt_from = date_parser.parse(date_from)
            query = query.filter(Recording.start_time >= dt_from)
        except Exception as e:
            logger.warning(f"Invalid date_from in timeline: {date_from}: {e}")
    if date_to:
        try:
            dt_to = date_parser.parse(date_to)
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            query = query.filter(Recording.start_time <= dt_to)
        except Exception as e:
            logger.warning(f"Invalid date_to in timeline: {date_to}: {e}")

    recordings = query.order_by(Recording.start_time.asc()).limit(1000).all()

    return jsonify([{
        'id': rec.id,
        'start_time': rec.start_time.isoformat() if rec.start_time else None,
        'end_time': rec.end_time.isoformat() if rec.end_time else None,
        'event_type': rec.event_type,
        'camera_id': rec.camera_id,
    } for rec in recordings])


# --- CAMERA SNAPSHOT ---

@app.route('/api/cameras/<int:camera_id>/snapshot', methods=['GET'])
@token_required
def get_camera_snapshot(current_user, camera_id):
    """Capture a single frame from a camera and return as JPEG"""
    import cv2
    camera = Camera.query.get_or_404(camera_id)
    if not camera.active:
        return jsonify({'error': 'Camera is inactive'}), 404

    stream_url = camera.get_stream_url()
    if not stream_url:
        return jsonify({'error': 'Camera stream URL is not configured'}), 400

    try:
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            return jsonify({'error': 'Cannot connect to camera'}), 503

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return jsonify({'error': 'Failed to capture frame'}), 503

        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        log_audit('snapshot', 'camera', camera_id,
                  f'Snapshot taken by {current_user.username}',
                  user_id=current_user.id, username=current_user.username)
        return Response(buffer.tobytes(), mimetype='image/jpeg')
    except Exception as e:
        logger.error(f"Snapshot error for camera {camera_id}: {e}")
        return jsonify({'error': f'Snapshot failed: {str(e)}'}), 500


@app.route('/api/cameras/<int:camera_id>/snapshot', methods=['POST'])
@token_required
def save_camera_snapshot(current_user, camera_id):
    """Capture a snapshot from the camera and save as JPEG in instance/snapshots/"""
    import cv2
    camera = Camera.query.get_or_404(camera_id)
    if not camera.active:
        return jsonify({'error': 'Camera is inactive'}), 404

    stream_url = camera.get_stream_url()
    if not stream_url:
        return jsonify({'error': 'Camera stream URL is not configured'}), 400

    try:
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            return jsonify({'error': 'Cannot connect to camera'}), 503

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return jsonify({'error': 'Failed to capture frame'}), 503

        timestamp_str = utc_now().strftime('%Y%m%d_%H%M%S')
        filename = f"camera_{camera_id}_{timestamp_str}.jpg"
        file_path = os.path.join(app.config['SNAPSHOTS_FOLDER'], filename)

        cv2.imwrite(file_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        log_audit('snapshot_saved', 'camera', camera_id,
                  f'Snapshot saved by {current_user.username}: {filename}',
                  user_id=current_user.id, username=current_user.username)

        return jsonify({
            'message': 'Snapshot saved',
            'file_path': filename,
            'url': f'/api/snapshots/{filename}'
        }), 201
    except Exception as e:
        logger.error(f"Snapshot save error for camera {camera_id}: {e}")
        return jsonify({'error': f'Snapshot failed: {str(e)}'}), 500


@app.route('/api/snapshots/<path:filename>', methods=['GET'])
@token_required
def get_saved_snapshot(current_user, filename):
    """Serve a saved snapshot image"""
    safe_name = os.path.basename(filename)
    return send_from_directory(app.config['SNAPSHOTS_FOLDER'], safe_name)


@app.route('/api/cameras/<int:camera_id>/poster', methods=['GET'])
@token_required
def get_camera_poster(current_user, camera_id):
    """Fast poster frame via go2rtc (uses cached stream when available)."""
    import requests as http_requests
    camera = Camera.query.get_or_404(camera_id)
    if not camera.active:
        return jsonify({'error': 'Camera is inactive'}), 404

    stream_url = camera.get_stream_url()
    if not stream_url:
        return jsonify({'error': 'No stream URL'}), 400

    go2rtc_host = os.environ.get('GO2RTC_HOST', 'localhost')
    go2rtc_port = os.environ.get('GO2RTC_PORT', '1984')
    # Use raw stream name for poster (no need to transcode a single frame)
    go2rtc_url = f"http://{go2rtc_host}:{go2rtc_port}/api/frame.jpeg?src=camera_{camera_id}_raw"

    try:
        resp = http_requests.get(go2rtc_url, timeout=8)
        if resp.status_code == 200 and resp.content:
            return Response(
                resp.content,
                mimetype='image/jpeg',
                headers={'Cache-Control': 'no-cache, max-age=0'}
            )
    except Exception as e:
        logger.debug(f"go2rtc poster failed for camera {camera_id}: {e}")

    # Fallback: capture via OpenCV
    import cv2
    try:
        cap = cv2.VideoCapture(stream_url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                return Response(buf.tobytes(), mimetype='image/jpeg',
                                headers={'Cache-Control': 'no-cache, max-age=0'})
        else:
            cap.release()
    except Exception as e:
        logger.debug(f"OpenCV poster failed for camera {camera_id}: {e}")

    return jsonify({'error': 'Unable to capture poster frame'}), 503


@app.route('/api/cameras/<int:camera_id>/last-frame', methods=['GET'])
@token_required
def get_camera_last_frame(current_user, camera_id):
    """Return the most recent saved frame for camera (recording thumbnail or snapshot)."""
    camera = Camera.query.get_or_404(camera_id)

    # 1) Latest recording thumbnail from DB
    latest_rec = Recording.query.filter(
        Recording.camera_id == camera_id,
        Recording.thumbnail_path.isnot(None)
    ).order_by(Recording.start_time.desc(), Recording.id.desc()).first()

    if latest_rec and latest_rec.thumbnail_path:
        thumb_name = os.path.basename(latest_rec.thumbnail_path)
        thumb_full_path = os.path.join(app.config['RECORDINGS_FOLDER'], thumb_name)
        if os.path.exists(thumb_full_path):
            return send_file(
                thumb_full_path,
                mimetype='image/jpeg',
                headers={'Cache-Control': 'no-cache, max-age=0'}
            )

    # 2) Latest saved camera snapshot from disk
    snapshots_folder = app.config['SNAPSHOTS_FOLDER']
    prefix = f"camera_{camera_id}_"
    try:
        candidates = []
        for name in os.listdir(snapshots_folder):
            low = name.lower()
            if name.startswith(prefix) and (low.endswith('.jpg') or low.endswith('.jpeg') or low.endswith('.png')):
                full_path = os.path.join(snapshots_folder, name)
                if os.path.isfile(full_path):
                    candidates.append(full_path)

        if candidates:
            latest_path = max(candidates, key=os.path.getmtime)
            return send_file(
                latest_path,
                mimetype='image/jpeg',
                headers={'Cache-Control': 'no-cache, max-age=0'}
            )
    except Exception as e:
        logger.debug(f"Failed to read snapshots for camera {camera_id}: {e}")

    return jsonify({'error': f'No saved frame for camera {camera.id}'}), 404


# --- INTERNAL SNAPSHOT (no auth, for telegram bot on same network) ---

@app.route('/api/internal/cameras/<int:camera_id>/snapshot', methods=['GET'])
def internal_camera_snapshot(camera_id):
    """Internal snapshot endpoint for telegram bot (protected by internal network)"""
    import cv2
    internal_key = request.headers.get('X-Internal-Key', '')
    expected_key = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
    if internal_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401

    camera = Camera.query.get_or_404(camera_id)
    if not camera.active:
        return jsonify({'error': 'Camera is inactive'}), 404

    stream_url = camera.get_stream_url()
    if not stream_url:
        return jsonify({'error': 'Camera stream URL is not configured'}), 400

    try:
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            return jsonify({'error': 'Cannot connect to camera'}), 503

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return jsonify({'error': 'Failed to capture frame'}), 503

        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return Response(buffer.tobytes(), mimetype='image/jpeg')
    except Exception as e:
        logger.error(f"Internal snapshot error for camera {camera_id}: {e}")
        return jsonify({'error': f'Snapshot failed: {str(e)}'}), 500


# --- INTERNAL ENDPOINTS FOR TELEGRAM BOT ---

@app.route('/api/internal/employees', methods=['POST'])
def internal_add_employee():
    """Add employee via internal API (for telegram bot)"""
    internal_key = request.headers.get('X-Internal-Key', '')
    expected_key = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
    if internal_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401

    full_name = request.form.get('name')
    department = request.form.get('department', '').strip()
    position = request.form.get('position', '')

    file_bytes = None
    if 'photo' in request.files:
        file_bytes = request.files['photo'].read()

    if not file_bytes:
        return jsonify({'error': 'No photo provided'}), 400
    if not full_name:
        return jsonify({'error': 'Name is required'}), 400
    if not department:
        return jsonify({'error': 'Department is required'}), 400

    department_obj = ensure_department_exists(department)
    db.session.flush()

    emp_id = generate_employee_id(department_obj)

    if Employee.query.filter_by(employee_id=emp_id).first():
        return jsonify({'error': 'Employee ID conflict'}), 409

    try:
        embedding, bbox = face_engine.get_vector(file_bytes)
        if embedding is None:
            return jsonify({'error': 'No face detected in photo'}), 400
        if len(embedding) != 512:
            return jsonify({'error': f'Invalid face encoding length: {len(embedding)}'}), 400

        duplicate = find_duplicate_employee_by_face(embedding)
        if duplicate:
            status_text = 'active' if duplicate.get('active') else 'inactive'
            return jsonify({
                'error': f"Employee with similar face already exists: {duplicate['name']} (ID: {duplicate['employee_id']}, {status_text})",
                'duplicate_employee_id': duplicate['id'],
                'similarity': round(float(duplicate['similarity']), 3)
            }), 409

        vector_json = json.dumps(embedding)
        vector_blob = np.array(embedding, dtype=np.float32).tobytes()
    except Exception as e:
        logger.error(f"Face detection error: {e}")
        return jsonify({'error': f'Face detection failed: {str(e)}'}), 500

    photo_filename = f"{emp_id}.jpg"
    photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
    with open(photo_path, 'wb') as f:
        f.write(file_bytes)

    employee = Employee(
        name=full_name,
        employee_id=emp_id,
        department=department,
        position=position,
        face_encoding=vector_json,
        face_encoding_blob=vector_blob,
        photo_path=photo_filename,
        active=True
    )
    db.session.add(employee)
    db.session.commit()

    load_face_db_to_memory()
    log_audit('add_employee', 'employee', employee.id,
              f'Employee {full_name} added via Telegram', source='telegram')
    return jsonify({
        'message': 'Employee added',
        'id': employee.id,
        'employee_id': employee.employee_id,
        'name': full_name,
        'department': department
    }), 201


@app.route('/api/internal/cameras', methods=['GET'])
def internal_get_cameras():
    """Get cameras via internal API (for telegram bot)"""
    internal_key = request.headers.get('X-Internal-Key', '')
    expected_key = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
    if internal_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401

    cameras = Camera.query.filter_by(active=True).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'location': c.location,
        'is_online': c.is_online(),
        'face_recognition_enabled': c.face_recognition_enabled
    } for c in cameras])


@app.route('/api/internal/cameras/<int:camera_id>/rename', methods=['PUT'])
def internal_rename_camera(camera_id):
    """Rename camera via internal API (for telegram bot)"""
    internal_key = request.headers.get('X-Internal-Key', '')
    expected_key = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
    if internal_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401

    camera = Camera.query.get_or_404(camera_id)
    data = request.get_json() or {}
    new_name = data.get('name', '').strip()
    if not new_name:
        return jsonify({'error': 'Name is required'}), 400

    old_name = camera.name
    camera.name = new_name
    db.session.commit()
    log_audit('rename_camera', 'camera', camera_id,
              f'Camera renamed: "{old_name}" -> "{new_name}" via Telegram', source='telegram')
    return jsonify({'message': 'Camera renamed', 'old_name': old_name, 'new_name': new_name})


@app.route('/api/internal/cameras/<int:camera_id>/detections', methods=['GET'])
def internal_get_camera_detections(camera_id):
    """Get recent detections for a camera (for telegram bot)"""
    internal_key = request.headers.get('X-Internal-Key', '')
    expected_key = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
    if internal_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401

    camera = Camera.query.get_or_404(camera_id)

    # Get recent attendance logs for this camera (last 10 minutes)
    ten_min_ago = utc_now() - timedelta(minutes=10)
    recent_logs = AttendanceLog.query.filter(
        AttendanceLog.camera_id == camera_id,
        AttendanceLog.timestamp >= ten_min_ago
    ).order_by(AttendanceLog.timestamp.desc()).limit(20).all()

    people = []
    seen_employees = set()
    for log in recent_logs:
        if log.employee_id not in seen_employees:
            seen_employees.add(log.employee_id)
            people.append({
                'employee_name': log.employee.name if log.employee else 'Unknown',
                'employee_id': log.employee.employee_id if log.employee else '',
                'department': log.employee.department if log.employee else '',
                'last_seen': log.timestamp.isoformat() if log.timestamp else '',
                'confidence': log.confidence
            })

    return jsonify({
        'camera_id': camera_id,
        'camera_name': camera.name,
        'people': people,
        'total': len(people)
    })


@app.route('/api/internal/cameras/search', methods=['GET'])
def internal_search_camera():
    """Search camera by name (for telegram bot)"""
    internal_key = request.headers.get('X-Internal-Key', '')
    expected_key = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
    if internal_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401

    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Search query is required'}), 400

    cameras = Camera.query.filter(
        Camera.active == True,
        Camera.name.ilike(f'%{query}%')
    ).all()

    return jsonify([{
        'id': c.id,
        'name': c.name,
        'location': c.location,
        'is_online': c.is_online()
    } for c in cameras])


# --- INTERNAL ENDPOINTS FOR WORKER ---

@app.route('/api/internal/worker/cameras', methods=['GET'])
def internal_worker_cameras():
    """Get active cameras with stream URLs for the worker process"""
    internal_key = request.headers.get('X-Internal-Key', '')
    expected_key = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
    if internal_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401

    cameras = Camera.query.filter_by(active=True, face_recognition_enabled=True).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'stream_url': c.get_stream_url(),
    } for c in cameras])


@app.route('/api/internal/worker/recording-cameras', methods=['GET'])
def internal_worker_recording_cameras():
    """Get ALL active cameras for recording (not just face-recognition ones)"""
    internal_key = request.headers.get('X-Internal-Key', '')
    expected_key = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
    if internal_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401

    cameras = Camera.query.filter_by(active=True).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'stream_url': c.get_stream_url(),
    } for c in cameras])


@app.route('/api/internal/worker/faces', methods=['GET'])
def internal_worker_faces():
    """Get all known face embeddings for the worker"""
    internal_key = request.headers.get('X-Internal-Key', '')
    expected_key = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
    if internal_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401

    employees = Employee.query.filter_by(active=True).all()
    faces = []
    for emp in employees:
        if emp.face_encoding:
            faces.append({
                'id': emp.id,
                'name': emp.name,
                'encoding': emp.face_encoding,  # JSON string of 512-dim vector
            })
    return jsonify(faces)


@app.route('/api/internal/worker/attendance', methods=['POST'])
def internal_worker_attendance():
    """Log attendance from worker process"""
    internal_key = request.headers.get('X-Internal-Key', '')
    expected_key = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
    if internal_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400

    # Support batch logging
    entries = data if isinstance(data, list) else [data]
    logged = 0
    for entry in entries:
        try:
            log = AttendanceLog(
                employee_id=entry['employee_id'],
                camera_id=entry['camera_id'],
                timestamp=datetime.fromisoformat(entry['timestamp']) if entry.get('timestamp') else utc_now(),
                confidence=entry.get('confidence'),
                event_type=entry.get('event_type', 'check-in')
            )
            db.session.add(log)
            logged += 1
        except Exception as e:
            logger.error(f"Failed to log attendance entry: {e}")

    db.session.commit()
    return jsonify({'logged': logged})


@app.route('/api/internal/worker/recording', methods=['POST'])
def internal_worker_recording():
    """Internal endpoint for the worker to report a recording event.
    Worker sends camera_id, employee_id (optional), event_type, and the recording file.
    """
    internal_key = request.headers.get('X-Internal-Key', '')
    expected_key = os.environ.get('INTERNAL_API_KEY', 'surveillance-internal-key')
    if internal_key != expected_key:
        return jsonify({'error': 'Unauthorized'}), 401

    camera_id = request.form.get('camera_id', type=int)
    employee_id = request.form.get('employee_id', type=int)
    event_type = request.form.get('event_type', 'face')
    start_time_str = request.form.get('start_time')
    end_time_str = request.form.get('end_time')

    if not camera_id:
        return jsonify({'error': 'camera_id is required'}), 400
    if not start_time_str:
        return jsonify({'error': 'start_time is required'}), 400

    try:
        start_time = date_parser.parse(start_time_str)
    except Exception as e:
        return jsonify({'error': f'Invalid start_time: {e}'}), 400

    end_time = None
    if end_time_str:
        try:
            end_time = date_parser.parse(end_time_str)
        except Exception as e:
            logger.warning(f"Invalid end_time: {end_time_str}: {e}")

    file_path = None
    file_size = 0
    thumbnail_path = None

    # Handle recording file upload
    if 'file' in request.files:
        recording_file = request.files['file']
        timestamp_str = start_time.strftime('%Y%m%d_%H%M%S')
        filename = f"cam{camera_id}_{event_type}_{timestamp_str}.mp4"
        full_path = os.path.join(app.config['RECORDINGS_FOLDER'], filename)
        recording_file.save(full_path)
        file_path = filename
        file_size = os.path.getsize(full_path)

    # Handle thumbnail upload
    if 'thumbnail' in request.files:
        thumb_file = request.files['thumbnail']
        timestamp_str = start_time.strftime('%Y%m%d_%H%M%S')
        thumb_filename = f"cam{camera_id}_{event_type}_{timestamp_str}_thumb.jpg"
        thumb_full_path = os.path.join(app.config['RECORDINGS_FOLDER'], thumb_filename)
        thumb_file.save(thumb_full_path)
        thumbnail_path = thumb_filename

    recording = Recording(
        camera_id=camera_id,
        employee_id=employee_id if employee_id else None,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
        file_path=file_path,
        thumbnail_path=thumbnail_path,
        file_size=file_size,
    )
    db.session.add(recording)
    db.session.commit()

    logger.info(f"Recording logged: camera={camera_id}, type={event_type}, id={recording.id}")

    return jsonify({
        'message': 'Recording logged',
        'id': recording.id,
        'file_path': file_path
    }), 201


# --- AUDIT LOG API ---

@app.route('/api/audit', methods=['GET'])
@token_required
@role_required('super_admin', 'admin')
def get_audit_logs(current_user):
    """View audit trail (admin only)"""
    page = request.args.get('page', type=int, default=1)
    per_page = request.args.get('per_page', type=int, default=50)
    per_page = min(per_page, 200)

    query = AuditLog.query
    action = request.args.get('action')
    source = request.args.get('source')
    if action:
        query = query.filter_by(action=action)
    if source:
        query = query.filter_by(source=source)

    pagination = query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [{
            'id': log.id,
            'username': log.username,
            'action': log.action,
            'resource_type': log.resource_type,
            'resource_id': log.resource_id,
            'details': log.details,
            'ip_address': log.ip_address,
            'source': log.source,
            'timestamp': log.timestamp.isoformat() if log.timestamp else None
        } for log in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': pagination.page
    })


@app.route('/api/audit/logins', methods=['GET'])
@token_required
@role_required('super_admin', 'admin')
def get_login_audit_logs(current_user):
    """View login history (admin only)"""
    page = request.args.get('page', type=int, default=1)
    per_page = request.args.get('per_page', type=int, default=50)
    per_page = min(per_page, 200)

    query = AuditLog.query.filter(AuditLog.action.in_(['login_success', 'login_failed']))

    username = request.args.get('username', type=str)
    if username:
        query = query.filter(AuditLog.username.ilike(f"%{username.strip()}%"))

    pagination = query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [{
            'id': log.id,
            'username': log.username,
            'action': log.action,
            'details': log.details,
            'ip_address': log.ip_address,
            'source': log.source,
            'timestamp': log.timestamp.isoformat() if log.timestamp else None
        } for log in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': pagination.page,
        'per_page': per_page
    })


# --- INITIALIZATION ---
with app.app_context():
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    db.create_all()

    # Seed departments from already existing employees (for old databases)
    existing_departments = db.session.query(Employee.department).distinct().all()
    for row in existing_departments:
        if row[0]:
            ensure_department_exists(row[0])
    db.session.commit()

    # Migrate existing JSON face_encoding to blob format
    employees_without_blob = Employee.query.filter(
        Employee.face_encoding.isnot(None),
        Employee.face_encoding_blob.is_(None),
        Employee.active == True
    ).all()
    migrated = 0
    for emp in employees_without_blob:
        try:
            vec = np.array(json.loads(emp.face_encoding), dtype=np.float32)
            if vec.shape[0] == 512:
                emp.face_encoding_blob = vec.tobytes()
                migrated += 1
        except Exception as e:
            logger.warning(f"Failed to migrate face encoding for employee {emp.id}: {e}")
    if migrated:
        db.session.commit()
        logger.info(f"Migrated {migrated} face encodings to binary format")

    if not User.query.filter_by(username='admin').first():
        u = User(username='admin', role='admin')
        u.set_password('admin123')
        db.session.add(u)
        db.session.commit()
        logger.info("Admin user created (admin/admin123)")

    try:
        face_engine.load()
        logger.info("Face recognition model loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load face recognition model: {e}")

    load_face_db_to_memory()

    # Pre-register all active camera streams in go2rtc for instant playback
    # Camera sends H.265/HEVC which Chrome cannot play via MSE.
    # Solution: raw RTSP + ffmpeg:raw#video=h264 transcoder for browser playback.
    def _register_go2rtc_streams():
        import time
        time.sleep(3)  # Wait for go2rtc to be ready
        go2rtc_host = os.environ.get('GO2RTC_HOST', 'localhost')
        go2rtc_port = os.environ.get('GO2RTC_PORT', '1984')
        base = f"http://{go2rtc_host}:{go2rtc_port}/api/streams"
        try:
            with app.app_context():
                cameras = Camera.query.filter_by(active=True).all()
                registered = 0
                for cam in cameras:
                    url = cam.get_stream_url()
                    if url:
                        try:
                            import requests as _req
                            # 1) Raw RTSP source (H.265, for poster/snapshots/worker)
                            _req.put(base, params={'src': url, 'name': f'camera_{cam.id}_raw'}, timeout=5)
                            # 2) FFmpeg transcoder: reads from raw H.265, outputs H.264 for browser MSE
                            _req.put(base, params={
                                'src': f'ffmpeg:camera_{cam.id}_raw#video=h264',
                                'name': f'camera_{cam.id}'
                            }, timeout=5)
                            registered += 1
                        except Exception as e:
                            logger.debug(f"Failed to register camera {cam.id} in go2rtc: {e}")
                logger.info(f"Pre-registered {registered}/{len(cameras)} camera streams in go2rtc (H.265->H.264)")
        except Exception as e:
            logger.error(f"Failed to pre-register go2rtc streams: {e}")

    import threading
    threading.Thread(target=_register_go2rtc_streams, daemon=True).start()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('FLASK_PORT', 5002)), debug=False, allow_unsafe_werkzeug=True)
