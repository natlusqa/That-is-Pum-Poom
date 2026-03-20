"""Tests for BaseAgent, ActionPlan, and ActionResult."""

from __future__ import annotations

import pytest

from core.agents.base import (
    ActionPlan,
    ActionResult,
    ActionStatus,
    BaseAgent,
    RiskLevel,
)


class DummyAgent(BaseAgent):
    """Concrete agent for testing."""

    async def plan(self, task: str, context: str = "") -> ActionPlan:
        return ActionPlan(
            agent_name=self.name,
            description=f"Test: {task}",
            steps=["step1"],
            risk_level=self.risk_level,
        )

    async def execute(self, task: str, context: str = "") -> ActionResult:
        if "fail" in task:
            return ActionResult(
                agent_name=self.name,
                action_type="test",
                status=ActionStatus.FAILED,
                summary="Failed deliberately",
                error="Deliberate failure",
            )
        return ActionResult(
            agent_name=self.name,
            action_type="test",
            summary=f"Executed: {task}",
        )

    async def rollback(self, action_id: str) -> bool:
        return True


@pytest.fixture
def agent():
    return DummyAgent(name="test_agent", description="Test agent", risk_level=RiskLevel.LOW)


class TestActionPlan:
    def test_plan_has_id(self):
        plan = ActionPlan(agent_name="test", description="desc", steps=["s1"])
        assert plan.id
        assert len(plan.id) > 0

    def test_plan_to_dict(self):
        plan = ActionPlan(
            agent_name="test",
            description="desc",
            steps=["s1", "s2"],
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
        )
        d = plan.to_dict()
        assert d["agent_name"] == "test"
        assert d["requires_approval"] is True
        assert len(d["steps"]) == 2

    def test_plan_default_risk(self):
        plan = ActionPlan(agent_name="test", description="desc")
        assert plan.risk_level == RiskLevel.LOW


class TestActionResult:
    def test_success_property(self):
        result = ActionResult(agent_name="test", action_type="op")
        assert result.success is True

    def test_failed_property(self):
        result = ActionResult(
            agent_name="test",
            action_type="op",
            status=ActionStatus.FAILED,
        )
        assert result.success is False

    def test_result_to_dict(self):
        result = ActionResult(
            agent_name="test",
            action_type="op",
            summary="Done",
            output={"key": "val"},
        )
        d = result.to_dict()
        assert d["summary"] == "Done"
        assert d["output"]["key"] == "val"


class TestBaseAgent:
    @pytest.mark.asyncio
    async def test_plan(self, agent):
        plan = await agent.plan("do something")
        assert plan.agent_name == "test_agent"
        assert "do something" in plan.description

    @pytest.mark.asyncio
    async def test_execute_success(self, agent):
        result = await agent.execute("run task")
        assert result.success is True
        assert "run task" in result.summary

    @pytest.mark.asyncio
    async def test_execute_failure(self, agent):
        result = await agent.execute("fail this")
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_rollback(self, agent):
        assert await agent.rollback("some-id") is True

    @pytest.mark.asyncio
    async def test_execute_with_tracking_no_memory(self, agent):
        """execute_with_tracking works even without memory manager."""
        result = await agent.execute_with_tracking("do something")
        assert result.success is True
        assert result.duration_ms >= 0
