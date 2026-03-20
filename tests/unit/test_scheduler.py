"""
KORGAN AI — Unit Tests for KorganScheduler
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.scheduler import KorganScheduler


@pytest.fixture
def mock_components():
    """Create mock intelligence components."""
    return {
        "self_analysis": AsyncMock(),
        "daily_brief": AsyncMock(),
        "crisis_detector": AsyncMock(),
        "memory_compressor": AsyncMock(),
        "feedback_loop": AsyncMock(),
        "improvement_engine": AsyncMock(),
        "predictive_engine": AsyncMock(),
    }


@pytest.fixture
def scheduler(mock_components):
    return KorganScheduler(**mock_components)


class TestKorganScheduler:
    def test_initial_state(self, scheduler):
        assert scheduler._running is False

    def test_start_registers_jobs(self, scheduler):
        scheduler.start()
        jobs = scheduler.get_jobs()
        assert len(jobs) >= 5  # at least 5 scheduled jobs
        assert scheduler._running is True

        # Check job IDs
        job_ids = [j["id"] for j in jobs]
        assert "self_analysis" in job_ids
        assert "daily_brief" in job_ids
        assert "crisis_check" in job_ids
        assert "feedback_eval" in job_ids
        assert "improvement_cycle" in job_ids

        scheduler.stop()

    def test_start_idempotent(self, scheduler):
        scheduler.start()
        jobs_count = len(scheduler.get_jobs())
        scheduler.start()  # Second start should be no-op
        assert len(scheduler.get_jobs()) == jobs_count
        scheduler.stop()

    def test_stop(self, scheduler):
        scheduler.start()
        scheduler.stop()
        assert scheduler._running is False

    def test_get_jobs_format(self, scheduler):
        scheduler.start()
        jobs = scheduler.get_jobs()
        for job in jobs:
            assert "id" in job
            assert "name" in job
            assert "next_run" in job
            assert "trigger" in job
        scheduler.stop()

    def test_no_jobs_without_components(self):
        """Scheduler with no components registers no jobs."""
        scheduler = KorganScheduler()
        scheduler.start()
        assert len(scheduler.get_jobs()) == 0
        scheduler.stop()

    def test_partial_components(self):
        """Scheduler with only some components registers only relevant jobs."""
        scheduler = KorganScheduler(crisis_detector=AsyncMock())
        scheduler.start()
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "crisis_check"
        scheduler.stop()
