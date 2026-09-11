# SPEC: internal link shortener

Source: docs/REQUIREMENTS.md. This document is the contract that tests are written against before any
code exists. Tickets in tasks/ copy their Interface section from here verbatim.

## 1. Goal

A small FastAPI service where an engineer holding an API key can turn a long http(s) URL into a short code,
`GET /<code>` redirects to the original URL, links may expire, every successful redirect is counted, and the
set of links can be listed with paging.

## 2. Non-goals (out of scope for every ticket below)

- Custom aliases, editing or deleting links, per-key ownership, rate limiting.
- Persistent storage. Only the in-memory repository is built. DynamoDB is a later implementation of the
  same `LinkRepository` interface and is not part of these tickets.
- A web UI, analytics beyond a per-link hit count, geo/referrer data.
- Dockerfile and deployment config (the service is a plain `uvicorn app.main:app` process; a Dockerfile is
  a follow-up).
- Key management (rotation, hashing, issuing). Keys are a static list from an environment variable.
- HEAD/POST handling on the redirect route, favicon, robots.

## 3. Assumptions (requirements were vague here)

A1. Authentication is a static API key passed in the `X-API-Key` header. Valid keys come from the
    environment variable `LINKS_API_KEYS` (comma-separated). With no keys configured every protected
    request is rejected with 401 (safe default). Any valid key grants full access; there is no ownership.
A2. Creating a link and reading/listing link metadata require the API key. Following a redirect
    (`GET /{code}`) does NOT require a key, because links are pasted into docs and Slack and opened in
    browsers.
A3. Short codes are 8 characters from `[A-Za-z0-9]`, generated with `secrets`. Collisions are retried up
    to 5 times; the space is 62^8 (about 2.2e14) so exhaustion is treated as unreachable. Changed from 7 to 8 at human review of PR #2.
A4. A "valid http(s) URL" is a string of at most 2048 characters whose scheme is `http` or `https` and
    which has a non-empty host. The URL is stored and redirected to verbatim (no normalisation, no
    trailing-slash rewriting).
A5. Expiry is an absolute, timezone-aware ISO 8601 `expires_at` timestamp supplied at creation. It must
    be strictly in the future at creation time. A link is expired when `expires_at <= now`. Expired
    links answer 410 Gone and are still visible in metadata and listing (no deletion).
A6. "How often each link has been used" = an integer `hit_count` incremented once per successful
    redirect (302). 404 and 410 responses do not count.
A7. Redirects use 302 Found so browsers do not cache them (301 would bypass expiry and hit counting).
A8. Listing is cursor-paged (DynamoDB has no offset), ordered by `code` ascending. `limit` is 1..100,
    default 20. `cursor` is opaque to clients: pass back `next_cursor` from the previous page.
A9. Time is injected through a `Clock` so tests can control expiry deterministically.
A10. The service returns a `short_url` only if a base URL is configured; this is NOT built. Clients
    build `<host>/<code>` themselves. Responses return `code` only.

## 4. Stack and conventions

- Python 3.11+, FastAPI, pydantic v2, pytest + httpx `TestClient`, ruff (`E,F,I,B,UP`, line length 100).
- Commands: `python -m pytest -q`; `ruff check . && ruff format .`; `uvicorn app.main:app --reload`.
- `src/` is on `pythonpath` (pyproject), so imports are `from app.main import create_app`.
- Use `datetime.UTC` (ruff UP rule), timezone-aware datetimes everywhere. Never naive datetimes in models.
- Regular hyphens only in docs and code comments; no em-dashes.
- One ticket per branch `feat/T-00X-slug`, one test file per ticket `tests/test_T-00X_<slug>.py`.

## 5. Module layout under src/app/

    src/app/__init__.py       (exists, empty)
    src/app/main.py           create_app() factory, module-level `app`, route registration order
    src/app/settings.py       Settings (api_keys), Settings.from_env()
    src/app/clock.py          Clock protocol, SystemClock, FixedClock
    src/app/models.py         Link dataclass
    src/app/repository.py     LinkRepository protocol, InMemoryLinkRepository, repository exceptions
    src/app/codes.py          generate_code()
    src/app/errors.py         ApiError, error envelope, register_error_handlers(app)
    src/app/auth.py           require_api_key dependency
    src/app/schemas.py        CreateLinkRequest, LinkOut, LinkPage (pydantic)
    src/app/routes/__init__.py
    src/app/routes/links.py   /links endpoints (create, get, list)
    src/app/routes/redirect.py  GET /{code}
    src/app/routes/health.py  GET /healthz

