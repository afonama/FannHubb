# Fan Hub Plus — SRS Compliance Audit Report

| Field | Value |
|---|---|
| **Project** | Fan Hub Plus (`C:\Users\HP\OneDrive\Desktop\FanHub`) |
| **Audit date** | 2026-09-27 |
| **Scope** | Every requirement in the supplied SRS checklist, verified against source, live HTTP behaviour, database state, and logs |
| **Environment** | Python 3.13.14 · FastAPI · Neon PostgreSQL 18.6 · Redis (Upstash) · Alembic `0001_initial` (head) |
| **Surface audited** | 70 routes, of which 64 are `/api/v1` operations |
| **Method** | Live HTTP requests driven through the complete ASGI middleware stack (`httpx.ASGITransport`), plus static source reading |
| **Overall verdict** | **Backend substantially functional; no user-facing product.** One systemic error-handling defect corrupts every authenticated 4xx response, one confirmed IDOR, one false-failure data bug, and zero automated tests. |

---

## 1. Executive summary

The backend is competently built. Authentication, catalogue filtering, engagement features, admin CRUD, analytics, and the database schema all work and are internally consistent. The schema deliverable in particular is fully verified: **17/17 tables and every column match** across the ORM models, `docs/schema.sql`, and the live database, with Alembic at head.

Three problems dominate.

1. **A systemic defect turns every authenticated error response into a `500`.** Any request bearing a valid token that fails with a handled `AppError` before a database commit has its correct 4xx body discarded and replaced by `INTERNAL_ERROR`. This is not a single endpoint — it affects the entire API surface for logged-in users. Full analysis in §3.1.
2. **Confirmed broken access control.** Chat conversation history is readable by any caller — including a fully anonymous one — who can guess or enumerate a session id. Demonstrated live in §3.6.
3. **Moderation writes report failure while succeeding.** Admin submission review commits its changes and *then* crashes on read-back, so the administrator receives a `500` for an operation that actually took effect. Verified by reading the persisted row back in §3.5.

Set against this, **there is no frontend of any kind.** The tracked `index.html` is zero bytes, there are no templates, no JavaScript, and no build configuration. Every presentation-layer requirement — pages, dashboard, dark mode, font controls, breadcrumbs, spinners, transitions, responsive design, accessibility — is therefore not merely incomplete but entirely absent. The deliverable is an API, not a web application.

Finally, **the project has no tests.** `pytest` collects nothing, despite four test dependencies being declared. Each defect catalogued in this report is precisely the class of failure a modest test suite would have caught at first run.

### Findings by severity

| Severity | Count | Summary |
|---|---|---|
| Critical | 1 | Systemic authenticated 4xx → 500 corruption |
| High | 4 | Chatbot history IDOR; false-failure submission moderation; broken personalized dashboard; content pagination unusable |
| Medium | 7 | Event `from_date` inverted; `admin_note` leak; password reset unusable; no tests; missing `.env.example`; fabricated media; chatbot LLM inert |
| Low | 5 | Sitemap/robots absent; credential docs incomplete; Redis instability; merch schema limits; media upload scope |

---

## 2. Methodology and evidence base

Every claim below is backed by one of: executed HTTP request and observed status/body, database query, source line reference, or log line.

- Requests were issued against the real application object with `raise_app_exceptions=False`, so genuine client-visible status codes were recorded rather than raw tracebacks.
- Where a defect was non-obvious, the mechanism was isolated with a minimal controlled experiment before being reported — this corrected two initial hypotheses during the audit (see §7).
- Anonymous and authenticated requests were tested separately, because the systemic defect in §3.1 is invisible to anonymous callers and would otherwise be under-reported.
- Negative cases were probed deliberately: nonexistent ids, invalid enum values, bad foreign keys, wrong content types, and unprivileged role access.

### Test data residue

Verification mutated the configured database. Residue left behind, disclosed in full:

| Artefact | State |
|---|---|
| `audit.tester@fanhubplus.dev` | registered; password changed during the audit — **value redacted, rotate it** |
| `audit.avatar@fanhubplus.dev` | registered; password set during the audit — **value redacted, rotate it** |
| Bookmark id 3 | merchandise/1 — retained |
| Feedback id 1 | `status=closed`, `admin_note` set |
| Submission id 1 | `status=approved`, `review_note` set, `reviewed_by=1` |
| Chatbot session id 1 | 2 messages |
| `media/avatars/user_6_08cbc5d2a646.png` | 72-byte uploaded avatar |
| User 2 display name + favorite categories | changed, then partially reverted |

Created-then-deleted: content id 41, one rating, two bookmarks. The git working tree is clean; `media/` is gitignored.

---

## 3. Findings — done but broken or incomplete

### 3.1 Systemic: every authenticated 4xx is returned as 500 — *Critical*

**Location:** `app/core/deps.py:38`, `app/main.py:88`

**Mechanism.** When a request raises, the session dependency rolls back:

