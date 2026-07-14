from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from app.core.config import Settings


def _enable_sqlite_foreign_keys(connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def build_engine(settings: Settings) -> Engine:
    connect_args = (
        {"check_same_thread": False} if settings.resolved_database_url.startswith("sqlite") else {}
    )
    engine = create_engine(settings.resolved_database_url, connect_args=connect_args)
    if settings.resolved_database_url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
