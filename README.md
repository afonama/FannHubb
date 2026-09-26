# Fan Hub Plus - Backend

A FastAPI backend for a multi-fandom hub covering anime, gaming, movies, TV,
K-Pop, comics, manga and cosplay. It serves public catalogue browsing,
registered-user engagement (bookmarks, ratings, preferences, fan submissions,
feedback) and a swappable FAQ/LLM chatbot assistant.

Backend only: there is no frontend in this repository.

## Stack

| Concern     | Choice                                                        |
| ----------- | ------------------------------------------------------------- |
| API         | FastAPI 0.115, Pydantic v2                                      |
| ORM / DB    | SQLAlchemy 2.0 (async), asyncpg, PostgreSQL 15+                |
| Migrations  | Alembic 1.13 (async `env.py`)                                  |
| Cache       | Redis (rate limits, token blacklist, popularity counters)      |
| Auth        | HS256 JWT access/refresh pairs, Argon2id password hashing      |
| Scheduling  | APScheduler (popularity flush)                                  |
| Testing     | pytest, pytest-asyncio, httpx ASGI transport                    |

## Requirements

- Python 3.11+
- PostgreSQL 15+ (the project targets **Neon**; the pooled `-pooler` host is used
  for runtime traffic because PgBouncer does not support prepared statements)
- Redis 6+ (optional in development: the app falls back to an in-process cache)

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
copy .env.example .env          # Windows: copy .env.example .env
```

`.env` must be filled in before the app will import - `DATABASE_URL` and
`JWT_SECRET_KEY` are required fields and are validated at startup.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # JWT_SECRET_KEY
```

### Database

```bash
alembic upgrade head            # apply migrations
alembic current                 # what is applied
alembic downgrade -1            # roll back one revision
```

`alembic upgrade head --sql` renders the full DDL to stdout without connecting,
which is useful for reviewing a migration or piping it into `psql`.

### Seed data

```bash
python scripts/seed.py          # idempotent: safe to re-run
python scripts/seed.py --reset  # drop seeded rows first
```

Creates 8 categories, 40 content items, users and preferences, characters,
merchandise, events, FAQs, plus sample ratings, bookmarks, submissions and
feedback. Seeded logins come from `SEED_*` in `.env` (admin
`admin@fanhubplus.dev` / `Admin@12345` by default - change them).

### Schema export

```bash
python scripts/export_schema.py            # docs/schema.sql, offline
python scripts/export_schema.py --live     # introspect the real database
```

### Run

```bash
uvicorn app.main:app --reload
```

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI JSON: <http://localhost:8000/openapi.json>
- Health: `/api/v1/health` (checks dependencies), `/api/v1/health/live` (liveness only)

## API surface

64 operations under `/api/v1`. Content mutation is admin-only; ratings are
written through `POST /content/{id}/rate` (upsert) and read via
`GET /content/{id}/rating`.

| Area          | Endpoints                                                                                                                                   |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth          | `register`, `login`, `refresh`, `logout`, `change-password`, `forgot-password`, `reset-password`, `verify-email/{token}`, `resend-verification`, `me` |
| Users         | `users/me`, `PATCH users/me`, `users/me/avatar`, `users/me/preferences`, `users/me/bookmarks`, `users/me/dashboard`                        |
| Catalogue     | `content`, `content/{id}`, `categories`, `categories/{slug}`, `characters`, `characters/{id}`, `merchandise`, `merchandise/{id}`, `events`, `events/{id}` |
| Engagement    | `bookmarks` (list/create/delete), `content/{id}/rate`, `content/{id}/rating`, `content/{id}/rating/me`, `feedback`, `submissions`        |
| Chatbot       | `chatbot/message`, `chatbot/history/{session_id}`                                                                                             |
| Admin         | `admin/content`, `admin/characters`, `admin/merchandise`, `admin/feedback`, `admin/submissions`, `admin/stats`, `admin/tasks/flush-popularity` |
| Health        | `health`, `health/live`                                                                                                                      |

### Error envelope

Every non-2xx response shares one shape:

```json
{
  "status_code": 404,
  "code": "NOT_FOUND",
  "message": "content 42 not found",
  "details": {},
  "request_id": "0f3c...",
  "timestamp": "2026-09-25T18:04:11.512Z"
}
```

## Design notes