```python
# app/core/deps.py:32-41
async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()      # line 38
            raise
```

`Session.rollback()` **unconditionally expires every instance in the identity map**, regardless of the `expire_on_commit=False` setting. The authenticated `User` was loaded into `request.state.current_user` but not yet committed, so it is expired here.

The exception handler then correctly serialises the intended 4xx envelope. But as that response unwinds back out through the access-log middleware, line 88 dereferences the now-expired object:

```python
# app/main.py:88
"user_id": getattr(getattr(request.state, "current_user", None), "id", None),
```

`getattr(..., "id", None)` gives a false sense of safety: a default only suppresses `AttributeError`, whereas SQLAlchemy's expired-attribute access raises `DetachedInstanceError`, which propagates and is converted to `500 INTERNAL_ERROR`. **The correct status code and body are computed, then thrown away.**

**Exact trigger condition.** Any request presenting a valid access token — via `Authorization` header *or* httpOnly cookie — that ends in a handled `AppError` raised **before** any `session.commit()`. Anonymous callers are unaffected because no `User` is ever loaded, which is why the guard tests in §4.1 all pass.

**Confirmed immunity by accident.** Services that commit before raising are unaffected, because the commit closes the active transaction and the later rollback has nothing to expire. This is why `DELETE /content/{id}/rating` correctly returns `404` while its sibling `GET /content/{id}/rating/me` returns `500` for the identical condition (`app/services/rating_service.py:111` commits first). The correct behaviour here is accidental, not designed.

**Verified casualties:**

| Request | Expected | Actual |
|---|---|---|
| `GET /admin/stats` as non-admin | `403` | `500` |
| `GET /admin/content` as non-admin | `403` | `500` |
| `GET /admin/feedback` as non-admin | `403` | `500` |
| `GET /bookmarks/99999` | `404` | `500` |
| `POST /bookmarks` with nonexistent target | `404` | `500` |
| `GET /content/1/rating/me` after delete | `404` | `500` |
| `PATCH /users/me/preferences` bad slug | `404` | `500` |
| `POST /users/me/avatar` with `.exe` | `4xx` | `500` |
| `POST /auth/change-password` wrong current | `4xx` | `500` |

**Assessment.** Functionally this is a denial-of-usability rather than a privilege escalation — access is still refused — but it destroys API contract conformance, makes every client unable to distinguish "missing" from "server broken", suppresses correct error codes from monitoring, and will corrupt any retry logic. The one-line fix is to capture the scalar id before the route executes rather than dereferencing the ORM instance afterwards, or to guard the access.

### 3.2 Personalized dashboard fails for every user — *High*

`app/services/user_service.py:325` calls:

```python
bookmarks = await bookmark_service.list_bookmarks(session, user, limit=limit, offset=0)
```

but the callee signature (`app/services/bookmark_service.py:107-113`) is:

```python
async def list_bookmarks(
    session: AsyncSession, user: User, page: PageParams, *, target: Optional[BookmarkTarget] = None
) -> list[Bookmark]:
```

There is no `limit` or `offset` keyword; the third positional parameter is a `PageParams` object. The call raises `TypeError` on every invocation, so `GET /users/me/dashboard` returns `500` unconditionally — reproduced for a seeded user, for a user with data, and for a freshly registered user with none. The user dashboard is entirely non-functional.

### 3.3 Content pagination is unusable — *High*

`GET /content` advertises a full pagination envelope (`page`, `page_size`, `pages`, `total`, `has_next`, `has_prev`) but rejects both pagination parameters:

```
GET /api/v1/content?page=2        -> 422  "query.page: Extra inputs are not permitted"
GET /api/v1/content?page_size=50  -> 422  "query.page_size: Extra inputs are not permitted"
```

**Cause — a FastAPI footgun.** `ContentFilters` is bound as a query-parameter model and forbids extras:

```python
# app/api/v1/content.py:21-22
pagination: Pagination,                                  # separate dependency
filters: Annotated[ContentFilters, Query()],             # extra="forbid"
```

```python
# app/schemas/content.py:117
model_config = ConfigDict(extra="forbid")
```

When a Pydantic model is bound with `Annotated[..., Query()]`, FastAPI turns each model field into an individual query parameter, then applies the model's own `extra="forbid"` to the **entire** query string. Because `page` and `page_size` arrive from an independent dependency and are not fields of `ContentFilters`, they are treated as forbidden extras.

**Impact.** 40 content rows exist; only the first 20 are reachable by any caller, through any parameter combination, while `has_next` reports `true` — an API that lies about its own state. Characters, merchandise, and events do not use this pattern and paginate correctly, so the defect is isolated to the content catalogue.

### 3.4 Event `from_date` filter is inverted — *Medium*

```python
# app/services/event_service.py:71-75
if filters.from_date:
    stmt = stmt.where(Event.end_date.isnot(None), Event.end_date >= filters.from_date)
    stmt = stmt.where(Event.start_date <= filters.from_date)   # line 73 — spurious
```

