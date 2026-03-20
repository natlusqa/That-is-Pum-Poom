"""
KORGAN AI — Memory Compression Engine
Compresses old conversations, extracts key facts, deduplicates vectors.
Scheduled daily at 03:00.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import async_sessionmaker

from core.memory.models import Message, Conversation, Fact

logger = structlog.get_logger("korgan.memory.compression")


class MemoryCompressor:
    """
    Memory compression engine for infinite memory with finite storage.
    
    Operations:
    1. Summarize old conversations (>7 days)
    2. Extract key facts into facts table
    3. Compress verbose reasoning logs
    4. Deduplicate similar vectors in ChromaDB
    5. Archive old audit logs
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        llm_router: Any,  # LLMRouter
        chroma_collection: Any = None,
    ):
        self._session_factory = session_factory
        self._llm = llm_router
        self._collection = chroma_collection

    async def run_compression_cycle(self) -> dict[str, Any]:
        """
        Run a full compression cycle.
        Returns statistics about what was compressed.
        """
        logger.info("compression_cycle_started")
        stats = {
            "conversations_compressed": 0,
            "facts_extracted": 0,
            "reasoning_compressed": 0,
            "vectors_deduplicated": 0,
        }

        try:
            # Step 1: Compress old conversations
            stats["conversations_compressed"] = await self._compress_conversations(
                older_than_days=7
            )

            # Step 2: Extract facts from recent messages
            stats["facts_extracted"] = await self._extract_facts(
                from_days=1
            )

            # Step 3: Compress reasoning logs
            stats["reasoning_compressed"] = await self._compress_reasoning(
                older_than_days=3
            )

            # Step 4: Deduplicate vectors
            if self._collection:
                stats["vectors_deduplicated"] = await self._deduplicate_vectors()

        except Exception as e:
            logger.error("compression_cycle_failed", error=str(e))
            stats["error"] = str(e)

        logger.info("compression_cycle_completed", stats=stats)
        return stats

    async def _compress_conversations(self, older_than_days: int = 7) -> int:
        """Summarize and compress old conversations."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        compressed = 0

        async with self._session_factory() as session:
            result = await session.execute(
                select(Conversation).where(
                    and_(
                        Conversation.started_at < cutoff,
                        Conversation.summary.is_(None),
                    )
                )
            )
            conversations = result.scalars().all()

            for conv in conversations:
                # Get messages for this conversation
                msg_result = await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at)
                )
                messages = msg_result.scalars().all()

                if not messages:
                    continue

                # Build conversation text for summarization
                conv_text = "\n".join(
                    f"[{m.role}]: {m.content[:500]}" for m in messages
                )

                # Generate summary using local LLM
                try:
                    summary_response = await self._llm.generate(
                        prompt=f"Кратко (2-3 предложения) суммаризируй этот диалог:\n\n{conv_text[:3000]}",
                        task_type="summarization",
                        force_local=True,
                        temperature=0.3,
                        max_tokens=200,
                    )
                    conv.summary = summary_response.content
                    compressed += 1
                except Exception as e:
                    logger.warning("conversation_summarization_failed", conv_id=str(conv.id), error=str(e))

            await session.commit()

        return compressed

    async def _extract_facts(self, from_days: int = 1) -> int:
        """Extract key facts from recent messages."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=from_days)
        extracted = 0

        async with self._session_factory() as session:
            result = await session.execute(
                select(Message).where(
                    and_(
                        Message.created_at > cutoff,
                        Message.role == "user",
                    )
                )
            )
            messages = result.scalars().all()

            if not messages:
                return 0

            # Batch messages for fact extraction
            batch_text = "\n".join(
                f"- {m.content[:300]}" for m in messages[:20]
            )

            try:
                fact_response = await self._llm.generate(
                    prompt=f"""Извлеки ключевые факты из этих сообщений пользователя.
Верни JSON массив в формате: [{{"category": "preference|project|decision|personal", "key": "краткий ключ", "value": "значение"}}]
Если фактов нет — верни пустой массив [].

Сообщения:
{batch_text}""",
                    task_type="extraction",
                    force_local=True,
                    temperature=0.1,
                    max_tokens=500,
                )

                # Parse facts
                import json
                content = fact_response.content.strip()
                # Try to find JSON array in response
                start = content.find("[")
                end = content.rfind("]") + 1
                if start >= 0 and end > start:
                    facts = json.loads(content[start:end])
                    for fact_data in facts:
                        fact = Fact(
                            category=fact_data.get("category", "general"),
                            key=fact_data.get("key", ""),
                            value=fact_data.get("value", ""),
                            confidence=0.8,
                        )
                        if fact.key and fact.value:
                            session.add(fact)
                            extracted += 1
                    await session.commit()

            except Exception as e:
                logger.warning("fact_extraction_failed", error=str(e))

        return extracted

    async def _compress_reasoning(self, older_than_days: int = 3) -> int:
        """Compress verbose reasoning logs to save space."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        compressed = 0

        async with self._session_factory() as session:
            result = await session.execute(
                select(Message).where(
                    and_(
                        Message.created_at < cutoff,
                        Message.reasoning.isnot(None),
                        Message.role == "assistant",
                    )
                )
            )
            messages = result.scalars().all()

            for msg in messages:
                if msg.reasoning and len(msg.reasoning) > 500:
                    # Keep only first and last lines of reasoning
                    lines = msg.reasoning.split("\n")
                    if len(lines) > 5:
                        msg.reasoning = "\n".join(
                            lines[:2] + ["  ... (compressed) ..."] + lines[-2:]
                        )
                        compressed += 1

            await session.commit()

        return compressed

    async def _deduplicate_vectors(self) -> int:
        """Remove duplicate or very similar vectors from ChromaDB."""
        if not self._collection:
            return 0

        count_before = self._collection.count()
        if count_before < 10:
            return 0

        removed = 0
        batch_size = 100
        ids_to_remove: list[str] = []
        seen_hashes: set[str] = set()

        try:
            # Process in batches
            offset = 0
            while offset < count_before:
                results = self._collection.get(
                    limit=batch_size,
                    offset=offset,
                    include=["documents", "metadatas"],
                )

                if not results or not results["ids"]:
                    break

                for i, doc_id in enumerate(results["ids"]):
                    doc = results["documents"][i] if results["documents"] else ""

                    # Create a content hash for exact/near-exact dedup
                    import hashlib
                    # Normalize whitespace for comparison
                    normalized = " ".join(doc.split()).strip().lower()
                    content_hash = hashlib.md5(normalized.encode()).hexdigest()

                    if content_hash in seen_hashes:
                        ids_to_remove.append(doc_id)
                    else:
                        seen_hashes.add(content_hash)

                offset += batch_size

            # Remove duplicates
            if ids_to_remove:
                # ChromaDB delete in batches of 100
                for i in range(0, len(ids_to_remove), 100):
                    batch = ids_to_remove[i : i + 100]
                    self._collection.delete(ids=batch)
                removed = len(ids_to_remove)

            logger.info(
                "vector_dedup_completed",
                before=count_before,
                removed=removed,
                after=count_before - removed,
            )

        except Exception as e:
            logger.warning("vector_dedup_failed", error=str(e))

        return removed
