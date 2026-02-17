"""
KORGAN AI — Unit Tests for ReasoningEngine
"""

from __future__ import annotations

import pytest

from core.brain.reasoning import ReasoningEngine, ReasoningLog


@pytest.fixture
def engine() -> ReasoningEngine:
    """Create a fresh ReasoningEngine instance."""
    return ReasoningEngine()


class TestReasoningEngine:
    """Tests for ReasoningEngine class."""

    def test_start_chain(self, engine: ReasoningEngine) -> None:
        """Creates a reasoning chain."""
        chain = engine.start_chain(request_id="req-001")
        assert chain.request_id == "req-001"
        assert len(chain.steps) >= 1
        assert chain.steps[0].phase == "start"
        assert chain.started_at is not None
        assert chain.completed_at is None
        assert chain in engine.get_active_chains()

    def test_add_step(self, engine: ReasoningEngine) -> None:
        """Adds steps to chain."""
        chain = engine.start_chain(request_id="req-002")
        step = engine.add_step(chain, "analyze", "Analyzing task requirements", duration_ms=50)
        assert step.phase == "analyze"
        assert step.content == "Analyzing task requirements"
        assert step.duration_ms == 50
        assert len(chain.steps) >= 2
        assert chain.steps[-1] == step

    def test_complete_chain(self, engine: ReasoningEngine) -> None:
        """Marks chain as complete."""
        chain = engine.start_chain(request_id="req-003")
        engine.add_step(chain, "process", "Processing...")
        engine.complete_chain(chain, outcome="success")
        assert chain.completed_at is not None
        assert chain.outcome == "success"
        assert chain not in engine.get_active_chains()
        assert any(s.phase == "complete" for s in chain.steps)

    def test_to_text(self, engine: ReasoningEngine) -> None:
        """Produces readable text."""
        chain = engine.start_chain(request_id="req-004")
        engine.add_step(chain, "step1", "First step")
        engine.add_step(chain, "step2", "Second step")
        engine.complete_chain(chain, outcome="done")
        text = chain.to_text()
        assert "Reasoning Chain [req-004]" in text
        assert "step1" in text
        assert "step2" in text
        assert "Outcome: done" in text

    def test_fail_chain(self, engine: ReasoningEngine) -> None:
        """Records failures."""
        chain = engine.start_chain(request_id="req-005")
        engine.add_step(chain, "attempt", "Attempting operation")
        engine.fail_chain(chain, error="Connection timeout")
        assert chain.completed_at is not None
        assert "failed:" in chain.outcome
        assert "Connection timeout" in chain.outcome
        assert chain not in engine.get_active_chains()
        assert any(s.phase == "error" for s in chain.steps)
        assert any("Connection timeout" in s.content for s in chain.steps)
