import sqlite3

from sqlalchemy import create_engine
from sqlmodel import Session, text

from app.internal.env_settings import Settings

db = Settings().db
if db.use_postgres:
    engine = create_engine(
        f"postgresql+psycopg2://{db.postgres_user}:{db.postgres_password}@{db.postgres_host}:{db.postgres_port}/{db.postgres_db}?sslmode={db.postgres_ssl_mode}"
    )
else:
    sqlite_path = Settings().get_sqlite_path()
    engine = create_engine(f"sqlite+pysqlite:///{sqlite_path}")


def get_session():
    with Session(engine) as session:
        if not Settings().db.use_postgres:
            session.execute(text("PRAGMA foreign_keys=ON"))
            # WAL lets readers proceed while a write is in flight; the busy
            # timeout makes concurrent writers wait instead of failing with
            # "database is locked".
            session.execute(text("PRAGMA busy_timeout=30000"))
            try:
                session.execute(text("PRAGMA journal_mode=WAL"))
            except sqlite3.OperationalError:
                # Some network filesystems do not support WAL; the busy timeout
                # still serializes writers there.
                pass
        yield session
