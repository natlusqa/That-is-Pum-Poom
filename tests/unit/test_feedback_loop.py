"""
KORGAN AI — Unit Tests for FeedbackLoop
"""

from __future__ import annotations

import pytest

from intelligence.feedback_loop import FeedbackLoop, FeedbackEntry


@pytest.fixture
def feedback_loop() -> FeedbackLoop:
    """Create FeedbackLoop with mocked dependencies."""
    return FeedbackLoop(memory_manager=None, llm_router=None, autonomy_engine=None)


@pytest.fixture
def sample_entry() -> FeedbackEntry:
    """Create a sample FeedbackEntry."""
    return FeedbackEntry(
        action_id="act-001",
        agent="code_agent",
        action_type="analyze",
        input_summary="Analyze project",
        output_summary="Analysis complete",
        success=True,
        duration_ms=150,
    )


class TestFeedbackLoop:
    """Tests for FeedbackLoop class."""

    @pytest.mark.asyncio
    async def test_record_entry(self, feedback_loop: FeedbackLoop, sample_entry: FeedbackEntry) -> None:
        """Entries get buffered."""
        await feedback_loop.record(sample_entry)
        assert len(feedback_loop._buffer) == 1
        assert feedback_loop._buffer[0].agent == "code_agent"
        assert feedback_loop._buffer[0].success is True

    @pytest.mark.asyncio
    async def test_agent_success_rates(
        self, feedback_loop: FeedbackLoop, sample_entry: FeedbackEntry
    ) -> None:
        """Rates track correctly."""
        await feedback_loop.record(sample_entry)
        await feedback_loop.record(
            FeedbackEntry(
                action_id="act-002",
                agent="code_agent",
                action_type="fix",
                input_summary="Fix bug",
                output_summary="Fixed",
                success=False,
                duration_ms=100,
            )
        )
        rates = feedback_loop.get_agent_success_rates()
        assert "code_agent" in rates
        assert rates["code_agent"] == 0.5

    @pytest.mark.asyncio
    async def test_multimodal_signal(self, feedback_loop: FeedbackLoop) -> None:
        """Calibration adjusts on voice/vision failure."""
        initial = feedback_loop.get_confidence_calibration()
        await feedback_loop.record_multimodal_signal(
            signal_type="face_recognition",
            success=False,
            confidence=0.0,
            latency_ms=200,
        )
        assert feedback_loop.get_confidence_calibration() < initial
        assert feedback_loop.get_confidence_calibration() == initial - 0.05

    def test_improvement_trend(self, feedback_loop: FeedbackLoop) -> None:
        """Trending calculation."""
        # Insufficient data
        result = feedback_loop.get_improvement_trend()
        assert result.get("status") == "insufficient_data"

        # Add entries - first half fails more, second half succeeds more
        for i in range(25):
            entry = FeedbackEntry(
                action_id=f"act-{i}",
                agent="test_agent",
                action_type="test",
                input_summary="test",
                output_summary="test",
                success=i >= 12,
                duration_ms=100,
            )
            feedback_loop._buffer.append(entry)

        result = feedback_loop.get_improvement_trend()
        assert "first_half_success_rate" in result
        assert "second_half_success_rate" in result
        assert "improvement" in result
        assert result["trending"] in ("up", "down", "stable")
