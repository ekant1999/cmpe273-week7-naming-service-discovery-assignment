import asyncio
import time
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
services: Dict[str, Dict[str, dict]] = {}

TTL_SECONDS = 15.0      # instance marked dead if no heartbeat for 15s
PURGE_SECONDS = 30.0    # instance removed from memory after 30s (2x TTL)
SWEEP_INTERVAL = 10.0   # sweep runs every 10s


# ---------------------------------------------------------------------------
# Background TTL sweep
# ---------------------------------------------------------------------------
async def sweep_loop() -> None:
    """Periodically mark and purge instances that have stopped sending heartbeats."""
    while True:
        await asyncio.sleep(SWEEP_INTERVAL)
        now = time.time()
        for service_name in list(services.keys()):
            bucket = services[service_name]
            for instance_id, inst in list(bucket.items()):
                elapsed = now - inst["last_seen"]
                if elapsed > PURGE_SECONDS:
                    del bucket[instance_id]
                    print(f"[registry] PURGED  {instance_id} ({service_name}) — silent for {elapsed:.1f}s")
                elif elapsed > TTL_SECONDS and inst["status"] == "healthy":
                    inst["status"] = "dead"
                    print(f"[registry] DEAD    {instance_id} ({service_name}) — silent for {elapsed:.1f}s")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(sweep_loop())
    print("[registry] Started — TTL sweep active")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    print("[registry] Shut down")


app = FastAPI(title="Service Registry", version="1.0.0", lifespan=lifespan)
