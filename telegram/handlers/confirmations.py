"""
KORGAN AI — Approval Flow Handlers
Inline keyboard approve/reject, callback handlers, API integration.
"""

from __future__ import annotations

import httpx
import structlog
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from telegram.config import CORE_API_URL

router = Router(name="confirmations")
log = structlog.get_logger("korgan.telegram.confirmations")


def build_approval_keyboard(plan_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with Approve / Reject for a plan."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✓ Одобрить", callback_data=f"approve:{plan_id}"),
        InlineKeyboardButton(text="✗ Отклонить", callback_data=f"reject:{plan_id}"),
    )
    return builder.as_markup()


async def _post(path: str) -> dict | None:
    """POST to Core API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{CORE_API_URL}{path}")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.warning("api_error", path=path, error=str(e))
        return None


@router.callback_query(F.data.startswith("approve:"))
async def cb_approve(callback: CallbackQuery):
    """Approve plan — POST /api/brain/approve/{plan_id}."""
    plan_id = callback.data.split(":", 1)[-1]
    data = await _post(f"/api/brain/approve/{plan_id}")
    if not data:
        await callback.answer("Ошибка одобрения.", show_alert=True)
        return

    await callback.answer("Одобрено.", show_alert=False)
    await callback.message.edit_text(
        f"✓ План <b>{plan_id}</b> одобрен, Мистер Корган."
    )


@router.callback_query(F.data.startswith("reject:"))
async def cb_reject(callback: CallbackQuery):
    """Reject plan — POST /api/brain/reject/{plan_id}."""
    plan_id = callback.data.split(":", 1)[-1]
    data = await _post(f"/api/brain/reject/{plan_id}")
    if not data:
        await callback.answer("Ошибка отклонения.", show_alert=True)
        return

    await callback.answer("Отклонено.", show_alert=False)
    await callback.message.edit_text(
        f"✗ План <b>{plan_id}</b> отклонён, Мистер Корган."
    )
