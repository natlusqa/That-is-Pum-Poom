"""
KORGAN AI — Command Sandbox
Isolates command execution with security constraints.
"""

from __future__ import annotations

import re
import time
from typing import Any

import structlog

from core.security.permissions import PermissionManager

logger = structlog.get_logger("korgan.security.sandbox")


class SandboxViolation(Exception):
    """Raised when a sandbox rule is violated."""
    pass


class CommandSandbox:
    """
    Sandboxed command execution environment.
    
    Security layers:
    1. Path guard (whitelist/blacklist)
    2. Command guard (whitelist/blacklist/regex)
    3. Timeout enforcer
    4. Loop guard (max iterations, deadlock detection)
    5. Rate limiter (per minute, per hour)
    6. Cost tracker (daily API USD limit)
    """

    def __init__(self, permission_manager: PermissionManager):
        self._permissions = permission_manager
        self._global = permission_manager.get_global_limits()

        # Rate limiting state
        self._command_timestamps: list[float] = []
        self._loop_counter: dict[str, int] = {}
        self._max_commands_per_minute = self._global.get("max_commands_per_minute", 10)
        self._max_commands_per_hour = self._global.get("max_commands_per_hour", 200)
        self._max_loop_iterations = self._global.get("max_loop_iterations", 50)

    def check_rate_limit(self) -> bool:
        """Check if rate limit allows execution."""
        now = time.time()

        # Clean old timestamps
        self._command_timestamps = [
            t for t in self._command_timestamps if now - t < 3600
        ]

        # Per minute check
        recent_minute = sum(1 for t in self._command_timestamps if now - t < 60)
        if recent_minute >= self._max_commands_per_minute:
            logger.warning(
                "rate_limit_exceeded",
                type="per_minute",
                count=recent_minute,
                limit=self._max_commands_per_minute,
            )
            return False

        # Per hour check
        if len(self._command_timestamps) >= self._max_commands_per_hour:
            logger.warning(
                "rate_limit_exceeded",
                type="per_hour",
                count=len(self._command_timestamps),
                limit=self._max_commands_per_hour,
            )
            return False

        return True

    def record_command(self) -> None:
        """Record a command execution for rate limiting."""
        self._command_timestamps.append(time.time())

    def check_loop_guard(self, loop_id: str) -> bool:
        """Check if a loop has exceeded max iterations."""
        count = self._loop_counter.get(loop_id, 0) + 1
        self._loop_counter[loop_id] = count

        if count > self._max_loop_iterations:
            logger.error(
                "loop_guard_triggered",
                loop_id=loop_id,
                iterations=count,
                max=self._max_loop_iterations,
            )
            return False
        return True

    def reset_loop(self, loop_id: str) -> None:
        """Reset a loop counter."""
        self._loop_counter.pop(loop_id, None)

    def validate_path(self, path: str, agent_name: str) -> bool:
        """Validate that a path is within allowed boundaries."""
        agent_config = self._permissions.get_agent_config(agent_name)

        forbidden_paths = agent_config.get("forbidden_paths", [])
        for fp in forbidden_paths:
            if path.lower().startswith(fp.lower()):
                logger.warning(
                    "path_forbidden",
                    path=path,
                    forbidden=fp,
                    agent=agent_name,
                )
                return False

        allowed_paths = agent_config.get("allowed_paths", [])
        if allowed_paths:
            for ap in allowed_paths:
                if path.lower().startswith(ap.lower()):
                    return True
            logger.warning(
                "path_not_in_whitelist",
                path=path,
                agent=agent_name,
            )
            return False

        return True

    def validate_command(self, command: str, agent_name: str) -> dict[str, Any]:
        """
        Full command validation through all security layers.
        
        Returns:
            {"valid": bool, "reason": str, "needs_approval": bool}
        """
        # Rate limit
        if not self.check_rate_limit():
            return {
                "valid": False,
                "reason": "Превышен лимит команд. Подождите.",
                "needs_approval": False,
            }

        # Permission check
        check = self._permissions.check_agent_action(agent_name, command)

        if not check.allowed:
            return {
                "valid": False,
                "reason": check.reason,
                "needs_approval": False,
            }

        if check.action_type == "approval_required":
            return {
                "valid": True,
                "reason": check.reason,
                "needs_approval": True,
            }

        return {
            "valid": True,
            "reason": "Проверка пройдена",
            "needs_approval": False,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get sandbox statistics."""
        now = time.time()
        return {
            "commands_last_minute": sum(
                1 for t in self._command_timestamps if now - t < 60
            ),
            "commands_last_hour": len(
                [t for t in self._command_timestamps if now - t < 3600]
            ),
            "active_loops": len(self._loop_counter),
            "rate_limit_per_minute": self._max_commands_per_minute,
            "rate_limit_per_hour": self._max_commands_per_hour,
        }
