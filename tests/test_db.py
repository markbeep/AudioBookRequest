from contextlib import ExitStack

from sqlalchemy.pool import NullPool
from sqlmodel import Session

from app.util.db import engine


def test_sqlite_sessions_are_not_capped_by_a_pool():
    # #251: a bounded pool (5 + 10) wedged the server once requests held every connection.
    assert isinstance(engine.pool, NullPool)
    with ExitStack() as stack:
        for _ in range(30):
            session = stack.enter_context(Session(engine))
            # Fresh connections must get the per-connection pragmas too.
            conn = session.connection()
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