Line 73 ANDs `start_date <= from_date`, so the two conditions together match only events whose date span **contains that exact day**. `from_date` therefore behaves as "events happening on this date", not "events from this date onward".

All ten seeded events fall in October–November 2026. `from_date=2026-01-01&to_date=2027-12-31` — a range containing every event — returns **0 results**, while `to_date` alone correctly returns 10. The "upcoming events from date X" query is unreachable.

### 3.5 Submission moderation is broken and reports false failure — *High*

`app/services/submission_service.py` references a relationship that does not exist. The model declares `author` and `reviewer`; the service references `.user` in three places:

- line 78 — `selectinload(FanSubmission.user)` (admin list)
- line 105 — `selectinload(FanSubmission.user)` (detail)
- line 111 — `submission.user`

`GET /admin/submissions`, `GET /admin/submissions/{id}`, and `PATCH /admin/submissions/{id}` all return `500`. Admin submission moderation is entirely non-functional.

**The false-failure defect is more serious than the crash.** `review_submission` commits *before* the failing read-back:

```python
# app/services/submission_service.py:122-134
submission.status = payload.status
submission.reviewed_by = reviewer.id
...
await session.commit()                                    # line 129 — persisted
logger.info("submission_reviewed", ...)
return await get_submission(session, submission_id)       # line 134 — crashes here
```

Verified by reading the row back through the owning user's own submissions endpoint: submission 1 held `status='approved'`, `review_note='Audit approved.'`, `reviewed_by=1` — while the administrator had received `500 INTERNAL_ERROR`. **The API reports failure for a write that succeeded.** Any moderation UI built on this endpoint would show an error and an administrator would reasonably retry or assume the change was lost, risking inconsistent state.

### 3.6 Chatbot history is readable by anyone — *High (security)*

```python
# app/api/v1/chatbot.py:47-55
@router.get("/history/{session_id}", ...)
async def get_history(session_id: int, db: DbSession) -> ChatHistoryResponse:
```

The route declares no authentication dependency, and `app/services/chatbot_service.py:365-383` loads the session purely by integer id with no ownership or `session_token` comparison.

Demonstrated live against session 1:

| Caller | Result |
|---|---|
| Owning user | `200`, 2 messages |
| **Different authenticated user** | **`200`, 2 messages** |
| **Fully anonymous** | **`200`, 2 messages** |

Any party who can guess or enumerate a session id — a small sequential integer — can read another user's conversation. Chat history is user-generated content and may contain personal information, making this a genuine confidentiality breach. Session ids are trivially enumerable, so this is realistically exploitable, not theoretical.

### 3.7 Admin moderation notes leak to end users — *Medium*

`app/schemas/feedback.py:23-29` defines a single `FeedbackRead` model used by **both** the public endpoint and the admin endpoint, and it includes:

```python
admin_note: str | None = None
```

Verified: after an administrator set a moderation note, the owning regular user's `GET /api/v1/feedback` returned `"admin_note": "Audit note."` Internal administrative commentary is exposed to end users. The field should be split into separate public and admin response models.

### 3.8 Password reset cannot be completed — *Medium*

No SMTP or mail-delivery dependency exists in the project. The reset flow therefore dead-ends at every stage:

- `app/services/auth_service.py` only writes the reset link to the application log.
- `POST /auth/forgot-password` returns `200` with the body `{"message": "If that email is registered, a password reset link has been generated.", "reset_url": null}` — the URL is null because `DEBUG=false`.
- The generated link points at `/reset-password`, which returns `404`; no such page or route exists.

A user who forgets their password receives a success message, no email, and no usable link. **The account-recovery path is non-functional.** Email verification has the same gap: the token is generated and persisted correctly, but never delivered.

### 3.9 No test suite exists — *Medium*

```
$ pytest --collect-only -q
PytestConfigWarning: No files were found in testpaths
no tests collected in 0.11s
```

`pyproject.toml` declares `testpaths = ["tests"]` and pins `pytest`, `pytest-asyncio`, `httpx`, and `anyio` as dev dependencies, but the `tests/` directory does not exist. The tracked `test/` entry is an unconfigured gitlink (mode `160000`, commit `63a71f0`) with no `.gitmodules` and a zero-byte `index.html`; README-referenced test files are absent. The four bugs in §3.1, §3.3, §3.4, and §3.5 are all trivially detectable with a handful of integration tests.

### 3.10 Installation instructions are broken — *Medium*

The README instructs `copy .env.example .env`, but **`.env.example` does not exist**. A new developer following the documented setup hits a missing-file error at the first configuration step. Required settings `database_url` and `jwt_secret_key` are correctly declared as mandatory fields with no defaults (`app/core/config.py:40-43, 64-66`), so the failure is purely the absent template.

### 3.11 Media assets are fabricated — *Medium*

