"""
KORGAN AI — Voice Message Handler
Receives voice, sends to STT, then to Core Brain, returns text (optionally TTS).
"""

from __future__ import annotations

import io
from typing import Any

import httpx
import structlog
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile

from telegram.config import CORE_API_URL, VOICE_SERVICE_URL

router = Router(name="voice")
log = structlog.get_logger("korgan.telegram.voice")


@router.message(F.voice)
async def handle_voice(message: Message):
    """Process voice message: STT → Brain chat → reply (text, optional TTS)."""
    voice = message.voice
    if not voice:
        return

    await message.answer("Обрабатываю голосовое сообщение...")

    # 1. Download voice file
    bot = message.bot
    file = await bot.get_file(voice.file_id)
    voice_bytes = await bot.download_file(file.file_path)
    if not voice_bytes:
        await message.answer("Не удалось загрузить голосовое сообщение.")
        return

    audio_data = voice_bytes.read()

    # 2. STT — Voice Service
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"audio": ("voice.ogg", audio_data, "audio/ogg")}
            r = await client.post(f"{VOICE_SERVICE_URL}/stt", files=files)
            r.raise_for_status()
            stt_data = r.json()
    except Exception as e:
        log.warning("stt_error", error=str(e))
        await message.answer(f"Ошибка распознавания речи: {e}")
        return

    text = stt_data.get("text", "").strip()
    if not text:
        await message.answer("Текст не распознан. Попробуйте ещё раз.")
        return

    await message.answer(f"<i>Распознано:</i> {text[:200]}{'…' if len(text) > 200 else ''}")

    # 3. Brain chat
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{CORE_API_URL}/api/brain/chat",
                json={
                    "content": text,
                    "interface": "telegram",
                    "context": {"voice": True},
                },
            )
            r.raise_for_status()
            brain_data = r.json()
    except Exception as e:
        log.warning("brain_chat_error", error=str(e))
        await message.answer(f"Ошибка обработки запроса: {e}")
        return

    response_text = brain_data.get("content", "")
    if len(response_text) > 4000:
        response_text = response_text[:3997] + "..."

    await message.answer(response_text)

    # 4. Optional: TTS response
    # User said "optionally as voice via /tts" — we could add a button or auto-send voice
    # For now, we only send text. TTS can be triggered by reply "озвучь" or similar.
    # Minimal implementation: skip TTS to avoid latency; user can request via /tts command if needed.
