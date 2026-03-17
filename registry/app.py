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


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    service_name: str
    host: str
    port: int
    instance_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/register", status_code=201)
def register(req: RegisterRequest):
    """Register a service instance. Idempotent — re-registering overwrites stale data."""
    if req.service_name not in services:
        services[req.service_name] = {}
    now = time.time()
    services[req.service_name][req.instance_id] = {
        "instance_id": req.instance_id,
        "service_name": req.service_name,
        "host": req.host,
        "port": req.port,
        "registered_at": now,
        "last_seen": now,
        "status": "healthy",
    }
    print(f"[registry] REGISTERED  {req.instance_id} ({req.service_name}) @ {req.host}:{req.port}")
    return services[req.service_name][req.instance_id]


@app.post("/heartbeat/{instance_id}")
def heartbeat(instance_id: str):
    """Update last_seen for an instance. Returns 404 if unknown (service should re-register)."""
    for bucket in services.values():
        if instance_id in bucket:
            bucket[instance_id]["last_seen"] = time.time()
            bucket[instance_id]["status"] = "healthy"
            return {"instance_id": instance_id, "last_seen": bucket[instance_id]["last_seen"]}
    raise HTTPException(status_code=404, detail=f"Unknown instance: {instance_id}")


@app.delete("/deregister/{instance_id}")
def deregister(instance_id: str):
    """Explicitly remove an instance (called on graceful shutdown)."""
    for service_name, bucket in services.items():
        if instance_id in bucket:
            del bucket[instance_id]
            print(f"[registry] DEREGISTERED  {instance_id} ({service_name})")
            return {"message": f"Deregistered {instance_id}"}
    raise HTTPException(status_code=404, detail=f"Unknown instance: {instance_id}")


@app.get("/discover/{service_name}")
def discover(service_name: str):
    """Return only healthy instances of a service. 503 if none available."""
    if service_name not in services:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service_name}")
    healthy = [
        inst for inst in services[service_name].values()
        if inst["status"] == "healthy"
    ]
    if not healthy:
        raise HTTPException(status_code=503, detail=f"No healthy instances of '{service_name}'")
    return healthy


@app.get("/services")
def list_services():
    """Admin endpoint — returns all instances including dead ones."""
    return services


@app.get("/health")
def health():
    """Docker healthcheck endpoint."""
    total = sum(len(b) for b in services.values())
    return {"status": "ok", "registered_instances": total}
