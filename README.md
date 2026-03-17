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
