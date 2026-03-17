# Service Discovery — Trivia Microservice Demo

A from-scratch service discovery system built with **FastAPI** and **Docker Compose**.
Two instances of a Trivia service register themselves with a custom-built registry,
and a client dynamically discovers and load-balances across them.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Docker Network: service-mesh                    │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                  SERVICE REGISTRY  (:8000)                   │  │
│   │                                                             │  │
│   │   POST /register          GET  /discover/{service_name}     │  │
│   │   POST /heartbeat/{id}    DELETE /deregister/{id}           │  │
│   │   GET  /services          GET  /health                      │  │
│   │                                                             │  │
│   │   in-memory store: { service_name: { id: instance } }      │  │
│   │   background sweep every 10s — TTL = 15s, purge = 30s      │  │
│   └──────────────────┬──────────────────────────────────────────┘  │
│                      │                                              │
│           ┌──────────┴──────────┐                                  │
│           │ register + heartbeat│ register + heartbeat              │
│           │ (every 5 seconds)   │ (every 5 seconds)                 │
│           ▼                     ▼                                  │
│   ┌───────────────┐   ┌───────────────┐                           │
│   │ TRIVIA-SVC-1  │   │ TRIVIA-SVC-2  │                           │
│   │  (:5001)      │   │  (:5001)      │                           │
│   │               │   │               │                           │
│   │ GET /trivia   │   │ GET /trivia   │                           │
│   │ GET /health   │   │ GET /health   │                           │
│   └───────▲───────┘   └───────▲───────┘                           │
│           │                   │                                    │
│           └─────────┬─────────┘                                    │
│                     │  random.choice(healthy_instances)            │
│               ┌─────▼──────┐                                       │
│               │   CLIENT   │                                       │
│               │            │                                       │
│               │ 1. discover│ ──► GET /discover/trivia-service      │
│               │ 2. pick 1  │     (re-discover on every request)    │
│               │ 3. call it │                                       │
│               │  × 10 req  │                                       │
│               └────────────┘                                       │
└─────────────────────────────────────────────────────────────────────┘
```

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

