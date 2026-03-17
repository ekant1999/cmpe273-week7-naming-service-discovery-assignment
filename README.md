# Service Discovery — Trivia Microservice Demo

A from-scratch service discovery system built with **FastAPI** and **Docker Compose**.
Two instances of a Trivia service register themselves with a custom-built registry,
and a client dynamically discovers and load-balances across them.

---

## Architecture Overview

```
╔══════════════════════════════════════════════════════════════════════════╗
║                    Docker Network: service-mesh                         ║
║                                                                         ║
║   ┌─────────────────────────────────────────────────────────────────┐  ║
║   │                   SERVICE REGISTRY  :8000                        │  ║
║   │                                                                 │  ║
║   │  Endpoints:                        Internal State:              │  ║
║   │  POST /register              ──►   {                            │  ║
║   │  POST /heartbeat/{id}              "trivia-service": {          │  ║
║   │  DELETE /deregister/{id}             "trivia-svc-1": {          │  ║
║   │  GET  /discover/{name}                 host, port,              │  ║
║   │  GET  /services  (admin)               last_seen,               │  ║
║   │  GET  /health                          status                   │  ║
║   │                                      }                          │  ║
║   │  Background: TTL sweep every 10s    }                           │  ║
║   │  dead after 15s · purge after 30s  }                            │  ║
║   └────────────────┬────────────────────────────────────────────────┘  ║
║                    │                                                    ║
║        ┌───────────┴────────────┐                                      ║
║        │  ① register on boot   │  ① register on boot                  ║
║        │  ② heartbeat / 5s     │  ② heartbeat / 5s                    ║
║        ▼                       ▼                                      ║
║   ┌─────────────────┐   ┌─────────────────┐                           ║
║   │  TRIVIA-SVC-1   │   │  TRIVIA-SVC-2   │                           ║
║   │  host: :5001    │   │  host: :5002    │   (same image,            ║
║   │  internal: 5001 │   │  internal: 5001 │    different env)         ║
║   │                 │   │                 │                           ║
║   │  GET /trivia    │   │  GET /trivia    │                           ║
║   │  GET /health    │   │  GET /health    │                           ║
║   └────────▲────────┘   └────────▲────────┘                           ║
║            │                     │                                    ║
║            └──────────┬──────────┘                                    ║
║                       │  random.choice(healthy_instances)             ║
║                 ┌─────▼──────┐                                        ║
║                 │   CLIENT   │                                        ║
║                 │            │ ──► GET /discover/trivia-service        ║
║                 │  discover  │     (re-discovers before every call)   ║
║                 │  pick one  │                                        ║
║                 │  call it   │ ──► GET /trivia  (on chosen instance)  ║
║                 │  × 10 reqs │                                        ║
║                 └────────────┘                                        ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## Service Data Flow

### Phase 1 — Registration (Service Startup)

```
  trivia-svc-1                           registry
      │                                      │
      │  POST /register                      │
      │  { service_name: "trivia-service",   │
      │    instance_id:  "trivia-svc-1",     │
      │    host:         "trivia-svc-1",     │
      │    port:         5001 }              │
      │─────────────────────────────────────►│
      │                                      │  store instance
      │                                      │  last_seen = now()
      │                                      │  status    = "healthy"
      │  201 { instance registered }         │
      │◄─────────────────────────────────────│
      │                                      │
      │  (same flow for trivia-svc-2)        │
```

### Phase 2 — Heartbeating (Continuous Liveness Signal)

```
  trivia-svc-1                           registry
      │                                      │
      │  ← every 5 seconds →                 │
      │                                      │
      │  POST /heartbeat/trivia-svc-1        │
      │─────────────────────────────────────►│
      │                                      │  last_seen = now()
      │                                      │  status    = "healthy"
      │  200 { last_seen: <timestamp> }      │
      │◄─────────────────────────────────────│
      │                                      │
      │  (if registry restarted → 404)       │
      │◄─────────────────────────────────────│
      │  → immediately calls POST /register  │
      │    (self-healing re-registration)    │
