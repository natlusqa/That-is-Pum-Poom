"""
KORGAN AI — Audit Logger
Complete action logging for transparency and rollback.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import structlog

logger = structlog.get_logger("korgan.security.audit")


class AuditLogger:
    """
    Comprehensive audit logging system.
    
    Every action KORGAN performs is logged with:
    - Who initiated (user, auto, conditional)
    - What was done (action, agent, parameters)
    - Risk level
    - Rollback data (for reversible actions)
    - Timestamp and duration
    
    Logs are stored in PostgreSQL via MemoryManager.
    """

    def __init__(self, memory_manager: Any = None):
        self._memory = memory_manager
        self._buffer: list[dict[str, Any]] = []

    async def log(
        self,
        action: str,
        agent: str | None = None,
        details: dict[str, Any] | None = None,
        risk_level: str = "low",
        autonomy_level: str | None = None,
        approved_by: str | None = None,
        rollback_data: dict[str, Any] | None = None,
    ) -> str | None:
        """Log an action to the audit trail."""
        entry = {
            "action": action,
            "agent": agent,
            "details": details or {},
            "risk_level": risk_level,
            "autonomy_level": autonomy_level,
            "approved_by": approved_by,
            "rollback_data": rollback_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "audit_entry",
            action=action,
            agent=agent,
            risk=risk_level,
            approved_by=approved_by,
        )

        if self._memory:
            try:
                return await self._memory.log_audit(**{
                    k: v for k, v in entry.items() if k != "timestamp"
                })
            except Exception as e:
                logger.error("audit_store_failed", error=str(e))
                self._buffer.append(entry)
                return None
        else:
            self._buffer.append(entry)
            return None

    async def flush_buffer(self) -> int:
        """Flush buffered entries to storage."""
        if not self._memory or not self._buffer:
            return 0

        flushed = 0
        remaining = []

        for entry in self._buffer:
            try:
                await self._memory.log_audit(**{
                    k: v for k, v in entry.items() if k != "timestamp"
                })
                flushed += 1
            except Exception:
                remaining.append(entry)

        self._buffer = remaining
        return flushed

    async def get_recent(
        self,
        limit: int = 50,
        agent: str | None = None,
        risk_level: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent audit entries (from memory or buffer)."""
        # In full implementation, query PostgreSQL
        return self._buffer[-limit:]

    def get_buffer_size(self) -> int:
        """Get number of buffered entries."""
        return len(self._buffer)
