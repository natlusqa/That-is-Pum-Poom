"""
KORGAN AI — FastAPI Application
Main entry point for the Core API.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings

from core.api.state import get_state, set_state
from core.api.routes import brain, agents, memory, system
from core.brain.orchestrator import Orchestrator, OrchestratorRequest
from core.brain.reasoning import ReasoningEngine
from core.brain.router import LLMRouter
from core.memory.manager import MemoryManager
from core.security.permissions import PermissionManager
from core.security.sandbox import CommandSandbox
from core.security.audit import AuditLogger
from core.autonomy.engine import AutonomyEngine
from core.agents.git_agent import GitAgent
from core.agents.powershell_agent import PowerShellAgent
from core.agents.code_agent import CodeAgent
from core.agents.system_agent import SystemAgent
from core.scheduler import KorganScheduler
from core.memory.compression import MemoryCompressor
from intelligence.self_analysis import SelfAnalysisEngine
from intelligence.daily_brief import DailyBriefGenerator
from intelligence.crisis import CrisisDetector
from intelligence.code_scoring import CodeQualityScorer
from intelligence.predictive import PredictiveEngine
from intelligence.feedback_loop import FeedbackLoop
from intelligence.improvement import ContinuousImprovementEngine

logger = structlog.get_logger("korgan.api")


class Settings(BaseSettings):
    """Application settings from environment."""
    database_url: str = "postgresql+asyncpg://korgan:password@postgresql:5432/korgan_ai"
    redis_url: str = "redis://redis:6379/0"
    chromadb_host: str = "chromadb"
    chromadb_port: int = 8003
    ollama_host: str = "http://ollama:11434"
    log_level: str = "INFO"
    autonomy_level: int = 0

    class Config:
        env_prefix = ""


def _load_json_config(filename: str) -> dict:
    """Load a JSON config file."""
    path = Path(f"config/{filename}")
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialize and cleanup."""
    settings = Settings()

    logger.info("korgan_starting", version="1.0.0")

    # Load configs
    system_config = _load_json_config("system.json")
    permissions_config = _load_json_config("permissions.json")

    # Initialize Memory Manager
    memory_mgr = MemoryManager(
        database_url=settings.database_url,
        redis_url=settings.redis_url,
        chromadb_host=settings.chromadb_host,
        chromadb_port=settings.chromadb_port,
    )
    await memory_mgr.initialize()

    # Initialize Security
    permission_mgr = PermissionManager()
    sandbox = CommandSandbox(permission_mgr)
    audit = AuditLogger(memory_manager=memory_mgr)

    # Initialize Autonomy
    autonomy_engine = AutonomyEngine()

    # Initialize LLM Router
    llm_router = LLMRouter(system_config)
    await llm_router.initialize()

    # Initialize Reasoning Engine
    reasoning_engine = ReasoningEngine()

    # Initialize Agents
    ps_config = permissions_config.get("agents", {}).get("powershell_agent", {})
    agents_dict = {
        "git_agent": GitAgent(memory_manager=memory_mgr, permission_manager=permission_mgr),
        "powershell_agent": PowerShellAgent(
            permissions_config=ps_config,
            memory_manager=memory_mgr,
            permission_manager=permission_mgr,
        ),
        "code_agent": CodeAgent(
            llm_router=llm_router,
            memory_manager=memory_mgr,
            permission_manager=permission_mgr,
        ),
        "system_agent": SystemAgent(memory_manager=memory_mgr, permission_manager=permission_mgr),
    }

    # Initialize Orchestrator (with feedback loop and crisis detector)
    orchestrator = Orchestrator(
        llm_router=llm_router,
        reasoning_engine=reasoning_engine,
        memory_manager=memory_mgr,
        permission_manager=permission_mgr,
        autonomy_engine=autonomy_engine,
        agents=agents_dict,
        feedback_loop=feedback_loop,
        crisis_detector=crisis_detector,
    )

    # Initialize Intelligence Engine components
    crisis_config = system_config.get("intelligence", {}).get("crisis_detection", {})
    self_analysis = SelfAnalysisEngine(
        memory_manager=memory_mgr,
        llm_router=llm_router,
    )
    daily_brief = DailyBriefGenerator(
        memory_manager=memory_mgr,
        llm_router=llm_router,
    )
    crisis_detector = CrisisDetector(
        autonomy_engine=autonomy_engine,
        memory_manager=memory_mgr,
        config=crisis_config,
    )
    code_scorer = CodeQualityScorer(llm_router=llm_router)
    feedback_loop = FeedbackLoop(
        memory_manager=memory_mgr,
        llm_router=llm_router,
        autonomy_engine=autonomy_engine,
    )
    improvement_engine = ContinuousImprovementEngine(
        memory_manager=memory_mgr,
        llm_router=llm_router,
    )
    predictive_engine = PredictiveEngine(memory_manager=memory_mgr)
    memory_compressor = MemoryCompressor(
        session_factory=memory_mgr._session_factory,
        llm_router=llm_router,
        chroma_collection=memory_mgr._collection,
    )

    # Initialize Scheduler
    scheduler = KorganScheduler(
        self_analysis=self_analysis,
        daily_brief=daily_brief,
        crisis_detector=crisis_detector,
        memory_compressor=memory_compressor,
        feedback_loop=feedback_loop,
        improvement_engine=improvement_engine,
        predictive_engine=predictive_engine,
    )

    # Store in state
    set_state("orchestrator", orchestrator)
    set_state("memory", memory_mgr)
    set_state("permissions", permission_mgr)
    set_state("sandbox", sandbox)
    set_state("audit", audit)
    set_state("autonomy", autonomy_engine)
    set_state("llm_router", llm_router)
    set_state("agents", agents_dict)
    set_state("settings", settings)
    set_state("scheduler", scheduler)
    set_state("crisis_detector", crisis_detector)
    set_state("feedback_loop", feedback_loop)
    set_state("self_analysis", self_analysis)
    set_state("code_scorer", code_scorer)
    set_state("predictive", predictive_engine)

    # Start scheduler
    scheduler.start()

    logger.info("korgan_ready", autonomy_level=autonomy_engine.current_level.name)

    # Log startup
    await audit.log(
        action="system_start",
        details={"version": "1.0.0", "autonomy_level": autonomy_engine.current_level.name},
        risk_level="low",
    )

    yield

    # Cleanup
    logger.info("korgan_shutting_down")
    scheduler.stop()
    await memory_mgr.close()


