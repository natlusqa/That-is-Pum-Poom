"""
KORGAN AI — Unit Tests for LLMRouter
"""

from __future__ import annotations

import pytest

from core.brain.router import (
    LLMRouter,
    LLMProvider,
    CostTracker,
    RoutingDecision,
)


@pytest.fixture
def router_config() -> dict:
    """Router config with cloud enabled for routing tests."""
    return {
        "global": {"max_api_cost_daily_usd": 5.0},
        "llm": {
            "local": {"host": "http://localhost:11434"},
            "cloud": {
                "enabled": True,
                "routing": {"context_length_threshold": 4000},
            },
        },
    }


@pytest.fixture
def router(router_config: dict) -> LLMRouter:
    """Create LLMRouter with test config."""
    return LLMRouter(router_config)


class TestLLMRouter:
    """Tests for LLMRouter class."""

    def test_route_code_task(self, router: LLMRouter) -> None:
        """Routes code tasks to OLLAMA_CODE."""
        for task_type in ("code_analysis", "code_generation", "code_review", "code_task"):
            decision = router.route(task_type=task_type)
            assert decision.provider == LLMProvider.OLLAMA_CODE
            assert "код" in decision.reason.lower() or "code" in decision.reason.lower()

    def test_route_strategic(self, router: LLMRouter) -> None:
        """Routes strategic tasks to CLAUDE."""
        decision = router.route(task_type="strategic")
        assert decision.provider == LLMProvider.CLAUDE
        assert decision.fallback == LLMProvider.OLLAMA_PRIMARY

    def test_route_default(self, router: LLMRouter) -> None:
        """Routes default to OLLAMA_PRIMARY."""
        decision = router.route(task_type="conversation")
        assert decision.provider == LLMProvider.OLLAMA_PRIMARY
        assert "Стандартная" in decision.reason or "Local" in decision.reason

    def test_route_force_cloud(self, router: LLMRouter) -> None:
        """Force_cloud parameter works."""
        decision = router.route(task_type="conversation", force_cloud=True)
        assert decision.provider == LLMProvider.CLAUDE
        assert decision.fallback == LLMProvider.OPENAI
        assert "cloud" in decision.reason.lower() or "Принудительное" in decision.reason

    def test_route_force_local(self, router: LLMRouter) -> None:
        """Force_local parameter works."""
        decision = router.route(task_type="strategic", force_local=True)
        assert decision.provider == LLMProvider.OLLAMA_PRIMARY
        assert decision.fallback == LLMProvider.OLLAMA_CODE
        assert "local" in decision.reason.lower() or "Принудительное" in decision.reason

    def test_route_over_limit(self, router_config: dict) -> None:
        """Switches to local when over API limit."""
        router = LLMRouter(router_config)
        router._cost_tracker.add(5.0)  # Hit limit
        # Use task type that reaches cost check (strategic routes to cloud before cost check)
        decision = router.route(task_type="conversation")
        assert decision.provider == LLMProvider.OLLAMA_PRIMARY
        assert "Лимит" in decision.reason or "limit" in decision.reason.lower()


class TestCostTracker:
    """Tests for CostTracker."""

    def test_cost_tracker_limits_and_tracking(self) -> None:
        """CostTracker limits and tracking."""
        tracker = CostTracker(daily_limit=2.0)
        assert not tracker.is_over_limit()
        assert tracker.get_remaining() == 2.0
        tracker.add(1.0)
        assert tracker.get_today_cost() == 1.0
        assert tracker.get_remaining() == 1.0
        assert not tracker.is_over_limit()
        tracker.add(1.5)
        assert tracker.is_over_limit()
        assert tracker.get_remaining() == 0.0
