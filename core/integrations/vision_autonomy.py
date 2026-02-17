"""
KORGAN AI — Vision ↔ Autonomy Integration
Connects face recognition results to autonomy decisions.

Flow:
- Face verified → unlock full autonomy features
- Face failed → downgrade autonomy, notify via Telegram
- Unknown face → alert, log, lock critical actions
- Re-enrollment → requires Telegram confirmation
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger("korgan.integrations.vision_autonomy")


class VisionAutonomyBridge:
    """
    Bridges the Vision system and Autonomy Engine.
    
    Monitors face recognition events and adjusts autonomy/security:
    - Successful verification → confirm identity, allow current autonomy level
    - Failed verification → increment failure counter
    - 3 consecutive failures → downgrade to MANUAL + Telegram alert
    - Unknown face detected → immediate alert + lock critical actions
    """

    def __init__(
        self,
        autonomy_engine: Any = None,
        memory_manager: Any = None,
        feedback_loop: Any = None,
        telegram_notify_url: str = "http://korgan-core:8000",
        owner_telegram_id: str = "",
        max_consecutive_failures: int = 3,
        lockout_duration_seconds: int = 300,
    ):
        self._autonomy = autonomy_engine
        self._memory = memory_manager
        self._feedback = feedback_loop
        self._notify_url = telegram_notify_url
        self._owner_id = owner_telegram_id

        self._max_failures = max_consecutive_failures
        self._lockout_duration = lockout_duration_seconds

        # State
        self._consecutive_failures = 0
        self._last_verified_at: Optional[float] = None
        self._locked_until: Optional[float] = None
        self._identity_confirmed = False

    @property
    def is_locked(self) -> bool:
        """Check if the system is in identity lockout."""
        if self._locked_until is None:
            return False
        if time.time() > self._locked_until:
            self._locked_until = None
            return False
        return True

    @property
    def identity_confirmed(self) -> bool:
        """Check if owner identity is currently confirmed."""
        if not self._identity_confirmed:
            return False
        # Identity confirmation expires after 30 minutes
        if self._last_verified_at and (time.time() - self._last_verified_at) > 1800:
            self._identity_confirmed = False
            return False
        return True

    async def on_face_verified(self, similarity: float, user_id: str) -> dict[str, Any]:
        """Called when face verification succeeds."""
        self._consecutive_failures = 0
        self._identity_confirmed = True
        self._last_verified_at = time.time()
        self._locked_until = None

        logger.info(
            "face_verified",
            user_id=user_id,
            similarity=similarity,
        )

        # Record in feedback loop
        if self._feedback:
            await self._feedback.record_multimodal_signal(
                signal_type="face_recognition",
                success=True,
                confidence=similarity,
                latency_ms=0,
                details={"user_id": user_id},
            )

        # Log to audit
        if self._memory:
            await self._memory.log_audit(
                action="face_verified",
                details={"user_id": user_id, "similarity": similarity},
                risk_level="low",
            )

        return {
            "status": "verified",
            "identity_confirmed": True,
            "autonomy_level": self._autonomy.current_level.name if self._autonomy else "unknown",
        }

    async def on_face_failed(self, similarity: float) -> dict[str, Any]:
        """Called when face verification fails."""
        self._consecutive_failures += 1
        self._identity_confirmed = False

        logger.warning(
            "face_verification_failed",
            similarity=similarity,
            consecutive_failures=self._consecutive_failures,
        )

        # Record in feedback loop
        if self._feedback:
            await self._feedback.record_multimodal_signal(
                signal_type="face_recognition",
                success=False,
                confidence=similarity,
                latency_ms=0,
                details={"consecutive_failures": self._consecutive_failures},
            )

        result = {
            "status": "failed",
            "consecutive_failures": self._consecutive_failures,
            "identity_confirmed": False,
        }

        # Check if we need to escalate
        if self._consecutive_failures >= self._max_failures:
            await self._escalate_face_failure()
            result["escalated"] = True
            result["locked_until"] = self._locked_until

        return result

    async def on_unknown_face(self) -> dict[str, Any]:
        """Called when an unknown face (not enrolled) is detected."""
        logger.warning("unknown_face_detected")

        # Immediate lockout
        self._locked_until = time.time() + self._lockout_duration
        self._identity_confirmed = False

        # Downgrade autonomy
        if self._autonomy:
            self._autonomy.enter_crisis_mode()

        # Log
        if self._memory:
            await self._memory.log_audit(
                action="unknown_face_detected",
                details={"locked_for_seconds": self._lockout_duration},
                risk_level="critical",
            )

        # Notify via Telegram
        await self._send_telegram_alert(
            "ВНИМАНИЕ: Обнаружено неизвестное лицо перед камерой.\n"
            f"Система заблокирована на {self._lockout_duration // 60} минут.\n"
            "Автономность понижена до MANUAL.\n"
            "Отправьте /unlock для разблокировки."
        )

        return {
            "status": "unknown_face",
            "locked": True,
            "locked_until": self._locked_until,
            "autonomy": "MANUAL",
        }

    async def on_voice_verified(self, similarity: float) -> dict[str, Any]:
        """Called when voice speaker verification succeeds."""
        logger.info("voice_verified", similarity=similarity)

        if self._feedback:
            await self._feedback.record_multimodal_signal(
                signal_type="voice_recognition",
                success=True,
                confidence=similarity,
                latency_ms=0,
            )

        # Voice alone doesn't confirm identity but adds confidence
        return {"status": "voice_verified", "similarity": similarity}

    async def on_voice_failed(self, similarity: float) -> dict[str, Any]:
        """Called when voice speaker verification fails."""
        logger.warning("voice_verification_failed", similarity=similarity)

        if self._feedback:
            await self._feedback.record_multimodal_signal(
                signal_type="voice_recognition",
                success=False,
                confidence=similarity,
                latency_ms=0,
            )

        return {"status": "voice_failed", "similarity": similarity}

    async def unlock(self, confirmed_via: str = "telegram") -> dict[str, Any]:
        """Unlock the system after identity lockout."""
        self._locked_until = None
        self._consecutive_failures = 0

        if self._autonomy and self._autonomy.is_crisis:
            self._autonomy.exit_crisis_mode()

        logger.info("system_unlocked", confirmed_via=confirmed_via)

        if self._memory:
            await self._memory.log_audit(
                action="system_unlocked",
                details={"confirmed_via": confirmed_via},
                risk_level="medium",
            )

        return {"status": "unlocked", "autonomy": self._autonomy.current_level.name if self._autonomy else "unknown"}

    async def request_re_enrollment(self) -> dict[str, Any]:
        """Request face re-enrollment (must be confirmed via Telegram)."""
        await self._send_telegram_alert(
            "Запрос на повторную регистрацию лица.\n"
            "Подтвердите через /reenroll чтобы начать процесс."
        )
        return {"status": "re_enrollment_requested", "confirmation": "telegram"}

    async def _escalate_face_failure(self) -> None:
        """Escalate after too many face verification failures."""
        logger.critical(
            "face_failure_escalated",
            failures=self._consecutive_failures,
        )

        # Lock system
        self._locked_until = time.time() + self._lockout_duration

        # Downgrade autonomy to MANUAL
        if self._autonomy:
            old_level = self._autonomy.current_level.name
            self._autonomy.enter_crisis_mode()

            if self._memory:
                await self._memory.log_audit(
                    action="autonomy_downgraded_face_failure",
                    details={
                        "from_level": old_level,
                        "to_level": "MANUAL",
                        "failures": self._consecutive_failures,
                    },
                    risk_level="critical",
                )

        # Notify
        await self._send_telegram_alert(
            f"БЕЗОПАСНОСТЬ: {self._consecutive_failures} неудачных попыток верификации лица.\n"
            f"Автономность понижена до MANUAL.\n"
            f"Система заблокирована на {self._lockout_duration // 60} минут.\n"
            "Отправьте /unlock для ручной разблокировки."
        )

    async def _send_telegram_alert(self, message: str) -> None:
        """Send an alert via Telegram."""
        if not self._owner_id:
            logger.warning("no_telegram_id_for_alert")
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{self._notify_url}/api/telegram/notify",
                    json={
                        "chat_id": self._owner_id,
                        "message": message,
                        "priority": "critical",
                    },
                )
        except Exception as e:
            logger.error("telegram_alert_failed", error=str(e))

    def get_status(self) -> dict[str, Any]:
        """Get current vision-autonomy bridge status."""
        return {
            "identity_confirmed": self.identity_confirmed,
            "is_locked": self.is_locked,
            "consecutive_failures": self._consecutive_failures,
            "last_verified_at": self._last_verified_at,
            "locked_until": self._locked_until,
        }