All `media_url` values point to `https://cdn.fanhubplus.dev/...`, a domain that does not resolve to a real host, and sampled `body_rich_text` fields were empty. The data model *describes* articles, video, audio, and images, but no genuine asset exists for any of them. The only functional upload path is avatars (`app/services/media_service.py`), which correctly validates against an allow-list and writes to `/media`.

### 3.12 Chatbot LLM provider is inert — *Low*

`chatbot_provider` defaults to `"rules"` and `chatbot_llm_api_key` is empty, so `LlmChatbotEngine.configured()` returns `False` and every call falls through to the rules engine with a logged warning (`app/services/chatbot_service.py:187-195`). The LLM code path is fully implemented but unused in this deployment; all observed responses came from keyword FAQ matching.

### 3.13 Merchandise schema cannot express the requirement — *Low*

`Merchandise` carries a single `image_url` and a single `tag` string. Image galleries and multi-tag grouping are not representable, so the corresponding SRS items are blocked at the data-model layer rather than merely unimplemented at the service layer.

### 3.14 Sitemap and robots.txt absent — *Low*

`/sitemap.xml` and `/robots.txt` both return `404`. The application root `/` returns a JSON payload rather than an HTML page, so there is no document from which a sitemap could be generated even manually.

### 3.15 Credential documentation incomplete — *Low*

The README documents only the default administrator account. The three seeded regular users exist solely inside the gitignored `.env` via `SEED_USER_EMAIL_LIST`, so the documented credential set is not complete for testing the registered-user role.

### 3.16 Redis connection instability — *Low*

`logs_boot.out:66` records a `ConnectionError` to `pro-mastodon-299559.upstash.io:6379` (`network name no longer available`), and the background scheduler repeatedly logged popularity flushes affecting `0 rows`. A manual flush later succeeded with `updated_rows: 4`, so the flush path is functional; the concern is connection resilience, not correctness of the logic.

---

## 4. What is done and working

### 4.1 Authentication and account management

Verified end to end and of notably high quality:

| Behaviour | Result |
|---|---|
| Registration | `201` + access/refresh token pair |
| Weak password / malformed email | `422` |
| Duplicate email | `409 CONFLICT` |
| Login (admin and seeded users) | `200` |
| Wrong password | `401 AUTH_INVALID_CREDENTIALS` |
| Password hashing | Argon2id, `$argon2id$v=19$m=65536,t=3,p=4$`; verify correct→`True`, wrong→`False` |
| JWT structure | HS256; claims `sub, jti, typ, iat, nbf, exp, iss, role`; 30-min access, 7-day refresh |
| Refresh rotation | Reusing the old refresh token → `401 AUTH_TOKEN_INVALID` |
| Logout blacklist | `200 "2 token(s) revoked"`, subsequent `/auth/me` → `401` |
| Rate limiting | 7 bad logins → `[401,401,401,401,429,429,429]` |
| Profile read/update | `200` / `200` |
| Preferences read/update | `200`; stores `favorite_categories` and `display_prefs` (`theme`, `language`, `compact`) |
| Avatar upload | `200` → `/media/avatars/user_6_*.png`, served via `StaticFiles` mount |
| Change password | `200`; new password authenticates; rejects wrong-current and reuse |
| Email-verification tokens | Issued with expiry; bogus token → `404` |
| Anonymous access control | **26 protected routes return `401`** |

Rate limits are additionally configured for registration, forgot-password, feedback, and chatbot scopes (`app/core/config.py:90-99`).

### 4.2 Content catalogue

- 8 categories seeded and served: `anime, gaming, movies, tv-shows, k-pop, comics, manga, cosplay`; list and slug detail work, unknown slug → `404`.
- 40 content rows in real PostgreSQL.
- `type` filter: article 25, video 7, audio 3, image 5 — sums to 40.
- `category=anime` → 5 · `genre=gallery` → 3 · `year=2024` → 22.
- `q` search is case-insensitive and whole-token (`Group` and `group` both → 1; `Grou` → 0).
- `sort=latest|popular|alpha` return three demonstrably different orderings; `relevance` is available.
- Detail responses include category, tags, and caller-aware `bookmarked` / `user_rating` fields.
- **View counter increments live** through Redis INCR: 14401 → 14402 across two reads.

### 4.3 Characters, merchandise, events

| Resource | Rows | Verified filters | Other |
|---|---|---|---|
| Characters | 15 | `category=anime`→4, `search=Anya`→1, combined | detail, `404` |
| Merchandise | 19 | `category=anime`→3, `tag=figure`→1, `upcoming`→7 | detail, view counter 12471→12472, `404` |
| Events | 10 | `city=Seoul`→1, `upcoming_only`→10, `near`+`radius_km`→2 with `distance_km` | real `lat`/`lng`, populated `ticket_url`, `404` |

Event geo-filtering uses a correct Haversine implementation (`app/services/event_service.py:31`).

### 4.4 Engagement features

