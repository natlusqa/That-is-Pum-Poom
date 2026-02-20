import os
import cv2
import numpy as np
import sqlite3
import json
import threading
from face_core import face_engine
from face_matching import build_face_matrix, match_face

# Pillow for proper Unicode text rendering (Cyrillic)
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

THRESHOLD = float(os.environ.get('FACE_THRESHOLD', '0.5'))


def _get_font(size=20):
    font_paths = [
        '/Library/Fonts/Arial Unicode.ttf',
        '/Library/Fonts/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/System/Library/Fonts/SFNSDisplay.ttf',
        'C:/Windows/Fonts/arial.ttf',
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
    """Draw unicode text onto an OpenCV BGR frame using PIL (if available)."""
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
RTSP_URL = 0


class VideoStream:
    """Threaded video capture for smooth reading"""
    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src)
        self.ret, self.frame = self.stream.read()
        self.stopped = False

    def start(self):
        threading.Thread(target=self.update, daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            self.ret, self.frame = self.stream.read()

    def read(self):
        return self.frame

    def stop(self):
        self.stopped = True
        self.stream.release()


def load_faces():
    """Load faces from DB and build normalized matrix for vectorized matching"""
    raw_faces = []
    if not os.path.exists(DB_PATH):
        return np.empty((0, 512), dtype=np.float32), [], []
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id, name, face_encoding FROM employee WHERE active=1")
        rows = cur.fetchall()
        for emp_id, name, enc in rows:
            if enc:
                try:
                    vec = np.array(json.loads(enc), dtype=np.float32)
                    if vec.shape[0] == 512:
                        raw_faces.append((emp_id, name, vec))
                except Exception:
                    pass
        conn.close()
    except Exception:
        pass

    return build_face_matrix(raw_faces)


def run():
    face_engine.load()
    face_matrix, face_ids, face_names = load_faces()
    print(f"Monitor started. Known faces: {len(face_ids)}")

    vs = VideoStream(RTSP_URL).start()

    while True:
        frame = vs.read()
        if frame is None:
            continue

        all_faces = face_engine.get_all_faces(frame)

        for face_info in all_faces:
            v_cam = face_info['embedding']
            bbox = face_info['bbox']

            emp_id, name, sim = match_face(
                v_cam, face_matrix, face_ids, face_names,
                threshold=THRESHOLD
            )

            if emp_id is not None:
                label = f"{name} ({sim:.2f})"
                color = (0, 255, 0)  # Green
            else:
                label = "Unknown"
                color = (0, 0, 255)  # Red

            x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            text_y = y1 - 10
            if text_y < 12:
                text_y = y1 + 20

            draw_text_unicode(frame, label, (x1, text_y), color=color, size=18)

        cv2.imshow("Monitor", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    vs.stop()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run()
