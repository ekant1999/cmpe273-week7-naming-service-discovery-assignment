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


async def main() -> None:
    banner = "  Service Discovery Demo — Trivia Client  "
    print("=" * len(banner))
    print(banner)
    print("=" * len(banner))

    # -----------------------------------------------------------------------
    # Phase 1: Initial discovery
    # -----------------------------------------------------------------------
    print(f"\n[client] Discovering '{SERVICE_NAME}' instances from registry...")
    instances = await discover_instances()

    if not instances:
        print("[client] No healthy instances found after all retries. Exiting.")
        return

    print(f"[client] Found {len(instances)} healthy instance(s):")
    for inst in instances:
        print(f"         - {inst['instance_id']}  @  {inst['host']}:{inst['port']}")

    # -----------------------------------------------------------------------
    # Phase 2: Make TOTAL_REQUESTS calls, re-discovering each time so topology
    #          changes (instance up/down) are reflected immediately.
    # -----------------------------------------------------------------------
    print(f"\n[client] Sending {TOTAL_REQUESTS} requests (1 per second)...\n")
    call_counts: dict[str, int] = {}

    for i in range(1, TOTAL_REQUESTS + 1):
        # Re-discover on every request — the whole point of dynamic service discovery
        fresh = await discover_instances()
        if not fresh:
            print(f"[client] Request {i:2d}: no healthy instances, skipping.")
            await asyncio.sleep(REQUEST_INTERVAL)
            continue

        chosen = random.choice(fresh)
        result = await call_trivia(chosen)

        if result:
            name = result.get("instance", chosen["instance_id"])
            call_counts[name] = call_counts.get(name, 0) + 1
            fact_preview = result["fact"][:65] + ("..." if len(result["fact"]) > 65 else "")
            print(f"[client] Request {i:2d}  ->  [{name}]  {fact_preview}")
        else:
            print(f"[client] Request {i:2d}  ->  [{chosen['instance_id']}]  FAILED")

        await asyncio.sleep(REQUEST_INTERVAL)

    # -----------------------------------------------------------------------
    # Phase 3: Load distribution summary
    # -----------------------------------------------------------------------
    print()
    print("=" * 50)
    print("  Load Distribution Summary")
    print("=" * 50)
    total_calls = sum(call_counts.values())
    for name, count in sorted(call_counts.items()):
        bar = "#" * count
        pct = count / total_calls * 100 if total_calls else 0
        print(f"  {name:20s}  {bar:<12s}  {count} calls ({pct:.0f}%)")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