**Auth tiers.** Three dependencies make a route's access level readable from its
signature: `OptionalUser` (visitor, JWT optional), `CurrentUser` (registered, 401
without a token) and `AdminUser` (401 anonymous, 403 non-admin). A *present but
invalid* token always 401s - silently downgrading to anonymous would hide client
bugs and revoked sessions.

**Popularity.** The read path never writes to PostgreSQL: `GET /content/{id}`
issues a Redis `INCR`. APScheduler flushes every
`POPULARITY_FLUSH_INTERVAL_SECONDS`, first `RENAME`-ing each pending counter to a
`:flushing` key. That rename is atomic, so views landing mid-flush start a fresh
counter instead of being lost. Scores blend log-scaled views, star average and a
30-day recency half-life (`app/services/popularity_service.py`).

**Tags.** `Content.tags` is a real many-to-many through the `Tag` entity and the
`content_tags` join table (both FKs cascading), while the API keeps the flat
`tags: list[str]` shape.

**Search.** `content.search_vector` is a generated `TSVECTOR` column
(`to_tsvector` over title + description) with a GIN index, so ranking stays
index-assisted rather than a `ILIKE` scan.

**Geospatial.** Events use plain `lat`/`lng` columns and a bounding-box
prefilter refined in Python with haversine. No PostGIS dependency.

**Rate limiting.** Fixed-window `INCR` with the TTL set on first hit, keyed by
client IP (honouring one proxy hop) plus user id when authenticated. Scopes:
`register`, `login`, `forgot_password`, `feedback`, `chatbot`.

**Cache fallback.** With `REDIS_URL` unreachable the app logs a warning and uses
an in-process cache with matching semantics. That keeps a laptop bootable; it is
never suitable for production, where Redis is required.

**Chatbot.** `CHATBOT_PROVIDER=rules` (default) matches input against the
`chatbot_faqs` keyword index - deterministic, offline, zero cost.
`CHATBOT_PROVIDER=llm` switches to an OpenAI-compatible call site that degrades
back to the rules engine when no key is configured or the call fails. Adding a
provider means implementing `ChatbotEngine` and registering it in `build_engine`;
no route or schema changes. `CHATBOT_ENABLED=false` returns
503 `SERVICE_DISABLED` from the chatbot routes and leaves the rest of the app
untouched.

## Testing

```bash
pytest                        # everything
pytest -m "not db"            # skip the database-backed tests
pytest -m db                  # only the database-backed tests
```

Tests that need PostgreSQL are marked `db` and skip automatically when no
reachable server is configured, so the suite is green offline. Point them at a
throwaway database - each test creates and drops its own schema:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/fanhubplus_test pytest -m db
```

| File                             | Covers                                                          |
| -------------------------------- | --------------------------------------------------------------- |
| `test_models.py`                 | Mapper configuration, constraints, index coverage                |
| `test_openapi.py`                | Route inventory, error contract, access tiers                    |
| `test_security.py`               | Password hashing, JWT issue/verify/refresh, revocation, SSL modes |
| `test_schemas.py`                | Field bounds, validators, enum values                            |
| `test_cache_and_rate_limit.py`   | Cache semantics, TTL, atomic `RENAME`, fixed-window limits       |
| `test_popularity.py`             | Score maths, counter drain, mid-flush view safety                |
| `test_chatbot.py`                | Tokenising, FAQ scoring, provider selection, disabled gate        |
| `test_service_contracts.py`      | Service signatures the DB tests depend on                        |
| `test_migration.py`              | Initial revision matches `Base.metadata` (rendered offline)      |
| `test_integration_db.py`         | Auth, ratings, bookmarks, content, chatbot, HTTP layer (needs DB) |

## Layout

```
app/
  api/v1/       route modules (one per resource)
  core/         config, security, deps, redis, rate limiting, errors, logging
  db/           Base metadata, session, models/
  schemas/      Pydantic request/response models
  services/     business logic, one module per domain
  worker/       APScheduler entry point and popularity flush
alembic/        migrations
docs/           generated schema.sql
scripts/        seed.py, export_schema.py
tests/
```

## Operational notes

- `GET /api/v1/health` reports the active cache backend; `CHATBOT_ENABLED` is
  surfaced there too so a client can hide the widget.
- `POST /api/v1/admin/tasks/flush-popularity` triggers the popularity flush
  manually instead of waiting for the scheduler.
- Structured JSON logging is on by default (`LOG_JSON=true`); set
  `LOG_JSON=false` for human-readable local output.
- `APP_ENV=prod` rejects a wildcard `CORS_ORIGINS`.
