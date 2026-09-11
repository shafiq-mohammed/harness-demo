"""Tests for T-002: POST /links creates a short link.

Acceptance criteria live in tasks/T-002.md. Interface in docs/SPEC.md sections 6, 7, 8 and 10.
Every assertion goes through the public HTTP surface: POST /links (plus GET /healthz for AC5).
"""

import re
from datetime import datetime

import pytest
from conftest import HEADERS, T0
from fastapi.testclient import TestClient

from app.clock import FixedClock
from app.main import create_app
from app.settings import Settings

CODE_PATTERN = re.compile(r"^[A-Za-z0-9]{8}$")

VALID_URL = "https://example.com/a/b?c=1"


def _long_url(total_length: int) -> str:
    """Build a syntactically valid https URL of exactly `total_length` characters."""
    prefix = "https://example.com/"
    return prefix + ("a" * (total_length - len(prefix)))


# --------------------------------------------------------------------------------------
# AC1: valid key + valid body -> 201 LinkOut with an 8 char code and created_at == T0
# --------------------------------------------------------------------------------------


def test_ac1_create_link_returns_201_link_out(client: TestClient) -> None:
    """Happy path: the documented request body yields the documented 201 envelope."""
    response = client.post("/links", headers=HEADERS, json={"url": VALID_URL})

    assert response.status_code == 201
    body = response.json()
    assert CODE_PATTERN.match(body["code"]), body["code"]
    assert body["url"] == VALID_URL
    assert body["expires_at"] is None
    assert body["hit_count"] == 0


def test_ac1_created_at_equals_clock_now(client: TestClient) -> None:
    """created_at is the injected clock's now, compared as an aware datetime."""
    response = client.post("/links", headers=HEADERS, json={"url": VALID_URL})

    assert response.status_code == 201
    created_at = datetime.fromisoformat(response.json()["created_at"])
    assert created_at.tzinfo is not None
    assert created_at == T0


def test_ac1_url_with_query_and_fragment_is_stored_verbatim(client: TestClient) -> None:
    """Edge: no normalisation. Query, fragment, casing and trailing slash survive untouched."""
    url = "https://Example.com:8443/path/with%20space/?b=2&a=1#frag-ment"

    response = client.post("/links", headers=HEADERS, json={"url": url})

    assert response.status_code == 201
    assert response.json()["url"] == url


# --------------------------------------------------------------------------------------
# AC2: missing or unknown X-API-Key -> 401 unauthorized envelope
# --------------------------------------------------------------------------------------


def test_ac2_missing_api_key_header_returns_401(client: TestClient) -> None:
    response = client.post("/links", json={"url": VALID_URL})

    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "unauthorized"
    assert isinstance(body["message"], str)
    assert body["message"] != ""


def test_ac2_wrong_api_key_returns_401(client: TestClient) -> None:
    response = client.post("/links", headers={"X-API-Key": "wrong"}, json={"url": VALID_URL})

    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "unauthorized"
    assert body["message"] != ""


def test_ac2_empty_api_key_header_returns_401(client: TestClient) -> None:
    """Edge: the header is present but empty, which is not a configured key."""
    response = client.post("/links", headers={"X-API-Key": ""}, json={"url": VALID_URL})

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_ac2_unauthorized_takes_precedence_over_invalid_body(client: TestClient) -> None:
    """Error path: an unauthenticated caller learns nothing about body validity."""
    response = client.post("/links", json={"url": "ftp://example.com"})

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


# --------------------------------------------------------------------------------------
# AC3: bad url values -> 422 validation_error with details, never 500
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("ftp_scheme", {"url": "ftp://example.com"}),
        ("no_scheme", {"url": "not a url"}),
        ("no_host", {"url": "http://"}),
        ("empty_string", {"url": ""}),
        ("missing_field", {}),
        ("too_long", {"url": _long_url(2049)}),
        ("null_url", {"url": None}),
    ],
)
def test_ac3_invalid_url_returns_validation_error(
    client: TestClient, label: str, payload: dict
) -> None:
    response = client.post("/links", headers=HEADERS, json=payload)

    assert response.status_code == 422, f"{label}: {response.status_code} {response.text}"
    body = response.json()
    assert body["error"] == "validation_error"
    assert isinstance(body["details"], list)
    assert body["details"] != []


def test_ac3_url_of_exactly_2048_chars_is_accepted(client: TestClient) -> None:
    """Edge: the boundary length is valid, only 2049 and above is rejected."""
    url = _long_url(2048)
    assert len(url) == 2048

    response = client.post("/links", headers=HEADERS, json={"url": url})

    assert response.status_code == 201
    assert response.json()["url"] == url


def test_ac3_non_json_body_returns_422_not_500(client: TestClient) -> None:
    """Error path: an unparseable body is a client error in the envelope, never a 500."""
    response = client.post(
        "/links",
        headers={**HEADERS, "Content-Type": "application/json"},
        content="not json",
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"
    assert isinstance(body["details"], list)


# --------------------------------------------------------------------------------------
# AC4: repeated creates of the same URL get distinct codes
# --------------------------------------------------------------------------------------


def test_ac4_two_links_for_same_url_get_distinct_codes(client: TestClient) -> None:
    first = client.post("/links", headers=HEADERS, json={"url": VALID_URL})
    second = client.post("/links", headers=HEADERS, json={"url": VALID_URL})

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["code"] != second.json()["code"]


def test_ac4_twenty_creates_all_return_distinct_codes(client: TestClient) -> None:
    """Edge: many creates of the same URL never collide in the response."""
    codes = []
    for _ in range(20):
        response = client.post("/links", headers=HEADERS, json={"url": VALID_URL})
        assert response.status_code == 201
        code = response.json()["code"]
        assert CODE_PATTERN.match(code), code
        codes.append(code)

    assert len(set(codes)) == 20


# --------------------------------------------------------------------------------------
# AC5: no keys configured -> every POST /links is 401, health stays open
# --------------------------------------------------------------------------------------


def test_ac5_no_keys_configured_rejects_valid_key(repo, clock: FixedClock) -> None:
    """Safe default: an app built with Settings() authorises nobody."""
    app = create_app(settings=Settings(), repo=repo, clock=clock)

    with TestClient(app, follow_redirects=False) as keyless_client:
        response = keyless_client.post("/links", headers=HEADERS, json={"url": VALID_URL})

    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "unauthorized"
    assert body["message"] != ""


def test_ac5_no_keys_configured_healthz_still_ok(repo, clock: FixedClock) -> None:
    """Edge: /healthz needs no key, so it is unaffected by an empty key set."""
    app = create_app(settings=Settings(), repo=repo, clock=clock)

    with TestClient(app, follow_redirects=False) as keyless_client:
        response = keyless_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
