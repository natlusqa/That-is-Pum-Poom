"""
KORGAN AI — Daily Intelligence Brief
Morning report delivered via Telegram at 08:00.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import structlog

logger = structlog.get_logger("korgan.intelligence.daily_brief")


class DailyBriefGenerator:
    """
    Generates a comprehensive daily intelligence briefing for Mr. Korgan.
    
    Delivered every morning at 08:00 via Telegram.
    
    Sections:
    1. Actions Summary (last 24h)
    2. Project Status (code quality, TODOs)
    3. Recommendations (improvements, reminders)
    4. Cost Report (API spending)
    5. System Health (resources, uptime)
    6. Trends (week-over-week)
    """

    def __init__(
        self,
        memory_manager: Any = None,
        llm_router: Any = None,
        code_scorer: Any = None,
    ):
        self._memory = memory_manager
        self._llm = llm_router
        self._code_scorer = code_scorer

    async def generate(self) -> str:
        """Generate the daily intelligence brief."""
        logger.info("daily_brief_generating")

        sections = []

        # Header
        now = datetime.now(timezone.utc)
        greeting = self._get_greeting(now)
        sections.append(f"{greeting}, Мистер Корган.\n")

        # Section 1: Actions Summary
        actions_summary = await self._actions_summary()
        sections.append(actions_summary)

        # Section 2: System Health
        health = await self._system_health()
        sections.append(health)

        # Section 3: Recommendations
        recommendations = await self._generate_recommendations()
        sections.append(recommendations)

        # Section 4: Cost Report
        cost_report = await self._cost_report()
        sections.append(cost_report)

        # Section 5: Memory Status
        memory_status = await self._memory_status()
        sections.append(memory_status)

        brief = "\n".join(sections)

        # Store brief in memory
        if self._memory:
            await self._memory.store_fact(
                category="daily_brief",
                key=f"brief_{now:%Y%m%d}",
                value=brief[:2000],
            )

        logger.info("daily_brief_generated", length=len(brief))
        return brief

    def _get_greeting(self, now: datetime) -> str:
        """Context-aware greeting."""
        hour = (now.hour + 6) % 24  # Approximate UTC+6 for Kazakhstan
        if 5 <= hour < 12:
            return "Доброе утро"
        elif 12 <= hour < 17:
            return "Добрый день"
        elif 17 <= hour < 22:
            return "Добрый вечер"
        else:
            return "Доброй ночи"

    async def _actions_summary(self) -> str:
        """Summary of actions in last 24 hours."""
        lines = ["--- Сводка за 24 часа ---"]

        if self._memory:
            stats = await self._memory.get_stats()
            total = stats.get("total_audit_entries", 0)
            messages = stats.get("total_messages", 0)
            lines.append(f"Сообщений обработано: {messages}")
            lines.append(f"Действий выполнено: {total}")
        else:
            lines.append("Данные не доступны (память не инициализирована)")

        return "\n".join(lines)

    async def _system_health(self) -> str:
        """System health overview."""
        lines = ["\n--- Система ---"]

        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("C:\\")

            lines.append(f"CPU: {cpu}%")
            lines.append(f"RAM: {mem.percent}% ({mem.used / 1024**3:.1f}/{mem.total / 1024**3:.1f} GB)")
            lines.append(f"Disk: {disk.percent}% ({disk.free / 1024**3:.0f} GB свободно)")

            # GPU
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 3:
                    lines.append(f"GPU VRAM: {parts[0]}/{parts[1]} MB (load: {parts[2]}%)")
        except Exception as e:
            lines.append(f"Мониторинг недоступен: {str(e)[:50]}")

        return "\n".join(lines)

    async def _generate_recommendations(self) -> str:
        """Generate AI-powered recommendations."""
        lines = ["\n--- Рекомендации ---"]

        if self._llm and self._memory:
            try:
                # Get recent context for recommendations
                recent = await self._memory.get_recent_messages(limit=10)
                context = "\n".join(
                    f"[{m['role']}]: {m['content'][:100]}"
                    for m in recent
                )

                result = await self._llm.generate(
                    prompt=f"""На основе последних взаимодействий с пользователем, дай 2-3 кратких рекомендации.
Контекст: {context[:1500]}

Формат: пронумерованный список. Кратко и по делу.""",
                    task_type="analysis",
                    force_local=True,
                    temperature=0.5,
                    max_tokens=200,
                )
                lines.append(result.content)
            except Exception:
                lines.append("Рекомендации будут доступны после накопления данных.")
        else:
            lines.append("Система накапливает данные для рекомендаций.")

        return "\n".join(lines)

    async def _cost_report(self) -> str:
        """API cost summary."""
        lines = ["\n--- Расходы API ---"]

        # In production: aggregate from audit logs
        lines.append("Детальный отчёт будет доступен после активации cloud LLM.")

        return "\n".join(lines)

    async def _memory_status(self) -> str:
        """Memory system status."""
        lines = ["\n--- Память ---"]

        if self._memory:
            stats = await self._memory.get_stats()
            lines.append(f"Сообщений: {stats.get('total_messages', 0)}")
            lines.append(f"Фактов: {stats.get('total_facts', 0)}")
            lines.append(f"Векторов: {stats.get('vector_count', 0)}")
            if "redis_memory_mb" in stats:
                lines.append(f"Redis: {stats['redis_memory_mb']} MB")
        else:
            lines.append("Не доступно")

        return "\n".join(lines)
