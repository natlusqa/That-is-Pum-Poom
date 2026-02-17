# KORGAN AI — Personal AI Operating System
## Architectural Design Document v1.0

**Кодовое имя**: KORGAN  
**Создатель**: Мистер Корган (Amanat Korgan)  
**Класс системы**: Personal AI Operating System (PAIOS)  
**Статус**: Phase 1 — Foundation

---

## 1. АРХИТЕКТУРНАЯ СХЕМА ВЕРХНЕГО УРОВНЯ

```
┌─────────────────────────────────────────────────────────────────┐
│                     INTERFACE LAYER                              │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Desktop  │  │   Telegram   │  │     Voice Interface      │  │
│  │ Overlay  │  │     Bot      │  │   (Whisper + TTS)        │  │
│  │(Electron)│  │  (Primary)   │  │                          │  │
│  └────┬─────┘  └──────┬───────┘  └────────────┬─────────────┘  │
│       │               │                       │                 │
└───────┼───────────────┼───────────────────────┼─────────────────┘
        │               │                       │
        ▼               ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CORE API GATEWAY                           │
│              FastAPI + WebSocket + Event Bus                     │
│                    (Redis Pub/Sub)                               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐  ┌─────────────────┐  ┌──────────────────┐
│  CORE BRAIN  │  │  AGENT FRAMEWORK│  │ AUTONOMY ENGINE  │
│              │  │                 │  │                  │
│ • Orchestr.  │  │ • Git Agent    │  │ • Decision Tree  │
│ • Reasoning  │  │ • PS Agent     │  │ • Permission Mgr │
│ • Router     │  │ • Code Agent   │  │ • Level Control  │
│ • LLM Mgr   │  │ • System Agent │  │ • Allowlist      │
└──────┬───────┘  └────────┬────────┘  └────────┬─────────┘
       │                   │                    │
       ▼                   ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MEMORY SYSTEM                                 │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ PostgreSQL │  │ ChromaDB     │  │    Redis Cache         │  │
│  │ (Long-term)│  │ (Vectors)    │  │    (Short-term)        │  │
│  └────────────┘  └──────────────┘  └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
        │                                       │
        ▼                                       ▼
┌──────────────────┐                 ┌────────────────────────┐
│  SECURITY LAYER  │                 │   INTELLIGENCE ENGINE  │
│                  │                 │                        │
│ • Sandbox        │                 │ • Self-analysis        │
│ • Audit Log      │                 │ • Daily Brief          │
│ • Rollback       │                 │ • Code Scoring         │
│ • Rate Limiter   │                 │ • Predictive Engine    │
│ • Loop Guard     │                 │ • Crisis Mode          │
└──────────────────┘                 └────────────────────────┘
        │
        ▼
┌──────────────────┐  ┌──────────────────┐
│  VISION SYSTEM   │  │   VOICE SYSTEM   │
│                  │  │                  │
│ • Face Detect    │  │ • Whisper STT    │
│ • Embeddings     │  │ • Piper TTS      │
│ • Verification   │  │ • Speaker ID     │
└──────────────────┘  └──────────────────┘
```

---

## 2. ДЕТАЛЬНЫЙ СТЕК ТЕХНОЛОГИЙ

### 2.1 Core Runtime
| Компонент | Технология | Обоснование |
|-----------|-----------|-------------|
| Backend API | **FastAPI 0.115+** (Python 3.12) | Async, WebSocket, высокая производительность |
| Event Bus | **Redis 7.x Pub/Sub + Streams** | Реальное время, персистентные очереди |
| Task Queue | **Celery 5.x + Redis broker** | Фоновые задачи, retry-логика |
| Database | **PostgreSQL 16** | ACID, JSONB, полнотекстовый поиск |
| Vector DB | **ChromaDB** (embedded) | Лёгкий, GPU-ускорение, Python-native |
| Cache | **Redis 7.x** | TTL, pub/sub, session state |
| Orchestration | **Docker Compose** | Единая среда, изоляция |
| Automation | **n8n** (self-hosted) | Visual workflows, webhook triggers |

### 2.2 AI / LLM Layer
| Компонент | Технология | Обоснование |
|-----------|-----------|-------------|
| Local LLM Runtime | **Ollama** | Простой API, авто-управление VRAM |
| Local Model (primary) | **Mistral 7B Q4_K_M** / **Llama 3.1 8B Q4** | 4-5 GB VRAM, быстрый inference |
| Local Model (code) | **DeepSeek Coder V2 Lite** | Специализация на коде |
| Cloud LLM (complex) | **Claude API** / **GPT-4o** | Сложные reasoning задачи |
| Embedding Model | **nomic-embed-text** (Ollama) | Локальный, 768-dim, быстрый |
| LLM Router | Custom Python | Маршрутизация по сложности задачи |