- **Ratings:** create, upsert (second call returns `created=false`, aggregate moves 5.0 → 3.0), public aggregate, caller's own rating, and delete all behave correctly. Upsert semantics are enforced by a `uq_ratings_user_content` constraint, as documented in the service.
- **Bookmarks:** all three target types create successfully (`content`, `character`, `merchandise`); list, detail, `/users/me/bookmarks`, delete-by-id, and delete-by-query-params all work. Read models are denormalized with `title`, `image_url`, and `category_slug` so no N+1 lookups are needed by a client.
- **Feedback:** submission `201`; caller's own list scoped correctly; admin list and moderation `PATCH status=closed` → `200`.
- **Fan submissions:** user submission `201`; own-list `200` with correct ownership scoping.
- **Chatbot:** `POST /message` → `200` with `session_token` and `session_id`; keyword FAQ engine responds; messages persist; `include_history` returns the thread.

### 4.5 Administration

- Lists: content 40, characters 15, merchandise 19, feedback — all `200`.
- **Content CRUD round-trip verified:** `POST` → `201` (id 41), `PATCH` → `200` with title and tags updated and tags normalised to `['audit','temp']`, `DELETE` → `200`.
- **`/admin/stats` is rich and correct:** `total_users: 4`, `users_by_role{admin:1, registered:3}`, `active_users_today: 16`, a 7-day active-user window sourced from Redis, chatbot volume, popular categories, and `cache_backend: "redis"`.
- `/admin/tasks/flush-popularity` → `200`, `updated_rows: 4, keys_processed: 4`.

### 4.6 Database, schema, and configuration

- **Schema deliverable fully verified:** 17/17 tables present in ORM, `docs/schema.sql`, and the live database, with **every column matching** in all three. The only extra live table is Alembic's own `alembic_version`.
- `alembic current` → `0001_initial (head)`; `alembic heads` → `0001_initial`. No pending migrations, no drift.
- `app/core/config.py` contains **no hardcoded credentials**; `database_url` and `jwt_secret_key` are required fields.
- **No `TODO`, `FIXME`, `XXX`, `HACK`, `NotImplementedError`, or stub markers anywhere in `app/`.** The only `...` occurrences are a legitimate abstract `CacheBackend` protocol (`app/core/redis_client.py:40-51`) and a protocol method in the chatbot engine.

---

## 5. What has not been done

### 5.1 The entire frontend — *Critical scope gap*

There is no user-facing application. The tracked root `index.html` is zero bytes; there are no templates, no JavaScript, no CSS, and no build configuration. The application root returns JSON, not HTML.

Every presentation-layer requirement is therefore absent, not partially complete:

- Home page, fandom category pages, content and article pages
- Personalized dashboard **UI** (the backend for it is also broken — §3.2)
- Dark-mode toggle and font-size controls
- Breadcrumb navigation
- Loading spinners and transition/animation polish
- Responsive design
- All visual, keyboard, and screen-reader accessibility

The backend does persist a `display_prefs` object containing `theme`, `language`, and `compact` flags, so the *data* for some preferences exists — but nothing consumes it.

### 5.2 Content and presentation features

- **Interactive multimedia center** — no video or trailer player, no audio clip playback, no animated explainers. Only a `ContentType` enum and `media_url` strings.
- **Featured article with rich text and embedded images** — no featured flag and no timeline or highlights model exist.
- **Event highlights section**, and **map / calendar UI** — the geo *query* capability exists (§4.3) but nothing renders it.
- **Merchandise image galleries** — blocked at the schema layer (§3.13).
- **Multi-tag grouping** for merchandise — blocked at the schema layer.

### 5.3 Chatbot

- **Personalized recommendations** — there is no `recommend*` code anywhere in `chatbot_service.py`.
- **Guided discovery flow** — absent; the bot is FAQ keyword matching plus a canned fallback.

### 5.4 Administration

- **Category CRUD** — no routes; categories are seed-only.
- **Event CRUD** — no routes.
- **Chatbot FAQ management** — no routes; FAQs are seed-only.
- **Dedicated multimedia management** — no routes; content accepts URLs only.

### 5.5 Infrastructure and deliverables

- **Email/SMTP delivery** for verification and password reset (§3.8).
- **Real media hosting** — no genuine image, video, or audio assets exist (§3.11).
- **Sitemap XML and robots.txt** (§3.14).
- **Any automated test suite** (§3.9).
- **Verifiable non-functional requirements** — responsiveness, WCAG accessibility, lazy-loading, load and performance testing, and uptime or availability monitoring have nothing to assess, because neither a UI nor monitoring exists.

---

## 6. Recommended remediation order

Ordered by risk-reduction per unit of effort.

**Immediate — correctness and security**

1. Fix `app/main.py:88` to stop dereferencing the ORM instance (capture the id before the route runs, or wrap the access). This one change repairs every symptom in §3.1 at once. *Highest value in the report.*
2. Add an authentication dependency and ownership check to `GET /chatbot/history/{session_id}`; verify against the `session_token`, not the raw id (§3.6).
3. Fix the call at `app/services/user_service.py:325` to pass a `PageParams` instance, restoring the dashboard (§3.2).
4. Replace `.user` with the correct relationships at `app/services/submission_service.py:78,105,111`, and move the commit in `review_submission` after the read-back so failures and successes agree (§3.5).
5. Split `FeedbackRead` into public and admin variants so `admin_note` is no longer serialized to end users (§3.7).

