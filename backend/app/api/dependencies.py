from collections.abc import Generator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import Settings


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session
