"""Download failure handling (issues #220 and #229)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from httpx2 import Response
from sqlmodel import Session

from app.internal.models import (
    EventEnum,
    Notification,
    NotificationBodyTypeEnum,
)
from tests.constants import ASIN
from tests.http import json_object
from tests.mock_services import MockServer


def _grab(admin_client: TestClient) -> Response:
    return admin_client.post(
        f"/api/requests/{ASIN}/download",
        json={"guid": "mock-guid-1", "indexer_id": 1},
    )


def test_issue_229_indexer_error_message_is_surfaced(
    admin_client: TestClient, prowlarr: MockServer
) -> None:
    prowlarr.state["grab_status"] = 409
    prowlarr.state["grab_body"] = {
        "message": "Download blocked: VIP torrent and you are not VIP or higher."
    }

    response = _grab(admin_client)
    assert response.status_code == 500
    assert "VIP" in response.text


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


def test_issue_220_magnet_redirect_does_not_fail_download(
    admin_client: TestClient, prowlarr: MockServer
) -> None:
    prowlarr.state["torrent_redirect"] = (
        "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"
    )
    response = admin_client.post(f"/api/requests/{ASIN}/auto-download")
    assert response.status_code == 204


def test_issue_229_notification_failure_does_not_mask_error(
    admin_client: TestClient, prowlarr: MockServer, db: Session
) -> None:
    db.add(
        Notification(
            name="failing",
            url=f"{prowlarr.base_url}/notify/failing",
            event=EventEnum.on_failed_download,
            body_type=NotificationBodyTypeEnum.text,
            body="failed",
            enabled=True,
        )
    )
    db.commit()
    prowlarr.state["notification_status"] = 500
    prowlarr.state["grab_status"] = 409
    prowlarr.state["grab_body"] = {"message": "Download blocked: VIP torrent"}

    response = _grab(admin_client)
    assert response.status_code == 500
    assert "VIP" in response.text


def test_api_auto_download_returns_json_error(
    admin_client: TestClient, prowlarr: MockServer
) -> None:
    prowlarr.state["grab_status"] = 409
    prowlarr.state["grab_body"] = {"message": "Download blocked: VIP torrent"}

    response = admin_client.post(f"/api/requests/{ASIN}/auto-download")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert json_object(response)["detail"] == "Download blocked: VIP torrent"


def test_page_auto_download_still_returns_toast(
    admin_client: TestClient, prowlarr: MockServer
) -> None:
    prowlarr.state["grab_status"] = 409
    prowlarr.state["grab_body"] = {"message": "Download blocked: VIP torrent"}

    response = admin_client.post(
        f"/wishlist/hx-auto-download/{ASIN}", headers={"HX-Request": "true"}
    )
    assert response.status_code < 500
    assert "toast(" in response.text
    assert "VIP" in response.text
