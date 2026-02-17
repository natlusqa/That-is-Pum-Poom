"""KORGAN AI Telegram — Configuration from environment."""

from __future__ import annotations

import os

CORE_API_URL = os.environ.get("CORE_API_URL", "http://korgan-core:8000")
VOICE_SERVICE_URL = os.environ.get("VOICE_SERVICE_URL", "http://korgan-voice:8001")
