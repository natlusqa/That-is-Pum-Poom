"""
KORGAN AI — Predictive Recommendations Engine
Pattern-based predictions and proactive suggestions.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any
from collections import Counter

import structlog

logger = structlog.get_logger("korgan.intelligence.predictive")


class Prediction:
    """A single predictive recommendation."""

    def __init__(
        self,
        category: str,
        message: str,
        confidence: float,
        action_suggestion: str | None = None,
    ):
        self.category = category  # routine, maintenance, project, health
        self.message = message
        self.confidence = confidence  # 0.0 - 1.0
        self.action_suggestion = action_suggestion
        self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "message": self.message,
            "confidence": self.confidence,
            "action": self.action_suggestion,
            "time": self.created_at.isoformat(),
        }

    def to_text(self) -> str:
        conf = f"({self.confidence:.0%})"
        text = f"[{self.category}] {conf} {self.message}"
        if self.action_suggestion:
            text += f"\n  → {self.action_suggestion}"
        return text


class PredictiveEngine:
    """
    Pattern-based predictive recommendation engine.
    
    Analyzes behavioral patterns to make proactive suggestions:
    - Routine detection (user usually commits at X time)
    - Maintenance reminders (project not updated for N days)
    - Resource warnings (disk growth rate, log accumulation)
    - Workflow optimization (common task sequences)
    
    Requires minimum 50 data points to start generating predictions.
    """

    def __init__(
        self,
        memory_manager: Any = None,
        min_data_points: int = 50,
    ):
        self._memory = memory_manager
        self._min_data_points = min_data_points
        self._action_history: list[dict[str, Any]] = []

    async def generate_predictions(self) -> list[Prediction]:
        """Generate all current predictions."""
        logger.info("generating_predictions")
        predictions: list[Prediction] = []

        try:
            # Collect data
            await self._load_history()

            if len(self._action_history) < self._min_data_points:
                logger.info(
                    "insufficient_data",
                    current=len(self._action_history),
                    needed=self._min_data_points,
                )
                return [
                    Prediction(
                        category="system",
                        message=f"Накоплено {len(self._action_history)}/{self._min_data_points} точек данных. Предсказания станут доступны после достижения порога.",
                        confidence=1.0,
                    )
                ]

            # Generate predictions from different analyzers
            predictions.extend(await self._routine_predictions())
            predictions.extend(await self._maintenance_predictions())
            predictions.extend(await self._resource_predictions())
            predictions.extend(await self._workflow_predictions())

            # Sort by confidence
            predictions.sort(key=lambda p: p.confidence, reverse=True)

            logger.info("predictions_generated", count=len(predictions))

        except Exception as e:
            logger.error("prediction_failed", error=str(e))

        return predictions

    async def _load_history(self) -> None:
        """Load action history from memory."""
        if self._memory:
            messages = await self._memory.get_recent_messages(limit=200)
            self._action_history = messages

    async def _routine_predictions(self) -> list[Prediction]:
        """Detect routine patterns."""
        predictions = []

        # Analyze time-based patterns
        hour_counts: Counter[int] = Counter()
        for action in self._action_history:
            created = action.get("created_at", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    hour_counts[dt.hour] += 1
                except (ValueError, TypeError):
                    pass

        # Find peak activity hours
        if hour_counts:
            peak_hour = hour_counts.most_common(1)[0][0]
            now_hour = datetime.now(timezone.utc).hour

            # If approaching peak hour
            if abs(now_hour - peak_hour) <= 1:
                predictions.append(
                    Prediction(
                        category="routine",
                        message=f"Обычно вы наиболее активны около {peak_hour}:00 UTC. Подготовить окружение?",
                        confidence=0.7,
                        action_suggestion="Проверить статус всех сервисов и проектов",
                    )
                )

        return predictions

    async def _maintenance_predictions(self) -> list[Prediction]:
        """Predict maintenance needs."""
        predictions = []

        # Check if any facts indicate stale projects
        if self._memory:
            facts = await self._memory.search_facts("project", category="project", limit=10)
            for fact in facts:
                # If a project hasn't been mentioned recently, suggest checking
                predictions.append(
                    Prediction(
                        category="maintenance",
                        message=f"Проект '{fact.get('key', 'unknown')}' — рекомендуется проверить статус",
                        confidence=0.5,
                        action_suggestion="Запустить анализ проекта через code_agent",
                    )
                )

        return predictions[:3]  # Limit

    async def _resource_predictions(self) -> list[Prediction]:
        """Predict resource issues."""
        predictions = []

        try:
            import psutil

            # Disk space
            disk = psutil.disk_usage("C:\\")
            if disk.percent > 80:
                days_until_full = None
                free_gb = disk.free / 1024**3
                predictions.append(
                    Prediction(
                        category="health",
                        message=f"Диск C: заполнен на {disk.percent}% ({free_gb:.0f} GB свободно)",
                        confidence=0.9,
                        action_suggestion="Запустить очистку временных файлов",
                    )
                )

            # RAM pressure
            mem = psutil.virtual_memory()
            if mem.percent > 85:
                predictions.append(
                    Prediction(
                        category="health",
                        message=f"RAM загружена на {mem.percent}%",
                        confidence=0.85,
                        action_suggestion="Проверить процессы и выгрузить неиспользуемые модели",
                    )
                )

        except ImportError:
            pass

        return predictions

    async def _workflow_predictions(self) -> list[Prediction]:
        """Detect common task sequences."""
        predictions = []

        # Analyze recent task patterns
        recent_tasks = [
            a.get("content", "")[:50].lower() for a in self._action_history[-20:]
        ]

        # Common sequences
        if any("git" in t for t in recent_tasks[-5:]):
            if not any("commit" in t for t in recent_tasks[-3:]):
                predictions.append(
                    Prediction(
                        category="routine",
                        message="Обнаружена работа с Git — хотите сделать review и commit?",
                        confidence=0.6,
                        action_suggestion="Запустить git_agent.analyze_diff()",
                    )
                )

        return predictions
