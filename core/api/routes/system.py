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


# =========================================================================
# Intelligence & Scheduler endpoints
# =========================================================================


@router.get("/scheduler/jobs")
async def list_scheduler_jobs():
    """List all scheduled jobs and their next run times."""
    state = get_state()
    scheduler = state.get("scheduler")

    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not ready")

    return {"jobs": scheduler.get_jobs()}


@router.post("/intelligence/self-analysis")
async def run_self_analysis():
    """Trigger self-analysis manually."""
    state = get_state()
    engine = state.get("self_analysis")

    if not engine:
        raise HTTPException(status_code=503, detail="Self-analysis engine not ready")

    report = await engine.run_analysis()
    return report.to_dict()


@router.post("/intelligence/daily-brief")
async def generate_daily_brief():
    """Generate daily brief on demand."""
    state = get_state()
    memory = state.get("memory")
    llm = state.get("llm_router")

    if not memory:
        raise HTTPException(status_code=503, detail="Memory not ready")

    from intelligence.daily_brief import DailyBriefGenerator
    brief_gen = DailyBriefGenerator(memory_manager=memory, llm_router=llm)
    brief = await brief_gen.generate()
    return {"brief": brief}


@router.get("/intelligence/crisis")
async def get_crisis_status():
    """Get current crisis detector status and active crises."""
    state = get_state()
    detector = state.get("crisis_detector")

    if not detector:
        raise HTTPException(status_code=503, detail="Crisis detector not ready")

    return {
        "status": detector.get_status(),
        "active_crises": detector.get_active_crises(),
    }


@router.post("/intelligence/crisis/check")
async def trigger_crisis_check():
    """Trigger an immediate crisis check."""
    state = get_state()
    detector = state.get("crisis_detector")

    if not detector:
        raise HTTPException(status_code=503, detail="Crisis detector not ready")

    events = await detector.check()
    return {
        "events_detected": len(events),
        "events": [e.to_dict() for e in events],
    }


@router.get("/intelligence/feedback")
async def get_feedback_stats():
    """Get feedback loop statistics."""
    state = get_state()
    feedback = state.get("feedback_loop")

    if not feedback:
        raise HTTPException(status_code=503, detail="Feedback loop not ready")

    return feedback.get_stats()


@router.post("/intelligence/predictions")
async def get_predictions():
    """Generate predictive recommendations."""
    state = get_state()
    predictive = state.get("predictive")

    if not predictive:
        raise HTTPException(status_code=503, detail="Predictive engine not ready")

    predictions = await predictive.generate_predictions()
    return {"predictions": [p.to_dict() for p in predictions]}
