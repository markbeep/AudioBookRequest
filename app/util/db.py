from sqlalchemy import create_engine
from sqlmodel import Session, text

from app.internal.env_settings import Settings

db = Settings().db
if db.use_postgres:
    engine = create_engine(
        f"postgresql://{db.postgres_user}:{db.postgres_password}@{db.postgres_host}:{db.postgres_port}/{db.postgres_db}?sslmode={db.postgres_ssl_mode}"
    )
else:
    sqlite_path = Settings().get_sqlite_path()
    engine = create_engine(f"sqlite+pysqlite:///{sqlite_path}")


def get_session():
    with Session(engine) as session:
        if not Settings().db.use_postgres:
            session.execute(text("PRAGMA foreign_keys=ON"))
        yield session
