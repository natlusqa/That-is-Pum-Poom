"""
KORGAN AI — Autonomy Decision Engine
Controls when KORGAN can act independently vs. requesting approval.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from core.autonomy.levels import AutonomyLevel, LevelBehavior, LEVEL_BEHAVIORS
from core.autonomy.decision import AutonomyDecision

logger = structlog.get_logger("korgan.autonomy")


class AutonomyEngine:
    """
    Autonomy decision engine that determines whether KORGAN
    can auto-execute an action or needs to ask Mr. Korgan.
    
    Decision factors:
    - Current autonomy level (0-3)
    - Action type (allowed, approval_required, forbidden)
    - Agent risk level
    - Confidence score (for Level 3)
    - Consecutive error count
    - Crisis mode state
    """

    def __init__(self, config_path: str = "config/autonomy.json"):
        self._config: dict[str, Any] = {}
        self._config_path = config_path
        self._current_level = AutonomyLevel.MANUAL
        self._consecutive_errors = 0
        self._crisis_mode = False
        self._auto_actions_this_hour = 0

        self._load_config()

    def _load_config(self) -> None:
        """Load autonomy configuration."""
        try:
            path = Path(self._config_path)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                level_num = self._config.get("current_level", 0)
                self._current_level = AutonomyLevel(level_num)
                logger.info(
                    "autonomy_loaded",
                    level=self._current_level.name,
                )
        except Exception as e:
            logger.error("autonomy_load_failed", error=str(e))

    @property
    def current_level(self) -> AutonomyLevel:
        """Get current autonomy level."""
        return self._current_level

    @property
    def behavior(self) -> LevelBehavior:
        """Get behavior for current level."""
        return LEVEL_BEHAVIORS.get(self._current_level, LEVEL_BEHAVIORS[AutonomyLevel.MANUAL])

    @property
    def is_crisis(self) -> bool:
        """Check if system is in crisis mode."""
        return self._crisis_mode

    def can_auto_execute(
        self,
        agent_name: str,
        action_type: str,
        risk_level: str = "low",
        confidence: float = 1.0,
    ) -> AutonomyDecision:
        """
        Determine if an action can be auto-executed.
        
        Decision matrix:
        
        Level 0 (MANUAL):
            → All actions need approval
            
        Level 1 (SUGGESTION):
            → All actions need approval (with preview)
            
        Level 2 (CONDITIONAL):
            → "allowed" actions → auto-execute
            → "approval_required" → ask user
            → "forbidden" → block
            
        Level 3 (FULL_AUTONOMOUS):
            → "allowed" → auto-execute
            → "approval_required" + confidence > threshold → auto-execute
            → "approval_required" + confidence <= threshold → ask user
            → "forbidden" → block ALWAYS
        """
        behavior = self.behavior

        # Crisis mode forces manual
        if self._crisis_mode:
            return AutonomyDecision(
                can_execute=False,
                needs_approval=True,
                reason="Система в кризисном режиме — все действия требуют подтверждения",
                notification_priority="immediate",
            )

        # Forbidden is always blocked
        if action_type == "forbidden":
            return AutonomyDecision(
                can_execute=False,
                needs_approval=False,
                reason=f"Действие запрещено для агента {agent_name}",
                notification_required=True,
                notification_priority="immediate",
            )

        # Check consecutive errors threshold
        if self._consecutive_errors >= behavior.stop_on_consecutive_errors:
            logger.warning(
                "consecutive_errors_threshold",
                errors=self._consecutive_errors,
                threshold=behavior.stop_on_consecutive_errors,
            )
            return AutonomyDecision(
                can_execute=False,
                needs_approval=True,
                reason=f"Превышен порог последовательных ошибок ({self._consecutive_errors})",
                notification_priority="immediate",
            )

        # Check hourly limit
        if self._auto_actions_this_hour >= behavior.max_auto_actions_per_hour:
            return AutonomyDecision(
                can_execute=False,
                needs_approval=True,
                reason="Превышен лимит автоматических действий в час",
                notification_priority="immediate",
            )

        # Level 0 & 1: Always need approval
        if self._current_level in (AutonomyLevel.MANUAL, AutonomyLevel.SUGGESTION):
            return AutonomyDecision(
                can_execute=False,
                needs_approval=True,
                reason=f"Уровень {self._current_level.name}: требуется подтверждение",
                notification_priority="immediate",
            )

        # Level 2: Conditional
        if self._current_level == AutonomyLevel.CONDITIONAL:
            if action_type == "allowed":
                return AutonomyDecision(
                    can_execute=True,
                    needs_approval=False,
                    auto_approved=True,
                    reason="Действие в списке разрешённых (Conditional Autonomy)",
                    notification_priority="batch" if risk_level == "low" else "immediate",
                )
            else:
                return AutonomyDecision(
                    can_execute=False,
                    needs_approval=True,
                    reason="Действие требует подтверждения (Conditional Autonomy)",
                    notification_priority="immediate",
                )

        # Level 3: Full Autonomous
        if self._current_level == AutonomyLevel.FULL_AUTONOMOUS:
            if action_type == "allowed":
                return AutonomyDecision(
                    can_execute=True,
                    needs_approval=False,
                    auto_approved=True,
                    reason="Авто-выполнение (Full Autonomous)",
                    notification_priority="batch",
                )
            elif action_type == "approval_required":
                if confidence >= behavior.confidence_threshold:
                    return AutonomyDecision(
                        can_execute=True,
                        needs_approval=False,
                        auto_approved=True,
                        reason=f"Авто-одобрено (confidence {confidence:.2f} >= {behavior.confidence_threshold})",
                        notification_priority="batch" if risk_level in ("low", "medium") else "immediate",
                    )
                else:
                    return AutonomyDecision(
                        can_execute=False,
                        needs_approval=True,
                        reason=f"Недостаточная уверенность ({confidence:.2f} < {behavior.confidence_threshold})",
                        notification_priority="immediate",
                    )

        # Default: need approval
        return AutonomyDecision(
            can_execute=False,
            needs_approval=True,
            reason="Требуется подтверждение (default)",
        )

    def set_level(self, level: int) -> bool:
        """Set autonomy level (with validation)."""
        try:
            new_level = AutonomyLevel(level)

            # Check allowed transitions
            transitions = self._config.get("level_change_rules", {}).get("allowed_transitions", {})
            allowed = transitions.get(str(self._current_level.value), [])

            if new_level.value not in allowed and new_level != self._current_level:
                logger.warning(
                    "level_transition_blocked",
                    current=self._current_level.name,
                    target=new_level.name,
                )
                return False

            old_level = self._current_level
            self._current_level = new_level
            self._consecutive_errors = 0

            # Persist
            self._save_config()

            logger.info(
                "autonomy_level_changed",
                from_level=old_level.name,
                to_level=new_level.name,
            )
            return True

        except ValueError:
            logger.error("invalid_autonomy_level", level=level)
            return False

    def record_error(self) -> None:
        """Record a consecutive error."""
        self._consecutive_errors += 1
        behavior = self.behavior

        if self._consecutive_errors >= behavior.stop_on_consecutive_errors:
            logger.error(
                "auto_stop_triggered",
                errors=self._consecutive_errors,
            )
            self.enter_crisis_mode()

    def record_success(self) -> None:
        """Record a successful action (resets error counter)."""
        self._consecutive_errors = 0
        self._auto_actions_this_hour += 1

    def enter_crisis_mode(self) -> None:
        """Activate crisis mode — downgrades to manual."""
        self._crisis_mode = True
        auto_downgrade = self._config.get("level_change_rules", {}).get("auto_downgrade_on_crisis", True)
        if auto_downgrade:
            target = self._config.get("level_change_rules", {}).get("auto_downgrade_target", 0)
            self._current_level = AutonomyLevel(target)
        logger.critical("crisis_mode_activated")

    def exit_crisis_mode(self) -> None:
        """Exit crisis mode."""
        self._crisis_mode = False
        self._consecutive_errors = 0
        logger.info("crisis_mode_deactivated")

    def _save_config(self) -> None:
        """Save current level to config file."""
        try:
            self._config["current_level"] = self._current_level.value
            path = Path(self._config_path)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("autonomy_save_failed", error=str(e))

    def get_status(self) -> dict[str, Any]:
        """Get current autonomy status."""
        return {
            "level": self._current_level.value,
            "level_name": self._current_level.name,
            "crisis_mode": self._crisis_mode,
            "consecutive_errors": self._consecutive_errors,
            "auto_actions_this_hour": self._auto_actions_this_hour,
            "behavior": self.behavior.model_dump(),
        }
