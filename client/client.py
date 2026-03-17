import asyncio
import os
import random

import httpx

REGISTRY_URL          = os.getenv("REGISTRY_URL", "http://localhost:8000")
SERVICE_NAME          = "trivia-service"
TOTAL_REQUESTS        = 10
REQUEST_INTERVAL      = 1.0   # seconds between requests
MAX_DISCOVERY_RETRIES = 5
DISCOVERY_RETRY_DELAY = 3.0   # seconds between discovery retries


async def discover_instances() -> list:
    """Query the registry for healthy trivia-service instances, retrying if none found."""
    for attempt in range(MAX_DISCOVERY_RETRIES):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{REGISTRY_URL}/discover/{SERVICE_NAME}", timeout=5.0
                )
                if resp.status_code == 200:
                    instances = resp.json()
                    if instances:
                        return instances
                    print(f"[client] No healthy instances yet (attempt {attempt + 1}/{MAX_DISCOVERY_RETRIES})")
                else:
                    print(f"[client] Discovery returned {resp.status_code} (attempt {attempt + 1}/{MAX_DISCOVERY_RETRIES})")
        except Exception as exc:
            print(f"[client] Discovery error: {exc} (attempt {attempt + 1}/{MAX_DISCOVERY_RETRIES})")
        await asyncio.sleep(DISCOVERY_RETRY_DELAY)
    return []


async def call_trivia(instance: dict) -> dict | None:
    """Call /trivia on a specific service instance."""
    url = f"http://{instance['host']}:{instance['port']}/trivia"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5.0)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        print(f"[client] Failed to call {url}: {exc}")
        return None
