"""Reproductions for currently open GitHub issues."""

from __future__ import annotations

from fastapi.testclient import TestClient
from httpx2 import Response
from sqlmodel import Session

from app.internal.models import Audiobook
from tests.constants import ASIN
from tests.http import json_list
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


def test_issue_237_recommendations_api_has_data(admin_client: TestClient) -> None:
    response = admin_client.get("/api/recommendations/popular")
    assert response.status_code == 200
    assert json_list(response)
