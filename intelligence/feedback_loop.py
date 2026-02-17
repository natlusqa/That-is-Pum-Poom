"""
KORGAN AI — Full Feedback Loop
Closes the loop: Action → Result → Evaluate → Learn → Improve Future Decisions.
Integrates multi-modal signals (voice/vision) into the intelligence pipeline.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import structlog

logger = structlog.get_logger("korgan.intelligence.feedback_loop")


class FeedbackEntry:
    """A single feedback data point from an action."""

    def __init__(
        self,
        action_id: str,
        agent: str,
        action_type: str,
        input_summary: str,
        output_summary: str,
        success: bool,
        duration_ms: int,
        was_auto: bool = False,
        was_rolled_back: bool = False,
        user_approved: Optional[bool] = None,
        confidence: float = 1.0,
        modality: str = "text",  # text, voice, vision, multimodal
    ):
        self.id = str(uuid.uuid4())[:12]
        self.action_id = action_id
        self.agent = agent
        self.action_type = action_type
        self.input_summary = input_summary
        self.output_summary = output_summary
        self.success = success
        self.duration_ms = duration_ms
        self.was_auto = was_auto
        self.was_rolled_back = was_rolled_back
        self.user_approved = user_approved
        self.confidence = confidence
        self.modality = modality
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "agent": self.agent,
            "action_type": self.action_type,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "was_auto": self.was_auto,
            "was_rolled_back": self.was_rolled_back,
            "user_approved": self.user_approved,
            "confidence": self.confidence,
            "modality": self.modality,
            "timestamp": self.timestamp.isoformat(),
        }


class LearningInsight:
    """An insight learned from feedback data."""

    def __init__(
        self,
        category: str,
        pattern: str,
        recommendation: str,
        confidence: float,
        data_points: int,
    ):
        self.category = category
        self.pattern = pattern
        self.recommendation = recommendation
        self.confidence = confidence
        self.data_points = data_points
        self.applied = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "pattern": self.pattern,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "data_points": self.data_points,
            "applied": self.applied,
        }


class FeedbackLoop:
    """
    Full feedback loop that closes the Action → Evaluate → Learn → Improve cycle.

    Pipeline:
    1. COLLECT  — Every action result feeds into the loop
    2. EVALUATE — Score the action quality vs expected outcome
    3. CLUSTER  — Group similar outcomes to find patterns
    4. LEARN    — Generate insights and adjustment rules
    5. APPLY    — Update routing weights, agent preferences, confidence thresholds
    6. VERIFY   — Track if applied changes actually improved performance

    Multi-modal integration:
    - Voice signals: speaker confidence, recognition latency
    - Vision signals: face match confidence, detection time
    - These feed into the overall decision confidence scoring
    """

    def __init__(
        self,
        memory_manager: Any = None,
        llm_router: Any = None,
        autonomy_engine: Any = None,
    ):
        self._memory = memory_manager
        self._llm = llm_router
        self._autonomy = autonomy_engine

        # In-memory feedback buffer (flushed to DB periodically)
        self._buffer: list[FeedbackEntry] = []
        self._insights: list[LearningInsight] = []

        # Learning state — adjustable parameters
        self._routing_adjustments: dict[str, float] = {}
        self._agent_success_rates: dict[str, list[bool]] = {}
        self._confidence_calibration: float = 0.0  # offset to apply to confidence

    # =========================================================================
    # 1. COLLECT
    # =========================================================================

    async def record(self, entry: FeedbackEntry) -> None:
        """Record a feedback entry from an action result."""
        self._buffer.append(entry)

        # Update running agent success rates
        if entry.agent not in self._agent_success_rates:
            self._agent_success_rates[entry.agent] = []
        self._agent_success_rates[entry.agent].append(entry.success)
        # Keep last 100
        self._agent_success_rates[entry.agent] = self._agent_success_rates[entry.agent][-100:]

        logger.debug(
            "feedback_recorded",
            agent=entry.agent,
            success=entry.success,
            buffer_size=len(self._buffer),
        )

        # Auto-flush to DB every 50 entries
        if len(self._buffer) >= 50:
            await self._flush_to_memory()

    async def record_from_action_result(
        self,
        agent_name: str,
        action_type: str,
        task: str,
        result: Any,
        was_auto: bool = False,
    ) -> None:
        """Convenience method to record from an ActionResult object."""
        entry = FeedbackEntry(
            action_id=getattr(result, "id", str(uuid.uuid4())),
            agent=agent_name,
            action_type=action_type,
            input_summary=task[:200],
            output_summary=getattr(result, "summary", "")[:200],
            success=getattr(result, "success", False),
            duration_ms=getattr(result, "duration_ms", 0),
            was_auto=was_auto,
            was_rolled_back=getattr(result, "status", "") == "rolled_back",
        )
        await self.record(entry)

    async def record_multimodal_signal(
        self,
        signal_type: str,  # voice_recognition, face_recognition, voice_command
        success: bool,
        confidence: float,
        latency_ms: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record a signal from voice/vision systems for feedback analysis."""
        entry = FeedbackEntry(
            action_id=str(uuid.uuid4()),
            agent=f"_{signal_type}",
            action_type=signal_type,
            input_summary=signal_type,
            output_summary=json.dumps(details or {}),
            success=success,
            duration_ms=latency_ms,
            confidence=confidence,
            modality="voice" if "voice" in signal_type else "vision",
        )
        self._buffer.append(entry)

        # If voice/face recognition fails, this affects overall security confidence
        if not success and signal_type in ("face_recognition", "voice_recognition"):
            self._confidence_calibration -= 0.05
            logger.warning(
                "multimodal_failure_recorded",
                signal=signal_type,
                calibration=self._confidence_calibration,
            )

    # =========================================================================
    # 2. EVALUATE — Score action quality
    # =========================================================================

    async def evaluate_cycle(self) -> dict[str, Any]:
        """
        Run evaluation on buffered feedback. Returns evaluation metrics.
        Called periodically (e.g., every hour or by scheduler).
        """
        if len(self._buffer) < 10:
            return {"status": "insufficient_data", "buffer_size": len(self._buffer)}

        logger.info("feedback_evaluation_started", entries=len(self._buffer))

        metrics = {
            "total_entries": len(self._buffer),
            "by_agent": {},
            "overall_success_rate": 0.0,
            "auto_vs_manual": {"auto_success": 0, "manual_success": 0, "auto_total": 0, "manual_total": 0},
            "rollback_rate": 0.0,
            "avg_duration_ms": 0.0,
            "multimodal_signals": {"voice": 0, "vision": 0},
        }

        # Calculate per-agent metrics
        successes = 0
        rollbacks = 0
        total_duration = 0

        for entry in self._buffer:
            agent = entry.agent

            if agent not in metrics["by_agent"]:
                metrics["by_agent"][agent] = {"success": 0, "fail": 0, "total": 0, "avg_ms": 0}

            metrics["by_agent"][agent]["total"] += 1
            if entry.success:
                metrics["by_agent"][agent]["success"] += 1
                successes += 1
            else:
                metrics["by_agent"][agent]["fail"] += 1

            if entry.was_rolled_back:
                rollbacks += 1

            total_duration += entry.duration_ms

            if entry.was_auto:
                metrics["auto_vs_manual"]["auto_total"] += 1
                if entry.success:
                    metrics["auto_vs_manual"]["auto_success"] += 1
            else:
                metrics["auto_vs_manual"]["manual_total"] += 1
                if entry.success:
                    metrics["auto_vs_manual"]["manual_success"] += 1

            if entry.modality == "voice":
                metrics["multimodal_signals"]["voice"] += 1
            elif entry.modality == "vision":
                metrics["multimodal_signals"]["vision"] += 1

        total = len(self._buffer)
        metrics["overall_success_rate"] = successes / total if total > 0 else 0
        metrics["rollback_rate"] = rollbacks / total if total > 0 else 0
        metrics["avg_duration_ms"] = total_duration / total if total > 0 else 0

        # Generate insights
        insights = await self._generate_insights(metrics)
        self._insights.extend(insights)

        # Store metrics
        if self._memory:
            await self._memory.store_fact(
                category="feedback_metrics",
                key=f"eval_{datetime.now(timezone.utc):%Y%m%d_%H}",
                value=json.dumps(metrics, default=str)[:2000],
            )

        logger.info(
            "feedback_evaluation_completed",
            success_rate=metrics["overall_success_rate"],
            insights=len(insights),
        )

        return metrics

    # =========================================================================
    # 3 & 4. CLUSTER + LEARN — Generate insights
    # =========================================================================

    async def _generate_insights(self, metrics: dict[str, Any]) -> list[LearningInsight]:
        """Generate learning insights from evaluation metrics."""
        insights = []

        # Insight: Agent with low success rate
        for agent, data in metrics["by_agent"].items():
            if agent.startswith("_"):
                continue  # Skip multimodal signals
            if data["total"] >= 5:
                rate = data["success"] / data["total"]
                if rate < 0.7:
                    insights.append(LearningInsight(
                        category="agent_performance",
                        pattern=f"Agent '{agent}' success rate: {rate:.0%} ({data['success']}/{data['total']})",
                        recommendation=f"Review {agent} configuration. Consider reducing autonomy for this agent.",
                        confidence=min(0.9, data["total"] / 20),
                        data_points=data["total"],
                    ))

        # Insight: Auto actions performing worse than manual
        auto = metrics["auto_vs_manual"]
        if auto["auto_total"] >= 5 and auto["manual_total"] >= 5:
            auto_rate = auto["auto_success"] / auto["auto_total"]
            manual_rate = auto["manual_success"] / auto["manual_total"]
            if auto_rate < manual_rate - 0.15:
                insights.append(LearningInsight(
                    category="autonomy",
                    pattern=f"Auto success ({auto_rate:.0%}) significantly lower than manual ({manual_rate:.0%})",
                    recommendation="Consider lowering autonomy level or tightening confidence thresholds.",
                    confidence=0.85,
                    data_points=auto["auto_total"] + auto["manual_total"],
                ))

        # Insight: High rollback rate
        if metrics["rollback_rate"] > 0.1:
            insights.append(LearningInsight(
                category="reliability",
                pattern=f"Rollback rate {metrics['rollback_rate']:.0%} exceeds 10% threshold",
                recommendation="Strengthen dry-run checks and increase approval requirements.",
                confidence=0.9,
                data_points=metrics["total_entries"],
            ))

        # Insight: Multimodal failures affecting confidence
        if self._confidence_calibration < -0.1:
            insights.append(LearningInsight(
                category="multimodal",
                pattern=f"Multiple voice/vision failures detected (calibration: {self._confidence_calibration:.2f})",
                recommendation="Check microphone/camera quality. Re-enrollment may be needed.",
                confidence=0.8,
                data_points=abs(int(self._confidence_calibration / 0.05)),
            ))

        # LLM-enhanced insights
        if self._llm and metrics["total_entries"] >= 20:
            llm_insights = await self._llm_insights(metrics)
            insights.extend(llm_insights)

        return insights

    async def _llm_insights(self, metrics: dict[str, Any]) -> list[LearningInsight]:
        """Use LLM to find deeper patterns."""
        try:
            agents_summary = "\n".join(
                f"  {agent}: {data['success']}/{data['total']} success"
                for agent, data in metrics["by_agent"].items()
                if not agent.startswith("_")
            )

            prompt = f"""Analyze these AI system performance metrics and suggest 2 concrete improvements:

Overall success: {metrics['overall_success_rate']:.0%}
Rollback rate: {metrics['rollback_rate']:.0%}
Avg response: {metrics['avg_duration_ms']:.0f}ms

Per agent:
{agents_summary}

Auto vs Manual: auto {metrics['auto_vs_manual']['auto_success']}/{metrics['auto_vs_manual']['auto_total']}, manual {metrics['auto_vs_manual']['manual_success']}/{metrics['auto_vs_manual']['manual_total']}

Return JSON: [{{"pattern": "...", "recommendation": "...", "priority": "high|medium|low"}}]"""

            result = await self._llm.generate(
                prompt=prompt,
                task_type="analysis",
                force_local=True,
                temperature=0.3,
                max_tokens=400,
            )

            content = result.content.strip()
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                items = json.loads(content[start:end])
                return [
                    LearningInsight(
                        category="llm_insight",
                        pattern=item.get("pattern", ""),
                        recommendation=item.get("recommendation", ""),
                        confidence=0.7,
                        data_points=metrics["total_entries"],
                    )
                    for item in items
                    if item.get("pattern")
                ]
        except Exception as e:
            logger.warning("llm_insight_failed", error=str(e))
        return []

    # =========================================================================
    # 5. APPLY — Update system parameters
    # =========================================================================

    async def apply_insights(self) -> list[str]:
        """
        Apply learned insights to system parameters.
        Returns list of changes applied.
        """
        applied = []

        for insight in self._insights:
            if insight.applied:
                continue

            # Only apply high-confidence insights automatically
            if insight.confidence < 0.8:
                continue

            if insight.category == "autonomy" and self._autonomy:
                current = self._autonomy.current_level.value
                if current > 0:
                    logger.info("feedback_applying_insight", insight=insight.pattern)
                    # Don't auto-downgrade, but flag for user
                    applied.append(
                        f"[РЕКОМЕНДАЦИЯ] {insight.recommendation}"
                    )
                    insight.applied = True

            elif insight.category == "agent_performance":
                applied.append(f"[МОНИТОРИНГ] {insight.pattern}")
                insight.applied = True

            elif insight.category == "reliability":
                applied.append(f"[ПРЕДУПРЕЖДЕНИЕ] {insight.recommendation}")
                insight.applied = True

            elif insight.category == "multimodal":
                # Reset calibration after notification
                applied.append(f"[ВНИМАНИЕ] {insight.recommendation}")
                self._confidence_calibration = max(self._confidence_calibration, -0.2)
                insight.applied = True

        if applied and self._memory:
            await self._memory.store_fact(
                category="feedback_applied",
                key=f"applied_{datetime.now(timezone.utc):%Y%m%d_%H}",
                value="\n".join(applied)[:2000],
            )

        return applied

    # =========================================================================
    # 6. VERIFY — Track improvement
    # =========================================================================

    def get_improvement_trend(self) -> dict[str, Any]:
        """Get trend data to verify if applied changes improved performance."""
        if len(self._buffer) < 20:
            return {"status": "insufficient_data"}

        # Split buffer into first half and second half
        mid = len(self._buffer) // 2
        first_half = self._buffer[:mid]
        second_half = self._buffer[mid:]

        first_rate = sum(1 for e in first_half if e.success) / len(first_half)
        second_rate = sum(1 for e in second_half if e.success) / len(second_half)

        return {
            "first_half_success_rate": first_rate,
            "second_half_success_rate": second_rate,
            "improvement": second_rate - first_rate,
            "trending": "up" if second_rate > first_rate else "down" if second_rate < first_rate else "stable",
            "data_points": len(self._buffer),
        }

    def get_confidence_calibration(self) -> float:
        """Get current confidence calibration offset."""
        return self._confidence_calibration

    def get_agent_success_rates(self) -> dict[str, float]:
        """Get current success rates per agent."""
        return {
            agent: sum(results) / len(results) if results else 0
            for agent, results in self._agent_success_rates.items()
        }

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    async def _flush_to_memory(self) -> None:
        """Flush feedback buffer to persistent storage."""
        if not self._memory or not self._buffer:
            return

        try:
            batch_summary = {
                "entries": len(self._buffer),
                "success_rate": sum(1 for e in self._buffer if e.success) / len(self._buffer),
                "agents": list(set(e.agent for e in self._buffer)),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            await self._memory.store_fact(
                category="feedback_batch",
                key=f"batch_{datetime.now(timezone.utc):%Y%m%d_%H%M}",
                value=json.dumps(batch_summary)[:2000],
            )

            # Store individual entries as embeddings for semantic search
            for entry in self._buffer[-10:]:  # Last 10 for vector store
                await self._memory.store_embedding(
                    content=f"[feedback:{entry.agent}] {entry.action_type}: {'success' if entry.success else 'fail'} — {entry.output_summary[:100]}",
                    metadata={
                        "type": "feedback",
                        "agent": entry.agent,
                        "success": str(entry.success),
                        "modality": entry.modality,
                    },
                )

            self._buffer.clear()
            logger.info("feedback_flushed_to_memory")

        except Exception as e:
            logger.error("feedback_flush_failed", error=str(e))

    def get_stats(self) -> dict[str, Any]:
        """Get feedback loop statistics."""
        return {
            "buffer_size": len(self._buffer),
            "total_insights": len(self._insights),
            "applied_insights": sum(1 for i in self._insights if i.applied),
            "confidence_calibration": self._confidence_calibration,
            "agent_rates": self.get_agent_success_rates(),
            "trend": self.get_improvement_trend(),
        }
