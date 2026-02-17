"""
KORGAN AI — Autonomy Levels Definition
"""

from __future__ import annotations

from enum import IntEnum
from pydantic import BaseModel


class AutonomyLevel(IntEnum):
    """
    Autonomy levels for KORGAN AI.
    
    Level 0 (MANUAL): All actions need explicit approval.
    Level 1 (SUGGESTION): System suggests and waits for approval.
    Level 2 (CONDITIONAL): Allowed actions auto-execute; others need approval.
    Level 3 (FULL_AUTONOMOUS): All allowed + approval actions auto-execute at high confidence.
    """
    MANUAL = 0
    SUGGESTION = 1
    CONDITIONAL = 2
    FULL_AUTONOMOUS = 3


class LevelBehavior(BaseModel):
    """Behavior configuration for an autonomy level."""
    auto_execute_allowed: bool = False
    auto_execute_approval_required: bool = False
    needs_preview: bool = True
    notification_mode: str = "immediate"  # immediate, after_action, batch
    notification_batch_interval_minutes: int = 5
    rollback_window_minutes: int = 5
    max_auto_actions_per_hour: int = 50
    confidence_threshold: float = 0.9
    stop_on_consecutive_errors: int = 3


# Default behaviors per level
LEVEL_BEHAVIORS: dict[AutonomyLevel, LevelBehavior] = {
    AutonomyLevel.MANUAL: LevelBehavior(
        auto_execute_allowed=False,
        auto_execute_approval_required=False,
        needs_preview=True,
        notification_mode="immediate",
    ),
    AutonomyLevel.SUGGESTION: LevelBehavior(
        auto_execute_allowed=False,
        auto_execute_approval_required=False,
        needs_preview=True,
        notification_mode="immediate",
    ),
    AutonomyLevel.CONDITIONAL: LevelBehavior(
        auto_execute_allowed=True,
        auto_execute_approval_required=False,
        needs_preview=True,
        notification_mode="after_action",
        notification_batch_interval_minutes=5,
        rollback_window_minutes=5,
        max_auto_actions_per_hour=50,
    ),
    AutonomyLevel.FULL_AUTONOMOUS: LevelBehavior(
        auto_execute_allowed=True,
        auto_execute_approval_required=True,
        needs_preview=False,
        notification_mode="batch",
        notification_batch_interval_minutes=15,
        rollback_window_minutes=10,
        max_auto_actions_per_hour=200,
        confidence_threshold=0.9,
        stop_on_consecutive_errors=3,
    ),
}
