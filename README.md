# AtomField

> **A production-grade distributed job scheduler for materials science simulations.**  
> Built as a "Hiring-Manager Magnet" — demonstrating senior-level distributed systems design.

---

## Architecture

```
Browser / Client
     │
     ▼
[ FastAPI :8000 ]  ──POST /jobs/submit──▶  [ PostgreSQL :5432 ]  (durable state)
     │                                      [ Redis :6379 ]        (task queue)
     │
[ ARQ Worker ]  ◀──dequeues from Redis──────────┘
     │
     ▼  (Phase 3: Docker container per job)
[ PostgreSQL ]  (status: Pending → Running → Success | Failed)
```

## Tech Stack

| Concern | Technology |
|---|---|
| Package Management | `uv` (Rust-based, deterministic lockfiles) |
| API Framework | `FastAPI` + `uvicorn` |
| Database | `PostgreSQL 15` + `SQLAlchemy 2.0 (async)` + `asyncpg` |
| Message Broker | `Redis 7` |
| Worker Engine | `ARQ` (Async Redis Queue) |
| Sandbox (Phase 3) | Docker SDK for Python |
| CI/CD (Phase 4) | GitHub Actions + GHCR |
| Cloud (Phase 4) | Oracle Cloud Free Tier (ARM A1) |

## Project Structure

```
atomfield/
├── app/
│   ├── __init__.py
│   ├── database.py   # SQLAlchemy async engine + session factory
│   ├── models.py     # Job ORM model (UUID PK, JSONB XCom fields)
│   ├── main.py       # FastAPI app (Phase 1+2: submit, poll, health)
│   └── worker.py     # ARQ worker (Phase 2+3: execute_script task)
├── scripts/
│   └── sample_script.py  # Sample simulation (band structure mock)
├── .env
└── pyproject.toml
```

## Running Locally (Mac)

**Terminal 1 — Infrastructure:**
```bash
docker run --name local-postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=atomfield_db -p 5432:5432 -d postgres:15-alpine
docker run --name local-redis -p 6379:6379 -d redis:7-alpine
```

**Terminal 2 — API Server:**
```bash
uv run uvicorn app.main:app --reload
```

**Terminal 3 — Worker:**
```bash
uv run arq app.worker.WorkerSettings
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `POST` | `/jobs/submit` | Submit a simulation job (202 Accepted) |
| `GET` | `/jobs/{job_id}` | Poll job status + output |

Interactive docs: http://localhost:8000/docs

## Phase Roadmap

- [x] **Phase 1** — Core API & State Management (FastAPI + PostgreSQL)
- [x] **Phase 2** — Decoupled Queue (Redis + ARQ Worker)
- [ ] **Phase 3** — Docker Sandbox (isolated container execution)
- [ ] **Phase 4** — CI/CD + Oracle Cloud deployment (zero-rupee infra)
- [ ] **Phase 5** — DAG Visual Builder (React Flow frontend)
