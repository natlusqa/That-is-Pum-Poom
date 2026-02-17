"""
KORGAN AI — Unit Tests for AutonomyEngine
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from core.autonomy.engine import AutonomyEngine
from core.autonomy.levels import AutonomyLevel


@pytest.fixture
def autonomy_config_path(tmp_path: Path) -> Path:
    """Create a temporary autonomy config file."""
    config = {
        "current_level": 0,
        "level_change_rules": {
            "allowed_transitions": {"0": [1], "1": [0, 2], "2": [0, 1, 3], "3": [0, 1, 2]},
            "auto_downgrade_on_crisis": True,
            "auto_downgrade_target": 0,
        },
    }
    path = tmp_path / "autonomy.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def autonomy_engine(autonomy_config_path: Path) -> AutonomyEngine:
    """Create AutonomyEngine with test config."""
    engine = AutonomyEngine(config_path=str(autonomy_config_path))
    engine._consecutive_errors = 0
    engine._auto_actions_this_hour = 0
    return engine


class TestAutonomyEngine:
    """Tests for AutonomyEngine class."""

    def test_default_level(self, autonomy_engine: AutonomyEngine) -> None:
        """Starts at MANUAL."""
        assert autonomy_engine.current_level == AutonomyLevel.MANUAL

    def test_set_level(self, autonomy_engine: AutonomyEngine) -> None:
        """Transitions work."""
        result = autonomy_engine.set_level(1)
        assert result is True
        assert autonomy_engine.current_level == AutonomyLevel.SUGGESTION
        result = autonomy_engine.set_level(2)
        assert result is True
        assert autonomy_engine.current_level == AutonomyLevel.CONDITIONAL

    def test_invalid_transition(self, autonomy_engine: AutonomyEngine) -> None:
        """Blocked transitions."""
        # 0 -> 2 is not in allowed_transitions (0 can only go to 1)
        result = autonomy_engine.set_level(2)
        assert result is False
        assert autonomy_engine.current_level == AutonomyLevel.MANUAL

    def test_crisis_mode(self, autonomy_engine: AutonomyEngine) -> None:
        """Enter/exit crisis."""
        assert not autonomy_engine.is_crisis
        autonomy_engine.enter_crisis_mode()
        assert autonomy_engine.is_crisis
        assert autonomy_engine.current_level == AutonomyLevel.MANUAL
        autonomy_engine.exit_crisis_mode()
        assert not autonomy_engine.is_crisis

    def test_consecutive_errors(self, autonomy_engine: AutonomyEngine) -> None:
        """Error threshold triggers crisis."""
        autonomy_engine.set_level(2)
        for _ in range(3):
            autonomy_engine.record_error()
        assert autonomy_engine.is_crisis

    def test_can_auto_execute_manual(self, autonomy_engine: AutonomyEngine) -> None:
        """Level 0 always needs approval."""
        decision = autonomy_engine.can_auto_execute("code_agent", "allowed")
        assert decision.can_execute is False
        assert decision.needs_approval is True

    def test_can_auto_execute_conditional(self, autonomy_engine: AutonomyEngine) -> None:
        """Level 2 auto-executes allowed."""
        autonomy_engine.set_level(1)
        autonomy_engine.set_level(2)
        decision = autonomy_engine.can_auto_execute("code_agent", "allowed")
        assert decision.can_execute is True
        assert decision.needs_approval is False

    def test_can_auto_execute_forbidden(self, autonomy_engine: AutonomyEngine) -> None:
        """Forbidden always blocked."""
        autonomy_engine.set_level(3)
        decision = autonomy_engine.can_auto_execute("code_agent", "forbidden")
        assert decision.can_execute is False
        assert decision.needs_approval is False

    def test_can_auto_execute_full_auto(self, autonomy_engine: AutonomyEngine) -> None:
        """Level 3 auto-executes with high confidence."""
        autonomy_engine.set_level(1)
        autonomy_engine.set_level(2)
        autonomy_engine.set_level(3)
        decision = autonomy_engine.can_auto_execute(
            "code_agent", "approval_required", confidence=0.95
        )
        assert decision.can_execute is True
        assert decision.auto_approved is True