# Create FastAPI app
app = FastAPI(
    title="KORGAN AI",
    description="Personal AI Operating System — Created by Мистер Корган",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: restrict to desktop app origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(brain.router, prefix="/api/brain", tags=["Brain"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(memory.router, prefix="/api/memory", tags=["Memory"])
app.include_router(system.router, prefix="/api/system", tags=["System"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "korgan-core",
        "version": "1.0.0",
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "KORGAN AI",
        "version": "1.0.0",
        "creator": "Amanat Korgan",
        "status": "operational",
    }


# =========================================================================
# WebSocket — Real-time connection for Desktop & Telegram
# =========================================================================

class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("ws_connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info("ws_disconnected", total=len(self.active_connections))

    async def broadcast(self, message: dict):
        """Broadcast to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


ws_manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication."""
    await ws_manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_json()

            # Process through orchestrator
            orchestrator = get_state().get("orchestrator")
            if not orchestrator:
                await websocket.send_json({"error": "System not ready"})
                continue

            request = OrchestratorRequest(
                content=data.get("content", ""),
                interface=data.get("interface", "desktop"),
                context=data.get("context", {}),
            )

            # Send "thinking" state
            await websocket.send_json({
                "type": "status",
                "state": "thinking",
                "request_id": request.id,
            })

            # Process
            response = await orchestrator.process(request)

            # Send response
            await websocket.send_json({
                "type": "response",
                "request_id": request.id,
                "content": response.content,
                "reasoning": response.reasoning,
                "actions": response.actions_taken,
                "suggestions": response.suggested_actions,
                "metadata": response.metadata,
            })

            # Send "idle" state
            await websocket.send_json({
                "type": "status",
                "state": "idle",
            })

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
