from datetime import UTC, datetime

import pytest
from app.clock import FixedClock
from app.main import create_app
from app.settings import Settings
from fastapi.testclient import TestClient

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(T0)


@pytest.fixture
def client(clock) -> TestClient:
    app = create_app(settings=Settings(), clock=clock)
    return TestClient(app, follow_redirects=False)