**Short term — functional gaps**

6. Remove `extra="forbid"` from `ContentFilters`, or fold `page`/`page_size` into it, restoring content pagination (§3.3).
7. Delete the spurious condition at `app/services/event_service.py:73` (§3.4).
8. Add `.env.example` matching the required settings in `app/core/config.py` (§3.10).
9. Add `tests/` with integration coverage of the endpoints in §3 — start with the four defects above, which are all one-request regressions (§3.9).

**Medium term — completing the product**

10. Implement email delivery, or explicitly reclassify password reset as out of scope and remove the misleading success response (§3.8).
11. Build the frontend, or formally reduce the SRS to a backend-only API specification. Every item in §5.1 is blocked on this decision.
12. Replace fabricated `cdn.fanhubplus.dev` URLs with real assets, and expand the upload path beyond avatars (§3.11).
13. Add the missing admin CRUD surfaces and chatbot recommendation / guided-flow logic (§5.3, §5.4).

---

## 7. Audit notes

Two initial hypotheses were **disproved** by controlled experiment during the audit and are recorded here because both would have produced incorrect findings:

1. *That the `500` on missing content was the same detached-instance defect.* Re-running `GET /content/99999` with **no** `Authorization` header returned a correct `404`. The trigger is the presence of a valid token, not the resource lookup — which refined §3.1 from a vague "some routes" claim to a precise, falsifiable rule.
2. *That `verify_password` was broken.* It had been called with arguments reversed; the real signature is `verify_password(password_hash, plain_password)`. Argon2id verification is correct.

One apparent defect was also a false positive: `DELETE /bookmarks` returned `422` when sent a JSON body, but the route takes `content_type` and `content_id` as **query** parameters (`app/api/v1/bookmarks.py:53-54`). The route is correctly implemented.

---

*Part I generated 2026-09-27. All findings reproducible against the audited environment; no application source code was modified during this audit.*

---

# Part II — Remediation Report

*Added 2026-09-27, after Part I was accepted. Line references are against the remediated tree.*

Part I recorded the backend as it was found. This part records what was changed, what was proven, and — more importantly — **five further defects that only became reachable once the Part I defects were fixed**, plus two residual risks that were deliberately not fixed.

## 8. Status of the Part I findings

All ten accepted findings are fixed and covered by automated tests.

| # | Part I finding | Severity | Fix | Regression test |
|---|---|---|---|---|
| 3.1 | Every authenticated 4xx returned as `500` | Critical | Capture the scalar user id in `request.state` before the route runs, so the handler never dereferences a detached instance | `test_regressions.py` |
| 3.2 | Personalized dashboard raised `TypeError` | High | Pass a `PageParams` to `list_bookmarks`; see also **N-5** | `test_regressions.py` |
| 3.3 | Content pagination unusable (`422`) | High | Drop `extra="forbid"` from `ContentFilters` so it ignores keys it does not own; pagination stays a separate `Pagination` dependency | `test_regressions.py` |
| 3.4 | Event `from_date` inverted | Medium | Delete the spurious `start_date <= from_date` predicate | `test_regressions.py` |
| 3.5 | Moderation reported failure after committing | High | Eager-load `FanSubmission.author`; order `flush → read-back → commit`. See also **N-3** | `test_regressions.py` |
| 3.6 | Chatbot history IDOR | High | Authenticate the route and match the `session_token`; anonymous callers may only adopt a thread they created | `test_regressions.py` |
| 3.7 | `admin_note` leaked to end users | Medium | Split `FeedbackRead` into public and admin variants | `test_regressions.py` |
| 3.8 | Password reset unusable | Medium | `PASSWORD_RESET_DELIVERY=log\|none` with an honest result envelope, plus a real `/reset-password` form. **No SMTP transport exists — see R-1** | `test_regressions.py` |
| 3.9 | No test suite | Medium | 36-case regression suite, 59-case functional suite, 4 isolation cases, 12 stress cases, 2 static guards | `tests/` |
| 3.10 | Installation instructions broken | Medium | `.env.example` now covers all 56 settings; README documents the seeded account via variables instead of published passwords | `test_regressions.py` |

## 9. Defects discovered during remediation

Each of these was found *by* the new test suite, and none was in Part I. All are fixed except where stated.

### N-1 Rating always returns `500` after the write has committed — *High*

**Location.** `app/services/rating_service.py:66` (the `extra=` dict of the `rating_saved` log call; formerly `created` at the old line 63).

**Reproduction.**
```
POST /api/v1/auth/login            # as a seeded user
POST /api/v1/content/{id}/rate     # Authorization: Bearer <token>, body {"scale":"stars","value":4}
```

