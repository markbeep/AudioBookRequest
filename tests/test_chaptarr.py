import aiohttp
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.internal.chaptarr.client import ChaptarrError, start_chaptarr_download
from app.internal.chaptarr.config import chaptarr_config
from app.internal.models import Audiobook
from app.internal.query import background_start_query
from app.internal.ranking.quality import quality_config
from tests import mock_services
from tests.constants import ASIN, MANUAL_ID
from tests.http import as_dict, json_object


def test_chaptarr_settings_roundtrip(
    admin_client: TestClient, chaptarr: mock_services.MockServer
) -> None:
    response = admin_client.get("/api/settings/chaptarr")
    assert response.status_code == 200
    settings = json_object(response)
    assert settings["base_url"] == f"{chaptarr.base_url}/chaptarr"
    assert settings["connected"] is True

    response = admin_client.put(
        "/api/settings/chaptarr/base-url", json={"base_url": "http://chaptarr:8789"}
    )
    assert response.status_code == 204
    response = admin_client.put(
        "/api/settings/chaptarr/api-key", json={"api_key": "new-key"}
    )
    assert response.status_code == 204

    settings = json_object(admin_client.get("/api/settings/chaptarr"))
    assert settings["base_url"] == "http://chaptarr:8789"
    assert settings["api_key"] == "new-key"


def test_auto_download_hands_off_to_chaptarr(
    admin_client: TestClient,
    chaptarr: mock_services.MockServer,
    db: Session,
) -> None:
    quality_config.set_auto_download(db, True)

    response = admin_client.post(f"/api/requests/{ASIN}/auto-download")
    assert response.status_code == 204

    lookup_requests = chaptarr.requests_to("/chaptarr/api/v1/book/lookup")
    assert lookup_requests[0]["query"]["term"] == f"az:{ASIN}"
    assert lookup_requests[0]["query"]["mediaType"] == "audiobook"

    added = chaptarr.state["chaptarr_added"]
    assert len(added) == 1
    body = added[0]
    assert body["mediaType"] == "audiobook"
    assert body["monitored"] is True
    assert body["addOptions"] == {
        "addType": "automatic",
        "searchForNewBook": True,
    }
    author = as_dict(body["author"])
    assert author["audiobookRootFolderPath"] == "/audiobooks"
    assert author["audiobookQualityProfileId"] == 1
    assert author["audiobookMetadataProfileId"] == 1

    db.expire_all()
    book = db.get(Audiobook, ASIN)
    assert book is not None
    assert book.downloaded is True

    # Chaptarr owns the download; Prowlarr must not be queried.
    assert not chaptarr.requests_to("/chaptarr/api/v1/search")


def test_chaptarr_lookup_miss_keeps_book_undownloaded(
    admin_client: TestClient,
    chaptarr: mock_services.MockServer,
    db: Session,
) -> None:
    chaptarr.state["chaptarr_lookup"] = []
    quality_config.set_auto_download(db, True)

    response = admin_client.post(f"/api/requests/{ASIN}/auto-download")
    assert response.status_code == 500
    assert "no match for ASIN" in str(json_object(response)["detail"])
    assert chaptarr.state["chaptarr_added"] == []

    db.expire_all()
    book = db.get(Audiobook, ASIN)
    assert book is not None
    assert book.downloaded is False


def test_auto_download_uses_prowlarr_when_selected(
    admin_client: TestClient,
    chaptarr: mock_services.MockServer,
    prowlarr: mock_services.MockServer,
    db: Session,
) -> None:
    assert prowlarr.base_url
    quality_config.set_auto_download(db, True)
    assert (
        admin_client.put(
            "/api/settings/prowlarr/backend", json={"backend": "prowlarr"}
        ).status_code
        == 204
    )

    response = admin_client.post(f"/api/requests/{ASIN}/auto-download")
    assert response.status_code == 204

    searches = prowlarr.requests_to("/prowlarr/api/v1/search")
    assert any(request["method"] == "POST" for request in searches)
    db.expire_all()
    book = db.get(Audiobook, ASIN)
    assert book is not None
    assert book.downloaded is True

    assert chaptarr.state["chaptarr_added"] == []
    assert not chaptarr.requests_to("/chaptarr/api/v1/book/lookup")


