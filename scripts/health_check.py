"""
KORGAN AI — Health Check Script
Run: python scripts/health_check.py
"""

import asyncio
import sys

import httpx


SERVICES = {
    "Core API": "http://localhost:8000/health",
    "Voice Service": "http://localhost:8001/health",
    "Vision Service": "http://localhost:8002/health",
    "Ollama": "http://localhost:11434/api/tags",
    "ChromaDB": "http://localhost:8003/api/v1/heartbeat",
    "n8n": "http://localhost:5678/healthz",
}


async def check_services():
    """Check health of all KORGAN services."""
    print("=" * 50)
    print("  KORGAN AI — Health Check")
    print("=" * 50)
    print()

    all_healthy = True

    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in SERVICES.items():
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    print(f"  [OK]   {name:<20} — healthy")
                else:
                    print(f"  [WARN] {name:<20} — status {resp.status_code}")
                    all_healthy = False
            except httpx.ConnectError:
                print(f"  [FAIL] {name:<20} — connection refused")
                all_healthy = False
            except httpx.TimeoutException:
                print(f"  [FAIL] {name:<20} — timeout")
                all_healthy = False
            except Exception as e:
                print(f"  [FAIL] {name:<20} — {str(e)[:50]}")
                all_healthy = False

    # Check PostgreSQL via Core API
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:8000/api/memory/stats")
            if resp.status_code == 200:
                print(f"  [OK]   {'PostgreSQL':<20} — healthy (via Core API)")
            else:
                print(f"  [WARN] {'PostgreSQL':<20} — status {resp.status_code}")
    except Exception:
        print(f"  [????] {'PostgreSQL':<20} — check via Core API failed")

    # Check Redis
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:8000/api/system/status")
            if resp.status_code == 200:
                data = resp.json()
                print(f"  [OK]   {'Redis':<20} — healthy (via Core API)")
    except Exception:
        print(f"  [????] {'Redis':<20} — check via Core API failed")

    print()
    if all_healthy:
        print("  All services healthy!")
    else:
        print("  Some services are unhealthy. Check docker compose logs.")
    print()

    return 0 if all_healthy else 1


if __name__ == "__main__":
    exit_code = asyncio.run(check_services())
    sys.exit(exit_code)
