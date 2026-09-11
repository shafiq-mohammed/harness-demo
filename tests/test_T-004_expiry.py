"""Tests for T-004: link expiry.

Acceptance criteria live in tasks/T-004.md. Interface in docs/SPEC.md sections 3 (A5), 6, 7,
8 ("T-004"), 9 and 10.

Links are only ever created through POST /links, and `expires_at` / `hit_count` are only ever
observed through GET /links/{code}; the repository dict is never inspected. Time moves only
through the injected FixedClock (`clock.set` / `clock.advance`), never by sleeping.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from conftest import HEADERS, T0
from fastapi.testclient import TestClient

from app.clock import FixedClock

URL_A = "https://example.com/x?y=1#z"
URL_B = "https://example.org/other/path"

IN_ONE_HOUR = T0 + timedelta(hours=1)
TEN_YEARS = 10 * 365 * 24 * 3600


def _create(client: TestClient, url: str, expires_at: str | None = ...) -> dict:  # type: ignore[assignment]
    """Create a link through the public API and return the 201 body.

    `expires_at` is omitted from the body entirely unless a value is passed (including None,
    which is sent as an explicit JSON null).
    """
    payload: dict[str, object] = {"url": url}
    if expires_at is not ...:
        payload["expires_at"] = expires_at
    response = client.post("/links", headers=HEADERS, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _read(client: TestClient, code: str) -> dict:
    """Read a link back through GET /links/{code}."""
    response = client.get(f"/links/{code}", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def _aware(value: str) -> datetime:
    """Parse an ISO 8601 timestamp from a response and require it to be tz-aware."""
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"{value!r} is not timezone aware"
    return parsed


# --------------------------------------------------------------------------------------
# AC1: POST /links accepts an optional, tz-aware, future expires_at and echoes it
# --------------------------------------------------------------------------------------


def test_ac1_create_with_future_expires_at_echoes_the_instant(client: TestClient) -> None:
    """Happy path: a +00:00 timestamp one hour ahead is stored and echoed unchanged."""
    body = _create(client, URL_A, IN_ONE_HOUR.isoformat())

    assert body["url"] == URL_A
    assert body["expires_at"] is not None
    assert _aware(body["expires_at"]) == IN_ONE_HOUR

    stored = _read(client, body["code"])
    assert stored["expires_at"] is not None
    assert _aware(stored["expires_at"]) == IN_ONE_HOUR


def test_ac1_create_without_expires_at_returns_null_expiry(client: TestClient) -> None:
    """A link created with no expiry reads back as null, while one with an expiry does not."""
    without = _create(client, URL_A)
    with_expiry = _create(client, URL_B, IN_ONE_HOUR.isoformat())

    assert without["expires_at"] is None
    assert _read(client, without["code"])["expires_at"] is None

    assert with_expiry["expires_at"] is not None
    assert _aware(with_expiry["expires_at"]) == IN_ONE_HOUR


def test_ac1_non_utc_offset_is_accepted_as_the_same_instant(client: TestClient) -> None:
    """Edge: an offset other than +00:00 is accepted and echoed as the equivalent UTC instant."""
    plus_two = timezone(timedelta(hours=2))
    same_instant = IN_ONE_HOUR.astimezone(plus_two)
    assert same_instant.isoformat().endswith("+02:00")

    body = _create(client, URL_A, same_instant.isoformat())

    assert body["expires_at"] is not None
    assert _aware(body["expires_at"]) == IN_ONE_HOUR


# --------------------------------------------------------------------------------------
# AC2: invalid expires_at values are 422 validation_error, never 500
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("equal_to_now", T0.isoformat()),
        ("one_second_in_the_past", (T0 - timedelta(seconds=1)).isoformat()),
        ("naive_timestamp", "2026-01-01T13:00:00"),
        ("unparseable", "not-a-date"),
    ],
)
def test_ac2_invalid_expires_at_returns_422(client: TestClient, label: str, value: str) -> None:
    """Error path: past, boundary, naive and unparseable expiries are all client errors."""
    response = client.post("/links", headers=HEADERS, json={"url": URL_A, "expires_at": value})

    assert response.status_code == 422, f"{label}: {response.status_code} {response.text}"
    body = response.json()
    assert body["error"] == "validation_error"
    assert isinstance(body["message"], str)
    assert body["message"] != ""
    assert isinstance(body["details"], list)
    assert body["details"] != []


def test_ac2_expires_at_equal_to_now_reports_the_future_requirement(client: TestClient) -> None:
    """The boundary value is rejected with the documented message (SPEC section 8, T-004)."""
    response = client.post(
        "/links", headers=HEADERS, json={"url": URL_A, "expires_at": T0.isoformat()}
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"] == "validation_error"
    assert "expires_at must be in the future" in json.dumps(response.json())


def test_ac2_explicit_null_expires_at_is_accepted(client: TestClient) -> None:
    """Edge: an explicit JSON null is a valid absent expiry, unlike a malformed value."""
    body = _create(client, URL_A, None)
    assert body["expires_at"] is None

    rejected = client.post(
        "/links", headers=HEADERS, json={"url": URL_A, "expires_at": "not-a-date"}
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"] == "validation_error"


# --------------------------------------------------------------------------------------
# AC3: before the expiry the link redirects and counts as usual
# --------------------------------------------------------------------------------------


def test_ac3_unexpired_link_redirects_and_counts(client: TestClient) -> None:
    """Happy path: at T0 a link expiring at T0 + 1h still redirects and reaches hit_count 1."""
    created = _create(client, URL_A, IN_ONE_HOUR.isoformat())
    code = created["code"]

    response = client.get(f"/{code}")

    assert response.status_code == 302
    assert response.headers["location"] == URL_A

    stored = _read(client, code)
    assert stored["hit_count"] == 1
    assert stored["expires_at"] is not None
    assert _aware(stored["expires_at"]) == IN_ONE_HOUR


def test_ac3_one_minute_before_expiry_still_redirects(
    client: TestClient, clock: FixedClock
) -> None:
    """Edge: at T0 + 59 minutes the link is not yet expired."""
    code = _create(client, URL_A, IN_ONE_HOUR.isoformat())["code"]

    clock.set(T0 + timedelta(minutes=59))
    response = client.get(f"/{code}")

    assert response.status_code == 302
    assert response.headers["location"] == URL_A

    stored = _read(client, code)
    assert stored["hit_count"] == 1
    assert stored["expires_at"] is not None
    assert _aware(stored["expires_at"]) == IN_ONE_HOUR


# --------------------------------------------------------------------------------------
# AC4: at and after expires_at the redirect is 410 and nothing is counted
# --------------------------------------------------------------------------------------


def test_ac4_at_expiry_redirect_returns_410(client: TestClient, clock: FixedClock) -> None:
    """Boundary: expires_at <= now is expired, so exactly T0 + 1h is already gone."""
    code = _create(client, URL_A, IN_ONE_HOUR.isoformat())["code"]
    assert client.get(f"/{code}").status_code == 302

    clock.set(IN_ONE_HOUR)
    response = client.get(f"/{code}")

    assert response.status_code == 410
    body = response.json()
    assert body["error"] == "link_expired"
    assert isinstance(body["message"], str)
    assert body["message"] != ""
    assert "location" not in response.headers


def test_ac4_after_expiry_redirect_returns_410(client: TestClient, clock: FixedClock) -> None:
    """Edge: one second past the expiry is 410 too."""
    code = _create(client, URL_A, IN_ONE_HOUR.isoformat())["code"]

    clock.set(IN_ONE_HOUR + timedelta(seconds=1))
    response = client.get(f"/{code}")

    assert response.status_code == 410
    assert response.json()["error"] == "link_expired"


def test_ac4_expired_link_keeps_its_hit_count_and_expiry(
    client: TestClient, clock: FixedClock
) -> None:
    """Error path: a 410 does not count, and the expired link stays readable unchanged."""
    code = _create(client, URL_A, IN_ONE_HOUR.isoformat())["code"]
    assert client.get(f"/{code}").status_code == 302
    assert _read(client, code)["hit_count"] == 1

    clock.set(IN_ONE_HOUR)
    assert client.get(f"/{code}").status_code == 410
    assert client.get(f"/{code}").status_code == 410

    stored = _read(client, code)
    assert stored["hit_count"] == 1
    assert stored["url"] == URL_A
    assert stored["expires_at"] is not None
    assert _aware(stored["expires_at"]) == IN_ONE_HOUR


# --------------------------------------------------------------------------------------
# AC5: a link created without an expiry never expires
# --------------------------------------------------------------------------------------


def test_ac5_link_without_expiry_still_redirects_after_ten_years(
    client: TestClient, clock: FixedClock
) -> None:
    """Happy path: only links that carry an expiry can go 410, however far the clock moves."""
    forever = _create(client, URL_A)["code"]
    expiring = _create(client, URL_B, IN_ONE_HOUR.isoformat())["code"]

    clock.advance(TEN_YEARS)

    response = client.get(f"/{forever}")
    assert response.status_code == 302
    assert response.headers["location"] == URL_A
    assert _read(client, forever)["hit_count"] == 1

    assert client.get(f"/{expiring}").status_code == 410


def test_ac5_link_without_expiry_reads_back_null_after_ten_years(
    client: TestClient, clock: FixedClock
) -> None:
    """Edge: metadata for a never-expiring link keeps expires_at null as the clock moves."""
    forever = _create(client, URL_A)["code"]
    expiring = _create(client, URL_B, IN_ONE_HOUR.isoformat())["code"]

    clock.advance(TEN_YEARS)

    assert _read(client, forever)["expires_at"] is None

    expiring_body = _read(client, expiring)
    assert expiring_body["expires_at"] is not None
    assert _aware(expiring_body["expires_at"]) == IN_ONE_HOUR