@pytest.mark.anyio
async def test_chaptarr_transport_error_is_wrapped(db: Session) -> None:
    chaptarr_config.set_base_url(db, "http://127.0.0.1:1")
    chaptarr_config.set_api_key(db, "key")
    book = db.get(Audiobook, ASIN)
    assert book is not None

    async with aiohttp.ClientSession() as client_session:
        with pytest.raises(ChaptarrError):
            await start_chaptarr_download(db, client_session, book)

    assert book.downloaded is False


def test_chaptarr_credential_forms(
    admin_client: TestClient, chaptarr: mock_services.MockServer
) -> None:
    assert chaptarr.base_url

    response = admin_client.put(
        "/settings/chaptarr/hx-base-url", data={"base_url": "http://chaptarr:9999"}
    )
    assert response.status_code == 204
    response = admin_client.put(
        "/settings/chaptarr/hx-api-key", data={"api_key": "form-key"}
    )
    assert response.status_code == 204

    settings = json_object(admin_client.get("/api/settings/chaptarr"))
    assert settings["base_url"] == "http://chaptarr:9999"
    assert settings["api_key"] == "form-key"


def test_chaptarr_hides_sources(
    admin_client: TestClient, chaptarr: mock_services.MockServer
) -> None:
    assert chaptarr.base_url
    wishlist = admin_client.get("/wishlist")
    assert wishlist.status_code == 200
    assert "/wishlist/sources/" not in wishlist.text

    manual = admin_client.get("/wishlist/manual")
    assert manual.status_code == 200
    assert "/wishlist/sources/" not in manual.text

    downloaded = admin_client.get("/wishlist/downloaded")
    assert downloaded.status_code == 200
    assert "/wishlist/sources/" not in downloaded.text

    redirect = admin_client.get(f"/wishlist/sources/{ASIN}", follow_redirects=False)
    assert redirect.status_code == 302
    assert redirect.headers["location"].endswith("/wishlist")

    source_post = admin_client.post(
        f"/wishlist/sources/{ASIN}",
        data={"guid": "mock-guid-1", "indexer_id": "1"},
        follow_redirects=False,
    )
    assert source_post.status_code == 302
    assert source_post.headers["location"].endswith("/wishlist")

    assert admin_client.get(f"/api/requests/{ASIN}/sources").status_code == 400
    assert admin_client.post(f"/api/requests/{ASIN}/refresh").status_code == 400
    assert (
        admin_client.post(
            f"/api/requests/{ASIN}/download",
            json={"guid": "mock-guid-1", "indexer_id": 1},
        ).status_code
        == 400
    )
    assert (
        admin_client.post(f"/api/requests/{MANUAL_ID}/auto-download").status_code == 400
    )


def test_prowlarr_shows_sources(
    admin_client: TestClient, prowlarr: mock_services.MockServer
) -> None:
    assert prowlarr.base_url
    wishlist = admin_client.get("/wishlist")
    assert wishlist.status_code == 200
    assert "/wishlist/sources/" in wishlist.text

    manual = admin_client.get("/wishlist/manual")
    assert manual.status_code == 200
    assert "/wishlist/sources/" in manual.text

    downloaded = admin_client.get("/wishlist/downloaded")
    assert downloaded.status_code == 200
    assert "/wishlist/sources/" in downloaded.text


def test_chaptarr_settings_page(
    admin_client: TestClient, chaptarr: mock_services.MockServer
) -> None:
    assert chaptarr.base_url
    response = admin_client.get("/settings/prowlarr")
    assert response.status_code == 200
    assert 'id="chaptarr-api-key"' in response.text
    assert 'id="prowlarr-api-key"' not in response.text

    switched = admin_client.put(
        "/settings/prowlarr/hx-backend", data={"backend": "prowlarr"}
    )
    assert switched.status_code == 204

    response = admin_client.get("/settings/prowlarr")
    assert response.status_code == 200
    assert 'id="prowlarr-api-key"' in response.text
    assert 'id="chaptarr-api-key"' not in response.text


@pytest.mark.anyio
async def test_background_chaptarr_failure_is_logged_not_raised(
    chaptarr: mock_services.MockServer, db: Session
) -> None:
    """A raise after the response started aborts the ASGI request context."""
    chaptarr.state["chaptarr_lookup"] = []
    quality_config.set_auto_download(db, True)

    await background_start_query(ASIN, auto_download=True)

    db.expire_all()
    book = db.get(Audiobook, ASIN)
    assert book is not None
    assert book.downloaded is False
