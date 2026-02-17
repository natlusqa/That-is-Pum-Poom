"""
KORGAN AI — Unit Tests for CommandSandbox
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.security.permissions import PermissionManager
from core.security.sandbox import CommandSandbox


@pytest.fixture
def mock_permissions(tmp_path: Path) -> PermissionManager:
    """Create PermissionManager with config that supports sandbox tests."""
    config = {
        "agents": {
            "test_agent": {
                "allowed_actions": ["read", "Get-Content"],
                "approval_required": ["Set-Content", "Remove-Item"],
                "forbidden": ["Format-Volume", "Invoke-Expression"],
                "forbidden_paths": ["C:\\Windows"],
                "allowed_paths": ["C:\\temp"],
            },
        },
        "global": {
            "max_commands_per_minute": 3,
            "max_commands_per_hour": 50,
            "max_loop_iterations": 5,
        },
    }
    path = tmp_path / "perms.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return PermissionManager(config_path=str(path))


@pytest.fixture
def sandbox(mock_permissions: PermissionManager) -> CommandSandbox:
    """Create CommandSandbox with mock permissions."""
    return CommandSandbox(mock_permissions)


class TestCommandSandbox:
    """Tests for CommandSandbox class."""

    def test_rate_limit(self, sandbox: CommandSandbox) -> None:
        """Rate limiting works."""
        for _ in range(3):
            assert sandbox.check_rate_limit() is True
            sandbox.record_command()
        assert sandbox.check_rate_limit() is False

    def test_loop_guard(self, sandbox: CommandSandbox) -> None:
        """Loop guard triggers."""
        loop_id = "main_loop"
        for _ in range(5):
            assert sandbox.check_loop_guard(loop_id) is True
        assert sandbox.check_loop_guard(loop_id) is False

    def test_validate_command(self, sandbox: CommandSandbox) -> None:
        """Command validation."""
        # Allowed command passes
        result = sandbox.validate_command("Get-Content file.txt", "test_agent")
        assert result["valid"] is True
        assert result["needs_approval"] is False

        # Forbidden command blocked
        result = sandbox.validate_command("Format-Volume C:", "test_agent")
        assert result["valid"] is False

        # Approval required
        result = sandbox.validate_command("Set-Content file.txt 'data'", "test_agent")
        assert result["valid"] is True
        assert result["needs_approval"] is True
