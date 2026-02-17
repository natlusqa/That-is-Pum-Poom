"""
KORGAN AI — Brain API Routes
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.api.state import get_state
from core.brain.orchestrator import OrchestratorRequest

router = APIRouter()


class ChatRequest(BaseModel):
    content: str
    interface: str = "api"
    context: dict = {}


class ChatResponse(BaseModel):
    request_id: str
    content: str
    reasoning: str | None = None
    actions_taken: list = []
    suggested_actions: list = []
    metadata: dict = {}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to KORGAN AI."""
    state = get_state()
    orchestrator = state.get("orchestrator")

    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")

    orch_request = OrchestratorRequest(
        content=request.content,
        interface=request.interface,
        context=request.context,
    )

    response = await orchestrator.process(orch_request)

    return ChatResponse(
        request_id=response.request_id,
        content=response.content,
        reasoning=response.reasoning,
        actions_taken=response.actions_taken,
        suggested_actions=response.suggested_actions,
        metadata=response.metadata,
    )


@router.get("/status")
async def brain_status():
    """Get brain status."""
    state = get_state()
    autonomy = state.get("autonomy")
    llm = state.get("llm_router")

    return {
        "status": "operational",
        "autonomy": autonomy.get_status() if autonomy else None,
        "api_cost_today": llm._cost_tracker.get_today_cost() if llm else 0,
        "api_cost_remaining": llm._cost_tracker.get_remaining() if llm else 0,
    }


@router.post("/approve/{plan_id}")
async def approve_action(plan_id: str):
    """Approve a pending action plan."""
    state = get_state()
    audit = state.get("audit")

    if audit:
        await audit.log(
            action="plan_approved",
            details={"plan_id": plan_id},
            approved_by="user",
        )

    return {"status": "approved", "plan_id": plan_id}


@router.post("/reject/{plan_id}")
async def reject_action(plan_id: str):
    """Reject a pending action plan."""
    state = get_state()
    audit = state.get("audit")

    if audit:
        await audit.log(
            action="plan_rejected",
            details={"plan_id": plan_id},
            approved_by="user",
        )

    return {"status": "rejected", "plan_id": plan_id}
