"""
KORGAN AI — System API Routes
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.api.state import get_state

router = APIRouter()


class AutonomyChangeRequest(BaseModel):
    level: int


@router.get("/status")
async def system_status():
    """Get full system status."""
    state = get_state()
    autonomy = state.get("autonomy")
    memory = state.get("memory")
    sandbox = state.get("sandbox")

    result = {
        "status": "operational",
        "version": "1.0.0",
    }

    if autonomy:
        result["autonomy"] = autonomy.get_status()
    if memory:
        result["memory"] = await memory.get_stats()
    if sandbox:
        result["sandbox"] = sandbox.get_stats()

    return result


@router.post("/autonomy")
async def change_autonomy(request: AutonomyChangeRequest):
    """Change autonomy level (requires authentication in production)."""
    state = get_state()
    autonomy = state.get("autonomy")
    audit = state.get("audit")

    if not autonomy:
        raise HTTPException(status_code=503, detail="Autonomy engine not ready")

    old_level = autonomy.current_level.name
    success = autonomy.set_level(request.level)

    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {old_level} to level {request.level}",
        )

    if audit:
        await audit.log(
            action="autonomy_level_changed",
            details={"from": old_level, "to": autonomy.current_level.name},
            risk_level="high",
            approved_by="user",
        )

    return {
        "status": "changed",
        "from": old_level,
        "to": autonomy.current_level.name,
    }


@router.get("/autonomy")
async def get_autonomy():
    """Get current autonomy status."""
    state = get_state()
    autonomy = state.get("autonomy")

    if not autonomy:
        raise HTTPException(status_code=503, detail="Autonomy engine not ready")

    return autonomy.get_status()


@router.post("/crisis/enter")
async def enter_crisis():
    """Manually enter crisis mode."""
    state = get_state()
    autonomy = state.get("autonomy")

    if autonomy:
        autonomy.enter_crisis_mode()
        return {"status": "crisis_mode_activated"}
    raise HTTPException(status_code=503, detail="Autonomy engine not ready")


@router.post("/crisis/exit")
async def exit_crisis():
    """Exit crisis mode."""
    state = get_state()
    autonomy = state.get("autonomy")

    if autonomy:
        autonomy.exit_crisis_mode()
        return {"status": "crisis_mode_deactivated"}
    raise HTTPException(status_code=503, detail="Autonomy engine not ready")


@router.post("/rollback/{action_id}")
async def rollback_action(action_id: str):
    """Rollback a specific action."""
    state = get_state()
    # In production: retrieve rollback data from audit log and execute
    return {"status": "rollback_requested", "action_id": action_id}


@router.get("/health/detailed")
async def detailed_health():
    """Detailed health check of all subsystems."""
    state = get_state()
    agents = state.get("agents", {})
    system_agent = agents.get("system_agent")

    if system_agent:
        result = await system_agent.health_check()
        return {
            "core": "healthy",
            "services": result.output,
            "summary": result.summary,
        }

    return {"core": "healthy", "services": "unknown"}
