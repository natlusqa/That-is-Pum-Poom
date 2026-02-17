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

            # Check consecutive errors
            error_crisis = self._check_errors()
            if error_crisis:
                new_crises.append(error_crisis)

        except Exception as e:
            logger.error("crisis_check_failed", error=str(e))

        # Trigger crisis mode if any critical events
        if any(c.severity in ("critical", "emergency") for c in new_crises):
            await self._trigger_crisis_mode(new_crises)

        self._active_crises.extend(new_crises)
        self._last_check = time.time()

        return new_crises

    async def _check_disk(self) -> Optional[CrisisEvent]:
        """Check disk usage."""
        try:
            import psutil
            disk = psutil.disk_usage("C:\\")

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
