# Surveillance AI — Intelligent Video Surveillance System

An intelligent video surveillance system with real-time face recognition, automated attendance logging, and a Telegram bot interface for remote management.

## Features

### Core
- **Real-time Face Recognition** — InsightFace (buffalo_l) model with 512-dimensional embeddings, GPU-accelerated (CUDA) with CPU fallback
- **Multi-Camera Support** — Simultaneous processing of up to 10 RTSP/IP cameras with auto-reconnection
- **Automated Attendance** — Automatic check-in logging when employees are detected on camera
- **Live Streaming** — WebRTC/MJPEG video streams via go2rtc bridge with real-time bounding box overlay
- **Role-Based Access Control** — JWT authentication with 4 roles: `super_admin`, `admin`, `hr`, `employee`

### Smart Camera Auto-Discovery (v3)
- **One-click discovery** — finds all IP cameras on the local network automatically
- **Fast:** typical scan completes in 15-30 seconds (hard limit: 5 minutes)
- **Multi-protocol detection:** ARP table, ONVIF WS-Discovery, UPnP/SSDP, TCP port sweep
- **RTSP Server fingerprinting** — identifies manufacturer (Hikvision, Dahua, XMEye, Axis, Reolink, etc.) from RTSP `Server` header
- **MAC OUI lookup** — 30+ camera vendor prefixes for priority credential ordering
- **53 statistically ordered credential+path combos** — covers ~95% of IP cameras worldwide
- **Smart fast-fail** — wrong credentials rejected in ~0.15s via OpenCV, correct match in ~2.3s
- **Extended combo fallback** — 100+ additional credential/path permutations if standard combos fail
- **Safe:** automatically excludes local machine IPs (Docker, VPN, WSL, VirtualBox)

### Web Dashboard
- Camera management (add/edit/delete, RTSP/DVR connection types)
- **Camera auto-discovery** with real-time progress, manufacturer detection, and one-click add
- Employee registration with facial photo and automatic face embedding extraction
- Attendance logs with filtering (date, employee, camera, department) and export (CSV, Excel, PDF)
- Live camera view with face detection overlay via WebSocket
- Department management
- User management (admin panel)

### Telegram Bot (Saphena AI)
- Password-protected sessions with automatic timeout
- Add employees remotely via photo + name
- Check who's currently in a room (by camera ID or name)
- Get live snapshots from any camera
- Rename cameras
- Natural language support (Russian)

### Security & Audit
- Immutable audit trail for all sensitive operations
- Internal API authentication with shared keys
- Camera credential masking in API responses
- Session management with configurable timeout

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  IP Cameras  │────▶│   Worker     │────▶│  Flask API   │
│  (RTSP)      │     │  (ML infer.) │     │  (Backend)   │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                │
                    ┌──────────────┐     ┌──────┴───────┐
                    │ Telegram Bot │────▶│  PostgreSQL   │
                    │  (Saphena)   │     │  (Database)   │
                    └──────────────┘     └──────────────┘
                                                │
┌─────────────┐     ┌──────────────┐     ┌──────┴───────┐
│   Browser   │────▶│    Nginx     │────▶│   React App  │
│   (Client)  │     │  (Reverse    │     │  (Frontend)  │
└─────────────┘     │   Proxy)     │     └──────────────┘
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │   go2rtc     │
                    │ (RTSP→Web)   │
                    └──────────────┘
```

### Services (Docker Compose)

| Service | Description | Port |
|---------|-------------|------|
| `postgres` | PostgreSQL 16 database | 5435 (external) |
| `backend` | Flask API + ML inference | 5002 |
| `frontend` | React SPA via Nginx | 80 |
| `go2rtc` | RTSP → MJPEG/WebRTC bridge | internal |
| `telegram-bot` | Saphena AI Telegram bot | polling |
| `worker` | Camera processor (runs locally) | — |

---

## Tech Stack

**Backend:** Python 3.11, Flask, SQLAlchemy, Flask-SocketIO, PyJWT
**Frontend:** React 18, Vite, React Router, Axios, Socket.IO
**ML/AI:** InsightFace, ONNX Runtime (CUDA/CPU), OpenCV
**Database:** PostgreSQL 16
**Infrastructure:** Docker, Nginx, go2rtc
**Telegram:** python-telegram-bot 21.3

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Git

### 1. Clone the repository
```bash
git clone https://github.com/Morgan141414/That-is-Pum-Poom.git
cd That-is-Pum-Poom
```

### 2. Configure environment
```bash
cp .env.example .env
```

Edit `.env` and fill in your values:
```env
POSTGRES_PASSWORD=your_secure_password
SECRET_KEY=your-random-secret-key
TELEGRAM_BOT_TOKEN=your_token_from_botfather
TELEGRAM_BOT_PASSWORD=your_bot_password
INTERNAL_API_KEY=your-random-internal-key
```

**Getting a Telegram bot token:**
1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the instructions
3. Copy the token into your `.env` file

### 3. Build and start
```bash
docker compose up -d --build
```

First start will download the InsightFace model (~300MB). Wait for it to complete:
```bash
docker compose logs backend -f
```

You should see:
```
Face recognition model loaded successfully
Face cache updated: 0 faces loaded
Running on http://0.0.0.0:5002
```

### 4. Access the system

| Interface | URL | Credentials |
|-----------|-----|-------------|
| Web Dashboard | http://localhost | `admin` / `admin123` |
| API Health | http://localhost:5002/api/health | — |
| Telegram Bot | Your bot link from BotFather | Bot password from `.env` |

### 5. Start the camera worker

The worker runs on the machine that has network access to the cameras:

```bash
cd backend
pip install -r requirements.txt

