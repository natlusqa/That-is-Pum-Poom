"""
KORGAN AI — Base Agent Abstract Class
All agents inherit from this and implement the standard protocol.
"""

from __future__ import annotations

import uuid
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger("korgan.agents")


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class ActionPlan(BaseModel):
    """Planned action before execution."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str
    description: str
    steps: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    estimated_duration_ms: int = 0
    requires_approval: bool = False
    dry_run_result: Optional[str] = None
    rollback_possible: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ActionResult(BaseModel):
    """Result of an executed action."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: Optional[str] = None
    agent_name: str
    action_type: str
    status: ActionStatus = ActionStatus.SUCCESS
    summary: str = ""
    output: Any = None
    error: Optional[str] = None
    duration_ms: int = 0
    rollback_data: Optional[dict[str, Any]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def success(self) -> bool:
        return self.status == ActionStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class BaseAgent(ABC):
    """
    Abstract base agent that all KORGAN agents must implement.
    
    Lifecycle:
    1. plan() — Analyze task, create execution plan
    2. validate_plan() — Check permissions, estimate risk
    3. execute() — Run the action
    4. validate_result() — Check outcome
    5. rollback() — Undo if needed
    """

    def __init__(
        self,
        name: str,
        description: str,
        risk_level: RiskLevel = RiskLevel.LOW,
        memory_manager: Any = None,
        permission_manager: Any = None,
    ):
        self.name = name
        self.description = description
        self.risk_level = risk_level
        self.memory = memory_manager
        self.permissions = permission_manager
        self.logger = structlog.get_logger(f"korgan.agent.{name}")

    @abstractmethod
    async def plan(self, task: str, context: str = "") -> ActionPlan:
        """Create an execution plan for the given task."""
        ...

    @abstractmethod
    async def execute(self, task: str, context: str = "") -> ActionResult:
        """Execute the task and return result."""
        ...

    @abstractmethod
    async def rollback(self, action_id: str) -> bool:
        """Rollback a previously executed action."""
        ...

    async def execute_with_tracking(self, task: str, context: str = "") -> ActionResult:
        """Execute with full audit tracking."""
        start = time.monotonic()
        action_id = None

        try:
            # Log start
            if self.memory:
                action_id = await self.memory.log_agent_action(
                    agent_name=self.name,
                    action_type="execute",
                    input_data={"task": task[:500]},
                    status="running",
                )

            # Execute
            result = await self.execute(task, context)
            duration = int((time.monotonic() - start) * 1000)
            result.duration_ms = duration

            # Log completion
            if self.memory and action_id:
                await self.memory.log_agent_action(
                    agent_name=self.name,
                    action_type="execute",
                    input_data={"task": task[:500]},
                    output_data={"summary": result.summary[:500]},
                    status=result.status.value,
                    duration_ms=duration,
                )

                # Audit log
                await self.memory.log_audit(
                    action=f"{self.name}:{result.action_type}",
                    agent=self.name,
                    details={
                        "task": task[:300],
                        "summary": result.summary[:300],
                        "status": result.status.value,
                    },
                    risk_level=self.risk_level.value,
                    rollback_data=result.rollback_data,
                )

            self.logger.info(
                "action_completed",
                status=result.status.value,
                duration_ms=duration,
            )
            return result

        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            self.logger.error("action_failed", error=str(e), duration_ms=duration)

            if self.memory:
                await self.memory.log_agent_action(
                    agent_name=self.name,
                    action_type="execute",
                    input_data={"task": task[:500]},
                    status="failed",
                    duration_ms=duration,
                    error_message=str(e),
                )

            return ActionResult(
                agent_name=self.name,
                action_type="execute",
                status=ActionStatus.FAILED,
                summary=f"Ошибка: {str(e)}",
                error=str(e),
                duration_ms=duration,
            )
