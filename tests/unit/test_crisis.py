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

    def test_check_errors_returns_none_below_threshold(
        self, crisis_detector: CrisisDetector
    ) -> None:
        """No crisis below threshold."""
        crisis_detector.record_error()
        crisis_detector.record_error()
        assert crisis_detector._check_errors() is None

    @pytest.mark.asyncio
    async def test_check_deduplicates_active_crises(
        self, crisis_detector: CrisisDetector
    ) -> None:
        """Same trigger doesn't create duplicate crises."""
        # Add an active crisis
        crisis_detector._active_crises.append(
            CrisisEvent(trigger="consecutive_errors", severity="critical", details="3 errors")
        )
        # Trigger errors to exceed threshold
        for _ in range(3):
            crisis_detector.record_error()

        events = await crisis_detector.check()
        # The consecutive_errors event should be deduplicated
        error_events = [e for e in events if e.trigger == "consecutive_errors"]
        assert len(error_events) == 0

    @pytest.mark.asyncio
    async def test_resolve_crisis(self, crisis_detector: CrisisDetector) -> None:
        """Crisis resolution works."""
        crisis_detector._active_crises.append(
            CrisisEvent(trigger="test", severity="warning", details="test")
        )
        result = await crisis_detector.resolve_crisis("test")
        assert result is True
        assert len(crisis_detector.get_active_crises()) == 0

    @pytest.mark.asyncio
    async def test_resolve_nonexistent(self, crisis_detector: CrisisDetector) -> None:
        """Resolving non-existent crisis returns False."""
        result = await crisis_detector.resolve_crisis("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_cpu_runs_without_error(self, crisis_detector: CrisisDetector) -> None:
        """CPU check completes without error."""
        result = await crisis_detector._check_cpu()
        # Result is either None or a CrisisEvent
        assert result is None or isinstance(result, CrisisEvent)

    @pytest.mark.asyncio
    async def test_check_ram_runs_without_error(self, crisis_detector: CrisisDetector) -> None:
        """RAM check completes without error."""
        result = await crisis_detector._check_ram()
        assert result is None or isinstance(result, CrisisEvent)

    def test_status_has_all_fields(self, crisis_detector: CrisisDetector) -> None:
        """Status dict has expected structure."""
        status = crisis_detector.get_status()
        assert "active_crises" in status
        assert "total_crises" in status
        assert "consecutive_errors" in status
        assert "thresholds" in status