Route registration order in `create_app` matters: `/healthz` and `/links...` routers are included BEFORE
the catch-all `/{code}` router so `GET /links` is never treated as a code.

## 6. Data model and storage

```python
# src/app/models.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Link:
    code: str
    url: str
    created_at: datetime            # tz-aware UTC
    expires_at: datetime | None = None
    hit_count: int = 0

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and self.expires_at <= now
```

```python
# src/app/repository.py
from typing import Protocol

class CodeAlreadyExistsError(Exception): ...
class LinkNotFoundError(Exception): ...

class LinkRepository(Protocol):
    def add(self, link: Link) -> None:
        """Insert. Raises CodeAlreadyExistsError if link.code exists."""
    def get(self, code: str) -> Link | None: ...
    # added in T-003
    def increment_hits(self, code: str) -> None:
        """Atomically add 1 to hit_count. Raises LinkNotFoundError if unknown."""
    # added in T-005
    def list(self, *, limit: int, after_code: str | None = None) -> list[Link]:
        """Up to `limit` links with code > after_code (or from the start), ordered by code ascending."""

class InMemoryLinkRepository:
    """Dict-backed implementation of LinkRepository. Not thread-safe; fine for a single uvicorn worker."""
    def __init__(self) -> None: ...
```

DynamoDB mapping (future, not built): table keyed by `code`; `increment_hits` = `UpdateItem ADD hit_count 1`
with a condition expression that the item exists; `list` = `Scan` with `ExclusiveStartKey`. Nothing above
the repository knows about this.

## 7. Cross-cutting interfaces (settings, clock, errors and the factory are built in T-001; auth and the
repository in T-002; all reused by every later ticket)

```python
# src/app/settings.py
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Settings:
    api_keys: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_env(cls) -> "Settings":
        """Reads LINKS_API_KEYS (comma-separated, whitespace stripped, empty entries dropped)."""
```

```python
# src/app/clock.py
from datetime import UTC, datetime
from typing import Protocol

class Clock(Protocol):
    def now(self) -> datetime: ...          # always tz-aware UTC

class SystemClock:
    def now(self) -> datetime: ...          # datetime.now(UTC)

class FixedClock:
    def __init__(self, now: datetime) -> None: ...   # raises ValueError if naive
    def now(self) -> datetime: ...
    def set(self, now: datetime) -> None: ...
    def advance(self, seconds: float) -> None: ...
```

```python
# src/app/errors.py
class ApiError(Exception):
    def __init__(self, status_code: int, error: str, message: str) -> None: ...

def register_error_handlers(app: FastAPI) -> None:
    """ApiError -> its status + envelope. Starlette HTTPException (404 unknown route, 405) -> envelope
    with error 'not_found' / 'method_not_allowed'. RequestValidationError -> 422 'validation_error'."""
```

Error envelope (every 4xx body, `Content-Type: application/json`):

```json
{"error": "<snake_case_code>", "message": "<human readable>"}
```

For `validation_error` an extra `"details": [{"loc": [...], "msg": "..."}]` list is included.
Error codes used: `unauthorized` (401), `not_found` (404), `method_not_allowed` (405),
`link_expired` (410), `validation_error` (422). The service never returns 500 for bad input.

```python
# src/app/auth.py
API_KEY_HEADER = "X-API-Key"

def require_api_key(request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    """Returns the key. Raises ApiError(401, 'unauthorized', ...) if header missing or not in
    request.app.state.settings.api_keys. Comparison uses secrets.compare_digest per key."""
```

