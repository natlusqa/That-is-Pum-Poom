# KORGAN AI

**Personal AI Operating System** — JARVIS-класс ассистент для управления разработкой, системой ПК, проектами и жизнью.

Создатель: **Amanat Korgan** (Мистер Корган)

---

## Архитектура

```
Interface Layer          Core Layer              Data Layer
┌──────────────┐    ┌─────────────────┐    ┌──────────────────┐
│  Desktop UI  │───→│  Core Brain     │───→│  PostgreSQL      │
│  (Electron)  │    │  (Orchestrator) │    │  (Long-term)     │
├──────────────┤    ├─────────────────┤    ├──────────────────┤
│  Telegram    │───→│  Agent Framework│───→│  ChromaDB        │
│  Bot         │    │  (Git, PS, Code)│    │  (Vectors)       │
├──────────────┤    ├─────────────────┤    ├──────────────────┤
│  Voice       │───→│  Autonomy       │───→│  Redis           │
│  Interface   │    │  Engine         │    │  (Cache)         │
└──────────────┘    └─────────────────┘    └──────────────────┘
```

## Системные требования

| Компонент | Минимум | Установлено |
|-----------|---------|-------------|
| OS | Windows 10/11 x64 | Windows 11 Pro |
| CPU | 8 cores | i5-13400F |
| RAM | 16 GB | 32 GB DDR4 |
| GPU | RTX 3060 8GB | RTX 5060 8GB |
| Docker | v24+ | Установлен |
| Node.js | v18+ | Для Desktop UI |

## Быстрый старт

### 1. Клонирование и настройка

```powershell
cd "C:\project on my Local PC\MainAi"
copy .env.example .env
# Отредактируйте .env — заполните TELEGRAM_BOT_TOKEN, DB_PASSWORD, etc.
```

### 2. Автоматическая установка

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

### 3. Запуск всех сервисов

```powershell
docker compose up -d
```

### 4. Проверка здоровья

```powershell
python scripts/health_check.py
```

### 5. Запуск Desktop Overlay

```powershell
cd desktop
npm install
npm start
```

## Сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| Core API | 8000 | Главный мозг + REST API + WebSocket |
| Voice | 8001 | Whisper STT + Piper TTS + Speaker ID |
| Vision | 8002 | Face Detection + Recognition |
| ChromaDB | 8003 | Векторная база данных |
| PostgreSQL | 5432 | Долговременная память |
| Redis | 6379 | Кеш + Event Bus |
| Ollama | 11434 | Локальные LLM модели |
| n8n | 5678 | Автоматизация workflows |

## API

Документация: http://localhost:8000/docs

### Основные эндпоинты

```
POST   /api/brain/chat        — Отправить сообщение
GET    /api/brain/status       — Статус мозга
POST   /api/agents/execute     — Выполнить задачу агентом
GET    /api/agents/             — Список агентов
GET    /api/memory/stats       — Статистика памяти
POST   /api/memory/search      — Поиск в памяти
GET    /api/system/status      — Статус системы
POST   /api/system/autonomy    — Изменить уровень автономности
WS     /ws                     — WebSocket (real-time)
```

## Telegram-команды

| Команда | Описание |
|---------|----------|
| `/start` | Инициализация |
| `/status` | Статус системы |
| `/mode` | Уровень автономности |
| `/agents` | Статус агентов |
| `/memory` | Состояние памяти |
| `/brief` | Утренняя сводка |
| `/strategy` | Стратегический режим |
| `/rollback <id>` | Откатить действие |
| `/stop` | Экстренная остановка |

## Уровни автономности

| Level | Название | Поведение |
|-------|----------|-----------|
| 0 | **MANUAL** | Все действия требуют подтверждения |
| 1 | **SUGGESTION** | Система предлагает план, ждёт одобрения |
| 2 | **CONDITIONAL** | Разрешённые — авто, остальные — подтверждение |
| 3 | **FULL AUTONOMOUS** | Автономное выполнение в рамках allowlist |

## Агенты

- **Git Agent** — анализ diff, commit, push, code review, dry-run
- **PowerShell Agent** — системные команды (sandboxed)
- **Code Agent** — анализ кода, поиск багов, оценка качества
- **System Agent** — мониторинг ресурсов, Docker, health check

## Intelligence Engine

- **Self-Analysis** — ежедневный анализ своих решений (02:00)
- **Daily Brief** — утренняя сводка в Telegram (08:00)
- **Code Scoring** — оценка качества кода (A-F)
- **Predictive** — предсказания на основе паттернов
- **Crisis Detection** — автоматическое обнаружение проблем
- **Continuous Improvement** — еженедельный цикл улучшений

## Безопасность

- Sandbox для всех команд (whitelist/blacklist)
- Permission matrix (permissions.json)
- Аудит-лог всех действий
- Rollback механизм (24 часа)
- Rate limiting (per minute, per hour)
- Лимит API расходов ($5/день по умолчанию)
- Face + Voice + Telegram верификация
- Encrypted face embeddings (AES-256)
- Docker network isolation

## Структура проекта

```
korgan-ai/
├── config/          — Конфигурации (permissions, autonomy, system)
├── core/
│   ├── brain/       — Orchestrator, Reasoning, LLM Router
│   ├── memory/      — 3-уровневая память (Redis → ChromaDB → PostgreSQL)
│   ├── agents/      — Git, PowerShell, Code, System агенты
│   ├── security/    — Sandbox, Permissions, Audit, Rollback
│   ├── autonomy/    — Decision Engine, Levels
│   └── api/         — FastAPI + WebSocket + Routes
├── voice/           — Whisper STT + Piper TTS + Speaker ID
├── vision/          — InsightFace + ArcFace + Encrypted Embeddings
├── desktop/         — Electron overlay (blue glow, status, action log)
├── telegram/        — aiogram 3.x bot
├── intelligence/    — Self-analysis, Daily Brief, Predictive, Crisis
├── docker/          — Dockerfiles
├── scripts/         — Setup, Health Check, DB Migration
├── n8n/             — Automation workflows
├── docs/            — ARCHITECTURE.md
└── tests/           — Unit & Integration tests
```

## VRAM Budget (RTX 5060 8GB)

```
Ollama (Mistral 7B Q4)   ~4.5 GB
faster-whisper (medium)   ~1.0 GB
InsightFace (ArcFace)     ~0.5 GB
Piper TTS                 ~0.2 GB
System overhead           ~1.8 GB
───────────────────────────────────
TOTAL                     ~8.0 GB
```

Dynamic VRAM management: модели загружаются/выгружаются по необходимости.

## Лицензия

Proprietary. Created by Amanat Korgan.
