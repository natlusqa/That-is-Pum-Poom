"""
KORGAN AI — Task Scheduler
APScheduler-based cron system for periodic intelligence tasks.

Schedule:
- Self-analysis:      Daily at 02:00
- Memory compression: Daily at 03:00
- Daily brief:        Daily at 08:00
- Feedback evaluation: Every hour
- Crisis check:       Every 5 minutes
- Improvement cycle:  Weekly on Sundays at 04:00
"""

from __future__ import annotations

from typing import Any, Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = structlog.get_logger("korgan.scheduler")


class KorganScheduler:
    """
    Central scheduler for all periodic KORGAN tasks.

    Wraps APScheduler and manages intelligence, memory, and monitoring jobs.
    """

    def __init__(
        self,
        self_analysis: Any = None,
        daily_brief: Any = None,
        crisis_detector: Any = None,
        memory_compressor: Any = None,
        feedback_loop: Any = None,
        improvement_engine: Any = None,
        predictive_engine: Any = None,
        telegram_notifier: Any = None,
    ):
        self._scheduler = AsyncIOScheduler(timezone="Asia/Almaty")

        self._self_analysis = self_analysis
        self._daily_brief = daily_brief
        self._crisis = crisis_detector
        self._compressor = memory_compressor
        self._feedback = feedback_loop
        self._improvement = improvement_engine
        self._predictive = predictive_engine
        self._notifier = telegram_notifier

        self._running = False

    def start(self) -> None:
        """Register all jobs and start the scheduler."""
        if self._running:
            return

        # Daily self-analysis at 02:00
        if self._self_analysis:
            self._scheduler.add_job(
                self._run_self_analysis,
                CronTrigger(hour=2, minute=0),
                id="self_analysis",
                name="Daily Self-Analysis",
                replace_existing=True,
            )

        # Memory compression at 03:00
        if self._compressor:
            self._scheduler.add_job(
                self._run_compression,
                CronTrigger(hour=3, minute=0),
                id="memory_compression",
                name="Memory Compression",
                replace_existing=True,
            )

        # Daily brief at 08:00
        if self._daily_brief:
            self._scheduler.add_job(
                self._run_daily_brief,
                CronTrigger(hour=8, minute=0),
                id="daily_brief",
                name="Daily Intelligence Brief",
                replace_existing=True,
            )

        # Crisis check every 5 minutes
        if self._crisis:
            self._scheduler.add_job(
                self._run_crisis_check,
                IntervalTrigger(minutes=5),
                id="crisis_check",
                name="Crisis Detection",
                replace_existing=True,
            )

        # Feedback evaluation every hour
        if self._feedback:
            self._scheduler.add_job(
                self._run_feedback_evaluation,
                IntervalTrigger(hours=1),
                id="feedback_eval",
                name="Feedback Evaluation",
                replace_existing=True,
            )

        # Weekly improvement cycle — Sundays at 04:00
        if self._improvement:
            self._scheduler.add_job(
                self._run_improvement_cycle,
                CronTrigger(day_of_week="sun", hour=4, minute=0),
                id="improvement_cycle",
                name="Weekly Improvement Cycle",
                replace_existing=True,
            )

        self._scheduler.start()
        self._running = True
        logger.info(
            "scheduler_started",
            jobs=len(self._scheduler.get_jobs()),
        )

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("scheduler_stopped")

    def get_jobs(self) -> list[dict[str, Any]]:
        """List all scheduled jobs."""
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in self._scheduler.get_jobs()
        ]

    # =========================================================================
    # Job runners (wrap with error handling and notifications)
    # =========================================================================

    async def _run_self_analysis(self) -> None:
        """Run daily self-analysis."""
        logger.info("scheduled_self_analysis_started")
        try:
            report = await self._self_analysis.run_analysis()
            logger.info(
                "scheduled_self_analysis_completed",
                score=report.overall_score,
            )
            if self._notifier:
                await self._notifier(
                    f"📊 Самоанализ завершён\nОценка: {report.overall_score:.0f}/100\n"
                    f"Действий: {report.total_actions}, "
                    f"Субоптимальных: {len(report.suboptimal_decisions)}"
                )
        except Exception as e:
            logger.error("scheduled_self_analysis_failed", error=str(e))

    async def _run_compression(self) -> None:
        """Run memory compression."""
        logger.info("scheduled_compression_started")
        try:
            stats = await self._compressor.run_compression_cycle()
            logger.info("scheduled_compression_completed", stats=stats)
        except Exception as e:
            logger.error("scheduled_compression_failed", error=str(e))

    async def _run_daily_brief(self) -> None:
        """Generate and send daily brief."""
        logger.info("scheduled_daily_brief_started")
        try:
            brief = await self._daily_brief.generate()
            logger.info("scheduled_daily_brief_generated", length=len(brief))
            if self._notifier:
                await self._notifier(brief)
        except Exception as e:
            logger.error("scheduled_daily_brief_failed", error=str(e))

    async def _run_crisis_check(self) -> None:
        """Run periodic crisis check."""
        try:
            events = await self._crisis.check()
            if events:
                logger.warning(
                    "crisis_events_detected",
                    count=len(events),
                    triggers=[e.trigger for e in events],
                )
                if self._notifier:
                    for event in events:
                        await self._notifier(
                            f"🚨 CRISIS [{event.severity.upper()}]: {event.trigger}\n"
                            f"{event.details}\n"
                            f"Remediation: {event.auto_remediation or 'Manual intervention required'}"
                        )
        except Exception as e:
            logger.error("scheduled_crisis_check_failed", error=str(e))

    async def _run_feedback_evaluation(self) -> None:
        """Run feedback evaluation cycle."""
        try:
            metrics = await self._feedback.evaluate_cycle()
            if metrics.get("status") != "insufficient_data":
                applied = await self._feedback.apply_insights()
                if applied:
                    logger.info("feedback_insights_applied", count=len(applied))
        except Exception as e:
            logger.error("scheduled_feedback_eval_failed", error=str(e))

    async def _run_improvement_cycle(self) -> None:
        """Run weekly improvement analysis."""
        logger.info("scheduled_improvement_cycle_started")
        try:
            suggestions = await self._improvement.run_improvement_cycle()
            report = self._improvement.generate_weekly_report()
            logger.info(
                "scheduled_improvement_completed",
                suggestions=len(suggestions),
            )
            if self._notifier and suggestions:
                await self._notifier(report[:4000])
        except Exception as e:
            logger.error("scheduled_improvement_failed", error=str(e))