```python
# src/app/main.py
def create_app(
    settings: Settings | None = None,        # default Settings.from_env()
    repo: LinkRepository | None = None,      # default InMemoryLinkRepository()   (added in T-002)
    clock: Clock | None = None,              # default SystemClock()
) -> FastAPI:
    """Stores the three on app.state.settings / app.state.repo / app.state.clock, registers error
    handlers and routers (health, links, then redirect). T-001 ships create_app(settings, clock)
    only; T-002 inserts the repo parameter. Callers always pass keyword arguments."""

app = create_app()
```

Route handlers read dependencies from `request.app.state`. Nothing is a module-level singleton, so each
test gets an isolated app.

## 8. Public interface per ticket

### T-001: App skeleton and health check

Modules: settings.py, clock.py, errors.py, routes/__init__.py, routes/health.py, main.py
(`create_app(settings, clock)`). No auth, no links, no repository.

Endpoints:

- `GET /healthz` -> 200 `{"status": "ok"}`. No auth.
- Any unknown path -> 404 `not_found` envelope; wrong method on a known path -> 405
  `method_not_allowed` envelope. Both JSON, never HTML.

Also public: `Settings.from_env()` parsing of `LINKS_API_KEYS`, and `FixedClock` construction /
`set` / `advance` (naive datetimes raise `ValueError`).

### T-002: Create a short link

Modules: models.py, repository.py (add, get), codes.py, auth.py, schemas.py (CreateLinkRequest,
LinkOut), routes/links.py (POST only), main.py (+repo parameter).

```python
# src/app/codes.py
CODE_ALPHABET = string.ascii_letters + string.digits   # 62 chars
CODE_LENGTH = 8
def generate_code(length: int = CODE_LENGTH) -> str: ...   # secrets.choice per char
```

```python
# src/app/schemas.py
class CreateLinkRequest(BaseModel):
    url: str            # max_length=2048; validator: scheme in {http, https} and non-empty host,
                        # else ValueError("url must be an absolute http or https URL")

class LinkOut(BaseModel):
    code: str
    url: str
    created_at: datetime
    expires_at: datetime | None     # always null until T-004
    hit_count: int                  # always 0 until T-003
```

Endpoints:

- `POST /links` (auth required)
  - Request JSON: `{"url": "https://example.com/some/long/path"}`
  - 201 Created, body = `LinkOut`, e.g.
    `{"code": "aB3dE9x", "url": "https://example.com/some/long/path", "created_at": "2026-01-01T00:00:00Z", "expires_at": null, "hit_count": 0}`
  - `created_at` = `clock.now()`.
  - 401 `unauthorized` if `X-API-Key` missing, unknown, or no keys are configured.
  - 422 `validation_error` if body is not JSON, `url` is missing, empty, not http(s), has no host, or
    exceeds 2048 chars.
  - Code generation: loop up to 5 times calling `generate_code()` and `repo.add()`; retry on
    `CodeAlreadyExistsError`.

### T-003: Redirect and hit counting

Modules: repository.py (+increment_hits), routes/redirect.py, routes/links.py (+GET /links/{code}), main.py
(include redirect router last).

```python
# src/app/repository.py (added)
def increment_hits(self, code: str) -> None: ...   # raises LinkNotFoundError
```

Endpoints:

- `GET /{code}` (no auth)
  - 302 Found with `Location: <link.url>` verbatim, empty body. Then `repo.increment_hits(code)`.
  - 404 `not_found` if no link with that code. Nothing is counted.
  - Reserved paths `/healthz` and `/links` are never treated as codes (router order).
- `GET /links/{code}` (auth required)
  - 200 body = `LinkOut` with the current `hit_count`.
  - 401 `unauthorized`, 404 `not_found`.

### T-004: Link expiry

Modules: schemas.py (+expires_at on CreateLinkRequest), routes/links.py (validation against clock),
routes/redirect.py (410 branch).

```python
# src/app/schemas.py (changed)
class CreateLinkRequest(BaseModel):
    url: str
    expires_at: datetime | None = None    # validator: if given, must be tz-aware, else
                                          # ValueError("expires_at must include a timezone offset")
```

Endpoints:

- `POST /links` (changed)
  - Request JSON: `{"url": "...", "expires_at": "2026-01-02T00:00:00+00:00"}` (`expires_at` optional).
  - 201 with `expires_at` echoed (serialised in UTC, e.g. `"2026-01-02T00:00:00Z"`).
  - 422 `validation_error` if `expires_at` is naive (no offset), unparseable, or not strictly greater
    than `clock.now()` (message: `"expires_at must be in the future"`).
