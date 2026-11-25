import pathlib
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool
from sqlmodel import Session

from app.internal.env_settings import Settings

# Async endpoints use the sync session on the event loop. With a bounded pool,
# a checkout there blocks the whole loop while every connection is held by
# requests that need the loop to finish, so the server wedges (#251). NullPool
# opens a connection per checkout, so a checkout never waits.
db = Settings().db
if db.use_postgres:
    engine = create_engine(
        f"postgresql+psycopg2://{db.postgres_user}:{db.postgres_password}@{db.postgres_host}:{db.postgres_port}/{db.postgres_db}?sslmode={db.postgres_ssl_mode}",
        poolclass=NullPool,
    )
else:
    sqlite_path = Settings().get_sqlite_path()
    engine = create_engine(f"sqlite+pysqlite:///{sqlite_path}", poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection: sqlite3.Connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # The busy timeout makes concurrent writers wait instead of failing
        # with "database is locked".
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    # WAL lets readers proceed while a write is in flight. It is stored in the
    # database file, so setting it once is enough.
    pathlib.Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:
        try:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        except OperationalError:
            # Some network filesystems do not support WAL; the busy timeout
            # still serializes writers there.
            pass


def get_session():
    with Session(engine) as session:
        yield session