### 2.3 Voice System
| Компонент | Технология | Обоснование |
|-----------|-----------|-------------|
| STT | **faster-whisper** (CTranslate2) | 4x быстрее оригинала, ~1GB VRAM |
| TTS | **Piper TTS** | Локальный, быстрый, мужские голоса |
| Speaker Recognition | **SpeechBrain** (ECAPA-TDNN) | SOTA speaker verification |
| Audio I/O | **sounddevice** + **webrtcvad** | VAD, низкая латентность |

### 2.4 Vision System
| Компонент | Технология | Обоснование |
|-----------|-----------|-------------|
| Face Detection | **InsightFace** (RetinaFace) | Высокая точность, GPU |
| Face Embeddings | **ArcFace** (via InsightFace) | 512-dim, SOTA верификация |
| Camera Capture | **OpenCV** | Универсальный, Windows-native |

### 2.5 Desktop Application
| Компонент | Технология | Обоснование |
|-----------|-----------|-------------|
| Framework | **Electron 30+** | Прозрачные окна, overlay, кроссплатформ |
| Frontend | **React 18 + TypeScript** | Компонентный UI |
| Styling | **Tailwind CSS** + custom shaders | Синяя подсветка, анимации |
| State | **Zustand** | Лёгкий, без бойлерплейта |
| IPC | **WebSocket** → Core API | Реальное время |

### 2.6 Telegram Interface
| Компонент | Технология | Обоснование |
|-----------|-----------|-------------|
| Bot Framework | **aiogram 3.x** | Async, middleware, FSM |
| Voice Processing | **faster-whisper** (shared) | Расшифровка голосовых |

### 2.7 VRAM Budget (RTX 5060 8GB)
```
┌─────────────────────────────────────┐
│ VRAM ALLOCATION STRATEGY            │
├─────────────────────────────────────┤
│ Ollama (Mistral 7B Q4)   ~4.5 GB   │
│ faster-whisper (medium)   ~1.0 GB   │
│ InsightFace (ArcFace)     ~0.5 GB   │
│ Piper TTS                 ~0.2 GB   │
│ System / Overhead         ~1.8 GB   │
├─────────────────────────────────────┤
│ TOTAL                     ~8.0 GB   │
└─────────────────────────────────────┘

Стратегия: Dynamic VRAM Management
- При активном voice: выгрузка InsightFace
- При активном vision: уменьшение контекста LLM
- Ollama auto-offload при бездействии >5 мин
```

---

## 3. МОДУЛЬНАЯ СТРУКТУРА ПРОЕКТА

```
korgan-ai/
├── docs/
│   └── ARCHITECTURE.md          # Этот документ
├── config/
│   ├── permissions.json          # Матрица разрешений
│   ├── autonomy.json             # Уровни автономности
│   └── system.json               # Системная конфигурация
├── core/
│   ├── brain/
│   │   ├── __init__.py
│   │   ├── orchestrator.py       # Главный дирижёр системы
│   │   ├── reasoning.py          # Chain-of-thought, reasoning log
│   │   ├── router.py             # LLM router (local vs cloud)
│   │   └── llm_manager.py        # Управление моделями
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── manager.py            # Unified Memory API
│   │   ├── vector_store.py       # ChromaDB operations
│   │   ├── compression.py        # Memory compression engine
│   │   └── models.py             # SQLAlchemy models
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract Agent class
│   │   ├── git_agent.py          # Git operations agent
│   │   ├── powershell_agent.py   # System command agent
│   │   ├── code_agent.py         # Code analysis/fix agent
│   │   └── system_agent.py       # OS management agent
│   ├── security/
│   │   ├── __init__.py
│   │   ├── sandbox.py            # Command sandboxing
│   │   ├── permissions.py        # Permission enforcement
│   │   ├── audit.py              # Action audit logger
│   │   └── rollback.py           # Rollback mechanism
│   ├── autonomy/
│   │   ├── __init__.py
│   │   ├── engine.py             # Autonomy decision engine
│   │   ├── levels.py             # Level definitions
│   │   └── decision.py           # Decision tree logic
│   └── api/
│       ├── __init__.py
│       ├── main.py               # FastAPI application
│       ├── websocket.py          # WebSocket handler
│       └── routes/
│           ├── __init__.py
│           ├── brain.py           # /api/brain/*
│           ├── agents.py          # /api/agents/*
│           ├── memory.py          # /api/memory/*
│           └── system.py          # /api/system/*
├── voice/
│   ├── __init__.py
│   ├── whisper_stt.py            # Speech-to-text
│   ├── tts_engine.py             # Text-to-speech (Piper)
│   └── speaker_recognition.py   # Speaker verification
├── vision/
│   ├── __init__.py
│   ├── face_recognition.py       # Face detection + verification
│   └── embeddings.py             # Face embedding storage
├── desktop/
│   ├── package.json
│   ├── electron-builder.json
│   ├── main.js                   # Electron main process
│   ├── preload.js                # Secure bridge
│   └── src/
│       ├── App.tsx
│       ├── index.tsx
│       ├── components/
│       │   ├── Overlay.tsx        # Blue glow overlay
│       │   ├── StatusBar.tsx      # Thinking/speaking status
│       │   ├── ActionLog.tsx      # Action journal
│       │   └── AutonomyPanel.tsx  # Autonomy mode toggle
│       └── styles/
│           ├── globals.css
│           └── overlay.css        # Blue edge glow animations
├── telegram/
│   ├── __init__.py
│   ├── bot.py                    # Bot entry point
│   └── handlers/
│       ├── __init__.py
│       ├── commands.py            # /start, /status, /mode
│       ├── voice.py               # Voice message processing
│       └── confirmations.py       # Autonomy confirmations
├── intelligence/
│   ├── __init__.py
│   ├── self_analysis.py          # Self-evaluation of decisions
│   ├── daily_brief.py            # Morning intelligence report
│   ├── code_scoring.py           # Code quality metrics
│   ├── predictive.py             # Predictive recommendations
│   ├── crisis.py                 # Crisis detection & response
│   └── improvement.py            # Continuous improvement engine
├── docker/
│   ├── Dockerfile.core            # Core brain + API
│   ├── Dockerfile.voice           # Voice services
│   ├── Dockerfile.vision          # Vision services
│   └── Dockerfile.telegram        # Telegram bot
├── n8n/
│   └── workflows/
│       ├── daily_brief.json       # Morning report workflow
│       └── health_check.json      # System health workflow
├── scripts/
│   ├── setup.ps1                  # Windows setup script
│   ├── health_check.py            # Health monitoring
│   └── migrate_db.py              # Database migrations
├── tests/
│   ├── unit/
│   └── integration/
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 4. ДЕТАЛЬНОЕ ОПИСАНИЕ КАЖДОГО УРОВНЯ

### 4.1 CORE BRAIN

**Назначение**: Центральный интеллект системы. Принимает входные данные от всех интерфейсов, выбирает стратегию обработки, маршрутизирует к агентам, формирует ответ.

**Компоненты**:

#### Orchestrator (`orchestrator.py`)
- Единая точка входа для всех запросов
- Определяет intent пользователя
- Создаёт execution plan
- Координирует агентов
- Формирует финальный ответ
- Логирует весь reasoning chain

#### Reasoning Engine (`reasoning.py`)
- Chain-of-Thought генерация
- Decomposition сложных задач
- Оценка confidence level
- Запись reasoning log в PostgreSQL

#### LLM Router (`router.py`)
```
Входящий запрос
       │
       ▼