**Expected.** `200` with `{"rating": {...}, "summary": {...}, "created": true}`.

**Actual.** `500 INTERNAL_ERROR`. The `Rating` row is nonetheless committed, and the public aggregate for that content reflects the new rating.

**Cause.** The service logged `extra={"created": created}`. `created` is already an attribute of every `logging.LogRecord`, and the logging module raises rather than overwrite it:

```
KeyError: "Attempt to overwrite 'created' in LogRecord"
```

The log call sits *after* `await session.commit()`, so the failure could only be converted into a `500` — never prevented. This is the same false-failure shape as Part I §3.5, and it is why the two defects had to be read together: the commit ordering that made moderation lie also made the client's retry duplicate work.

**Fix.** Renamed the key to `rating_created`.

### N-2 Avatar upload always returns `500` after the file has been written — *High*

**Location.** `app/services/media_service.py:111` (the `extra=` dict of the `avatar_stored` log call; formerly `filename` at the old line 107).

**Reproduction.**
```
POST /api/v1/users/me/avatar       # Authorization: Bearer <token>, multipart/form-data with a small PNG
```

**Expected.** `200` with the new avatar metadata.

**Actual.** `500 INTERNAL_ERROR`, while the file exists on disk under `media/avatars/`. A second consequence follows: the client sees a failure, retries, and each retry leaves another orphaned file behind, because the storage step has no compensating cleanup once the log call has failed.

**Cause.** Identical to N-1 — `filename` is a reserved `LogRecord` attribute. Two of the two `extra=` dicts in `app/` that used reserved names were both on a post-commit success path, which is why the failure was total rather than intermittent.

**Fix.** Renamed the key to `stored_filename`.

**Guard.** `tests/test_logging_contract.py` walks every `logger.*(extra={...})` call site in `app/` with `ast` and fails on any key that shadows one of the 23 `LogRecord` attributes. The audit is self-checking: one test asserts the walk actually found call sites, so a future refactor cannot silently neuter the guard.

### N-3 Moderation response reports the reviewer as `null` — *Medium*

**Location.** `app/db/models/submission.py:61-62` (`FanSubmission.author` is `lazy="noload"`) reached via `app/services/submission_service.py:118-126`.

**Reproduction.**
```
POST /api/v1/auth/login            # as an admin
POST /api/v1/admin/submissions/{id}/review   # body {"action":"approve","review_note":"..."}
```

**Expected.** The response's `author` object carries the admin's `name` and `email`.

**Actual.** `author_name` and `author_email` are `null`, although the row in the database is correct.

**Cause.** `review_submission` used `session.get(FanSubmission, id)`. With `lazy="noload"`, the ORM does not load the relationship, and it caches `None` *on the identity-mapped instance*. The eager load added as part of the §3.5 fix then ran against that same instance and did not repopulate it. The reviewer was silently erased from the response, not from the database.

**Why it was missed twice.** Before Part I §3.5, the read-back crashed outright, so this could not surface. Fixing §3.5 correctly exposed it. It is the clearest argument in this report for fixing the reported defect *and* re-running the endpoint rather than trusting the diff.

**Fix.** Use an explicit `select(FanSubmission).options(selectinload(FanSubmission.author))` instead of `session.get()`.

### N-4 `DB_SEARCH_PATH` was applied as a connection startup parameter — *High*

**Location.** `app/db/session.py:151-164`. Previously the schema was passed through `connect_args["server_settings"]`.

**Reproduction.**
```
DB_SEARCH_PATH=some_schema
DATABASE_URL=postgresql+asyncpg://…@ep-…-pooler.…/db   # a pooled endpoint
# then: a transaction that must use some_schema
```

**Expected.** The configured schema is in effect for the request's transactions, and never for anyone else's.

**Actual.** Two failures, both observed on the pooled endpoint:
1. A fresh connection did not have the schema applied at all — `SHOW search_path` returned the server default.
2. A connection that *did* have it applied retained it after the schema was dropped, so a later unrelated request ran `search_path` against a non-existent schema. This is a cross-tenant leak: a pooled backend is shared, but the setting outlived the request that asked for it.

The same mechanism produced `cache lookup failed for type <oid>` on native enums, because the PostgreSQL enum OIDs of a schema-local type and the `public` type with the same name collided on one backend.

**Cause.** Startup parameters (`server_settings`) are applied when a **backend** connection is established. A pooler multiplexes many logical connections over far fewer backends, so "per connection" intent is not "per backend" intent. The configuration option itself was sound; the mechanism used to apply it was not.

**Fix.** Validate the identifier with `quote_search_path`, then apply `SET LOCAL search_path` from an Engine `"begin"` event. `SET LOCAL` is transaction-scoped, so it is re-applied for every transaction on every checkout and is discarded on commit or rollback. Startup parameters are no longer used for this.

### N-5 Dashboard raised a second, independent failure — *High*

**Location.** `app/services/user_service.py:89-104`.

