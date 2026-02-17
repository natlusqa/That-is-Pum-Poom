"""
KORGAN AI — Unit Tests for CrisisDetector
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from intelligence.crisis import CrisisDetector, CrisisEvent


@pytest.fixture
def crisis_config() -> dict:
    """Config with consecutive_errors threshold of 3."""
    return {"triggers": {"consecutive_errors": 3}}


@pytest.fixture
def crisis_detector(crisis_config: dict) -> CrisisDetector:
    """Create CrisisDetector with mocked autonomy and memory."""
    mock_autonomy = MagicMock()
    mock_memory = AsyncMock()
    return CrisisDetector(
        autonomy_engine=mock_autonomy,
        memory_manager=mock_memory,
        config=crisis_config,
    )


class TestCrisisDetector:
    """Tests for CrisisDetector class."""

    def test_consecutive_errors(self, crisis_detector: CrisisDetector) -> None:
        """Error counting."""
        assert crisis_detector._consecutive_errors == 0
        crisis_detector.record_error()
        crisis_detector.record_error()
        assert crisis_detector._consecutive_errors == 2
        crisis_detector.record_error()
        assert crisis_detector._consecutive_errors == 3

    def test_success_resets_errors(self, crisis_detector: CrisisDetector) -> None:
        """Success resets counter."""
        crisis_detector.record_error()
        crisis_detector.record_error()
        crisis_detector.record_success()
        assert crisis_detector._consecutive_errors == 0

    def test_active_crises(self, crisis_detector: CrisisDetector) -> None:
        """Crisis tracking."""
        assert len(crisis_detector.get_active_crises()) == 0
        crisis_detector._active_crises.append(
            CrisisEvent(
                trigger="test_trigger",
                severity="warning",
                details="Test crisis",
            )
        )
        assert len(crisis_detector.get_active_crises()) == 1
        crisis_detector._active_crises[0].resolved = True
        assert len(crisis_detector.get_active_crises()) == 0

    def test_check_errors_returns_crisis_when_threshold_exceeded(
        self, crisis_detector: CrisisDetector
    ) -> None:
        """Consecutive errors trigger crisis event."""
        for _ in range(3):
            crisis_detector.record_error()
        crisis = crisis_detector._check_errors()
        assert crisis is not None
        assert crisis.trigger == "consecutive_errors"
        assert crisis.severity == "critical"
