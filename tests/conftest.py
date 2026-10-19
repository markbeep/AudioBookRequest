from __future__ import annotations

import base64
import os
import shutil
import tempfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = Path(tempfile.mkdtemp(prefix="abr-test-config-"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# These must exist before app.util.db builds the engine at import time.
os.environ.update(
    {
        "ABR_APP__CONFIG_DIR": str(CONFIG_DIR),
        "ABR_DB__SQLITE_PATH": "test.sqlite",
        "ABR_APP__INIT_ROOT_USERNAME": "",
        "ABR_APP__INIT_ROOT_PASSWORD": "",
        "ABR_APP__BASE_URL": "",
        "ABR_APP__DEBUG": "false",
        "ABR_APP__OPENAPI_ENABLED": "true",
        "ABR_APP__LOG_LEVEL": "ERROR",
    }
)
os.chdir(ROOT)

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.internal import models  # noqa: E402
from app.internal.audiobookshelf.config import abs_config  # noqa: E402
from app.internal.audible.search import search_cache, search_suggestions_cache  # noqa: E402
from app.internal.audible.similar import sims_cache  # noqa: E402
from app.internal.auth.authentication import create_user  # noqa: E402
from app.internal.auth.config import auth_config  # noqa: E402
from app.internal.auth.login_types import LoginTypeEnum  # noqa: E402
from app.internal.auth.oidc_config import oidc_config  # noqa: E402
from app.internal.indexers.configuration import indexer_configuration_cache  # noqa: E402
from app.internal.indexers.mam import MamIndexer  # noqa: E402
from app.internal.models import (  # noqa: E402
    Audiobook,
    AudiobookRequest,
    GroupEnum,
    ManualBookRequest,
)
from app.internal.prowlarr.util import (  # noqa: E402
    prowlarr_config,
    prowlarr_indexer_cache,
    prowlarr_source_cache,
)
from app.internal.ranking.quality import quality_config  # noqa: E402
from app.util.db import engine  # noqa: E402
from tests.constants import ASIN, DOWNLOADED_ASIN, MANUAL_ID  # noqa: E402

# app.main performs DB work at import time, so the schema must exist first.
models.BaseSQLModel.metadata.create_all(engine)

import app.main  # noqa: E402
from tests import mock_services  # noqa: E402


def _flush_caches() -> None:
    auth_config.flush()
    abs_config.flush()
    oidc_config.flush()
    prowlarr_config.flush()
    quality_config.flush()
    indexer_configuration_cache.flush()
    prowlarr_source_cache.flush()
    prowlarr_indexer_cache.flush()
    search_cache.clear()
    search_suggestions_cache.clear()
    sims_cache.clear()
    MamIndexer.results.clear()


def _seed() -> None:
    with Session(engine) as session:
        session.add(create_user("root", "rootpass", GroupEnum.admin, root=True))
        session.add(create_user("trusted", "trustedpass", GroupEnum.trusted))
        session.add(create_user("untrusted", "untrustedpass", GroupEnum.untrusted))
        session.commit()

        session.add(
            Audiobook(
                asin=ASIN,
                title="Test Book",
                subtitle=None,
                authors=["Mock Author"],
                narrators=["Mock Narrator"],
                cover_image=None,
                release_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
                runtime_length_min=600,
                downloaded=False,
            )
        )
        session.add(
            Audiobook(
                asin=DOWNLOADED_ASIN,
                title="Downloaded Book",
                subtitle=None,
                authors=["Mock Author"],
                narrators=["Mock Narrator"],
                cover_image=None,
                release_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
                runtime_length_min=300,
                downloaded=True,
            )
        )
        session.add(
            ManualBookRequest(
                id=MANUAL_ID,
                user_username="root",
                title="Manual Book",
                authors=["Manual Author"],
                narrators=[],
                downloaded=False,
            )
        )
        session.commit()

        session.add(AudiobookRequest(asin=ASIN, user_username="trusted"))
        session.add(AudiobookRequest(asin=DOWNLOADED_ASIN, user_username="trusted"))
        session.commit()

        auth_config.set_login_type(session, LoginTypeEnum.basic)
        auth_config.get_auth_secret(session)


@pytest.fixture(scope="session")
def mock_server() -> Iterator[mock_services.MockServer]:
    server = mock_services.MockServer()
    mock_services.install_prowlarr(server)
    mock_services.install_chaptarr(server)
    mock_services.install_notifications(server)
    mock_services.install_audiobookshelf(server)
    mock_services.install_oidc(server)
    server.start()
    yield server
    server.stop()
    shutil.rmtree(CONFIG_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_state(mock_server: mock_services.MockServer) -> Iterator[None]:
    models.BaseSQLModel.metadata.drop_all(engine)
    models.BaseSQLModel.metadata.create_all(engine)
    _flush_caches()
    _seed()
    mock_server.reset()
    app.main.user_exists = True
    yield


@pytest.fixture
def db() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def _basic(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def admin_client() -> Iterator[TestClient]:
    with TestClient(
        app.main.app, headers=_basic("root", "rootpass"), raise_server_exceptions=False
    ) as client:
        yield client


@pytest.fixture
def trusted_client() -> Iterator[TestClient]:
    with TestClient(
        app.main.app,
        headers=_basic("trusted", "trustedpass"),
        raise_server_exceptions=False,
    ) as client:
        yield client


@pytest.fixture
def anon_client() -> Iterator[TestClient]:
    with TestClient(app.main.app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def prowlarr(
    mock_server: mock_services.MockServer,
) -> Iterator[mock_services.MockServer]:
    with Session(engine) as session:
        prowlarr_config.set_base_url(session, f"{mock_server.base_url}/prowlarr")
        prowlarr_config.set_api_key(session, "mock-api-key")
        prowlarr_config.set_categories(session, [3030])
        prowlarr_config.set_indexers(session, [])
    yield mock_server


@pytest.fixture
def abs_service(
    mock_server: mock_services.MockServer,
) -> Iterator[mock_services.MockServer]:
    with Session(engine) as session:
        abs_config.set_base_url(session, f"{mock_server.base_url}/abs")
        abs_config.set_api_token(session, "mock-token")
        abs_config.set_library_id(session, "lib-1")
        abs_config.set_check_downloaded(session, True)
    yield mock_server


@pytest.fixture
def oidc_service(
    mock_server: mock_services.MockServer,
) -> Iterator[mock_services.MockServer]:
    with Session(engine) as session:
        oidc_config.set(session, "oidc_endpoint", f"{mock_server.base_url}/oidc/config")
        oidc_config.set(
            session, "oidc_authorize_endpoint", f"{mock_server.base_url}/oidc/authorize"
        )
        oidc_config.set(
            session, "oidc_token_endpoint", f"{mock_server.base_url}/oidc/token"
        )
        oidc_config.set(
            session, "oidc_userinfo_endpoint", f"{mock_server.base_url}/oidc/userinfo"
        )
        oidc_config.set(session, "oidc_client_id", "mock-client")
        oidc_config.set(session, "oidc_client_secret", "mock-secret")
        oidc_config.set(session, "oidc_scope", "openid profile")
        oidc_config.set(session, "oidc_username_claim", "preferred_username")
        oidc_config.set(session, "oidc_group_claim", "groups")
    yield mock_server
