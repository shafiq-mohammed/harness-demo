"""Tests for T-005: GET /links pages through links with a keyset cursor.

Acceptance criteria live in tasks/T-005.md. Interface in docs/SPEC.md sections 3 (A8), 6, 7,
8 ("T-005"), 9 and 10.

Every assertion goes through the public HTTP surface. Links are created with POST /links and the
expected ordering is derived from the returned codes via `sorted(codes)`; the repository dict is
never inspected.
"""

from datetime import datetime

import pytest
from conftest import HEADERS, T0
from fastapi.testclient import TestClient

VALID_URL = "https://example.com/a/b?c=1"

LINK_OUT_KEYS = {"code", "url", "created_at", "expires_at", "hit_count"}

# The code alphabet is [A-Za-z0-9] (SPEC A3) and "z" is its highest ASCII character, so an
# 8 character run of "z" sorts at or above every code that can ever be generated.
CURSOR_PAST_THE_END = "zzzzzzzz"

MAX_PAGES = 20  # Guard so a broken cursor cannot spin the page walk forever.


def create_links(client: TestClient, count: int) -> list[str]:
    """Create `count` links through the public API and return their codes."""
    codes = []
    for index in range(count):
        response = client.post("/links", headers=HEADERS, json={"url": f"{VALID_URL}&n={index}"})
        assert response.status_code == 201, response.text
        codes.append(response.json()["code"])
    assert len(set(codes)) == count
    return codes


def assert_link_out_shape(item: dict) -> None:
    """Each page item carries exactly the documented LinkOut fields with usable values."""
    assert set(item) == LINK_OUT_KEYS, item
    assert isinstance(item["code"], str)
    assert item["code"] != ""
    assert isinstance(item["url"], str)
    assert item["url"].startswith("https://")
    created_at = datetime.fromisoformat(item["created_at"])
    assert created_at.tzinfo is not None
    assert created_at == T0
    assert item["expires_at"] is None
    assert item["hit_count"] == 0


def walk_pages(client: TestClient, limit: int) -> tuple[list[str], int, str | None]:
    """Follow `next_cursor` until it is null. Returns (codes, page_count, last_cursor)."""
    codes: list[str] = []
    cursor: str | None = None
    pages = 0

    while pages < MAX_PAGES:
        params: dict[str, object] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        response = client.get("/links", headers=HEADERS, params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        pages += 1
        assert len(body["items"]) <= limit
        codes.extend(item["code"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    else:  # pragma: no cover - only reached if paging never terminates
        raise AssertionError(f"paging did not terminate within {MAX_PAGES} pages")

    return codes, pages, cursor


# --------------------------------------------------------------------------------------
# AC1: no links -> 200 {"items": [], "next_cursor": null}
# --------------------------------------------------------------------------------------


def test_ac1_empty_repository_returns_empty_page(client: TestClient) -> None:
    """Happy path: an empty store still answers with a well formed empty page."""
    response = client.get("/links", headers=HEADERS)

    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "next_cursor": None}


def test_ac1_empty_repository_with_explicit_limit_returns_empty_page(client: TestClient) -> None:
    """Edge: an explicit limit does not invent items or a cursor when nothing exists."""
    response = client.get("/links", headers=HEADERS, params={"limit": 20})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


def test_ac1_missing_key_returns_401_before_empty_list(client: TestClient) -> None:
    """Error path: auth is resolved before the (empty) listing is produced."""
    response = client.get("/links")

    assert response.status_code == 401, response.text
    body = response.json()
    assert body["error"] == "unauthorized"
    assert body["message"] != ""
    assert "items" not in body


# --------------------------------------------------------------------------------------
# AC2: 5 links, limit=2 -> the 2 smallest codes ascending plus a non-empty cursor
# --------------------------------------------------------------------------------------


def test_ac2_first_page_returns_two_smallest_codes_and_cursor(client: TestClient) -> None:
    """Happy path: the first page is the head of the ascending code ordering."""
    codes = create_links(client, 5)

    response = client.get("/links", headers=HEADERS, params={"limit": 2})

    assert response.status_code == 200, response.text
    body = response.json()
    page_codes = [item["code"] for item in body["items"]]
    assert page_codes == sorted(codes)[:2]
    assert isinstance(body["next_cursor"], str)
    assert body["next_cursor"] != ""


def test_ac2_page_items_have_link_out_shape(client: TestClient) -> None:
    """Each item is a full LinkOut, not a bare code."""
    create_links(client, 5)

    response = client.get("/links", headers=HEADERS, params={"limit": 2})

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 2
    for item in items:
        assert_link_out_shape(item)


def test_ac2_limit_one_returns_single_item_and_cursor(client: TestClient) -> None:
    """Edge: the smallest allowed limit still pages correctly."""
    codes = create_links(client, 5)

    response = client.get("/links", headers=HEADERS, params={"limit": 1})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["code"] for item in body["items"]] == sorted(codes)[:1]
    assert isinstance(body["next_cursor"], str)
    assert body["next_cursor"] != ""


# --------------------------------------------------------------------------------------
# AC3: walking every page yields each code exactly once, last page has a null cursor
# --------------------------------------------------------------------------------------


def test_ac3_walking_pages_covers_every_code_exactly_once(client: TestClient) -> None:
    """Happy path: three pages of 2, 2 and 1 reconstruct the full sorted listing."""
    codes = create_links(client, 5)

    walked, pages, last_cursor = walk_pages(client, limit=2)

    assert walked == sorted(codes)
    assert len(walked) == len(set(walked)) == 5
    assert pages == 3
    assert last_cursor is None


def test_ac3_limit_five_walks_in_a_single_page(client: TestClient) -> None:
    """Edge: a limit equal to the number of links terminates after one page."""
    codes = create_links(client, 5)

    walked, pages, last_cursor = walk_pages(client, limit=5)

    assert walked == sorted(codes)
    assert pages == 1
    assert last_cursor is None


def test_ac3_unknown_cursor_returns_empty_page_not_error(client: TestClient) -> None:
    """Error path: an unknown cursor is keyset semantics, so 200 with nothing after it."""
    create_links(client, 5)

    response = client.get(
        "/links", headers=HEADERS, params={"limit": 2, "cursor": CURSOR_PAST_THE_END}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


# --------------------------------------------------------------------------------------
# AC4: limit == count and the default limit both return everything with a null cursor
# --------------------------------------------------------------------------------------


def test_ac4_limit_equal_to_count_returns_null_cursor(client: TestClient) -> None:
    """Happy path: the exact boundary must not advertise an empty extra page."""
    codes = create_links(client, 3)

    response = client.get("/links", headers=HEADERS, params={"limit": 3})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["code"] for item in body["items"]] == sorted(codes)
    assert body["next_cursor"] is None


def test_ac4_default_limit_returns_all_three(client: TestClient) -> None:
    """Edge: omitting limit uses the documented default of 20, which covers all 3 links."""
    codes = create_links(client, 3)

    response = client.get("/links", headers=HEADERS)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["code"] for item in body["items"]] == sorted(codes)
    assert body["next_cursor"] is None


