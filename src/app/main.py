"""Application factory."""

from fastapi import FastAPI

from app.clock import Clock, SystemClock
from app.errors import register_error_handlers
from app.repository import InMemoryLinkRepository, LinkRepository
from app.routes import health, links
from app.settings import Settings


def create_app(
    settings: Settings | None = None,
    repo: LinkRepository | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Build an application with its settings, repository and clock injected.

    Defaults are Settings.from_env(), InMemoryLinkRepository() and SystemClock(). All three are
    stored on app.state so route handlers can read them and every test gets an isolated app.
    Callers pass keyword arguments.
    """
    app = FastAPI(title="links")
    app.state.settings = settings if settings is not None else Settings.from_env()
    app.state.repo = repo if repo is not None else InMemoryLinkRepository()
    app.state.clock = clock if clock is not None else SystemClock()

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(links.router)

    return app


app = create_app()
