"""
KORGAN AI — Autonomy Decision Logic
"""

from __future__ import annotations

from pydantic import BaseModel


class AutonomyDecision(BaseModel):
    """Result of an autonomy decision check."""
    can_execute: bool = False
    needs_approval: bool = True
    auto_approved: bool = False
    reason: str = ""
    notification_required: bool = True
    notification_priority: str = "immediate"  # immediate, batch