export API_BASE_URL=http://your-server-ip:5002
export FACE_THRESHOLD=0.5
export FACE_COOLDOWN=60
export FRAME_SKIP=2
export MAX_WORKERS=10

python worker_multiproc.py
```

---

## Local backend for ONVIF camera discovery

**Why:** ONVIF WS-Discovery uses multicast (UDP) on the LAN. A backend running inside Docker cannot see this traffic, so **camera auto-discovery does not work** when the backend is in a container.

**Solution:** run the rest of the stack in Docker, but run the **backend on the host**. The frontend and Telegram bot will talk to the backend via `host.docker.internal`.

### 1. Start stack without backend container

```bash
docker compose -f docker-compose.yml -f docker-compose.local-backend.yml up -d
```

This starts: Postgres, frontend, go2rtc, telegram-bot. The backend container is not started.

### 2. Run backend on the host

**Windows (PowerShell):**
```powershell
.\scripts\run-backend-local.ps1
```

**Linux / macOS:**
```bash
chmod +x scripts/run-backend-local.sh
./scripts/run-backend-local.sh
```

**Or manually:** from the project root, set the database URL to the exposed Postgres port (e.g. `5435`), then start the app:

```bash
cd backend
export DATABASE_URL="postgresql://surveillance:YOUR_POSTGRES_PASSWORD@localhost:5435/surveillance"
export FLASK_PORT=5002
export GO2RTC_HOST=localhost
export GO2RTC_PORT=1984
pip install -r requirements.txt   # if not already
python app.py
```

### 3. Use the system

- **Web:** http://localhost:8080 (or http://localhost if you kept port 80) — Nginx in Docker proxies `/api/` and `/socket.io/` to the backend on the host.
- **ONVIF discovery:** Cameras → **Discover cameras** — scanning will now see devices on your LAN.

**Note:** On Linux, `host.docker.internal` is added by the override via `extra_hosts: host-gateway`. On Docker Desktop (Windows/macOS) it works out of the box.

---

## Usage Guide

### Adding Cameras
1. Log in to the web dashboard
2. Go to **Cameras** → **Add Camera**
3. Choose connection type:
   - **Direct**: Enter IP, port, username, password, RTSP path
   - **DVR**: Enter full RTSP URL
4. Enable **Face Recognition** for cameras you want to use for attendance

### Registering Employees
**Via Web:**
1. Go to **Employees** → **Add Employee**
2. Enter name, department, and upload a clear face photo
3. The system will automatically extract and store the face embedding

**Via Telegram Bot:**
1. Send `/start` to your bot and enter the password
2. Tap **Add Employee** or send `/add`
3. Follow the prompts: name → department → photo

### Viewing Attendance
1. Go to **Attendance** in the web dashboard
2. Filter by date range, employee, camera, or department
3. Export to CSV, Excel, or PDF

### Telegram Bot Commands
| Command | Description |
|---------|-------------|
| `/start` | Start the bot and authenticate |
| `/cameras` | List all cameras with status |
| `/who` | Check who's in a specific room |
| `/snapshot` | Get a live snapshot from a camera |
| `/add` | Register a new employee |
| `/rename` | Rename a camera |
| `/help` | Show all commands |
| `/logout` | End the session |

---

## API Reference

### Authentication
```
POST /api/auth/login
Body: {"username": "admin", "password": "admin123"}
Response: {"token": "JWT_TOKEN", "user": {...}}
```

All protected endpoints require:
```
Authorization: Bearer <JWT_TOKEN>
```

### Key Endpoints
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/health` | No | System health check |
| POST | `/api/auth/login` | No | JWT login |
| GET | `/api/cameras` | Yes | List cameras |
| POST | `/api/cameras` | Admin | Add camera |
| GET | `/api/employees` | Yes | List employees |
| POST | `/api/employees` | HR/Admin | Register employee with photo |
| GET | `/api/attendance` | Yes | Attendance logs (paginated, filterable) |
| GET | `/api/attendance/export` | Yes | Export (CSV/XLSX/PDF) |
| GET | `/api/attendance/stats` | Yes | Aggregated statistics |
| GET | `/api/cameras/{id}/snapshot` | Yes | Camera snapshot |
| GET | `/api/audit` | Admin | Audit trail |
| POST | `/api/camera-discovery/scan` | Admin | Start auto-discovery scan |
| GET | `/api/camera-discovery/status` | Yes | Discovery progress & results |
| POST | `/api/camera-discovery/stop` | Admin | Stop running scan |
| POST | `/api/camera-discovery/add` | Admin | Add discovered camera |
| POST | `/api/camera-discovery/add-all` | Admin | Add all discovered cameras |
| GET/POST | `/api/users` | Super Admin | User management |
| GET/POST | `/api/departments` | HR/Admin | Department management |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_PASSWORD` | — | PostgreSQL password |
| `SECRET_KEY` | — | Flask JWT signing key |
| `FACE_MODEL` | `buffalo_l` | InsightFace model name |
| `FACE_THRESHOLD` | `0.5` | Face match confidence threshold (0-1) |
| `FACE_COOLDOWN` | `60` | Seconds between duplicate detections |
| `FRAME_SKIP` | `2` | Process every Nth frame |
| `MAX_WORKERS` | `10` | Max concurrent camera workers |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token from BotFather |
| `TELEGRAM_BOT_PASSWORD` | — | Password for bot authentication |
| `INTERNAL_API_KEY` | — | Shared key for internal API |
| `SESSION_TIMEOUT` | `3600` | Bot session timeout (seconds) |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Project Structure

```
surveillance-ai/
├── backend/
│   ├── app.py                    # Flask API + all endpoints + models
│   ├── camera_discovery.py       # Smart auto-discovery engine v3
│   ├── face_core.py              # InsightFace wrapper (detection + embeddings)
│   ├── face_matching.py          # Vectorized cosine similarity matching
│   ├── worker_multiproc.py       # Multi-process camera worker
│   ├── telegram_bot.py           # Saphena AI Telegram bot
│   ├── monitor.py                # Live video display (development)
│   ├── camera-endpoint-detector.py # RTSP channel discovery tool
│   ├── requirements.txt          # Python dependencies
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/                # React pages (Dashboard, Cameras, Employees, etc.)
│   │   ├── components/           # UI components (BoundingBoxOverlay, WebRTCPlayer, etc.)
│   │   ├── hooks/                # Custom hooks (useDetectionSocket, useAuthImage)
│   │   ├── services/api.js       # Axios API client
│   │   └── App.jsx               # Root component with routing
│   ├── package.json
│   └── Dockerfile
├── nginx/
│   ├── nginx.conf                # Default: backend inside Docker
│   └── nginx.local-backend.conf  # Backend on host (for ONVIF discovery)
├── go2rtc/
│   └── go2rtc.yaml               # RTSP bridge configuration
├── scripts/
│   ├── run-backend-local.ps1     # Windows: run backend on host
│   └── run-backend-local.sh      # Linux/macOS: run backend on host
├── docker-compose.yml
├── docker-compose.local-backend.yml  # Override for host backend
├── .env.example
└── README.md
```

---

## Troubleshooting

### Port conflict on startup
If PostgreSQL port 5432 is already in use, the compose file maps to **5434** externally. Internal connectivity is unaffected.

### Model download hangs
The InsightFace buffalo_l model (~300MB) downloads on first start. If it fails:
```bash
docker compose restart backend
```

### Camera not connecting
1. Verify the RTSP URL works: `ffplay rtsp://user:pass@ip:554/path`
2. Check that the worker machine has network access to the camera
3. Ensure the camera is enabled and face recognition is toggled on

### Telegram bot not responding
1. Check the bot token is correct in `.env`
2. Verify the bot container is running: `docker compose logs telegram-bot`
3. Make sure no other instance is polling the same bot token

---

## License

This project is proprietary software. All rights reserved.
