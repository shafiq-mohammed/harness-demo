"""Tests for T-003: GET /{code} redirects and counts hits, GET /links/{code} reads a link.

Acceptance criteria live in tasks/T-003.md. Interface in docs/SPEC.md sections 6, 7, 8 and 10.
Links are only ever created through POST /links and hit counts are only ever observed through
GET /links/{code}; the repository dict is never inspected.
"""

from datetime import datetime

from conftest import HEADERS, T0
from fastapi.testclient import TestClient

URL_A = "https://example.com/x?y=1#z"
URL_B = "https://example.org/other/path"
UNKNOWN_CODE = "zzzzzzz"


def _create(client: TestClient, url: str) -> dict:
    """Create a link through the public API and return the 201 body."""
    response = client.post("/links", headers=HEADERS, json={"url": url})
    assert response.status_code == 201, response.text
    return response.json()


def _hit_count(client: TestClient, code: str) -> int:
    """Read the live hit count through GET /links/{code}."""
    response = client.get(f"/links/{code}", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()["hit_count"]


# --------------------------------------------------------------------------------------
# AC1: GET /{code} without a key -> 302 with the verbatim Location and an empty body
# --------------------------------------------------------------------------------------


def test_ac1_redirect_returns_302_with_exact_location(client: TestClient) -> None:
    """Happy path: an anonymous caller is redirected to the stored URL, byte for byte."""
    code = _create(client, URL_A)["code"]

    response = client.get(f"/{code}")

    assert response.status_code == 302
    assert response.headers["location"] == URL_A
    assert response.content == b""


def test_ac1_reserved_paths_are_not_treated_as_codes(client: TestClient) -> None:
    """Edge: /links and /healthz are matched by their own routers, never by the catch-all.

    The redirect of a real code is asserted alongside so this test fails while /{code} is
    missing, rather than passing on the pre-existing catch-all behaviour.
    """
    code = _create(client, URL_A)["code"]

    assert client.get(f"/{code}").status_code == 302

    links_response = client.get("/links", headers=HEADERS)
    assert links_response.status_code != 302
    assert "location" not in links_response.headers

    health_response = client.get("/healthz")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}


# --------------------------------------------------------------------------------------
# AC2: GET /{unknown} -> 404 not_found envelope, nothing counted
# --------------------------------------------------------------------------------------


def test_ac2_unknown_code_returns_404_not_found(client: TestClient) -> None:
    """A code that was never created is a 404 in the error envelope, while a real one redirects."""
    code = _create(client, URL_A)["code"]
    assert client.get(f"/{code}").status_code == 302

    response = client.get(f"/{UNKNOWN_CODE}")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "not_found"
    assert isinstance(body["message"], str)
    assert body["message"] != ""


def test_ac2_code_outside_alphabet_returns_404_not_500(client: TestClient) -> None:
    """Edge: characters outside the code alphabet are a client error, never a crash."""
    code = _create(client, URL_A)["code"]
    assert client.get(f"/{code}").status_code == 302

    response = client.get("/not-a-code!")

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


# --------------------------------------------------------------------------------------
# AC3: GET /links/{code} with a valid key -> 200 LinkOut with hit_count 0
# --------------------------------------------------------------------------------------


def test_ac3_get_link_returns_link_out_with_zero_hits(client: TestClient) -> None:
    """Happy path: a freshly created link reads back exactly as it was created, unused."""
    created = _create(client, URL_A)

    response = client.get(f"/links/{created['code']}", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == created["code"]
    assert body["url"] == URL_A
    assert body["expires_at"] is None
    assert body["hit_count"] == 0
    created_at = datetime.fromisoformat(body["created_at"])
    assert created_at.tzinfo is not None
    assert created_at == T0


def test_ac3_two_links_each_report_zero_hits(client: TestClient) -> None:
    """Edge: counts start at zero per link, they are not shared or global."""
    first = _create(client, URL_A)
    second = _create(client, URL_B)

    assert first["code"] != second["code"]
    assert _hit_count(client, first["code"]) == 0
    assert _hit_count(client, second["code"]) == 0


# --------------------------------------------------------------------------------------
# AC4: successful redirects are counted; 404s are not
# --------------------------------------------------------------------------------------


def test_ac4_three_redirects_give_hit_count_three(client: TestClient) -> None:
    """Happy path: one increment per successful 302."""
    code = _create(client, URL_A)["code"]

    for _ in range(3):
        response = client.get(f"/{code}")
        assert response.status_code == 302
        assert response.headers["location"] == URL_A

    assert _hit_count(client, code) == 3


def test_ac4_hit_counts_are_tracked_per_link(client: TestClient) -> None:
    """Edge: redirecting link A does not move link B's counter."""
    code_a = _create(client, URL_A)["code"]
    code_b = _create(client, URL_B)["code"]

    assert client.get(f"/{code_a}").status_code == 302
    assert client.get(f"/{code_a}").status_code == 302
    assert client.get(f"/{code_b}").status_code == 302

    assert _hit_count(client, code_a) == 2
    assert _hit_count(client, code_b) == 1


def test_ac4_unknown_code_requests_do_not_change_counts(client: TestClient) -> None:
    """Error path: 404 redirect attempts count for nothing."""
    code = _create(client, URL_A)["code"]
    assert client.get(f"/{code}").status_code == 302
    assert _hit_count(client, code) == 1

    assert client.get(f"/{UNKNOWN_CODE}").status_code == 404
    assert client.get("/not-a-code!").status_code == 404

    assert _hit_count(client, code) == 1


# --------------------------------------------------------------------------------------
# AC5: GET /links/{code} auth and lookup failures
# --------------------------------------------------------------------------------------


def test_ac5_get_link_without_api_key_returns_401(client: TestClient) -> None:
    """No header at all is unauthorized, even for a link that exists."""
    code = _create(client, URL_A)["code"]

    response = client.get(f"/links/{code}")

    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "unauthorized"
    assert body["message"] != ""


def test_ac5_get_link_with_wrong_key_returns_401(client: TestClient) -> None:
    """Edge: authentication is checked before the lookup, so a wrong key on a real code is 401."""
    code = _create(client, URL_A)["code"]

    response = client.get(f"/links/{code}", headers={"X-API-Key": "wrong"})

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"

    unknown = client.get(f"/links/{UNKNOWN_CODE}", headers={"X-API-Key": "wrong"})
    assert unknown.status_code == 401
    assert unknown.json()["error"] == "unauthorized"


def test_ac5_unknown_code_with_valid_key_returns_404(client: TestClient) -> None:
    """A valid key reading a code that does not exist gets the not_found envelope.

    The 200 for a real code is asserted first so this test cannot pass on the pre-existing
    catch-all 404 for the unregistered route.
    """
    code = _create(client, URL_A)["code"]
    assert client.get(f"/links/{code}", headers=HEADERS).status_code == 200

    response = client.get(f"/links/{UNKNOWN_CODE}", headers=HEADERS)

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "not_found"
    assert body["message"] != ""
