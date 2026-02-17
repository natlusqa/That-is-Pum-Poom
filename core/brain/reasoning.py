"""
KORGAN AI — Reasoning Engine
Chain-of-thought logging and decision tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger("korgan.reasoning")


class ReasoningStep(BaseModel):
    """A single step in the reasoning chain."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    phase: str
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: Optional[int] = None


class ReasoningLog(BaseModel):
    """Complete reasoning chain for a request."""
    request_id: str
    steps: list[ReasoningStep] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    outcome: Optional[str] = None

    def to_text(self) -> str:
        """Convert reasoning log to human-readable text."""
        lines = [f"=== Reasoning Chain [{self.request_id[:8]}] ==="]
        for i, step in enumerate(self.steps, 1):
            elapsed = (step.timestamp - self.started_at).total_seconds()
            lines.append(f"  [{i}] ({elapsed:.1f}s) {step.phase}: {step.content}")
        if self.outcome:
            lines.append(f"  → Outcome: {self.outcome}")
        return "\n".join(lines)

    def to_dict_list(self) -> list[dict]:
        """Convert to list of dicts for storage."""
        return [
            {
                "phase": s.phase,
                "content": s.content,
                "timestamp": s.timestamp.isoformat(),
            }
            for s in self.steps
        ]


class ReasoningEngine:
    """
    Manages chain-of-thought reasoning for the orchestrator.
    
    Every decision KORGAN makes is logged with reasoning steps,
    enabling self-analysis and transparency for Mr. Korgan.
    """

    def __init__(self):
        self._active_chains: dict[str, ReasoningLog] = {}

    def start_chain(self, request_id: str) -> ReasoningLog:
        """Start a new reasoning chain for a request."""
        chain = ReasoningLog(request_id=request_id)
        self._active_chains[request_id] = chain
        self.add_step(chain, "start", "Начинаю обработку запроса")
        logger.debug("reasoning_chain_started", request_id=request_id)
        return chain

    def add_step(
        self,
        chain: ReasoningLog,
        phase: str,
        content: str,
        duration_ms: int | None = None,
    ) -> ReasoningStep:
        """Add a reasoning step to the chain."""
        step = ReasoningStep(
            phase=phase,
            content=content,
            duration_ms=duration_ms,
        )
        chain.steps.append(step)
        logger.debug(
            "reasoning_step",
            request_id=chain.request_id,
            phase=phase,
            content=content[:200],
        )
        return step

    def complete_chain(
        self, chain: ReasoningLog, outcome: str = "completed"
    ) -> None:
        """Mark a reasoning chain as complete."""
        chain.completed_at = datetime.now(timezone.utc)
        chain.outcome = outcome
        self.add_step(chain, "complete", f"Цепочка завершена: {outcome}")

        # Clean up
        self._active_chains.pop(chain.request_id, None)
        logger.info(
            "reasoning_chain_completed",
            request_id=chain.request_id,
            steps_count=len(chain.steps),
            duration_s=(chain.completed_at - chain.started_at).total_seconds(),
        )

    def fail_chain(self, chain: ReasoningLog, error: str) -> None:
        """Mark a reasoning chain as failed."""
        self.add_step(chain, "error", f"Ошибка: {error}")
        self.complete_chain(chain, outcome=f"failed: {error}")

    def get_active_chains(self) -> list[ReasoningLog]:
        """Get all active reasoning chains (for monitoring)."""
        return list(self._active_chains.values())
