"""
KORGAN AI — Unified Memory Manager
Three-tier memory architecture: Redis (L1) → ChromaDB (L2) → PostgreSQL (L3)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from core.memory.models import Base, Message, Fact, Conversation, AuditLog, AgentAction

logger = structlog.get_logger("korgan.memory")


class MemoryManager:
    """
    Unified Memory API — manages all three memory tiers.
    
    L1 (Redis): Working memory, current context, session state (TTL: 1h)
    L2 (ChromaDB): Semantic search, conversation embeddings (retention: 30d)
    L3 (PostgreSQL): Permanent facts, decisions, audit log (retention: ∞)
    """

    def __init__(
        self,
        database_url: str,
        redis_url: str,
        chromadb_host: str = "chromadb",
        chromadb_port: int = 8003,
    ):
        self.database_url = database_url
        self.redis_url = redis_url
        self.chromadb_host = chromadb_host
        self.chromadb_port = chromadb_port

        self._engine = None
        self._session_factory = None
        self._redis = None
        self._chroma_client = None
        self._collection = None
        self._current_conversation_id: Optional[str] = None

    async def initialize(self) -> None:
        """Initialize all memory tier connections."""
        # PostgreSQL
        self._engine = create_async_engine(self.database_url, echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("postgresql_initialized")

        # Redis
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("redis_initialized")
        except Exception as e:
            logger.warning("redis_init_failed", error=str(e))

        # ChromaDB
        try:
            import chromadb
            self._chroma_client = chromadb.HttpClient(
                host=self.chromadb_host, port=self.chromadb_port
            )
            self._collection = self._chroma_client.get_or_create_collection(
                name="korgan_memory",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("chromadb_initialized")
        except Exception as e:
            logger.warning("chromadb_init_failed", error=str(e))

    async def close(self) -> None:
        """Close all connections."""
        if self._engine:
            await self._engine.dispose()
        if self._redis:
            await self._redis.close()

    # =========================================================================
    # L1 — Redis (Working Memory)
    # =========================================================================

    async def set_working_memory(
        self, key: str, value: Any, ttl_seconds: int = 3600
    ) -> None:
        """Store in working memory (Redis L1)."""
        if not self._redis:
            return
        try:
            serialized = json.dumps(value, default=str, ensure_ascii=False)
            await self._redis.setex(f"korgan:wm:{key}", ttl_seconds, serialized)
        except Exception as e:
            logger.error("redis_set_failed", key=key, error=str(e))

    async def get_working_memory(self, key: str) -> Any:
        """Retrieve from working memory (Redis L1)."""
        if not self._redis:
            return None
        try:
            data = await self._redis.get(f"korgan:wm:{key}")
            return json.loads(data) if data else None
        except Exception as e:
            logger.error("redis_get_failed", key=key, error=str(e))
            return None

    async def get_session_context(self) -> dict[str, Any]:
        """Get current session context from Redis."""
        if not self._redis:
            return {}
        try:
            keys = []
            async for key in self._redis.scan_iter("korgan:wm:*"):
                keys.append(key)
            context = {}
            for key in keys[:50]:  # Limit to prevent overload
                short_key = key.replace("korgan:wm:", "")
                context[short_key] = await self.get_working_memory(short_key)
            return context
        except Exception as e:
            logger.error("session_context_failed", error=str(e))
            return {}

    # =========================================================================
    # L2 — ChromaDB (Semantic Memory)
    # =========================================================================

    async def semantic_search(
        self, query: str, limit: int = 5, where: dict | None = None
    ) -> list[dict[str, Any]]:
        """Search semantic memory using vector similarity."""
        if not self._collection:
            return []
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=limit,
                where=where,
            )
            items = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    items.append({
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else 0,
                        "id": results["ids"][0][i] if results["ids"] else "",
                    })
            return items
        except Exception as e:
            logger.error("semantic_search_failed", error=str(e))
            return []

    async def store_embedding(
        self, content: str, metadata: dict[str, Any] | None = None
    ) -> str:
        """Store content in semantic memory with auto-generated embedding."""
        if not self._collection:
            return ""
        try:
            doc_id = str(uuid.uuid4())
            meta = metadata or {}
            meta["timestamp"] = datetime.now(timezone.utc).isoformat()

            # Filter metadata to only string/int/float/bool values (ChromaDB requirement)
            clean_meta = {
                k: v for k, v in meta.items()
                if isinstance(v, (str, int, float, bool))
            }

            self._collection.add(
                documents=[content],
                metadatas=[clean_meta],
                ids=[doc_id],
            )
            return doc_id
        except Exception as e:
            logger.error("store_embedding_failed", error=str(e))
            return ""

    # =========================================================================
    # L3 — PostgreSQL (Persistent Memory)
    # =========================================================================

    async def store_message(
        self,
        role: str,
        content: str,
        reasoning: str | None = None,
        interface: str = "api",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a message in persistent memory."""
        async with self._session_factory() as session:
            msg = Message(
                role=role,
                content=content,
                reasoning=reasoning,
                interface=interface,
                conversation_id=self._current_conversation_id,
                metadata_=metadata or {},
            )
            session.add(msg)
            await session.commit()
            msg_id = str(msg.id)

        # Also store in semantic memory for future retrieval
        await self.store_embedding(
            content=f"[{role}]: {content[:500]}",
            metadata={"role": role, "interface": interface, "message_id": msg_id},
        )

        # Update working memory with recent context
        await self.set_working_memory(
            f"last_message_{role}",
            {"content": content[:300], "timestamp": datetime.now(timezone.utc).isoformat()},
            ttl_seconds=3600,
        )

        return msg_id

    async def get_recent_messages(
        self, limit: int = 10, interface: str | None = None
    ) -> list[dict[str, Any]]:
        """Get recent messages from persistent storage."""
        async with self._session_factory() as session:
            query = select(Message).order_by(desc(Message.created_at)).limit(limit)
            if interface:
                query = query.where(Message.interface == interface)
            result = await session.execute(query)
            messages = result.scalars().all()

        return [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "reasoning": m.reasoning,
                "interface": m.interface,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in reversed(messages)
        ]

    async def store_fact(
        self,
        category: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        source_message_id: str | None = None,
    ) -> str:
        """Store a fact in the knowledge base."""
        async with self._session_factory() as session:
            # Check if fact already exists — update if so
            existing = await session.execute(
                select(Fact).where(Fact.category == category, Fact.key == key)
            )
            fact = existing.scalar_one_or_none()

            if fact:
                fact.value = value
                fact.confidence = confidence
                fact.updated_at = datetime.now(timezone.utc)
            else:
                fact = Fact(
                    category=category,
                    key=key,
                    value=value,
                    confidence=confidence,
                    source_message_id=source_message_id,
                )
                session.add(fact)

            await session.commit()
            return str(fact.id)

    async def search_facts(
        self, query: str, category: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search facts — combines keyword and semantic search."""
        results = []

        # PostgreSQL keyword search
        async with self._session_factory() as session:
            stmt = select(Fact).order_by(desc(Fact.updated_at)).limit(limit)
            if category:
                stmt = stmt.where(Fact.category == category)
            result = await session.execute(stmt)
            facts = result.scalars().all()

        for f in facts:
            if query.lower() in f.key.lower() or query.lower() in f.value.lower():
                results.append({
                    "id": str(f.id),
                    "category": f.category,
                    "key": f.key,
                    "value": f.value,
                    "confidence": f.confidence,
                })

        return results[:limit]

    # =========================================================================
    # Audit & Agent Actions
    # =========================================================================

    async def log_audit(
        self,
        action: str,
        agent: str | None = None,
        details: dict | None = None,
        risk_level: str = "low",
        autonomy_level: str | None = None,
        approved_by: str | None = None,
        rollback_data: dict | None = None,
    ) -> str:
        """Log an action to the audit trail."""
        async with self._session_factory() as session:
            entry = AuditLog(
                action=action,
                agent=agent,
                details=details or {},
                risk_level=risk_level,
                autonomy_level=autonomy_level,
                approved_by=approved_by,
                rollback_data=rollback_data,
            )
            session.add(entry)
            await session.commit()
            return str(entry.id)

    async def log_agent_action(
        self,
        agent_name: str,
        action_type: str,
        input_data: dict | None = None,
        output_data: dict | None = None,
        status: str = "pending",
        duration_ms: int | None = None,
        error_message: str | None = None,
    ) -> str:
        """Log an agent action."""
        async with self._session_factory() as session:
            action = AgentAction(
                agent_name=agent_name,
                action_type=action_type,
                input_data=input_data or {},
                output_data=output_data or {},
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
            )
            session.add(action)
            await session.commit()
            return str(action.id)

    # =========================================================================
    # Conversation Management
    # =========================================================================

    async def start_conversation(self, interface: str = "api") -> str:
        """Start a new conversation."""
        async with self._session_factory() as session:
            conv = Conversation(interface=interface)
            session.add(conv)
            await session.commit()
            self._current_conversation_id = str(conv.id)
            return self._current_conversation_id

    async def end_conversation(self, summary: str | None = None) -> None:
        """End current conversation."""
        if not self._current_conversation_id:
            return
        async with self._session_factory() as session:
            conv = await session.get(Conversation, self._current_conversation_id)
            if conv:
                conv.ended_at = datetime.now(timezone.utc)
                conv.summary = summary
                await session.commit()
        self._current_conversation_id = None

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_action_stats(
        self, since: datetime | None = None
    ) -> dict[str, Any]:
        """Get aggregated action statistics from agent_actions table."""
        from sqlalchemy import func, case

        async with self._session_factory() as session:
            query = select(
                func.count(AgentAction.id).label("total"),
                func.count(
                    case((AgentAction.status == "success", 1))
                ).label("success"),
                func.count(
                    case((AgentAction.status == "failed", 1))
                ).label("failed"),
                func.count(
                    case((AgentAction.status == "rolled_back", 1))
                ).label("rolled_back"),
                func.coalesce(func.avg(AgentAction.duration_ms), 0).label("avg_duration_ms"),
            )
            if since:
                query = query.where(AgentAction.created_at >= since)

            result = await session.execute(query)
            row = result.one()

            return {
                "total": row.total,
                "success": row.success,
                "failed": row.failed,
                "rolled_back": row.rolled_back,
                "avg_duration_ms": float(row.avg_duration_ms),
            }

    async def get_cost_stats(
        self, since: datetime | None = None
    ) -> dict[str, Any]:
        """Get API cost statistics from audit logs."""
        from sqlalchemy import func

        async with self._session_factory() as session:
            query = select(AuditLog).where(
                AuditLog.action.like("llm_%")
            )
            if since:
                query = query.where(AuditLog.created_at >= since)

            result = await session.execute(query)
            entries = result.scalars().all()

            total_cost = 0.0
            by_model: dict[str, float] = {}
            request_count = 0

            for entry in entries:
                details = entry.details or {}
                cost = details.get("cost_usd", 0.0)
                model = details.get("model", "unknown")
                total_cost += cost
                by_model[model] = by_model.get(model, 0.0) + cost
                request_count += 1

            return {
                "total_cost_usd": round(total_cost, 4),
                "by_model": by_model,
                "request_count": request_count,
            }

    async def get_stats(self) -> dict[str, Any]:
        """Get memory system statistics."""
        stats = {}

        async with self._session_factory() as session:
            from sqlalchemy import func

            msg_count = await session.execute(select(func.count(Message.id)))
            stats["total_messages"] = msg_count.scalar() or 0

            fact_count = await session.execute(select(func.count(Fact.id)))
            stats["total_facts"] = fact_count.scalar() or 0

            audit_count = await session.execute(select(func.count(AuditLog.id)))
            stats["total_audit_entries"] = audit_count.scalar() or 0

        if self._collection:
            stats["vector_count"] = self._collection.count()

        if self._redis:
            try:
                info = await self._redis.info("memory")
                stats["redis_memory_mb"] = round(
                    info.get("used_memory", 0) / 1024 / 1024, 2
                )
            except Exception:
                pass

        return stats
