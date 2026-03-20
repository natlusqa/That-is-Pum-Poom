"""
KORGAN AI — Unit Tests for SelfAnalysisEngine
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from intelligence.self_analysis import AnalysisReport, SelfAnalysisEngine


class TestAnalysisReport:
    """Tests for AnalysisReport data class."""

    def test_empty_report(self):
        report = AnalysisReport()
        assert report.total_actions == 0
        assert report.overall_score == 0.0

    def test_to_dict(self):
        report = AnalysisReport()
        report.total_actions = 100
        report.successful_actions = 90
        report.failed_actions = 10

        d = report.to_dict()
        assert d["metrics"]["total_actions"] == 100
        assert d["metrics"]["success_rate"] == 90.0

    def test_to_dict_zero_actions(self):
        report = AnalysisReport()
        d = report.to_dict()
        assert d["metrics"]["success_rate"] == 0

    def test_to_text(self):
        report = AnalysisReport()
        report.total_actions = 50
        report.successful_actions = 45
        report.failed_actions = 5
        report.overall_score = 85.0

        text = report.to_text()
        assert "50" in text
        assert "85" in text

    def test_to_text_with_suboptimal(self):
        report = AnalysisReport()
        report.total_actions = 10
        report.successful_actions = 10
        report.suboptimal_decisions = [
            {"description": "Bad choice", "recommendation": "Do better"}
        ]

        text = report.to_text()
        assert "Bad choice" in text
        assert "Do better" in text


class TestSelfAnalysisEngine:
    """Tests for SelfAnalysisEngine class."""

    @pytest.mark.asyncio
    async def test_run_analysis_no_memory(self):
        """Analysis works without memory manager."""
        engine = SelfAnalysisEngine()
        report = await engine.run_analysis()
        assert isinstance(report, AnalysisReport)
        assert report.total_actions == 0

    @pytest.mark.asyncio
    async def test_run_analysis_with_mock_memory(self):
        """Analysis queries memory for stats."""
        mock_memory = AsyncMock()
        mock_memory.get_stats.return_value = {
            "total_audit_entries": 50,
            "total_messages": 100,
        }
        mock_memory.get_action_stats.return_value = {
            "total": 50,
            "success": 45,
            "failed": 5,
            "rolled_back": 1,
            "avg_duration_ms": 250.0,
        }
        mock_memory.get_recent_messages.return_value = []

        engine = SelfAnalysisEngine(memory_manager=mock_memory)
        report = await engine.run_analysis()

        assert report.total_actions == 50
        assert report.successful_actions == 45
        assert report.failed_actions == 5

    def test_calculate_score_no_actions(self):
        engine = SelfAnalysisEngine()
        report = AnalysisReport()
        score = engine._calculate_score(report)
        assert score == 50.0

    def test_calculate_score_perfect(self):
        engine = SelfAnalysisEngine()
        report = AnalysisReport()
        report.total_actions = 100
        report.successful_actions = 100
        report.rolled_back_actions = 0
        report.decisions_reviewed = 10
        report.suboptimal_decisions = []

        score = engine._calculate_score(report)
        assert score >= 90.0

    def test_calculate_score_poor(self):
        engine = SelfAnalysisEngine()
        report = AnalysisReport()
        report.total_actions = 100
        report.successful_actions = 50
        report.rolled_back_actions = 20
        report.decisions_reviewed = 10
        report.suboptimal_decisions = [{}] * 8

        score = engine._calculate_score(report)
        assert score < 80.0

    @pytest.mark.asyncio
    async def test_detect_patterns_high_error_rate(self):
        engine = SelfAnalysisEngine()
        report = AnalysisReport()
        report.total_actions = 100
        report.failed_actions = 25

        await engine._detect_patterns(report)
        assert any("ошибок" in p.lower() or "процент" in p.lower() for p in report.patterns_detected)

    @pytest.mark.asyncio
    async def test_detect_patterns_high_rollback(self):
        engine = SelfAnalysisEngine()
        report = AnalysisReport()
        report.total_actions = 100
        report.rolled_back_actions = 5

        await engine._detect_patterns(report)
        assert any("откат" in p.lower() for p in report.patterns_detected)

    @pytest.mark.asyncio
    async def test_detect_patterns_slow_response(self):
        engine = SelfAnalysisEngine()
        report = AnalysisReport()
        report.total_actions = 100
        report.avg_response_time_ms = 6000

        await engine._detect_patterns(report)
        assert any("время" in p.lower() for p in report.patterns_detected)
