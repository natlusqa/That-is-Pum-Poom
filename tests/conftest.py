"""
KORGAN AI — Pytest Configuration and Shared Fixtures
Ensures project root is in sys.path and provides common test setup.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path for imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
