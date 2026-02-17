"""
KORGAN AI — Telegram Command Handlers
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from telegram.config import CORE_API_URL

router = Router(name="commands")
log = structlog.get_logger("korgan.telegram.commands")

AUTONOMY_LEVELS = {
    0: "Ручной — все действия требуют подтверждения",
    1: "Предложения — система предлагает и ждёт одобрения",
    2: "Условный — разрешённые действия выполняются автоматически",
    3: "Полный — максимум автономии при высокой уверенности",
}


async def _get(path: str) -> dict[str, Any] | None:
    """GET request to Core API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{CORE_API_URL}{path}")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.warning("api_error", path=path, error=str(e))
        return None


async def _post(path: str, json_data: dict | None = None) -> dict[str, Any] | None:
    """POST request to Core API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{CORE_API_URL}{path}", json=json_data or {})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.warning("api_error", path=path, error=str(e))
        return None


# --- /start ---
@router.message(Command("start"))
async def cmd_start(message: Message):
    """Welcome message for Мистер Корган."""
    await message.answer(
        "Мистер Корган, добро пожаловать.\n\n"
        "Я — KORGAN AI, ваш персональный операционный помощник. "
        "Доступные команды:\n"
        "/status — статус системы\n"
        "/mode — уровень автономии\n"
        "/agents — список агентов\n"
        "/memory — статистика памяти\n"
        "/brief — дневная сводка\n"
        "/strategy — стратегический режим\n"
        "/stop — аварийная остановка\n"
        "/rollback &lt;id&gt; — откат действия\n"
        "/approve &lt;plan_id&gt; — подтверждение плана\n\n"
        "Голосовые сообщения обрабатываются автоматически.",
    )


# --- /status ---
@router.message(Command("status"))
async def cmd_status(message: Message):
    """System status from /api/system/status."""
    data = await _get("/api/system/status")
    if not data:
        await message.answer("Не удалось получить статус системы. Сервис недоступен.")
        return

    lines = [f"<b>Статус:</b> {data.get('status', '—')}"]
    if "autonomy" in data:
        a = data["autonomy"]
        lines.append(f"<b>Автономия:</b> {a.get('level', '—')} (уровень {a.get('level_num', '—')})")
    if "memory" in data:
        m = data["memory"]
        lines.append(f"<b>Память:</b> фактов {m.get('facts_count', 0)}, сессий {m.get('sessions_count', 0)}")
    if "version" in data:
        lines.append(f"<b>Версия:</b> {data['version']}")

    await message.answer("\n".join(lines))


# --- /mode --- (show/change autonomy with inline buttons)
@router.message(Command("mode"))
async def cmd_mode(message: Message):
    """Show current autonomy level and offer inline buttons to change."""
    data = await _get("/api/system/autonomy")
    if not data:
        await message.answer("Не удалось получить уровень автономии.")
        return

    level_num = data.get("level", 0)
    level_name = data.get("level_name", "MANUAL")

    kb = InlineKeyboardBuilder()
    for lev, desc in AUTONOMY_LEVELS.items():
        check = " ✓" if lev == level_num else ""
        kb.row(
            InlineKeyboardButton(
                text=f"Уровень {lev}{check}",
                callback_data=f"autonomy:{lev}",
            )
        )
    kb.adjust(2)  # 2 buttons per row

    await message.answer(
        f"Текущий уровень автономии: <b>{level_name}</b> ({level_num})\n"
        f"{AUTONOMY_LEVELS.get(level_num, '')}\n\nВыберите новый уровень:",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("autonomy:"))
async def cb_autonomy(callback: CallbackQuery):
    """Handle autonomy level change from inline button."""
    level_str = callback.data.split(":")[-1]
    try:
        level = int(level_str)
    except ValueError:
        await callback.answer("Некорректный уровень.", show_alert=True)
        return

    data = await _post("/api/system/autonomy", {"level": level})
    if not data:
        await callback.answer("Не удалось изменить уровень.", show_alert=True)
        return

    await callback.answer(f"Установлен уровень {level}")
    await callback.message.edit_text(
        f"Уровень автономии изменён: {data.get('from', '—')} → {data.get('to', '—')}.\n"
        f"Мистер Корган, изменения применены."
    )


# --- /agents ---
@router.message(Command("agents"))
async def cmd_agents(message: Message):
    """List agents and their status."""
    data = await _get("/api/agents/")
    if not data:
        await message.answer("Не удалось получить список агентов.")
        return

    agents = data.get("agents", [])
    if not agents:
        await message.answer("Агенты не загружены.")
        return

    lines = ["<b>Доступные агенты:</b>\n"]
    for a in agents:
        lines.append(f"• {a.get('name', '—')} — {a.get('description', '—')}")
    await message.answer("\n".join(lines))


# --- /memory ---
@router.message(Command("memory"))
async def cmd_memory(message: Message):
    """Memory statistics."""
    data = await _get("/api/memory/stats")
    if not data:
        await message.answer("Не удалось получить статистику памяти.")
        return

    lines = [
        f"<b>Фактов:</b> {data.get('facts_count', 0)}",
        f"<b>Сессий:</b> {data.get('sessions_count', 0)}",
        f"<b>Последнее обновление:</b> {str(data.get('last_updated', '—'))[:30]}",
    ]
    await message.answer("\n".join(lines))


# --- /brief ---
@router.message(Command("brief"))
async def cmd_brief(message: Message):
    """Request daily intelligence brief via Brain chat."""
    await message.answer("Подготавливаю дневную сводку...")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{CORE_API_URL}/api/brain/chat",
                json={
                    "content": "Сформируй дневную разведывательную сводку: статус системы, ключевые события, рекомендации.",
                    "interface": "telegram",
                    "context": {"command": "brief"},
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("brief_error", error=str(e))
        await message.answer(f"Ошибка при формировании сводки: {e}")
        return

    content = data.get("content", "Сводка недоступна.")
    if len(content) > 4000:
        content = content[:3997] + "..."
    await message.answer(content)


# --- /strategy ---
@router.message(Command("strategy"))
async def cmd_strategy(message: Message):
    """Activate strategic mode via Brain chat."""
    await message.answer("Активирую стратегический режим...")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{CORE_API_URL}/api/brain/chat",
                json={
                    "content": "Активируй стратегический режим. Проведи стратегический анализ текущей ситуации и приоритетов.",
                    "interface": "telegram",
                    "context": {"command": "strategy"},
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("strategy_error", error=str(e))
        await message.answer(f"Ошибка: {e}")
        return

    content = data.get("content", "Стратегический режим активирован.")
    if len(content) > 4000:
        content = content[:3997] + "..."
    await message.answer(content)


# --- /stop --- (emergency stop — enter crisis mode)
@router.message(Command("stop"))
async def cmd_stop(message: Message):
    """Emergency stop — enter crisis mode."""
    data = await _post("/api/system/crisis/enter")
    if not data:
        await message.answer("Не удалось активировать режим кризиса.")
        return

    await message.answer(
        "⚠️ <b>Режим кризиса активирован.</b>\n"
        "Мистер Корган, все автономные действия приостановлены."
    )


# --- /approve <plan_id> --- (shows approval keyboard for testing)
@router.message(Command("approve"))
async def cmd_approve(message: Message):
    """Show approve/reject keyboard for a plan (for testing approval flow)."""
    from telegram.handlers.confirmations import build_approval_keyboard

    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /approve &lt;plan_id&gt;")
        return

    plan_id = parts[1].strip()
    await message.answer(
        f"Требуется подтверждение для плана <b>{plan_id}</b>:",
        reply_markup=build_approval_keyboard(plan_id),
    )


# --- /rollback <id> ---
@router.message(Command("rollback"))
async def cmd_rollback(message: Message):
    """Rollback an action by ID."""
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /rollback &lt;action_id&gt;")
        return

    action_id = parts[1].strip()
    data = await _post(f"/api/system/rollback/{action_id}")
    if not data:
        await message.answer(f"Не удалось выполнить откат для {action_id}.")
        return

    await message.answer(f"Откат запрошен для действия {action_id}. Мистер Корган, статус: {data.get('status', '—')}.")
