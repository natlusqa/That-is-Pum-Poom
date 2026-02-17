"""Allow running as python -m telegram."""

import asyncio

from telegram.bot import main

if __name__ == "__main__":
    asyncio.run(main())
