"""Tests for T-001: app skeleton, health check and the JSON error envelope.

Acceptance criteria live in tasks/T-001.md. Interface in docs/SPEC.md sections 7, 8 and 10.
"""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import T0
from fastapi.testclient import TestClient

from app.clock import FixedClock
from app.main import create_app
from app.settings import Settings

# --------------------------------------------------------------------------------------
# AC1: GET /healthz -> 200 {"status": "ok"}
# --------------------------------------------------------------------------------------


def test_ac1_healthz_returns_ok(client: TestClient) -> None:
    """Happy path: no headers at all, 200 with exactly {"status": "ok"}."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ac1_healthz_ignores_arbitrary_api_key_header(client: TestClient) -> None:
    """Edge: /healthz is unauthenticated, an arbitrary X-API-Key changes nothing."""
    response = client.get("/healthz", headers={"X-API-Key": "not-a-configured-key"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --------------------------------------------------------------------------------------
# AC2: unknown path -> 404 not_found envelope, JSON
# --------------------------------------------------------------------------------------


def test_ac2_unknown_path_returns_not_found_envelope(client: TestClient) -> None:
    response = client.get("/no-such-route")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["error"] == "not_found"
    assert isinstance(body["message"], str)
    assert body["message"] != ""


def test_ac2_nested_unknown_path_returns_not_found_envelope(client: TestClient) -> None:
    """Edge: a deeply nested unknown path gets the same envelope, not a framework page."""
    response = client.get("/a/b/c")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["error"] == "not_found"
    assert isinstance(body["message"], str)
    assert body["message"] != ""


def test_ac2_not_found_body_is_json_not_html_or_text(client: TestClient) -> None:
    """Error path: the default Starlette plain-text/HTML 404 must never leak through."""
    response = client.get("/no-such-route")

    assert response.status_code == 404
    assert "text/html" not in response.headers["content-type"]
    assert "text/plain" not in response.headers["content-type"]
    assert "<html" not in response.text.lower()
    assert response.json()["error"] == "not_found"


# --------------------------------------------------------------------------------------
# AC3: wrong method on a known path -> 405 method_not_allowed envelope
# --------------------------------------------------------------------------------------


def test_ac3_post_healthz_returns_method_not_allowed(client: TestClient) -> None:
    response = client.post("/healthz")

    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["error"] == "method_not_allowed"
    assert isinstance(body["message"], str)
    assert body["message"] != ""


def test_ac3_delete_healthz_returns_method_not_allowed(client: TestClient) -> None:
    """Edge: any other verb on the known path is also a 405 envelope."""
    response = client.delete("/healthz")

    assert response.status_code == 405
    body = response.json()
    assert body["error"] == "method_not_allowed"
    assert body["message"] != ""


# --------------------------------------------------------------------------------------
# AC4: Settings.from_env() parsing of LINKS_API_KEYS
# --------------------------------------------------------------------------------------


def test_ac4_from_env_parses_comma_separated_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINKS_API_KEYS", " a, b ,,c ")

    settings = Settings.from_env()

    assert settings.api_keys == frozenset({"a", "b", "c"})


def test_ac4_from_env_unset_returns_empty_frozenset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINKS_API_KEYS", raising=False)

    settings = Settings.from_env()

    assert settings.api_keys == frozenset()


@pytest.mark.parametrize("raw", [",", "", "   ", " , , "])
def test_ac4_from_env_separator_only_value_yields_empty_frozenset(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """Edge: values that contain no key at all drop every empty entry."""
    monkeypatch.setenv("LINKS_API_KEYS", raw)

    settings = Settings.from_env()

    assert settings.api_keys == frozenset()


# --------------------------------------------------------------------------------------
# AC5: FixedClock advance / set, naive datetimes rejected, defaults resolve
# --------------------------------------------------------------------------------------


def test_ac5_fixed_clock_advance_moves_now_forward() -> None:
    clock = FixedClock(T0)

    clock.advance(60)

    assert clock.now() == T0 + timedelta(seconds=60)


def test_ac5_fixed_clock_set_replaces_now() -> None:
    clock = FixedClock(T0)
    later = datetime(2027, 6, 5, 4, 3, 2, tzinfo=UTC)

    clock.set(later)

    assert clock.now() == later


def test_ac5_fixed_clock_rejects_naive_datetime() -> None:
    """Failure path: naive datetimes are a ValueError at construction and at set()."""
    naive = datetime(2026, 1, 1, 12, 0, 0)

    with pytest.raises(ValueError):
        FixedClock(naive)

    clock = FixedClock(T0)
    with pytest.raises(ValueError):
        clock.set(naive)
    assert clock.now() == T0


def test_ac5_create_app_with_defaults_serves_healthz(monkeypatch: pytest.MonkeyPatch) -> None:
    """Edge: create_app() with no arguments resolves its defaults without any env vars."""
    monkeypatch.delenv("LINKS_API_KEYS", raising=False)

    with TestClient(create_app(), follow_redirects=False) as default_client:
        response = default_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
