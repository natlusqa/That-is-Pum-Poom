"""
KORGAN AI — Unit Tests for PermissionManager
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core.security.permissions import PermissionManager, PermissionCheck


@pytest.fixture
def permissions_config_path(tmp_path: Path) -> Path:
    """Create a temporary permissions config file."""
    config = {
        "agents": {
            "code_agent": {
                "risk_level": "low",
                "allowed_actions": ["analyze_code", "read_file", "search"],
                "approval_required": ["write_file", "apply_fix"],
                "forbidden": ["delete_all", "format_disk"],
                "forbidden_paths": ["C:\\Windows", "/etc"],
            },
            "test_agent": {
                "risk_level": "medium",
                "allowed_actions": ["status"],
                "approval_required": ["commit"],
                "forbidden": ["force_push"],
            },
        },
        "global": {
            "max_commands_per_minute": 10,
            "max_commands_per_hour": 200,
        },
    }
    path = tmp_path / "permissions.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def permission_manager(permissions_config_path: Path) -> PermissionManager:
    """Create PermissionManager with test config."""
    return PermissionManager(config_path=str(permissions_config_path))


class TestPermissionManager:
    """Tests for PermissionManager class."""

    def test_allowed_action(self, permission_manager: PermissionManager) -> None:
        """Allowed actions pass."""
        check = permission_manager.check_agent_action("code_agent", "analyze_code project")
        assert check.allowed is True
        assert check.action_type == "allowed"

    def test_forbidden_action(self, permission_manager: PermissionManager) -> None:
        """Forbidden actions are blocked."""
        check = permission_manager.check_agent_action("code_agent", "delete_all files")
        assert check.allowed is False
        assert check.action_type == "forbidden"
        assert "запрещено" in check.reason.lower() or "forbidden" in check.reason.lower()

    def test_approval_required(self, permission_manager: PermissionManager) -> None:
        """Approval_required actions flagged."""
        check = permission_manager.check_agent_action("code_agent", "write_file config.json")
        assert check.allowed is True
        assert check.action_type == "approval_required"

    def test_forbidden_path(self, permission_manager: PermissionManager) -> None:
        """Path restrictions work."""
        check = permission_manager.check_agent_action(
            "code_agent", "read C:\\Windows\\System32\\config"
        )
        assert check.allowed is False
        assert check.action_type == "forbidden"
        assert "путь" in check.reason.lower() or "path" in check.reason.lower()

    def test_unknown_agent(self, permission_manager: PermissionManager) -> None:
        """Unknown agents denied."""
        check = permission_manager.check_agent_action("nonexistent_agent", "any_action")
        assert check.allowed is False
        assert check.action_type == "forbidden"
        assert "неизвестный" in check.reason.lower() or "unknown" in check.reason.lower()

    def test_global_limits(self, permission_manager: PermissionManager) -> None:
        """Global limits returned correctly."""
        limits = permission_manager.get_global_limits()
        assert "max_commands_per_minute" in limits
        assert limits["max_commands_per_minute"] == 10
        assert limits["max_commands_per_hour"] == 200