def test_ac4_cursor_from_boundary_page_is_never_needed(client: TestClient) -> None:
    """Error path: a caller who reuses the last code as a cursor gets an empty page, not a 500."""
    codes = create_links(client, 3)

    response = client.get("/links", headers=HEADERS, params={"cursor": sorted(codes)[-1]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


# --------------------------------------------------------------------------------------
# AC5: invalid limits -> 422 validation_error; missing or wrong key -> 401 unauthorized
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "limit"),
    [
        ("zero", "0"),
        ("above_max", "101"),
        ("non_integer", "abc"),
        ("negative", "-1"),
        ("empty", ""),
    ],
)
def test_ac5_invalid_limit_returns_422_validation_error(
    client: TestClient, label: str, limit: str
) -> None:
    """Error path: out of range or non-integer limits are client errors, never 500."""
    response = client.get("/links", headers=HEADERS, params={"limit": limit})

    assert response.status_code == 422, f"{label}: {response.status_code} {response.text}"
    body = response.json()
    assert body["error"] == "validation_error"
    assert isinstance(body["details"], list)
    assert body["details"] != []


def test_ac5_limit_100_is_accepted(client: TestClient) -> None:
    """Edge: the upper boundary is valid and returns the whole (small) listing."""
    codes = create_links(client, 3)

    response = client.get("/links", headers=HEADERS, params={"limit": 100})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["code"] for item in body["items"]] == sorted(codes)
    assert body["next_cursor"] is None


def test_ac5_wrong_api_key_returns_401(client: TestClient) -> None:
    """Failure path: a key that is not configured is rejected."""
    create_links(client, 3)

    response = client.get("/links", headers={"X-API-Key": "wrong"}, params={"limit": 2})

    assert response.status_code == 401, response.text
    body = response.json()
    assert body["error"] == "unauthorized"
    assert body["message"] != ""


def test_ac5_unauthorized_takes_precedence_over_invalid_limit(client: TestClient) -> None:
    """Edge: an unauthenticated caller learns nothing about query validity."""
    response = client.get("/links", params={"limit": "0"})

    assert response.status_code == 401, response.text
    assert response.json()["error"] == "unauthorized"