- `GET /{code}` (changed)
  - 410 Gone `{"error": "link_expired", "message": "..."}` if `link.is_expired(clock.now())`.
    `hit_count` is NOT incremented.
  - Otherwise unchanged (302 + increment).
- `GET /links/{code}` unchanged: expired links remain readable, `expires_at` populated.

### T-005: List links with paging

Modules: repository.py (+list), schemas.py (+LinkPage), routes/links.py (+GET /links).

```python
# src/app/repository.py (added)
def list(self, *, limit: int, after_code: str | None = None) -> list[Link]: ...

# src/app/schemas.py (added)
class LinkPage(BaseModel):
    items: list[LinkOut]
    next_cursor: str | None
```

Endpoints:

- `GET /links?limit=20&cursor=<opaque>` (auth required)
  - `limit`: int, `ge=1`, `le=100`, default 20. `cursor`: optional string.
  - 200 `{"items": [LinkOut, ...], "next_cursor": "<string or null>"}`
  - `items` ordered by `code` ascending. `next_cursor` is null if and only if no links remain after
    the last item; otherwise it is the value to pass as `cursor` to fetch the next page. Pages never
    overlap or skip links. An unknown cursor value simply starts after that value (keyset semantics).
  - Implementation hint: call `repo.list(limit=limit + 1, after_code=cursor)`; if more than `limit`
    results, truncate and set `next_cursor = items[-1].code`.
  - 401 `unauthorized`; 422 `validation_error` for `limit` outside 1..100 or non-integer.

## 9. Error handling conventions

- Raise `ApiError(status, code, message)` from routes and dependencies; never `HTTPException` directly.
- Never let a pydantic or parsing error escape as 500; `register_error_handlers` converts everything
  client-caused into the envelope. Repository exceptions are caught in routes and mapped to 404
  (LinkNotFoundError) or retried (CodeAlreadyExistsError).
- 5xx responses are reserved for genuine bugs; a test that sees a 500 is a failing test.

## 10. Testing conventions

- File per ticket: `tests/test_T-001_health.py`, `tests/test_T-002_create_link.py`,
  `tests/test_T-003_redirect_hits.py`, `tests/test_T-004_expiry.py`, `tests/test_T-005_list_links.py`.
  One test per AC minimum, named
  `test_ac<N>_<what>`.
- Shared fixtures live in `tests/conftest.py`. T-001 creates it with `T0`, `clock` and a `client` built
  from `create_app(settings=Settings(), clock=clock)`. T-002 adds `API_KEY`, `HEADERS`, the `repo`
  fixture and passes the key and repo to `create_app`. Final form, used from T-002 onwards:

```python
# tests/conftest.py
from datetime import UTC, datetime
import pytest
from fastapi.testclient import TestClient
from app.clock import FixedClock
from app.main import create_app
from app.repository import InMemoryLinkRepository
from app.settings import Settings

API_KEY = "test-key"
HEADERS = {"X-API-Key": API_KEY}
T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(T0)

@pytest.fixture
def repo() -> InMemoryLinkRepository:
    return InMemoryLinkRepository()

@pytest.fixture
def client(repo, clock) -> TestClient:
    app = create_app(settings=Settings(api_keys=frozenset({API_KEY})), repo=repo, clock=clock)
    return TestClient(app, follow_redirects=False)
```

- Always construct `TestClient(..., follow_redirects=False)`; redirect tests assert on the 302 and the
  `Location` header, never on the target.
- Time: never `sleep`; use `clock.advance(seconds)` or `clock.set(datetime)` then re-request.
- Datetimes in responses are parsed with `datetime.fromisoformat(...)` (Python 3.11 accepts `Z`) and
  compared as aware datetimes, not as strings.
- Tests assert status codes, bodies, headers, and state observable through other endpoints
  (e.g. hit_count via `GET /links/{code}`). They do not import private helpers or inspect the repo dict.
- Auth failure tests send no header and a wrong header; both expect 401 with `error == "unauthorized"`.
