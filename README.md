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
feedback.

#### Seeded logins

`scripts/seed.py` creates one admin and three registered accounts. Every
address comes from `SEED_*` in `.env`; the password for the three registered
users is shared (`SEED_USER_PASSWORD`). Change all of them before seeding
anything you intend to expose.

| Role      | `SEED_ADMIN_EMAIL`           | Password                  | Notes                                        |
| --------- | ---------------------------- | ------------------------- | -------------------------------------------- |
| Admin     | `SEED_ADMIN_EMAIL`           | `SEED_ADMIN_PASSWORD`     | Moderation, content CRUD, `/admin/*`         |
| Registered| `SEED_USER_EMAILS[0]`        | `SEED_USER_PASSWORD`      | Ratings, bookmarks, submissions, feedback    |
| Registered| `SEED_USER_EMAILS[1]`        | `SEED_USER_PASSWORD`      | Same tier, different data                    |
| Registered| `SEED_USER_EMAILS[2]`        | `SEED_USER_PASSWORD`      | Same tier, different data                    |

The three addresses are read from the comma-separated `SEED_USER_EMAILS` and
exposed as `settings.seed_user_email_list`. `.env.example` ships placeholders
only; the defaults baked into `app/core/config.py` exist so a fresh clone runs,
and are not safe to expose.

`user_preferences` rows are created for every seeded user **except** the admin,
so the dashboard's get-or-create path is exercised on first admin login.

#### Password reset

There is **no mail transport**. The link is produced by one of two honest paths,
selected by `PASSWORD_RESET_DELIVERY`:

- `log` (default, development) - a single-use token is minted and the full
  `/reset-password?token=...` URL is written to the `password_reset_link_issued`
  log line. The operator hands it over. `GET /reset-password` serves a working
  form that consumes the token.
- `none` - **no token is minted** and the response says delivery is not
  configured, instead of claiming a link was generated.

`POST /api/v1/auth/forgot-password` returns the same `message` and `delivery`
for every address, registered or not, so it cannot be used to enumerate
accounts. `reset_url` is populated only when `DEBUG=true`, for local testing.

Before going live: wire a real transport, set `PASSWORD_RESET_DELIVERY=none`,
and note that `validate_runtime` logs a warning while `log` is active in
`APP_ENV=prod`, because single-use reset tokens should not sit in production
logs.

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
| Chatbot       | `chatbot/message` (visitor or JWT), `chatbot/history/{session_id}` (JWT **+** `?session_token=`, owner only)                                    |
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

**Ownership vs identifiers.** A path parameter is a locator, never a credential.
Anything that reads a *specific* user-owned row (currently
`GET /chatbot/history/{session_id}`) requires `CurrentUser` **and** an opaque
`session_token`, then checks the token matches and the row's `user_id` is either
the caller or unclaimed. Sequential ids are enumerable, so possession of an id
must never be enough.

**Response schemas are the disclosure boundary.** `FeedbackRead` (what a
submitter sees) has no `admin_note`; `FeedbackAdminRead` adds it. Splitting the
model rather than nulling the field in the service means a new public route
cannot leak the note by accident.

**Write-then-read ordering.** Mutating services `flush()`, read the row back to
build the response, and only then `commit()`. The session runs `autoflush=False`,
so the explicit flush is what makes the read-back see the change. Any failure
before the commit rolls the write back with the request, instead of persisting
work and then returning 500 for it.

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
client IP as resolved from `X-Forwarded-For` / `X-Real-IP` / the socket peer. The
auth routes tighten that to `IP|email` so one account cannot exhaust a shared
NAT's quota. Scopes: `register`, `login`, `forgot_password`, `feedback`,
`chatbot`. Because `X-Forwarded-For` is trusted unconditionally, a direct client
can rotate it to sidestep every limit - only expose the API through a proxy that
overwrites that header.

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
pytest                          # everything
pytest -m "not db"              # skip the database-backed tests
pytest -m db                    # only the database-backed tests
```

Tests that need PostgreSQL are marked `db` and skip automatically when no
reachable server is configured, so the suite is green offline.

**Test isolation uses a throwaway database, not a per-test schema.** Set
`TEST_DATABASE_URL` to a server you are allowed to create databases on; the
session fixture then creates `TEST_DB_NAME` (`fanhub_test` by default), runs
Alembic against it, and drops it on the way out:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/postgres pytest -m db
```

The target database is recreated even if a previous run crashed and left it
behind, and its connections are terminated before the drop. The database named
in `TEST_DATABASE_URL` is only used as the migration source - it is never
migrated or written to. Schemas are *not* used for isolation: a pooled endpoint
binds a connection to whichever backend it lands on, so a search-path-scoped
schema can leak onto the next tenant's connection, and schema-local native
enums collide with the ones in `public`.

The role needs `CREATEDB`, or `CREATE DATABASE`/`DROP DATABASE` plus permission
to terminate connections. On a hosted server such as Neon, use the pooled
hostname with the owner role.

### Stress and load

`tests/test_stress.py` has two tiers. The default tier covers concurrency and
abuse resistance: overlapping reads, concurrent rating upserts converging on one
row, concurrent submissions all landing, and the rate limiter's quota, retry
header, and per-identity isolation. The heavy tier is opt-in because a remote
database costs a network round trip per request:

```bash
RUN_STRESS=1 pytest tests/test_stress.py -k "sustained or high_parallelism"
RUN_STRESS=1 STRESS_ROUNDS=200 STRESS_CONCURRENCY=100 pytest tests/test_stress.py
```

The rate-limit checks use a unique scope per run and delete their keys, so they
neither need nor disturb a real Redis budget.

| File                      | Marker  | Covers                                                                          |
| ------------------------- | ------- | ------------------------------------------------------------------------------- |
| `support.py`              | -       | Shared credentials, constants and HTTP helpers; import it, don't run it         |
| `test_regressions.py`     | `db`    | One case per audited SRS defect, so a fix cannot silently regress               |
| `test_functional.py`      | `db`    | End-to-end HTTP contracts: auth, RBAC, content, engagement, admin, edge inputs   |
| `test_search_path.py`     | `db`    | `DB_SEARCH_PATH` quoting, transaction-local application, no pooled leakage      |
| `test_stress.py`          | `db`    | Concurrency, rating-upsert races, rate limiting, opt-in sustained load          |
| `test_logging_contract.py`| -       | Static check that no `extra=` key shadows a reserved `LogRecord` attribute      |

### Test environment

`tests/conftest.py` sets the process environment before the application is
imported, so the suite never talks to your development or production data. It
disables Redis and rate limiting, uses a local in-process cache, and points mail
delivery at logs.

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
