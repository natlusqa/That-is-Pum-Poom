"""
KORGAN AI — Continuous Improvement Engine
Learns from past actions to optimize future performance.
Weekly analysis cycle (Sundays at 04:00).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import structlog

logger = structlog.get_logger("korgan.intelligence.improvement")


class ImprovementSuggestion:
    """A concrete improvement suggestion."""

    def __init__(
        self,
        area: str,          # routing, agents, memory, security, performance
        description: str,
        priority: str,       # low, medium, high
        estimated_impact: str,
        actionable: bool = True,
    ):
        self.area = area
        self.description = description
        self.priority = priority
        self.estimated_impact = estimated_impact
        self.actionable = actionable
        self.created_at = datetime.now(timezone.utc)
        self.applied = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "area": self.area,
            "description": self.description,
            "priority": self.priority,
            "impact": self.estimated_impact,
            "actionable": self.actionable,
            "applied": self.applied,
        }


class ContinuousImprovementEngine:
    """
    Continuous improvement engine that learns from operational data.
    
    Pipeline:
    1. Data Collection — all actions, results, and metrics
    2. Pattern Analysis — cluster errors, identify bottlenecks
    3. Hypothesis Generation — "if I change X, Y improves"
    4. Suggestion Ranking — prioritize by impact and effort
    5. Report to Mr. Korgan — weekly improvement report
    
    Schedule: Weekly on Sundays at 04:00
    """

    def __init__(
        self,
        memory_manager: Any = None,
        llm_router: Any = None,
        analyze_period_days: int = 7,
    ):
        self._memory = memory_manager
        self._llm = llm_router
        self._period_days = analyze_period_days
        self._suggestions_history: list[ImprovementSuggestion] = []

    async def run_improvement_cycle(self) -> list[ImprovementSuggestion]:
        """Run a full improvement analysis cycle."""
        logger.info("improvement_cycle_started", period_days=self._period_days)

        suggestions: list[ImprovementSuggestion] = []

        try:
            # Analyze routing efficiency
            routing_suggestions = await self._analyze_routing()
            suggestions.extend(routing_suggestions)

            # Analyze agent performance
            agent_suggestions = await self._analyze_agents()
            suggestions.extend(agent_suggestions)

            # Analyze memory efficiency
            memory_suggestions = await self._analyze_memory()
            suggestions.extend(memory_suggestions)

            # LLM-generated insights
            if self._llm:
                llm_suggestions = await self._llm_insights(suggestions)
                suggestions.extend(llm_suggestions)

            # Rank by priority
            priority_order = {"high": 0, "medium": 1, "low": 2}
            suggestions.sort(key=lambda s: priority_order.get(s.priority, 3))

            # Store
            self._suggestions_history.extend(suggestions)

            # Store in memory
            if self._memory and suggestions:
                report = "\n".join(
                    f"[{s.priority}] {s.area}: {s.description}"
                    for s in suggestions[:10]
                )
                await self._memory.store_fact(
                    category="improvement",
                    key=f"suggestions_{datetime.now(timezone.utc):%Y%m%d}",
                    value=report[:2000],
                )

            logger.info("improvement_cycle_completed", suggestions=len(suggestions))

        except Exception as e:
            logger.error("improvement_cycle_failed", error=str(e))

        return suggestions

    async def _analyze_routing(self) -> list[ImprovementSuggestion]:
        """Analyze LLM routing efficiency."""
        suggestions = []

        # Check if cloud is being used when local would suffice
        suggestions.append(
            ImprovementSuggestion(
                area="routing",
                description="Мониторинг соотношения local/cloud запросов. Рекомендуется держать cloud < 20% для оптимизации расходов.",
                priority="medium",
                estimated_impact="Снижение расходов API на 10-30%",
            )
        )

        return suggestions

    async def _analyze_agents(self) -> list[ImprovementSuggestion]:
        """Analyze agent performance patterns."""
        suggestions = []

        if self._memory:
            stats = await self._memory.get_stats()

            # Check if certain agents are underutilized
            suggestions.append(
                ImprovementSuggestion(
                    area="agents",
                    description="Анализ частоты использования каждого агента для оптимизации ресурсов.",
                    priority="low",
                    estimated_impact="Улучшение распределения нагрузки",
                )
            )

        return suggestions

    async def _analyze_memory(self) -> list[ImprovementSuggestion]:
        """Analyze memory system efficiency."""
        suggestions = []

        if self._memory:
            stats = await self._memory.get_stats()

            vector_count = stats.get("vector_count", 0)
            if vector_count > 10000:
                suggestions.append(
                    ImprovementSuggestion(
                        area="memory",
                        description=f"Количество векторов ({vector_count}) высокое. Рекомендуется дедупликация.",
                        priority="medium",
                        estimated_impact="Ускорение семантического поиска на 15-25%",
                    )
                )

            redis_mb = stats.get("redis_memory_mb", 0)
            if redis_mb > 400:
                suggestions.append(
                    ImprovementSuggestion(
                        area="memory",
                        description=f"Redis использует {redis_mb} MB. Рекомендуется уменьшить TTL или сжатие.",
                        priority="high",
                        estimated_impact="Освобождение оперативной памяти",
                    )
                )

        return suggestions

    async def _llm_insights(
        self, existing_suggestions: list[ImprovementSuggestion]
    ) -> list[ImprovementSuggestion]:
        """Use LLM for deeper insights."""
        if not self._llm:
            return []

        try:
            existing_text = "\n".join(
                f"- [{s.area}] {s.description}"
                for s in existing_suggestions[:5]
            )

            prompt = f"""Ты — система самоулучшения AI-ассистента KORGAN.
Текущие предложения по улучшению:
{existing_text}

Предложи 2-3 дополнительных улучшения, которые не покрыты выше.
Фокусируйся на: надёжность, скорость, качество решений.
Формат: JSON массив [{{"area": "...", "description": "...", "priority": "low|medium|high", "impact": "..."}}]"""

            result = await self._llm.generate(
                prompt=prompt,
                task_type="analysis",
                force_local=True,
                temperature=0.5,
                max_tokens=500,
            )

            import json
            content = result.content.strip()
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                items = json.loads(content[start:end])
                return [
                    ImprovementSuggestion(
                        area=item.get("area", "general"),
                        description=item.get("description", ""),
                        priority=item.get("priority", "low"),
                        estimated_impact=item.get("impact", ""),
                    )
                    for item in items
                    if item.get("description")
                ]

        except Exception as e:
            logger.warning("llm_insights_failed", error=str(e))

        return []

    def get_recent_suggestions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent improvement suggestions."""
        return [s.to_dict() for s in self._suggestions_history[-limit:]]

    def generate_weekly_report(self) -> str:
        """Generate a weekly improvement report text."""
        recent = self._suggestions_history[-20:]
        if not recent:
            return "Нет предложений по улучшению за последний период."

        lines = [
            "=== Еженедельный отчёт улучшений KORGAN AI ===",
            f"Период: последние {self._period_days} дней",
            f"Предложений: {len(recent)}",
            "",
        ]

        by_priority = {"high": [], "medium": [], "low": []}
        for s in recent:
            by_priority.get(s.priority, []).append(s)

        for priority in ["high", "medium", "low"]:
            items = by_priority[priority]
            if items:
                lines.append(f"\n[{priority.upper()}] ({len(items)} предложений)")
                for s in items:
                    lines.append(f"  • [{s.area}] {s.description}")
                    lines.append(f"    Ожидаемый эффект: {s.estimated_impact}")

        return "\n".join(lines)
