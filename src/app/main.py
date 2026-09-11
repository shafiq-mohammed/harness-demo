"""Application factory."""

from fastapi import FastAPI

from app.clock import Clock, SystemClock
from app.errors import register_error_handlers
from app.routes import health
from app.settings import Settings


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    """Build an application with its settings and clock injected.

    Defaults are Settings.from_env() and SystemClock(). Both are stored on app.state so route
    handlers can read them and every test gets an isolated app. Callers pass keyword arguments:
    T-002 inserts a `repo` parameter between `settings` and `clock`.
    """
    app = FastAPI(title="links")
    app.state.settings = settings if settings is not None else Settings.from_env()
    app.state.clock = clock if clock is not None else SystemClock()

    register_error_handlers(app)
    app.include_router(health.router)

    return app


app = create_app()