┌──────────────┐
│ Complexity   │──── Simple (< 100 tokens) ──→ Local Mistral 7B
│ Analyzer     │──── Medium (code tasks)   ──→ Local DeepSeek Coder
│              │──── Complex (reasoning)   ──→ Cloud Claude/GPT-4o
│              │──── Critical (autonomy)   ──→ Cloud + Local verify
└──────────────┘
```

**Маршрутизация по критериям**:
- Длина контекста (>4K → cloud)
- Тип задачи (код → DeepSeek, reasoning → Claude)
- Уровень критичности (системные команды → двойная проверка)
- Стоимость (бюджет API в system.json)

#### LLM Manager (`llm_manager.py`)
- Управление Ollama моделями (pull, load, unload)
- Мониторинг VRAM
- Failover: если local недоступен → cloud
- Rate limiting для cloud API

**Риски уровня**:
| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| VRAM overflow | Средняя | Dynamic model offload, мониторинг |
| Cloud API down | Низкая | Fallback на local модель |
| Hallucination | Средняя | Reasoning log + self-check |
| Latency spike | Средняя | Redis cache популярных запросов |

---

### 4.2 MEMORY SYSTEM

**Назначение**: Персистентная память с тремя уровнями: оперативная (Redis), семантическая (ChromaDB), долговременная (PostgreSQL).

**Архитектура памяти**:
```
┌─────────────────────────────────────────────┐
│              MEMORY MANAGER                  │
│         (Unified Memory API)                 │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────────────┐  TTL: 1h                  │
│  │ Redis Cache  │  Working memory           │
│  │ (L1 - Hot)  │  Current context           │
│  │             │  Session state             │
│  └──────┬──────┘                            │
│         │ overflow                          │
│         ▼                                   │
│  ┌─────────────┐  Retention: 30d           │
│  │  ChromaDB   │  Semantic search           │
│  │(L2-Vectors) │  Conversation embeddings   │
│  │             │  Project knowledge          │
│  └──────┬──────┘                            │
│         │ archive                           │
│         ▼                                   │
│  ┌─────────────┐  Retention: ∞             │
│  │ PostgreSQL  │  Facts, decisions           │
│  │ (L3 - Cold) │  User preferences          │
│  │             │  Audit log                  │
│  └─────────────┘                            │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ COMPRESSION ENGINE                  │    │
│  │ • Summarize old conversations       │    │
│  │ • Extract key facts → PostgreSQL    │    │
│  │ • Merge duplicate vectors           │    │
│  │ • Compress reasoning logs           │    │
│  │ • Schedule: daily at 03:00          │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

