"""
KORGAN AI — Main Telegram Bot Entry Point
Uses aiogram 3.x, connects to Core API via httpx and WebSocket.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, Awaitable

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import structlog
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update

from telegram.handlers import commands, voice, confirmations

logger = structlog.get_logger("korgan.telegram")

# Environment
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OWNER_TELEGRAM_ID = int(os.environ.get("OWNER_TELEGRAM_ID", "0") or "0")
CORE_API_URL = os.environ.get("CORE_API_URL", "http://korgan-core:8000")
CORE_WS_URL = os.environ.get("CORE_WS_URL", "ws://korgan-core:8000/ws")


def is_owner(user_id: int) -> bool:
    """Check if user is the owner (Мистер Корган)."""
    return bool(OWNER_TELEGRAM_ID and user_id == OWNER_TELEGRAM_ID)


async def owner_middleware(
    handler: Callable[[Update, dict], Awaitable[Any]],
    event: Update,
    data: dict[str, Any],
) -> Any:
    """Reject updates from non-owner users."""
    user_id = 0
    if event.message and event.message.from_user:
        user_id = event.message.from_user.id
    elif event.callback_query and event.callback_query.from_user:
        user_id = event.callback_query.from_user.id

    if user_id and not is_owner(user_id):
        logger.warning("access_denied", user_id=user_id, expected=OWNER_TELEGRAM_ID)
        if event.message:
            await event.message.answer(
                "Извините, доступ ограничен. Система предназначена исключительно для Мистера Коргана."
            )
        elif event.callback_query:
            await event.callback_query.answer(
                "Доступ ограничен.",
                show_alert=True,
            )
        return
    return await handler(event, data)


def create_bot() -> tuple[Bot, Dispatcher]:
    """Create and configure bot with aiogram 3.x."""
    bot = Bot(
        token=TELEGRAM_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Owner-only middleware (outer — runs before filters)
    dp.update.outer_middleware(owner_middleware)

    # Routers
    dp.include_router(commands.router)
    dp.include_router(voice.router)
    dp.include_router(confirmations.router)

    return bot, dp


async def websocket_listener():
    """Connect to Core WebSocket for real-time events (runs in background)."""
    try:
        import websockets
        ws_url = CORE_WS_URL.replace("http://", "ws://").replace("https://", "wss://")
        async with websockets.connect(ws_url) as ws:
            logger.info("ws_connected", url=ws_url)
            while True:
                msg = await ws.recv()
                logger.debug("ws_message", data=str(msg)[:200])
    except ImportError:
        logger.warning("websockets_not_installed", msg="WebSocket listener disabled")
    except Exception as e:
        logger.warning("ws_disconnected", error=str(e))


async def main():
    """Start the bot with polling."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return
    if not OWNER_TELEGRAM_ID:
        logger.warning("OWNER_TELEGRAM_ID not set — owner filter disabled")

    global TELEGRAM_TOKEN
    TELEGRAM_TOKEN = token

    bot, dp = create_bot()
    logger.info("korgan_telegram_starting", core_url=CORE_API_URL)

    # Optional: run WebSocket listener in background
    ws_task = asyncio.create_task(websocket_listener())
    ws_task.add_done_callback(lambda t: None)  # ignore exceptions in bg

    try:
        await dp.start_polling(bot)
    finally:
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
