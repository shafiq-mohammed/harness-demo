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