**Схема PostgreSQL**:
```sql
-- Conversations
CREATE TABLE conversations (
    id UUID PRIMARY KEY,
    interface TEXT,        -- 'telegram', 'desktop', 'voice'
    started_at TIMESTAMPTZ,
    summary TEXT,
    metadata JSONB
);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id),
    role TEXT,             -- 'user', 'assistant', 'system'
    content TEXT,
    reasoning TEXT,        -- chain-of-thought log
    tokens_used INTEGER,
    model_used TEXT,
    created_at TIMESTAMPTZ
);

-- Facts (extracted knowledge)
CREATE TABLE facts (
    id UUID PRIMARY KEY,
    category TEXT,         -- 'preference', 'project', 'decision', 'personal'
    key TEXT,
    value TEXT,
    confidence FLOAT,
    source_message_id UUID REFERENCES messages(id),
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

-- Audit Log
CREATE TABLE audit_log (
    id UUID PRIMARY KEY,
    action TEXT,
    agent TEXT,
    details JSONB,
    risk_level TEXT,       -- 'low', 'medium', 'high', 'critical'
    autonomy_level TEXT,
    approved_by TEXT,      -- 'user', 'auto', 'conditional'
    rollback_data JSONB,
    created_at TIMESTAMPTZ
);

-- Agent Actions
CREATE TABLE agent_actions (
    id UUID PRIMARY KEY,
    agent_name TEXT,
    action_type TEXT,
    input_data JSONB,
    output_data JSONB,
    status TEXT,           -- 'pending', 'running', 'success', 'failed', 'rolled_back'
    duration_ms INTEGER,
    created_at TIMESTAMPTZ
);
```

**Риски**:
| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Memory bloat | Средняя | Compression engine, TTL |
| Vector drift | Низкая | Периодический re-index |
| Data loss | Низкая | PostgreSQL WAL + daily backup |

---

### 4.3 AGENT FRAMEWORK

**Назначение**: Специализированные агенты для выполнения конкретных категорий задач. Каждый агент наследует `BaseAgent` и имеет чёткие boundaries.

#### Base Agent Protocol
```python
class BaseAgent(ABC):
    name: str
    description: str
    allowed_actions: list[str]
    risk_level: str  # low, medium, high, critical
    requires_approval: bool
    
    async def plan(self, task) -> ActionPlan
    async def execute(self, plan) -> ActionResult
    async def rollback(self, action_id) -> bool
    async def validate(self, result) -> ValidationResult
```

#### Git Agent
```
Capabilities:
├── analyze_diff()      — анализ изменений в репозитории
├── generate_patch()    — создание patch файлов
├── dry_run()           — симуляция commit/push
├── commit()            — коммит с сообщением (requires approval)
├── push()              — push в remote (requires approval)
├── create_branch()     — создание веток
├── review_code()       — code review с комментариями
└── log_history()       — анализ git log

Flow:
  User request → analyze_diff → generate plan → dry_run → 
  → request approval (Telegram/Desktop) → execute → log
```

#### PowerShell Agent
```
Capabilities:
├── execute_command()   — выполнение PS команд (sandboxed)
├── get_system_info()   — информация о системе
├── manage_services()   — управление службами
├── manage_processes()  — процессы
├── file_operations()   — файловые операции (sandboxed paths)
└── network_info()      — сетевая информация

Sandbox Rules:
- Whitelist разрешённых команд
- Запрет: Remove-Item на системных путях
- Запрет: Registry modifications
- Таймаут: 30 секунд на команду
- Логирование каждой команды
```

#### Code Agent
```
Capabilities:
├── analyze_project()   — структура и метрики проекта
├── find_bugs()         — статический анализ
├── suggest_fixes()     — предложения исправлений
├── apply_fix()         — применение fix (requires approval)
├── generate_tests()    — генерация тестов
├── score_quality()     — code quality scoring
└── explain_code()      — объяснение кода

Stack Analysis:
- Python: pylint, mypy, ruff
- JS/TS: eslint patterns
- Generic: LLM-based review
```

#### System Agent
```
Capabilities:
├── monitor_resources() — CPU, RAM, GPU, Disk
├── manage_docker()     — Docker containers status
├── health_check()      — проверка всех сервисов
├── cleanup()           — temp files, logs rotation
└── backup()            — конфигурации и данные
```

---

### 4.4 COMMAND EXECUTION LAYER

**Назначение**: Безопасное выполнение системных команд через изолированный sandbox.

```
Command Request
       │
       ▼
┌──────────────┐
│  Permission  │──── Denied ──→ Log + Notify user
│   Check      │
└──────┬───────┘
       │ Allowed
       ▼
┌──────────────┐
│  Sandbox     │──── Restricted paths
│  Validator   │──── Command whitelist
│              │──── Timeout limits
└──────┬───────┘
       │ Valid
       ▼
┌──────────────┐
│  Execution   │──── subprocess with timeout
│  Engine      │──── stdout/stderr capture
│              │──── exit code check
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Audit Log   │──── Full command log
│  + Rollback  │──── Rollback data saved
│  Data        │──── Duration tracked
└──────────────┘
```