**Reproduction.**
```
POST /api/v1/auth/register        # a brand-new user has no preference row
GET  /api/v1/users/me/dashboard   # Authorization: Bearer <token>
```

**Expected.** `200`.

**Actual.** `409 CONFLICT` (`UniqueViolation` on the primary key of `user_preferences`).

**Cause.** `get_or_create_preferences` is called three times during one dashboard render. Its guard read `user.preference`, but the get-then-insert path never set that attribute, so the second call re-inserted the same `user_id` and violated the primary key. The two guards also lost a race between concurrent requests for the same user.

**Why it is reported as new.** Part I §3.2 attributed the dashboard's total failure to the `TypeError` at `user_service.py:325`. That was correct but incomplete: the endpoint could not get far enough to reach this second defect. Fixing §3.2 alone would have left the dashboard returning `409` and the original fix would have looked complete.

**Fix.** `INSERT ... ON CONFLICT DO NOTHING` on `user_id`, then read the row back and assign `user.preference` so the fast path actually hits. This is also safe under concurrent requests for the same user.

## 10. Residual risks — not fixed, by decision

### R-1 Password reset has no mail transport — *Medium*

`PASSWORD_RESET_DELIVERY` supports `log` and `none`. Neither sends email, and under `none` no token is minted at all. The endpoint now reports honestly instead of returning a link that cannot be delivered, but **account recovery is still non-functional for real users** until an SMTP or webhook transport is configured. This is a deployment task, not a code task, and it is the one Part I finding that is not fully closed.

### R-2 The rate limiter trusts `X-Forwarded-For` from any client — *Medium (security)*

**Location.** `app/core/rate_limit.py:45-53`.

Any client can set the header and receive a fresh rate-limit bucket by rotating it, so `login`, `register`, `forgot-password`, `feedback` and `chatbot` limits are all bypassable by an attacker who knows this. Fixing it properly requires knowing the deployment's proxy topology — trusting one hop is only correct if something overwrites the header — so the choice is documented rather than guessed.

**Interim requirement:** front the app with a proxy that overwrites `X-Forwarded-For`, and do not expose it directly. The behaviour is pinned by `test_stress.py::test_rate_limiter_is_bypassed_by_rotating_forwarded_for`, so fixing it will fail that test and force this entry to be revisited.

### R-3 The connection pool is small and sheds load without retry — *Low (operational)*

**Location.** `app/core/config.py:44-46` (`db_pool_size = 5`, `db_pool_timeout = 30`).

`build_engine` reserves a small pool, which is correct for serverless Postgres. The consequence is that a burst above the pool size is answered with `503 DATABASE_ERROR`. This is graceful — the app does not hang and never leaks a `500` — but it is untuned: `db_pool_size` and `db_pool_timeout` were never load-tested against real traffic, and no client-side retry is documented. `test_stress.py` asserts the 200/503 contract so the behaviour is pinned; the numbers are not yet justified by evidence.

## 11. Verification

Measured on the remediated tree against a disposable database, never the deployment database.

| Suite | Result |
|---|---|
| `tests/test_regressions.py` | **36 passed**, run twice |
| `tests/test_functional.py` | **59 passed** |
| `tests/test_search_path.py` | **4 passed** |
| `tests/test_stress.py` | **12 passed** (3 heavy cases opt-in via `RUN_STRESS=1`, verified separately) |
| `tests/test_logging_contract.py` | **2 passed** |
| OpenAPI generation | succeeds, 49 paths, public/admin feedback schemas distinct |

### Test isolation

Database tests run against a **throwaway database**, not a per-test schema. `TEST_DATABASE_URL` supplies a server; the fixture creates `TEST_DB_NAME` (`fanhub_test` by default), migrates it, and drops it, terminating connections first. It recreates the target even after a crashed run, and never migrates or writes to the database named in `TEST_DATABASE_URL`.

Schemas were tried first and abandoned for the reason given in N-4: on a pooled endpoint a schema-scoped `search_path` can leak onto the next connection, and schema-local native enums collide with `public`.

Three defects in the test harness itself were found and fixed during this work, and are recorded because each silently invalidated earlier results: importing `tests.conftest` twice created two schema names and clobbered the shared environment (fixed by making `tests` a package and moving shared data to `support.py`); `pytest-asyncio` 0.24 applies its own auto-mode marker *after* the conftest marker, so the intended session loop was not applied; and the pool could not be torn down per test because a pooled connection is bound to the loop that opened it.

### Operational note

Verification mutated the deployment database before the disposable-database harness existed: submissions, chatbot and feedback rows, user display preferences, and the administrator's password were changed. **Rotate the administrator password and delete the two `audit.*@fanhubplus.dev` accounts**, whose password appeared in an earlier draft of this report and has been redacted above. The full residue list is Part I §2.

---

*Part II added 2026-09-27. N-1 through N-5 are fixed and regression-covered; R-1, R-2 and R-3 are open by decision.*
