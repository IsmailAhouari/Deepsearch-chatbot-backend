# DeepSearch Backend

FastAPI + PostgreSQL backend for the DeepSearch Conversational Qualification System.

## Architecture Overview

**Two-tier Visitor/Lead model:**
- `Session` — created at lead capture; holds anonymous behavioural metadata (no PII)
- `Lead` — promoted from Session at form submission; holds PII + qualification snapshot

**Canonical qualification fields:** `target`, `obiettivo`, `geografia`, `role`

**Event log:** Every user action produces a `FunnelEvent` (append-only, immutable).
Analytics can be derived entirely from the event log via SQL.

**CRM integration:** Pluggable adapter pattern (`CRM_ADAPTER_CLASS` env var).
Default: `NullAdapter` (logs and acknowledges without transmitting data).

**Constitution:** 15 architectural principles govern all design decisions.
See [`.specify/memory/constitution.md`](.specify/memory/constitution.md).
Two documented exceptions: batched events (v1) and GDPR consent (v1.1).

---

## Quick Local Setup

### Prerequisites
- Docker & Docker Compose
- Python 3.12+

### Steps

```bash
# 1. Copy environment file
cp .env.example .env
# Edit .env: set JWT_SECRET_KEY and ADMIN_PASSWORD_HASH

# 2. Start PostgreSQL
docker-compose up -d db

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Run database migrations
alembic upgrade head

# 5. Start the API
uvicorn src.main:app --reload

# 6. Verify
curl http://localhost:8000/health
# {"status":"ok","environment":"development","database":"ok","version":"1.0.0"}
```

### Using Docker Compose (full stack)

```bash
docker-compose up --build
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | asyncpg connection string |
| `ADMIN_API_KEY` | ✅ | — | Static API key for admin routes (`X-Admin-Key` header) |
| `CRM_ADAPTER_CLASS` | — | `NullAdapter` | Dotted import path of CRM adapter |
| `CRM_API_KEY` | — | — | API key for the CRM provider |
| `BOOKING_EVENT_URL` | prod | — | Cal.com event type URL for Booking Links (e.g. `https://cal.com/yourname/demo`) |
| `RESEND_API_KEY` | prod | — | Resend API key for transactional emails |
| `EMAIL_FROM_ADDRESS` | prod | — | Verified sender (or `onboarding@resend.dev` for testing) |
| `INSIDE_NOTIFICATION_EMAIL` | prod | — | Commercial Team inbox for Operator Notifications |
| `ENVIRONMENT` | — | `development` | `development` / `staging` / `production` |
| `CORS_ORIGINS` | — | `http://localhost:5173` | Comma-separated allowed origins |
| `LOG_LEVEL` | — | `INFO` | Minimum log level |
| `PORT` | — | `8000` | Server port (Railway injects this) |

Generate secrets:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> **Note:** JWT authentication has been removed (v1.1). Admin access uses a static
> API key supplied via `X-Admin-Key` header. No login endpoint exists.

---

## Railway Deployment

1. Connect repository to a Railway project.
2. Add a PostgreSQL service — Railway auto-provides `DATABASE_URL`.
3. Set all required env vars in Railway dashboard.
4. Deploy: Railway runs `alembic upgrade head && uvicorn src.main:app` automatically.
5. Verify: `GET https://your-app.railway.app/health` returns `{"status":"ok"}`.

---

## API Endpoints

### Public (no auth)
| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/leads/capture` | Capture a qualified lead |

Rate limit: 5 requests / 10 minutes per IP on capture endpoint.

### Admin (`X-Admin-Key` header required)
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/admin/leads` | List leads (paginated, filterable) |
| `GET` | `/api/v1/admin/leads/{id}` | Lead detail + event log |
| `PATCH` | `/api/v1/admin/leads/{id}/lifecycle` | Transition lifecycle state |
| `PATCH` | `/api/v1/admin/leads/{id}/qualification` | Correct qualification |
| `POST` | `/api/v1/admin/leads/{id}/crm-sync` | Re-queue CRM sync |
| `GET` | `/api/v1/admin/leads/export` | Export as JSON or CSV |

OpenAPI docs: `http://localhost:8000/docs` (development only).

---

## Running Tests

```bash
# Unit tests (no DB required)
pytest tests/unit/ -v

# Contract tests (no DB required)
pytest tests/contract/ -v

# Integration tests (requires running PostgreSQL)
DATABASE_URL=postgresql+asyncpg://deepsearch:deepsearch@localhost:5432/deepsearch_test \
pytest tests/integration/ -v

# Full suite with coverage
pytest --cov=src --cov-report=term-missing
```

---

## Constitution Compliance Summary

| # | Principle | Status |
|---|---|---|
| I | Source of truth | ✅ Backend owns business state |
| II | Session management | ✅ 24h TTL, auto-expiry |
| III | Event tracking | ⚠️ v1 exception: batched delivery |
| IV | Qualification persistence | ✅ All 4 canonical fields + JSONB overflow |
| V | Data integrity | ✅ raw_qualification preserved, no silent drops |
| VI | Observability | ✅ structlog JSON, request_id, no PII in logs |
| VII | Security / GDPR | ⚠️ v1 exception: consent deferred to v1.1 |
| VIII | Scalability | ✅ Stateless API, Railway horizontal scaling |
| IX | Analytics readiness | ✅ SQL-queryable from event log |
| X | Backward compatibility | ✅ 30-day shim for legacy field names |
| XI | Deployment standards | ✅ Docker, Railway, health check |
| XII | API design | ✅ REST, RFC 7807 errors, versioned prefix |
| XIII | DB evolution | ✅ Alembic-only DDL, migration-safe |
| XIV | Failure handling | ✅ DB unavailable → 503, CRM failure → retry |
| XV | Lead lifecycle tracking | ✅ All transitions in lead_lifecycle_events |

---

## Frontend Migration Note

The frontend (`DemoForm.jsx`) currently sends legacy field names:
`subject_type`, `motivation`, `country`, `user_role`

The backend maps these to canonical names via a 30-day backward compatibility shim.
**Action required:** Update `DemoForm.jsx` to use `target`, `obiettivo`, `geografia`, `role`
before the shim is removed in v1.1.