---

### 4.5 DESKTOP UI LAYER

**Назначение**: Прозрачный overlay поверх всех окон с синей подсветкой по краям при речи, статусом системы и журналом действий.

**Визуальная концепция**:
```
┌─────────────────────────────────────────────────────┐
│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│ ← Синий glow (top)
│░                                                   ░│
│░                                                   ░│
│░              [ Рабочий стол / Приложения ]         ░│ ← Прозрачная область
│░                                                   ░│
│░                                                   ░│
│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│ ← Синий glow (bottom)
│                                                     │
│  ┌─────────┐  ┌───────────┐  ┌───────────────────┐ │
│  │ STATUS  │  │  ACTIONS  │  │   AUTONOMY MODE   │ │
│  │Thinking…│  │ • Git pull│  │ ● Manual          │ │
│  │         │  │ • Scan..  │  │ ○ Suggestion      │ │
│  │ [====] │  │ • Fixed.. │  │ ○ Conditional     │ │
│  └─────────┘  └───────────┘  └───────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**Состояния overlay**:
- **Idle**: Без подсветки, минимальный UI
- **Listening**: Пульсирующий синий по краям
- **Thinking**: Бегущие синие частицы по периметру
- **Speaking**: Яркий синий glow, волновая анимация
- **Alert**: Оранжевый glow (требуется подтверждение)
- **Crisis**: Красный glow (обнаружена проблема)

---

### 4.6 VOICE SYSTEM

**Pipeline**:
```
Microphone → VAD → Whisper STT → Speaker Verify → Text
                                                    │
                                                    ▼
                                              Core Brain
                                                    │
                                                    ▼
Text Response → Piper TTS → Speaker Output → Desktop Glow
```

**Speaker Recognition Flow**:
1. При первом запуске: enrollment (запись 5 фраз)
2. Создание voice embedding (ECAPA-TDNN, 192-dim)
3. При каждом voice input: сравнение cosine similarity
4. Threshold: 0.75 для подтверждения личности
5. При failure: запрос подтверждения через Telegram

---

### 4.7 VISION SYSTEM

**Pipeline**:
```
Camera → Frame Capture → Face Detection (RetinaFace)
                              │
                              ▼
                     Face Alignment + Crop
                              │
                              ▼
                     ArcFace Embedding (512-dim)
                              │
                              ▼
                     Compare with stored embedding
                              │
                    ┌─────────┴──────────┐
                    │                    │
              Match (>0.6)         No Match
                    │                    │
                    ▼                    ▼
            Unlock features       Log attempt
            Greet user           Notify via Telegram
```

**Безопасность**:
- Face embeddings хранятся в зашифрованном виде (AES-256)
- Нет хранения фотографий — только числовые вектора
- Embeddings привязаны к hardware ID машины
- Re-enrollment требует Telegram-подтверждение

---

### 4.8 SECURITY & PERMISSIONS

**Permission Matrix** (`permissions.json`):
```json
{
  "agents": {
    "git_agent": {
      "allowed_actions": ["analyze_diff", "generate_patch", "dry_run", "review_code", "log_history"],
      "approval_required": ["commit", "push", "create_branch"],
      "forbidden": ["force_push", "delete_branch_remote", "rebase_remote"],
      "risk_level": "medium"
    },
    "powershell_agent": {
      "allowed_paths": ["C:\\Users\\User\\Projects", "C:\\temp"],
      "forbidden_paths": ["C:\\Windows", "C:\\Program Files"],
      "allowed_commands_regex": ["Get-*", "Test-*", "Write-Output"],
      "approval_required_commands": ["Set-*", "Install-*", "Start-Service"],
      "forbidden_commands": ["Remove-Item -Recurse C:\\", "Format-*", "Clear-EventLog"],
      "timeout_seconds": 30,
      "risk_level": "high"
    },
    "code_agent": {
      "allowed_actions": ["analyze_project", "find_bugs", "suggest_fixes", "explain_code", "score_quality"],
      "approval_required": ["apply_fix", "generate_tests"],
      "risk_level": "low"
    },
    "system_agent": {
      "allowed_actions": ["monitor_resources", "health_check"],
      "approval_required": ["cleanup", "manage_docker", "backup"],
      "risk_level": "medium"
    }
  },
  "global": {
    "max_api_cost_daily_usd": 5.00,
    "max_commands_per_minute": 10,
    "max_loop_iterations": 50,
    "require_human_for_critical": true,
    "audit_retention_days": 90
  }
}
```

**Sandbox Architecture**:
```
┌──────────────────────────────────┐
│       SECURITY SANDBOX           │
│                                  │
│  ┌────────────┐ ┌────────────┐  │
│  │ Path Guard │ │ Cmd Guard  │  │
│  │            │ │            │  │
│  │ whitelist  │ │ whitelist  │  │
│  │ blacklist  │ │ blacklist  │  │
│  │ regex      │ │ regex      │  │
│  └────────────┘ └────────────┘  │
│                                  │
│  ┌────────────┐ ┌────────────┐  │
│  │ Timeout    │ │ Loop Guard │  │
│  │ Enforcer   │ │            │  │
│  │            │ │ max_iter   │  │
│  │ 30s default│ │ deadlock   │  │
│  │ kill on    │ │ detection  │  │
│  │ exceed     │ │            │  │
│  └────────────┘ └────────────┘  │
│                                  │
│  ┌────────────┐ ┌────────────┐  │
│  │ Rate       │ │ Cost       │  │
│  │ Limiter    │ │ Tracker    │  │
│  │            │ │            │  │
│  │ per minute │ │ daily USD  │  │
│  │ per hour   │ │ per model  │  │
│  └────────────┘ └────────────┘  │
└──────────────────────────────────┘
```

---

### 4.9 AUTONOMOUS DECISION ENGINE

**Уровни автономности**:

```
Level 0: MANUAL
├── Все действия требуют явного подтверждения
├── Система только предлагает
└── Default для новых пользователей

