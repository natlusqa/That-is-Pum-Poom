"""
KORGAN AI — Shared Application State
Separated from main.py to avoid circular imports.
"""

from typing import Any

_state: dict[str, Any] = {}


def get_state() -> dict[str, Any]:
    """Get application state."""
    return _state


def set_state(key: str, value: Any) -> None:
    """Set a state value."""
    _state[key] = value
