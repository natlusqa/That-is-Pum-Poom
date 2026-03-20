"""
KORGAN AI — Crisis Detection & Response
Monitors system health and triggers crisis mode when thresholds are exceeded.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

logger = structlog.get_logger("korgan.intelligence.crisis")


class CrisisEvent:
    """Represents a detected crisis event."""

    def __init__(
        self,
        trigger: str,
        severity: str,  # warning, critical, emergency
        details: str,
        auto_remediation: str | None = None,
    ):
        self.trigger = trigger
        self.severity = severity
        self.details = details
        self.auto_remediation = auto_remediation
        self.detected_at = datetime.now(timezone.utc)
        self.resolved = False
        self.resolved_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "severity": self.severity,
            "details": self.details,
            "remediation": self.auto_remediation,
            "detected_at": self.detected_at.isoformat(),
            "resolved": self.resolved,
        }


class CrisisDetector:
    """
    Continuous crisis detection system.
    
    Monitors:
    - Consecutive errors (threshold: 3)
    - Disk usage (threshold: 90%)
    - VRAM usage (threshold: 95%)
    - API cost (threshold: 90% of daily limit)
    - Unusual activity patterns
    
    On crisis:
    1. Downgrade to MANUAL autonomy
    2. Send immediate Telegram notification
    3. Run auto-diagnostics
    4. Propose remediation plan
    5. Log crisis event
    """

    def __init__(
        self,
        autonomy_engine: Any = None,
        memory_manager: Any = None,
        config: dict[str, Any] | None = None,
    ):
        self._autonomy = autonomy_engine
        self._memory = memory_manager
        self._config = config or {}

        # Thresholds
        triggers = self._config.get("triggers", {})
        self._consecutive_error_threshold = triggers.get("consecutive_errors", 3)
        self._disk_threshold = triggers.get("disk_usage_percent", 90)
        self._vram_threshold = triggers.get("vram_usage_percent", 95)
        self._api_cost_threshold = triggers.get("api_cost_percent", 90)

        # State
        self._active_crises: list[CrisisEvent] = []
        self._consecutive_errors = 0
        self._last_check: Optional[float] = None

    async def check(self) -> list[CrisisEvent]:
        """Run all crisis checks. Returns list of new crisis events."""
        new_crises: list[CrisisEvent] = []

        try:
            # Check disk usage
            disk_crisis = await self._check_disk()
            if disk_crisis:
                new_crises.append(disk_crisis)

            # Check VRAM
            vram_crisis = await self._check_vram()
            if vram_crisis:
                new_crises.append(vram_crisis)

            # Check CPU overload
            cpu_crisis = await self._check_cpu()
            if cpu_crisis:
                new_crises.append(cpu_crisis)

            # Check RAM pressure
            ram_crisis = await self._check_ram()
            if ram_crisis:
                new_crises.append(ram_crisis)

            # Check consecutive errors
            error_crisis = self._check_errors()
            if error_crisis:
                new_crises.append(error_crisis)

            # Check API cost budget
            cost_crisis = await self._check_api_cost()
            if cost_crisis:
                new_crises.append(cost_crisis)

        except Exception as e:
            logger.error("crisis_check_failed", error=str(e))

        # Deduplicate — don't re-trigger active crises
        active_triggers = {c.trigger for c in self._active_crises if not c.resolved}
        new_crises = [c for c in new_crises if c.trigger not in active_triggers]

        # Trigger crisis mode if any critical events
        if any(c.severity in ("critical", "emergency") for c in new_crises):
            await self._trigger_crisis_mode(new_crises)

        self._active_crises.extend(new_crises)
        self._last_check = time.time()

        # Auto-resolve: check if previously active crises are now OK
        await self._auto_resolve()

        return new_crises

    async def _check_disk(self) -> Optional[CrisisEvent]:
        """Check disk usage."""
        try:
            import psutil
            import platform as _platform
            _root = "/" if _platform.system() != "Windows" else "C:\\"
            disk = psutil.disk_usage(_root)

            if disk.percent >= self._disk_threshold:
                free_gb = disk.free / 1024**3
                return CrisisEvent(
                    trigger="disk_usage",
                    severity="critical" if disk.percent >= 95 else "warning",
                    details=f"Disk C: {disk.percent}% used ({free_gb:.1f} GB free)",
                    auto_remediation="Очистка temp файлов и ротация логов",
                )
        except Exception as e:
            logger.warning("disk_check_failed", error=str(e))
        return None

    async def _check_vram(self) -> Optional[CrisisEvent]:
        """Check GPU VRAM usage."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 2:
                    used = int(parts[0])
                    total = int(parts[1])
                    usage_pct = (used / total) * 100

                    if usage_pct >= self._vram_threshold:
                        return CrisisEvent(
                            trigger="vram_usage",
                            severity="critical",
                            details=f"VRAM: {used}/{total} MB ({usage_pct:.0f}%)",
                            auto_remediation="Выгрузить неиспользуемые модели из VRAM",
                        )
        except Exception as e:
            logger.warning("vram_check_failed", error=str(e))
        return None

    def _check_errors(self) -> Optional[CrisisEvent]:
        """Check consecutive error count."""
        if self._consecutive_errors >= self._consecutive_error_threshold:
            return CrisisEvent(
                trigger="consecutive_errors",
                severity="critical",
                details=f"{self._consecutive_errors} consecutive errors detected",
                auto_remediation="Переключение в Manual mode, диагностика",
            )
        return None

    def record_error(self) -> None:
        """Record an error occurrence."""
        self._consecutive_errors += 1
        logger.warning("error_recorded", consecutive=self._consecutive_errors)

    def record_success(self) -> None:
        """Record a success (resets error counter)."""
        self._consecutive_errors = 0

    async def _trigger_crisis_mode(self, events: list[CrisisEvent]) -> None:
        """Activate crisis mode and notify."""
        logger.critical(
            "crisis_mode_triggered",
            events=[e.trigger for e in events],
        )

        # Downgrade autonomy to manual
        if self._autonomy:
            self._autonomy.enter_crisis_mode()

        # Log to memory
        if self._memory:
            for event in events:
                await self._memory.log_audit(
                    action=f"crisis_{event.trigger}",
                    details=event.to_dict(),
                    risk_level="critical",
                )

    async def resolve_crisis(self, trigger: str) -> bool:
        """Mark a crisis as resolved."""
        for crisis in self._active_crises:
            if crisis.trigger == trigger and not crisis.resolved:
                crisis.resolved = True
                crisis.resolved_at = datetime.now(timezone.utc)
                logger.info("crisis_resolved", trigger=trigger)
                return True
        return False

    def get_active_crises(self) -> list[dict[str, Any]]:
        """Get all active (unresolved) crises."""
        return [c.to_dict() for c in self._active_crises if not c.resolved]

    async def _check_cpu(self) -> Optional[CrisisEvent]:
        """Check CPU usage."""
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent >= 95:
                return CrisisEvent(
                    trigger="cpu_overload",
                    severity="critical",
                    details=f"CPU at {cpu_percent}% — system overloaded",
                    auto_remediation="Проверить процессы, приостановить фоновые задачи",
                )
            elif cpu_percent >= 85:
                return CrisisEvent(
                    trigger="cpu_high",
                    severity="warning",
                    details=f"CPU at {cpu_percent}%",
                    auto_remediation="Мониторинг процессов",
                )
        except Exception as e:
            logger.warning("cpu_check_failed", error=str(e))
        return None

    async def _check_ram(self) -> Optional[CrisisEvent]:
        """Check RAM usage."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            if mem.percent >= 95:
                free_gb = mem.available / 1024**3
                return CrisisEvent(
                    trigger="ram_critical",
                    severity="critical",
                    details=f"RAM at {mem.percent}% ({free_gb:.1f} GB free)",
                    auto_remediation="Выгрузить модели из памяти, очистить кэш Redis",
                )
            elif mem.percent >= 85:
                return CrisisEvent(
                    trigger="ram_high",
                    severity="warning",
                    details=f"RAM at {mem.percent}%",
                    auto_remediation="Мониторинг потребления памяти",
                )
        except Exception as e:
            logger.warning("ram_check_failed", error=str(e))
        return None

    async def _check_api_cost(self) -> Optional[CrisisEvent]:
        """Check daily API cost against budget."""
        if not self._memory:
            return None
        try:
            cost_stats = await self._memory.get_cost_stats(
                since=datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
            )
            total_cost = cost_stats.get("total_cost_usd", 0)
            daily_limit = self._config.get("daily_api_budget_usd", 5.0)
            usage_pct = (total_cost / daily_limit) * 100 if daily_limit > 0 else 0

            if usage_pct >= self._api_cost_threshold:
                return CrisisEvent(
                    trigger="api_cost",
                    severity="critical" if usage_pct >= 100 else "warning",
                    details=f"API cost ${total_cost:.2f} / ${daily_limit:.2f} ({usage_pct:.0f}%)",
                    auto_remediation="Переключить все запросы на локальный Ollama",
                )
        except Exception as e:
            logger.warning("api_cost_check_failed", error=str(e))
        return None

    async def _auto_resolve(self) -> None:
        """Auto-resolve crises that are no longer active."""
        try:
            import psutil
            import platform as _platform
            _root = "/" if _platform.system() != "Windows" else "C:\\"

            for crisis in self._active_crises:
                if crisis.resolved:
                    continue

                if crisis.trigger == "disk_usage":
                    disk = psutil.disk_usage(_root)
                    if disk.percent < self._disk_threshold - 5:
                        crisis.resolved = True
                        crisis.resolved_at = datetime.now(timezone.utc)
                        logger.info("crisis_auto_resolved", trigger=crisis.trigger)

                elif crisis.trigger in ("ram_critical", "ram_high"):
                    mem = psutil.virtual_memory()
                    if mem.percent < 80:
                        crisis.resolved = True
                        crisis.resolved_at = datetime.now(timezone.utc)
                        logger.info("crisis_auto_resolved", trigger=crisis.trigger)

                elif crisis.trigger in ("cpu_overload", "cpu_high"):
                    cpu = psutil.cpu_percent(interval=0.5)
                    if cpu < 80:
                        crisis.resolved = True
                        crisis.resolved_at = datetime.now(timezone.utc)
                        logger.info("crisis_auto_resolved", trigger=crisis.trigger)

                elif crisis.trigger == "consecutive_errors":
                    if self._consecutive_errors == 0:
                        crisis.resolved = True
                        crisis.resolved_at = datetime.now(timezone.utc)
                        logger.info("crisis_auto_resolved", trigger=crisis.trigger)
        except Exception as e:
            logger.warning("auto_resolve_failed", error=str(e))

    def get_status(self) -> dict[str, Any]:
        """Get crisis detector status."""
        return {
            "active_crises": len([c for c in self._active_crises if not c.resolved]),
            "total_crises": len(self._active_crises),
            "consecutive_errors": self._consecutive_errors,
            "last_check": self._last_check,
            "thresholds": {
                "disk_percent": self._disk_threshold,
                "vram_percent": self._vram_threshold,
                "consecutive_errors": self._consecutive_error_threshold,
            },
        }