Level 1: SUGGESTION  
├── Система анализирует и предлагает план
├── Показывает preview результата
├── Ждёт подтверждения
└── Может группировать предложения

Level 2: CONDITIONAL AUTONOMY
├── Действия из allowlist выполняются автоматически
├── Действия из approval_required — запрос подтверждения
├── Действия из forbidden — блокировка
├── Уведомление после каждого автоматического действия
└── Rollback доступен в течение 5 минут

Level 3: FULL AUTONOMOUS (в рамках allowlist)
├── Все разрешённые действия — автоматически
├── Approval — автоматически при confidence > 0.9
├── Forbidden — блокировка ВСЕГДА
├── Batch-уведомления каждые 15 минут
├── Auto-rollback при ошибках
└── Стоп при 3 последовательных ошибках
```

**Decision Flow**:
```
Task arrives
     │
     ▼
┌──────────┐
│ Classify │─── risk_level: low/medium/high/critical
│ Task     │─── action_type
└────┬─────┘─── required_agent
     │
     ▼
┌──────────┐
│ Check    │─── current autonomy level
│ Level    │─── agent permissions
└────┬─────┘─── action in allowlist?
     │
     ▼
┌──────────┐     ┌──────────┐
│ Auto?    │─No─→│ Request  │──→ Telegram/Desktop
│          │     │ Approval │    notification
└────┬─────┘     └──────────┘
     │ Yes
     ▼
┌──────────┐
│ Execute  │──→ Log + Notify
└──────────┘
```

---

## 5. DOCKER-СХЕМА

```yaml
# docker-compose.yml architecture
┌─────────────────────────────────────────────────┐
│                DOCKER NETWORK: korgan-net        │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐ │
│  │ korgan-core│  │korgan-voice│  │korgan-     │ │
│  │            │  │            │  │vision      │ │
│  │ FastAPI    │  │ Whisper    │  │ InsightFace│ │
│  │ Brain      │  │ Piper TTS  │  │ OpenCV     │ │
│  │ Agents     │  │ Speaker ID │  │            │ │
│  │ Port:8000  │  │ Port:8001  │  │ Port:8002  │ │
│  └─────┬──────┘  └────────────┘  └───────────┘ │
│        │                                        │
│  ┌─────┴──────┐  ┌────────────┐  ┌───────────┐ │
│  │korgan-tg   │  │ postgresql │  │   redis    │ │
│  │            │  │            │  │            │ │
│  │ aiogram    │  │ Port:5432  │  │ Port:6379  │ │
│  │            │  │            │  │            │ │
│  └────────────┘  └────────────┘  └───────────┘ │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐ │
│  │   ollama   │  │  chromadb  │  │    n8n     │ │
│  │            │  │            │  │            │ │
│  │ Port:11434 │  │ Port:8003  │  │ Port:5678  │ │
│  │ GPU access │  │            │  │            │ │
│  └────────────┘  └────────────┘  └───────────┘ │
└─────────────────────────────────────────────────┘

