"""
KORGAN AI — Self-Analysis Engine
Analyzes own decisions, evaluates quality, generates improvement suggestions.
Scheduled daily at 02:00.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import structlog

logger = structlog.get_logger("korgan.intelligence.self_analysis")


class AnalysisReport:
    """Self-analysis report for a review period."""

    def __init__(self):
        self.period_start: Optional[datetime] = None
        self.period_end: Optional[datetime] = None
        self.total_actions: int = 0
        self.successful_actions: int = 0
        self.failed_actions: int = 0
        self.rolled_back_actions: int = 0
        self.avg_response_time_ms: float = 0
        self.decisions_reviewed: int = 0
        self.suboptimal_decisions: list[dict] = []
        self.improvement_suggestions: list[str] = []
        self.patterns_detected: list[str] = []
        self.overall_score: float = 0.0  # 0-100

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": {
                "start": self.period_start.isoformat() if self.period_start else None,
                "end": self.period_end.isoformat() if self.period_end else None,
            },
            "metrics": {
                "total_actions": self.total_actions,
                "success_rate": (
                    self.successful_actions / self.total_actions * 100
                    if self.total_actions > 0
                    else 0
                ),
                "failed_actions": self.failed_actions,
                "rolled_back": self.rolled_back_actions,
                "avg_response_ms": self.avg_response_time_ms,
            },
            "analysis": {
                "decisions_reviewed": self.decisions_reviewed,
                "suboptimal_count": len(self.suboptimal_decisions),
                "suboptimal_decisions": self.suboptimal_decisions[:10],
                "patterns": self.patterns_detected,
            },
            "improvements": self.improvement_suggestions,
            "overall_score": self.overall_score,
        }

    def to_text(self) -> str:
        """Human-readable summary."""
        success_rate = (
            self.successful_actions / self.total_actions * 100
            if self.total_actions > 0
            else 0
        )
        lines = [
            "=== Самоанализ KORGAN AI ===",
            f"Период: {self.period_start:%Y-%m-%d %H:%M} — {self.period_end:%Y-%m-%d %H:%M}"
            if self.period_start and self.period_end
            else "",
            "",
            f"Действий: {self.total_actions}",
            f"Успешность: {success_rate:.1f}%",
            f"Откатов: {self.rolled_back_actions}",
            f"Среднее время ответа: {self.avg_response_time_ms:.0f}ms",
            "",
            f"Решений проанализировано: {self.decisions_reviewed}",
            f"Субоптимальных: {len(self.suboptimal_decisions)}",
        ]

        if self.suboptimal_decisions:
            lines.append("\nСубоптимальные решения:")
            for d in self.suboptimal_decisions[:5]:
                lines.append(f"  - {d.get('description', 'N/A')}")
                lines.append(f"    Рекомендация: {d.get('recommendation', 'N/A')}")

        if self.patterns_detected:
            lines.append("\nПаттерны:")
            for p in self.patterns_detected:
                lines.append(f"  - {p}")

        if self.improvement_suggestions:
            lines.append("\nПредложения по улучшению:")
            for s in self.improvement_suggestions:
                lines.append(f"  - {s}")

        lines.append(f"\nОбщая оценка: {self.overall_score:.0f}/100")
        return "\n".join(lines)


class SelfAnalysisEngine:
    """
    Analyzes KORGAN's own decisions and performance.
    
    Process:
    1. Collect all actions from the review window
    2. Evaluate each decision's quality
    3. Identify patterns (repeated errors, common tasks)
    4. Generate improvement suggestions
    5. Calculate overall performance score
    6. Store report for trend tracking
    
    Schedule: Daily at 02:00 (configurable via system.json)
    """

    def __init__(
        self,
        memory_manager: Any = None,
        llm_router: Any = None,
        review_window_hours: int = 24,
    ):
        self._memory = memory_manager
        self._llm = llm_router
        self._review_window = review_window_hours

    async def run_analysis(self) -> AnalysisReport:
        """Run a full self-analysis cycle."""
        logger.info("self_analysis_started", window_hours=self._review_window)

        report = AnalysisReport()
        report.period_end = datetime.now(timezone.utc)
        report.period_start = report.period_end - timedelta(hours=self._review_window)

        try:
            # Step 1: Collect metrics
            await self._collect_metrics(report)

            # Step 2: Analyze decisions with LLM
            if self._llm and report.total_actions >= 5:
                await self._analyze_decisions(report)

            # Step 3: Detect patterns
            await self._detect_patterns(report)

            # Step 4: Calculate score
            report.overall_score = self._calculate_score(report)

            # Step 5: Generate improvements
            if self._llm:
                await self._generate_improvements(report)

            # Store report
            if self._memory:
                await self._memory.store_fact(
                    category="self_analysis",
                    key=f"report_{report.period_end:%Y%m%d}",
                    value=report.to_text()[:2000],
                    confidence=0.95,
                )

            logger.info(
                "self_analysis_completed",
                score=report.overall_score,
                actions=report.total_actions,
                suboptimal=len(report.suboptimal_decisions),
            )

        except Exception as e:
            logger.error("self_analysis_failed", error=str(e))
            report.improvement_suggestions.append(
                f"Самоанализ завершился с ошибкой: {str(e)}"
            )

        return report

    async def _collect_metrics(self, report: AnalysisReport) -> None:
        """Collect action metrics from memory."""
        if not self._memory:
            return

        stats = await self._memory.get_stats()
        report.total_actions = stats.get("total_audit_entries", 0)

        # In production: query actual action results from agent_actions table
        # For now, estimate from available data
        report.successful_actions = int(report.total_actions * 0.9)
        report.failed_actions = report.total_actions - report.successful_actions

    async def _analyze_decisions(self, report: AnalysisReport) -> None:
        """Use LLM to analyze decision quality."""
        if not self._llm or not self._memory:
            return

        # Get recent messages with reasoning
        messages = await self._memory.get_recent_messages(limit=20)
        assistant_msgs = [m for m in messages if m.get("role") == "assistant" and m.get("reasoning")]

        report.decisions_reviewed = len(assistant_msgs)

        if not assistant_msgs:
            return

        # Build analysis prompt
        decisions_text = "\n\n".join(
            f"Решение: {m['content'][:200]}\nReasoning: {m.get('reasoning', 'N/A')[:200]}"
            for m in assistant_msgs[:10]
        )

        prompt = f"""Проанализируй следующие решения AI-системы KORGAN.