```

### Phase 3 — TTL Sweep (Failure Detection)

```
  registry (background task — every 10 seconds)
      │
      │  for each instance:
      │    elapsed = now() - last_seen
      │
      │    elapsed ≤ 15s  →  status stays "healthy"   ✓
      │    elapsed > 15s  →  status = "dead"           ✗  (no client traffic)
      │    elapsed > 30s  →  instance purged from memory
      │
      │  Worst-case failure detection = TTL + sweep = 15 + 10 = 25 seconds
```

### Phase 4 — Discovery (Client Lookup)

```
  client                              registry
      │                                  │
      │  GET /discover/trivia-service    │
      │─────────────────────────────────►│
      │                                  │  filter: status == "healthy"
      │  200 [ { trivia-svc-1, ... },    │
      │         { trivia-svc-2, ... } ]  │
      │◄─────────────────────────────────│
      │                                  │
      │  (if no healthy instances → 503, client retries 5× with 3s delay)
```

### Phase 5 — Service Call (Random Load Balancing)

```
  client                         trivia-svc-? (randomly chosen)
      │                                  │
      │  chosen = random.choice(         │
      │    healthy_instances)            │
      │                                  │
      │  GET /trivia                     │
      │─────────────────────────────────►│
      │                                  │  picks random fact
      │  200 {                           │
      │    "fact": "...",                │
      │    "instance": "trivia-svc-1",   │
      │    "port": 5001,                 │
      │    "served_at": "2026-..."       │
      │  }                               │
      │◄─────────────────────────────────│
      │                                  │
      │  (re-discovers before next req → topology changes reflected live)
```

### Phase 6 — Graceful Shutdown (Clean Deregistration)

```
  trivia-svc-1                           registry
      │                                      │
      │  receives SIGTERM                    │
      │  → cancel heartbeat task             │
      │                                      │
      │  DELETE /deregister/trivia-svc-1     │
      │─────────────────────────────────────►│
      │                                      │  remove from store immediately
      │  200 { deregistered }                │  (no need to wait for TTL)
      │◄─────────────────────────────────────│
```

---

## Heartbeat TTL — Failure & Recovery Timeline

```
t= 0s   trivia-svc-1 registers   → last_seen=0,   status=healthy
t= 5s   trivia-svc-1 heartbeat   → last_seen=5,   status=healthy
t=10s   registry sweep           → elapsed=5s  < 15s TTL  ✓ healthy
t=10s   trivia-svc-1 heartbeat   → last_seen=10,  status=healthy

── trivia-svc-1 CRASHES at t=12s ──────────────────────────────────────

t=20s   registry sweep           → elapsed=10s < 15s TTL  ✓ healthy (grace)
t=25s   trivia-svc-1 heartbeat   → (never arrives)
t=30s   registry sweep           → elapsed=20s > 15s TTL  → DEAD ✗
t=35s   client discovers         → only trivia-svc-2 returned
t=40s   registry sweep           → elapsed=30s > 30s PURGE → removed

── trivia-svc-1 RESTARTS at t=45s ─────────────────────────────────────

t=45s   trivia-svc-1 registers   → last_seen=45, status=healthy
t=46s   client discovers         → BOTH instances returned again ✓
```

Worst-case detection latency = TTL (15s) + sweep interval (10s) = **25 seconds**.

---

## Heartbeat TTL — How Failure Detection Works

```
t= 0s   trivia-svc-1 registers   → last_seen=0,   status=healthy
t= 5s   trivia-svc-1 heartbeat   → last_seen=5,   status=healthy
t=10s   registry sweep           → elapsed=5s  < 15s TTL  ✓ healthy
t=10s   trivia-svc-1 heartbeat   → last_seen=10,  status=healthy

── trivia-svc-1 CRASHES at t=12s ──────────────────────────────────────

t=20s   registry sweep           → elapsed=10s < 15s TTL  ✓ healthy (grace)
t=25s   trivia-svc-1 heartbeat   → (never arrives)
t=30s   registry sweep           → elapsed=20s > 15s TTL  → DEAD ✗
t=35s   client discovers         → only trivia-svc-2 returned
t=40s   registry sweep           → elapsed=30s > 30s PURGE → removed

── trivia-svc-1 RESTARTS at t=45s ─────────────────────────────────────