Desktop App (Electron) runs natively on Windows,
connects to korgan-core via WebSocket (ws://localhost:8000/ws)
```

---

## 6. ПЛАН РАЗРАБОТКИ ПО ФАЗАМ

### Phase 1: Foundation (Неделя 1-2)
```
Priority: CRITICAL
├── Docker infrastructure (compose, Dockerfiles)
├── PostgreSQL schema + migrations
├── Redis configuration
├── FastAPI skeleton + WebSocket
├── Basic Ollama integration
├── Config system (permissions.json, system.json)
├── Audit logging
└── Health check endpoint

Deliverable: Рабочий API, принимающий текстовые запросы
             и возвращающий LLM-ответы с логированием
```

### Phase 2: Memory & Agents (Неделя 3-4)
```
Priority: HIGH
├── ChromaDB integration
├── Memory Manager (3 уровня)
├── Base Agent framework
├── Git Agent (полный цикл)
├── PowerShell Agent (sandboxed)
├── Permission enforcement
└── Sandbox system

Deliverable: Система с памятью, способная выполнять
             Git и системные операции с разрешениями
```

### Phase 3: Telegram Interface (Неделя 5)
```
Priority: HIGH
├── aiogram bot setup
├── Command handlers
├── Voice message → Whisper → response
├── Confirmation dialogs (inline buttons)
├── Status notifications
└── Autonomy level control via Telegram

Deliverable: Полностью функциональный Telegram-интерфейс
```

### Phase 4: Voice System (Неделя 6-7)
```
Priority: MEDIUM
├── faster-whisper integration
├── Piper TTS setup (мужской голос)
├── Speaker recognition enrollment
├── Speaker verification pipeline
├── Audio I/O с VAD
└── VRAM dynamic management

Deliverable: Голосовое взаимодействие с верификацией
```

### Phase 5: Desktop Overlay (Неделя 8-9)
```
Priority: MEDIUM
├── Electron transparent window
├── Blue edge glow (CSS + WebGL)
├── Status indicators (thinking, speaking)
├── Action log panel
├── Autonomy mode toggle
├── WebSocket connection to core
└── System tray integration

Deliverable: Премиальный десктоп-overlay с анимациями
```

### Phase 6: Vision System (Неделя 10)
```
Priority: LOW
├── InsightFace integration
├── Face enrollment flow
├── Face verification on camera
├── Encrypted embedding storage
├── Telegram notification on unknown face
└── Integration with autonomy levels

Deliverable: Face-based authentication
```

### Phase 7: Intelligence Engine (Неделя 11-12)
```
Priority: MEDIUM
├── Self-analysis module
├── Daily intelligence brief
├── Code quality scoring
├── Continuous improvement engine
├── Predictive recommendations
├── Crisis detection
└── Strategic mode

Deliverable: AI, который улучшает сам себя
```

### Phase 8: Autonomy & Polish (Неделя 13-14)
```
Priority: HIGH
├── Full autonomy engine
├── Decision tree optimization
├── Rollback mechanism testing
├── End-to-end integration tests
├── Performance optimization
├── VRAM profiling & optimization
└── Documentation

Deliverable: Production-ready система
```

---

## 7. СТРАТЕГИЯ МАСШТАБИРОВАНИЯ

```
ТЕКУЩАЯ АРХИТЕКТУРА (Single Machine)
│
├── Vertical Scaling
│   ├── Upgrade GPU → RTX 4090 → более крупные модели
│   ├── Add RAM → 64GB → больше контекста
│   └── NVMe cache → быстрее vector search
│
├── Horizontal Scaling (Future)
│   ├── Kubernetes migration
│   ├── Отдельный GPU-сервер для inference
│   ├── Distributed ChromaDB → Qdrant cluster
│   ├── PostgreSQL → read replicas
│   └── Redis Cluster
│
├── Multi-Device (Future)
│   ├── Mobile app (React Native)
│   ├── Web dashboard
│   ├── Smart home integration (Home Assistant)
│   └── Wearable notifications
│
└── Multi-User (Future, если нужно)
    ├── Tenant isolation
    ├── Per-user permissions
    └── Shared knowledge base
```

---

## 8. СТРАТЕГИЯ БЕЗОПАСНОСТИ

### 8.1 Defense in Depth
```
Layer 1: Network    — Docker network isolation, no external ports except API
Layer 2: Auth       — Face + Voice + Telegram token verification
Layer 3: Permission — Per-agent allowlist/blocklist
Layer 4: Sandbox    — Command execution isolation
Layer 5: Audit      — Full action logging with rollback data
Layer 6: Limits     — Rate limits, cost limits, loop guards
Layer 7: Rollback   — Every destructive action is reversible
```

### 8.2 Threat Model
| Угроза | Вектор | Митигация |
|--------|--------|-----------|
| Prompt injection | Злонамеренный input | Input sanitization, system prompt hardening |
| Runaway agent | Бесконечный цикл | Loop guard (max 50 iterations), timeout |
| Data exfiltration | Agent sends data out | Network whitelist, no arbitrary HTTP |
| Privilege escalation | Agent escapes sandbox | Minimal OS permissions, Docker isolation |
| Cost attack | Excessive API calls | Daily USD limit, rate limiting |
| Impersonation | Fake voice/face | Multi-factor (voice + face + Telegram) |

### 8.3 Rollback Mechanism
```
Каждое деструктивное действие:
1. Сохраняет pre-state snapshot в audit_log.rollback_data
2. Выполняет действие
3. Проверяет результат
4. При ошибке — автоматический rollback
5. Rollback доступен вручную через Telegram: /rollback <action_id>
6. Retention: 24 часа для полных данных, 90 дней для логов
```

---

## 9. ВОЗМОЖНЫЕ ТОЧКИ ОТКАЗА

| # | Точка отказа | Вероятность | Влияние | Митигация |
|---|-------------|-------------|---------|-----------|
| 1 | Ollama crash | Средняя | Высокое | Auto-restart, cloud fallback |
| 2 | VRAM OOM | Средняя | Высокое | Dynamic model management |
| 3 | PostgreSQL down | Низкая | Критическое | Docker restart policy, WAL |
| 4 | Redis down | Низкая | Среднее | Fallback to direct DB queries |
| 5 | ChromaDB corruption | Низкая | Среднее | Periodic backup, rebuild from PG |
| 6 | Cloud API outage | Низкая | Среднее | Local-only mode |
| 7 | Telegram API ban | Низкая | Среднее | Desktop-only mode |
| 8 | Docker daemon crash | Очень низкая | Критическое | Windows service auto-restart |
| 9 | Disk full | Низкая | Критическое | Monitoring + auto-cleanup |
| 10 | Power loss | Низкая | Высокое | PostgreSQL WAL recovery |

---

## 10. МЕТРИКИ КАЧЕСТВА

### System Performance
- **API latency** (p50 < 100ms, p99 < 500ms)
- **LLM response time** (local < 3s, cloud < 10s)
- **Voice pipeline latency** (STT + TTS < 4s)
- **Face recognition time** (< 500ms)
- **Memory query time** (< 200ms)

### AI Quality
- **Task completion rate** (target: > 90%)
- **Rollback frequency** (target: < 5%)
- **User approval rate** (suggestions accepted: > 70%)
- **Self-analysis accuracy** (measured monthly)
- **Code quality score improvement** (project-level trend)

### Reliability
- **Uptime** (target: 99.5% during active hours)
- **Mean time to recovery** (target: < 60s)
- **Error rate** (target: < 2% of requests)
- **Audit log completeness** (target: 100%)

### Cost
- **Daily API cost** (track, alert at 80% of limit)
- **VRAM utilization** (target: < 90% peak)
- **Disk growth rate** (predict when cleanup needed)

---

## 11. МОДУЛИ "ПРЕВЫШЕНИЯ ОЖИДАНИЙ"

### 11.1 Self-Analysis Mode
Система периодически анализирует свои решения:
- Ревью последних 24 часов действий
- Оценка: было ли решение оптимальным?
- Генерация improvement suggestions
- Хранение в `self_analysis` таблице
- Еженедельный self-report для Мистера Коргана

### 11.2 Continuous Improvement Engine
```
Data Collection → Pattern Analysis → Hypothesis → Test → Deploy
     │                   │                │          │        │
  Все действия    Кластеризация     "Если бы я    A/B     Обновить
  и результаты    ошибок и          сделал X      test    стратегию
                  успехов           вместо Y..."
```

### 11.3 Code Quality Scoring
- **Complexity Score** (cyclomatic complexity)
- **Maintainability Index**
- **Test Coverage** (если есть тесты)
- **Security Score** (known vulnerability patterns)
- **Performance Score** (anti-patterns detection)
- **Overall Grade**: A-F с трендом

### 11.4 Daily Intelligence Brief
Каждое утро в 08:00 через Telegram:
```
🔵 Доброе утро, Мистер Корган.

📊 Сводка за 24 часа:
• Выполнено действий: 47
• Успешность: 95.7%
• Обнаружено проблем: 2 (исправлено: 2)

💻 Проекты:
• MainAi: Code quality A- (↑ от B+)
• WebApp: 3 новых TODO найдено

🧠 Рекомендации:
• Рефакторинг auth модуля снизит complexity на 30%
• Обнаружена N+1 query в user_service.py

📈 Тренд: Производительность системы стабильна.
Расход API за вчера: $0.47
```

### 11.5 AI Memory Compression
- Ежедневно в 03:00: сжатие разговоров старше 7 дней
- Извлечение ключевых фактов в таблицу `facts`
- Суммаризация длинных reasoning logs
- Deduplification векторов в ChromaDB
- Цель: ∞ память при конечном хранилище

### 11.6 Strategic Mode
Активируется командой `/strategy` или автоматически при обнаружении:
- Крупного рефакторинга
- Нового проекта
- Архитектурного решения

Поведение:
- Глубокий анализ (cloud LLM)
- Генерация альтернатив (минимум 3)
- Оценка trade-offs
- Рекомендация с обоснованием
- Запрос подтверждения стратегии

### 11.7 Crisis Mode
Автоматическая активация при:
- 3+ ошибки подряд
- Disk usage > 90%
- VRAM > 95%
- API cost > 90% лимита
- Unusual activity pattern

Поведение:
- Переключение в Manual mode
- Уведомление через Telegram (высокий приоритет)
- Автоматическая диагностика
- Предложение remediation плана
- Логирование crisis event

### 11.8 Predictive Recommendations
Основано на паттернах поведения:
- "Вы обычно коммитите в это время — хотите review?"
- "Проект X не обновлялся 7 дней — проверить?"
- "Размер логов растёт на 15% быстрее обычного"
- "На основе предыдущих задач, вероятно понадобится: ..."
