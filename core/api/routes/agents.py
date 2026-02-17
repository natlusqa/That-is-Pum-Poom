"""
KORGAN AI — Agents API Routes
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.api.state import get_state

router = APIRouter()


class AgentTaskRequest(BaseModel):
    agent: str
    task: str
    context: str = ""


@router.get("/")
async def list_agents():
    """List all available agents."""
    state = get_state()
    agents = state.get("agents", {})

    return {
        "agents": [
            {
                "name": agent.name,
                "description": agent.description,
                "risk_level": agent.risk_level.value,
            }
            for agent in agents.values()
        ]
    }


@router.post("/execute")
async def execute_agent_task(request: AgentTaskRequest):
    """Execute a task using a specific agent."""
    state = get_state()
    agents = state.get("agents", {})
    agent = agents.get(request.agent)

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent}' not found")

    # Permission check
    permissions = state.get("permissions")
    if permissions:
        check = permissions.check_agent_action(request.agent, request.task)
        if not check.allowed:
            raise HTTPException(status_code=403, detail=check.reason)

    result = await agent.execute_with_tracking(request.task, request.context)

    return {
        "agent": result.agent_name,
        "action": result.action_type,
        "status": result.status.value,
        "summary": result.summary,
        "output": result.output,
        "duration_ms": result.duration_ms,
    }


@router.get("/{agent_name}/plan")
async def get_agent_plan(agent_name: str, task: str):
    """Get execution plan from an agent without executing."""
    state = get_state()
    agents = state.get("agents", {})
    agent = agents.get(agent_name)

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    plan = await agent.plan(task)
    return plan.to_dict()
