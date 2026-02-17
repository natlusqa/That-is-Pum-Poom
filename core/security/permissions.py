"""
KORGAN AI — Permission Manager
Enforces the permission matrix from permissions.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import structlog
from pydantic import BaseModel

logger = structlog.get_logger("korgan.security.permissions")


class PermissionCheck(BaseModel):
    """Result of a permission check."""
    allowed: bool
    action_type: str = "unknown"  # allowed, approval_required, forbidden
    risk_level: str = "low"
    reason: str = ""
    agent_name: str = ""


class PermissionManager:
    """
    Enforces the permission matrix defined in permissions.json.
    
    Checks:
    - Agent-level permissions (allowed, approval_required, forbidden)
    - Path restrictions
    - Command whitelist/blacklist
    - Global limits (rate, cost, loop)
    """

    def __init__(self, config_path: str = "config/permissions.json"):
        self._config: dict[str, Any] = {}
        self._config_path = config_path
        self._load_config()

    def _load_config(self) -> None:
        """Load permissions configuration."""
        try:
            path = Path(self._config_path)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                logger.info("permissions_loaded", path=self._config_path)
            else:
                logger.warning("permissions_file_not_found", path=self._config_path)
        except Exception as e:
            logger.error("permissions_load_failed", error=str(e))

    def reload(self) -> None:
        """Reload permissions from file."""
        self._load_config()

    def check_agent_action(
        self,
        agent_name: str,
        action: str,
    ) -> PermissionCheck:
        """
        Check if an agent action is permitted.
        Returns PermissionCheck with allowed status and details.
        """
        agent_config = self._config.get("agents", {}).get(agent_name, {})

        if not agent_config:
            logger.warning("unknown_agent", agent=agent_name)
            return PermissionCheck(
                allowed=False,
                action_type="forbidden",
                reason=f"Неизвестный агент: {agent_name}",
                agent_name=agent_name,
            )

        risk_level = agent_config.get("risk_level", "medium")

        # Check forbidden actions
        forbidden = agent_config.get("forbidden", [])
        for f in forbidden:
            if f.lower() in action.lower():
                logger.warning(
                    "action_forbidden",
                    agent=agent_name,
                    action=action[:100],
                    rule=f,
                )
                return PermissionCheck(
                    allowed=False,
                    action_type="forbidden",
                    risk_level=risk_level,
                    reason=f"Действие запрещено правилом: {f}",
                    agent_name=agent_name,
                )

        # Check forbidden commands (for PS agent)
        forbidden_cmds = agent_config.get("forbidden_commands", [])
        for cmd in forbidden_cmds:
            if cmd.lower() in action.lower():
                return PermissionCheck(
                    allowed=False,
                    action_type="forbidden",
                    risk_level="critical",
                    reason=f"Команда в чёрном списке: {cmd}",
                    agent_name=agent_name,
                )

        # Check forbidden paths
        forbidden_paths = agent_config.get("forbidden_paths", [])
        for fp in forbidden_paths:
            if fp.lower() in action.lower():
                return PermissionCheck(
                    allowed=False,
                    action_type="forbidden",
                    risk_level="critical",
                    reason=f"Путь запрещён: {fp}",
                    agent_name=agent_name,
                )

        # Check approval_required
        approval_required = agent_config.get("approval_required", [])
        for ar in approval_required:
            if ar.lower() in action.lower():
                return PermissionCheck(
                    allowed=True,
                    action_type="approval_required",
                    risk_level=risk_level,
                    reason=f"Требуется подтверждение для: {ar}",
                    agent_name=agent_name,
                )

        # Check approval_required command patterns
        approval_patterns = agent_config.get("approval_required_patterns", [])
        for pattern_str in approval_patterns:
            if re.match(pattern_str, action):
                return PermissionCheck(
                    allowed=True,
                    action_type="approval_required",
                    risk_level=risk_level,
                    reason=f"Паттерн требует подтверждения: {pattern_str}",
                    agent_name=agent_name,
                )

        # Check allowed actions
        allowed = agent_config.get("allowed_actions", [])
        if allowed:
            for a in allowed:
                if a.lower() in action.lower():
                    return PermissionCheck(
                        allowed=True,
                        action_type="allowed",
                        risk_level=risk_level,
                        reason=f"Разрешено: {a}",
                        agent_name=agent_name,
                    )

        # Check allowed command patterns
        allowed_patterns = agent_config.get("allowed_commands_patterns", [])
        for pattern_str in allowed_patterns:
            if re.match(pattern_str, action):
                return PermissionCheck(
                    allowed=True,
                    action_type="allowed",
                    risk_level=risk_level,
                    reason="Команда в белом списке",
                    agent_name=agent_name,
                )

        # Default: require approval for anything not explicitly allowed
        return PermissionCheck(
            allowed=True,
            action_type="approval_required",
            risk_level=risk_level,
            reason="Действие не в явном списке — требуется подтверждение",
            agent_name=agent_name,
        )

    def get_global_limits(self) -> dict[str, Any]:
        """Get global system limits."""
        return self._config.get("global", {})

    def get_agent_config(self, agent_name: str) -> dict[str, Any]:
        """Get full agent configuration."""
        return self._config.get("agents", {}).get(agent_name, {})

    def get_owner_config(self) -> dict[str, Any]:
        """Get owner configuration."""
        return self._config.get("owner", {})
