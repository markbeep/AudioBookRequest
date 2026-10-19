"""Reproductions for currently open GitHub issues."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlmodel import Session

from app.internal.models import Audiobook
from tests.constants import ASIN
from tests.http import json_list, json_object
from tests.mock_services import MockServer


def _grab(admin_client: TestClient) -> Response:
    return admin_client.post(
        f"/api/requests/{ASIN}/download",
        json={"guid": "mock-guid-1", "indexer_id": 1},
    )


def test_issue_232_downloaded_on_grab_not_completion(
    admin_client: TestClient, prowlarr: MockServer, db: Session
) -> None:
    assert prowlarr.base_url
    assert _grab(admin_client).status_code == 204
    db.expire_all()
    book = db.get(Audiobook, ASIN)
    assert book is not None
    # Prowlarr merely accepted the grab; ABR already marks it downloaded.
    assert book.downloaded is True


def test_issue_229_indexer_error_message_is_lost(
    admin_client: TestClient, prowlarr: MockServer
) -> None:
    prowlarr.state["grab_status"] = 409
    prowlarr.state["grab_body"] = {
        "message": "Download blocked: VIP torrent and you are not VIP or higher."
    }

    response = _grab(admin_client)
    assert response.status_code == 500
    assert json_object(response)["detail"] == "Failed to start download"
    assert "VIP" not in response.text


@pytest.mark.xfail(
    strict=True, reason="HTTPException 500 after the HTMX response started (issue #229)"
)
def test_issue_229_page_surfaces_indexer_error(
    admin_client: TestClient, prowlarr: MockServer
) -> None:
    prowlarr.state["grab_status"] = 409
    prowlarr.state["grab_body"] = {"message": "Download blocked: VIP torrent"}

    response = admin_client.post(
        f"/wishlist/sources/{ASIN}",
        data={"guid": "mock-guid-1", "indexer_id": "1"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code < 500
    assert "VIP" in response.text


@pytest.mark.xfail(
    strict=True,
    reason="NonHttpUrlRedirectClientError from magnet redirect (issue #220)",
)
def test_issue_220_magnet_redirect_does_not_fail_download(
    admin_client: TestClient, prowlarr: MockServer
) -> None:
    prowlarr.state["torrent_redirect"] = (
        "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"
    )
    response = admin_client.post(f"/api/requests/{ASIN}/auto-download")
    assert response.status_code == 204


def test_issue_237_recommendations_api_has_data(admin_client: TestClient) -> None:
    response = admin_client.get("/api/recommendations/popular")
    assert response.status_code == 200
    assert json_list(response)