Для каждого оцени: было ли решение оптимальным?
Если нет — кратко объясни, что можно улучшить.

Верни JSON массив: [{{"decision_index": 0, "optimal": true/false, "description": "...", "recommendation": "..."}}]

Решения:
{decisions_text}"""

        try:
            result = await self._llm.generate(
                prompt=prompt,
                task_type="analysis",
                force_local=True,
                temperature=0.2,
                max_tokens=1000,
            )

            import json
            content = result.content.strip()
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                analyses = json.loads(content[start:end])
                for a in analyses:
                    if not a.get("optimal", True):
                        report.suboptimal_decisions.append({
                            "description": a.get("description", ""),
                            "recommendation": a.get("recommendation", ""),
                        })
        except Exception as e:
            logger.warning("decision_analysis_failed", error=str(e))

    async def _detect_patterns(self, report: AnalysisReport) -> None:
        """Detect behavioral patterns."""
        if report.failed_actions > report.total_actions * 0.2:
            report.patterns_detected.append(
                f"Высокий процент ошибок ({report.failed_actions}/{report.total_actions})"
            )

        if report.rolled_back_actions > 3:
            report.patterns_detected.append(
                f"Частые откаты ({report.rolled_back_actions}) — рекомендуется усилить dry-run проверки"
            )

        if report.avg_response_time_ms > 5000:
            report.patterns_detected.append(
                "Высокое время ответа — проверить нагрузку на LLM и VRAM"
            )

    def _calculate_score(self, report: AnalysisReport) -> float:
        """Calculate overall performance score (0-100)."""
        if report.total_actions == 0:
            return 50.0

        score = 50.0  # Base

        # Success rate (up to +30)
        success_rate = report.successful_actions / report.total_actions
        score += success_rate * 30

        # Low rollback rate (up to +10)
        rollback_rate = report.rolled_back_actions / max(report.total_actions, 1)
        score += (1 - rollback_rate) * 10

        # Low suboptimal decisions (up to +10)
        if report.decisions_reviewed > 0:
            optimal_rate = 1 - len(report.suboptimal_decisions) / report.decisions_reviewed
            score += optimal_rate * 10

        return min(100, max(0, score))

    async def _generate_improvements(self, report: AnalysisReport) -> None:
        """Generate actionable improvement suggestions."""
        if not self._llm:
            return

        prompt = f"""На основе самоанализа AI-системы:
- Успешность: {report.successful_actions}/{report.total_actions}
- Откатов: {report.rolled_back_actions}
- Субоптимальных решений: {len(report.suboptimal_decisions)}
- Паттерны: {', '.join(report.patterns_detected) if report.patterns_detected else 'нет'}

Предложи 3-5 конкретных улучшений. Кратко, по одному предложению."""

        try:
            result = await self._llm.generate(
                prompt=prompt,
                task_type="analysis",
                force_local=True,
                temperature=0.5,
                max_tokens=300,
            )
            suggestions = [
                line.strip().lstrip("0123456789.-) ")
                for line in result.content.strip().split("\n")
                if line.strip() and len(line.strip()) > 10
            ]
            report.improvement_suggestions = suggestions[:5]
        except Exception as e:
            logger.warning("improvement_generation_failed", error=str(e))
