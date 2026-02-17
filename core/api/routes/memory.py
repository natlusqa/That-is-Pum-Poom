"""
KORGAN AI — Memory API Routes
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.api.state import get_state

router = APIRouter()


class StoreFactRequest(BaseModel):
    category: str
    key: str
    value: str
    confidence: float = 1.0


class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    category: str | None = None


@router.get("/stats")
async def memory_stats():
    """Get memory system statistics."""
    state = get_state()
    memory = state.get("memory")

    if not memory:
        raise HTTPException(status_code=503, detail="Memory system not ready")

    return await memory.get_stats()


@router.post("/facts")
async def store_fact(request: StoreFactRequest):
    """Store a fact in the knowledge base."""
    state = get_state()
    memory = state.get("memory")

    if not memory:
        raise HTTPException(status_code=503, detail="Memory system not ready")

    fact_id = await memory.store_fact(
        category=request.category,
        key=request.key,
        value=request.value,
        confidence=request.confidence,
    )

    return {"id": fact_id, "status": "stored"}


@router.post("/search")
async def search_memory(request: SearchRequest):
    """Search across all memory tiers."""
    state = get_state()
    memory = state.get("memory")

    if not memory:
        raise HTTPException(status_code=503, detail="Memory system not ready")

    # Search facts
    facts = await memory.search_facts(
        query=request.query,
        category=request.category,
        limit=request.limit,
    )

    # Semantic search
    semantic = await memory.semantic_search(
        query=request.query,
        limit=request.limit,
    )

    return {
        "facts": facts,
        "semantic_results": semantic,
        "total": len(facts) + len(semantic),
    }


@router.get("/history")
async def get_history(limit: int = 20, interface: str | None = None):
    """Get recent conversation history."""
    state = get_state()
    memory = state.get("memory")

    if not memory:
        raise HTTPException(status_code=503, detail="Memory system not ready")

    messages = await memory.get_recent_messages(limit=limit, interface=interface)
    return {"messages": messages, "count": len(messages)}
