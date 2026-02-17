"""
KORGAN AI — Batch Notification System
Collects notifications and sends them in batches to reduce interruptions.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger("korgan.integrations.batch_notifier")


class Notification:
    """A single notification."""

    def __init__(
        self,
        message: str,
        priority: str = "medium",  # immediate, high, medium, low
        source: str = "system",
        action_id: str | None = None,
    ):
        self.message = message
        self.priority = priority
        self.source = source
        self.action_id = action_id
        self.timestamp = datetime.now(timezone.utc)

    def to_text(self) -> str:
        time_str = self.timestamp.strftime("%H:%M")
        return f"[{time_str}] {self.message}"


class BatchNotifier:
    """
    Intelligent notification batching system.
    
    Priority levels:
    - immediate: Send right now (security alerts, crisis events)
    - high: Send within 1 minute
    - medium: Batch every 5 minutes
    - low: Batch every 15 minutes
    
    Autonomy level affects batching:
    - Level 0-1: All notifications are immediate
    - Level 2: Batch medium/low
    - Level 3: Batch everything except immediate
    """

    def __init__(
        self,
        telegram_bot_token: str = "",
        owner_chat_id: str = "",
        core_api_url: str = "http://korgan-core:8000",
    ):
        self._token = telegram_bot_token
        self._chat_id = owner_chat_id
        self._api_url = core_api_url

        self._buffer: list[Notification] = []
        self._last_flush: dict[str, float] = {
            "high": 0, "medium": 0, "low": 0,
        }
        self._flush_intervals = {
            "high": 60,       # 1 minute
            "medium": 300,    # 5 minutes
            "low": 900,       # 15 minutes
        }
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the batch notification background task."""
        self._running = True
        self._task = asyncio.create_task(self._flush_loop())
        logger.info("batch_notifier_started")

    async def stop(self) -> None:
        """Stop and flush remaining notifications."""
        self._running = False
        if self._task:
            self._task.cancel()
        # Final flush
        await self._flush_all()
        logger.info("batch_notifier_stopped")

    async def notify(self, notification: Notification) -> None:
        """Add a notification. Immediate priority sends right away."""
        if notification.priority == "immediate":
            await self._send_telegram(notification.message)
            logger.info("immediate_notification_sent", source=notification.source)
        else:
            self._buffer.append(notification)
            logger.debug(
                "notification_buffered",
                priority=notification.priority,
                buffer_size=len(self._buffer),
            )

    async def notify_simple(
        self,
        message: str,
        priority: str = "medium",
        source: str = "system",
    ) -> None:
        """Convenience method for simple text notifications."""
        await self.notify(Notification(
            message=message,
            priority=priority,
            source=source,
        ))

    async def _flush_loop(self) -> None:
        """Background loop that flushes batches at intervals."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                now = time.time()

                for priority in ("high", "medium", "low"):
                    interval = self._flush_intervals[priority]
                    if now - self._last_flush[priority] >= interval:
                        await self._flush_priority(priority)
                        self._last_flush[priority] = now

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("flush_loop_error", error=str(e))
                await asyncio.sleep(5)

    async def _flush_priority(self, priority: str) -> None:
        """Flush notifications of a specific priority."""
        to_send = [n for n in self._buffer if n.priority == priority]
        if not to_send:
            return

        # Remove from buffer
        self._buffer = [n for n in self._buffer if n.priority != priority]

        # Format batch message
        if len(to_send) == 1:
            message = to_send[0].to_text()
        else:
            header = f"--- {len(to_send)} уведомлений ({priority}) ---\n"
            body = "\n".join(n.to_text() for n in to_send)
            message = header + body

        await self._send_telegram(message)
        logger.info("batch_flushed", priority=priority, count=len(to_send))

    async def _flush_all(self) -> None:
        """Flush all buffered notifications."""
        if not self._buffer:
            return

        message = f"--- {len(self._buffer)} уведомлений ---\n"
        message += "\n".join(n.to_text() for n in self._buffer)
        self._buffer.clear()

        await self._send_telegram(message)

    async def _send_telegram(self, text: str) -> bool:
        """Send a message via Telegram Bot API directly."""
        if not self._token or not self._chat_id:
            logger.warning("telegram_not_configured")
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{self._token}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                )
                if resp.status_code == 200:
                    return True
                else:
                    logger.warning(
                        "telegram_send_failed",
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
                    return False
        except Exception as e:
            logger.error("telegram_send_error", error=str(e))
            return False

    def get_buffer_size(self) -> int:
        """Get current buffer size."""
        return len(self._buffer)

    def get_stats(self) -> dict[str, Any]:
        """Get notifier stats."""
        return {
            "buffer_size": len(self._buffer),
            "by_priority": {
                p: sum(1 for n in self._buffer if n.priority == p)
                for p in ("high", "medium", "low")
            },
            "running": self._running,
        }