t=45s   trivia-svc-1 registers   → last_seen=45, status=healthy
t=46s   client discovers         → BOTH instances returned again ✓
```

Worst-case detection latency = TTL (15s) + sweep interval (10s) = **25 seconds**.

---

## How It Differs from Consul-based Approach

| Aspect              | Consul (reference)               | This project                          |
|---------------------|----------------------------------|---------------------------------------|
| Registry            | HashiCorp Consul (external tool) | Custom-built FastAPI app              |
| Health model        | Pull — Consul polls `/health`    | Push — services send heartbeats       |
| Framework           | Flask                            | FastAPI                               |
| Re-registration     | Not needed (Consul persists)     | Heartbeat 404 triggers re-register    |
| Client discovery    | Once, 5 requests                 | Re-discovers on every request (×10)   |

---

## Quick Start

```bash
# 1. Build images and start all 4 containers
docker compose up --build

# 2. (Different terminal) Stream client output in real time
docker compose logs -f client

# 3. Check registry state
curl http://localhost:8000/services | python3 -m json.tool

# 4. See only healthy instances
curl http://localhost:8000/discover/trivia-service | python3 -m json.tool

# 5. Tear down
docker compose down
```

---

## Demo Script (Failure & Recovery)

```bash
# --- Step 1: Confirm both instances registered ---
curl -s http://localhost:8000/services | python3 -m json.tool
# Expect: trivia-svc-1 and trivia-svc-2 both show status: "healthy"

# --- Step 2: Simulate instance failure ---
docker compose stop trivia-svc-1

# --- Step 3: Wait for TTL sweep to kick in (~25 seconds) ---
sleep 25

# --- Step 4: Verify failure detection ---
curl -s http://localhost:8000/discover/trivia-service | python3 -m json.tool
# Expect: only trivia-svc-2 returned (trivia-svc-1 is dead/purged)

# --- Step 5: Simulate recovery ---
docker compose start trivia-svc-1

# --- Step 6: Wait for re-registration ---
sleep 10

# --- Step 7: Confirm both instances healthy again ---
curl -s http://localhost:8000/discover/trivia-service | python3 -m json.tool
# Expect: both trivia-svc-1 and trivia-svc-2 returned

# --- Step 8: Call the trivia service directly (host ports) ---
curl http://localhost:5001/trivia
curl http://localhost:5002/trivia
```

---

## API Reference

### Service Registry (port 8000)

| Method   | Path                         | Description                                          |
|----------|------------------------------|------------------------------------------------------|
| `POST`   | `/register`                  | Register a service instance                          |
| `POST`   | `/heartbeat/{instance_id}`   | Send heartbeat; 404 means unknown → re-register      |
| `DELETE` | `/deregister/{instance_id}`  | Explicit deregister on graceful shutdown             |
| `GET`    | `/discover/{service_name}`   | Returns healthy instances only; 503 if none          |
| `GET`    | `/services`                  | Admin: all instances including dead ones             |
| `GET`    | `/health`                    | Docker healthcheck                                   |

### Trivia Service (port 5001 / 5002 on host)

| Method | Path      | Description                                         |
|--------|-----------|-----------------------------------------------------|
| `GET`  | `/trivia` | Random trivia fact + instance name + timestamp      |
| `GET`  | `/health` | Health check                                        |

---

## Design Decisions

**1. Custom registry vs Consul**
Building the registry from scratch reveals the core mechanism: a store of
`{service_name → {instance_id → {host, port, last_seen, status}}}` with a
background TTL sweep. Consul abstracts this away; here it is explicit.

**2. Push-based heartbeat vs pull-based health polling**
The registry does not actively poll services. Instead, each service sends
a heartbeat every 5 seconds. Silence beyond 15 seconds triggers the dead
transition. This avoids the registry needing to know service topology in advance.

**3. Re-discovery on every client request**
The client re-queries `/discover/trivia-service` before each of the 10 calls.
This means if an instance fails mid-demo, subsequent requests immediately stop
routing to it — no stale routing table.

**4. Heartbeat 404 triggers re-registration**
If the registry restarts (losing its in-memory state), the next heartbeat
from each service returns 404. The service reacts by calling `/register`
again. This makes the system self-healing without operator intervention.

**5. In-memory state**
Acceptable for a demo. Production alternatives: Redis (persistence +
pub/sub), etcd (distributed consensus), or a proper service mesh like Consul,
Linkerd, or Istio.
