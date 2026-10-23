"""Exercise the HTML/page endpoints, including static assets."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.models import APIKey
from app.util.log import logger
from tests.constants import ASIN, MANUAL_ID
from tests.http import as_dict, json_list
from tests.mock_services import MockServer


# -- index / recommendations ----------------------------------------------
def test_index(admin_client: TestClient) -> None:
    response = admin_client.get("/")
    assert response.status_code == 200


# -- init / auth -----------------------------------------------------------
def test_init_redirect(admin_client: TestClient) -> None:
    response = admin_client.get("/init", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_init_post_blocked_after_setup(anon_client: TestClient) -> None:
    response = anon_client.post(
        "/init/hx-init",
        data={
            "login_type": "basic",
            "username": "second-root",
            "password": "pw",
            "confirm_password": "pw",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_login_pages(anon_client: TestClient) -> None:
    response = anon_client.get("/login", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login"

    response = anon_client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"

    response = anon_client.post(
        "/auth/login/hx-login",
        data={"username": "root", "password": "rootpass", "redirect_uri": "/"},
    )
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == "/"


def test_logout(admin_client: TestClient) -> None:
    response = admin_client.post("/auth/logout")
    assert response.status_code == 204


def test_oidc_flow(anon_client: TestClient, oidc_service: MockServer) -> None:
    response = anon_client.get("/auth/oidc?code=abc")
    assert response.status_code == 200, response.text
    assert oidc_service.requests_to("/oidc/token")
    assert oidc_service.requests_to("/oidc/userinfo")


def test_oidc_invalid_page(admin_client: TestClient, db: Session) -> None:
    assert admin_client.get("/auth/oidc/invalid").status_code == 404

    auth_config.set_login_type(db, LoginTypeEnum.oidc)
    response = admin_client.get("/auth/oidc/invalid?error=boom")
    assert response.status_code == 200
    assert "boom" in response.text


# -- recommendations page --------------------------------------------------
def test_for_you_page(trusted_client: TestClient) -> None:
    response = trusted_client.get("/recommendations/for-you")
    assert response.status_code == 200, response.text


# -- search / request ------------------------------------------------------
def test_search_pages(admin_client: TestClient) -> None:
    assert admin_client.get("/search").status_code == 200
    assert admin_client.get("/search?q=harry+potter&num_results=1").status_code == 200
    assert admin_client.get("/search/hx-suggestions?q=harry").status_code == 200
    assert admin_client.get("/search/manual").status_code == 200


def test_add_request_page(admin_client: TestClient) -> None:
    response = admin_client.post(f"/request/hx-add/{ASIN}", data={"region": "us"})
    assert response.status_code == 200, response.text


def test_add_manual_page(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/search/manual/hx-add",
        data={"title": "UI Manual", "author": "Author"},
    )
    assert response.status_code == 200, response.text


# -- wishlist --------------------------------------------------------------
def test_wishlist_pages(admin_client: TestClient) -> None:
    assert admin_client.get("/wishlist").status_code == 200
    assert admin_client.get("/wishlist/downloaded").status_code == 200
    assert admin_client.get("/wishlist/manual").status_code == 200


def test_wishlist_source_pages(admin_client: TestClient, prowlarr: MockServer) -> None:
    assert prowlarr.base_url
    response = admin_client.get(f"/wishlist/sources/{ASIN}")
    assert response.status_code == 200, response.text
    response = admin_client.get(f"/wishlist/sources/{ASIN}?only_body=1")
    assert response.status_code == 200, response.text

    download = admin_client.post(
        f"/wishlist/sources/{ASIN}",
        data={"guid": "mock-guid-1", "indexer_id": "1"},
    )
    assert download.status_code == 204, download.text


def test_wishlist_actions(admin_client: TestClient, prowlarr: MockServer) -> None:
    assert prowlarr.base_url
    auto = admin_client.post(f"/wishlist/hx-auto-download/{ASIN}")
    assert auto.status_code == 200, auto.text

    marked = admin_client.patch(f"/wishlist/downloaded/hx-add/{ASIN}")
    assert marked.status_code == 200, marked.text

    deleted = admin_client.delete(f"/wishlist/hx-delete/{ASIN}")
    assert deleted.status_code == 200, deleted.text


def test_wishlist_manual_actions(admin_client: TestClient) -> None:
    marked = admin_client.patch(f"/wishlist/manual/hx-add/{MANUAL_ID}")
    assert marked.status_code == 200, marked.text

    deleted = admin_client.delete(f"/wishlist/manual/hx-delete/{MANUAL_ID}")
    assert deleted.status_code == 200, deleted.text


# -- settings: account -----------------------------------------------------
def test_account_page(admin_client: TestClient, db: Session) -> None:
    assert admin_client.get("/settings/account").status_code == 200

    key_response = admin_client.post(
        "/settings/account/hx-api-key", data={"name": "ui-key"}
    )
    assert key_response.status_code == 200, key_response.text
    key = db.exec(select(APIKey).where(APIKey.name == "ui-key")).one()

    toggled = admin_client.patch(f"/settings/account/hx-api-key/{key.id}/toggle")
    assert toggled.status_code == 200
    deleted = admin_client.delete(f"/settings/account/hx-api-key/{key.id}")
    assert deleted.status_code == 200

    changed = admin_client.post(
        "/settings/account/hx-password",
        data={
            "old_password": "rootpass",
            "password": "newrootpass",
            "confirm_password": "newrootpass",
        },
    )
    assert changed.status_code == 200, changed.text


# -- settings: audiobookshelf ---------------------------------------------
def test_audiobookshelf_page(admin_client: TestClient, abs_service: MockServer) -> None:
    assert admin_client.get("/settings/audiobookshelf").status_code == 200
    assert (
        admin_client.put(
            "/settings/audiobookshelf/hx-base-url",
            data={"base_url": f"{abs_service.base_url}/abs"},
        ).status_code
        == 204
    )
    assert (
        admin_client.put(
            "/settings/audiobookshelf/hx-api-token", data={"api_token": "mock-token"}
        ).status_code
        == 204
    )
    assert (
        admin_client.put(
            "/settings/audiobookshelf/hx-library", data={"library_id": "lib-1"}
        ).status_code
        == 204
    )
    assert (
        admin_client.put(
            "/settings/audiobookshelf/hx-check-downloaded",
            data={"check_downloaded": "true"},
        ).status_code
        == 204
    )


# -- settings: download ----------------------------------------------------
def test_download_page(admin_client: TestClient) -> None:
    assert admin_client.get("/settings/download").status_code == 200

    sliders = admin_client.post(
        "/settings/download/hx-sliders",
        data={
            "flac_from": "1",
            "flac_to": "1000",
            "m4b_from": "1",
            "m4b_to": "1000",
            "mp3_from": "1",
            "mp3_to": "1000",
            "unknown_audio_from": "1",
            "unknown_audio_to": "1000",
            "unknown_from": "1",
            "unknown_to": "1000",
            "min_seeders": "2",
            "name_ratio": "75",
            "title_ratio": "90",
            "auto_download": "on",
        },
    )
    assert sliders.status_code == 200, sliders.text

    flag = admin_client.post(
        "/settings/download/hx-flags", data={"flag": "freeleech", "score": "5"}
    )
    assert flag.status_code == 200, flag.text
    assert (
        admin_client.delete("/settings/download/hx-flags/freeleech").status_code == 200
    )
    assert admin_client.delete("/settings/download").status_code == 204


# -- settings: indexers ----------------------------------------------------
def test_indexers_page(admin_client: TestClient) -> None:
    assert admin_client.get("/settings/indexers").status_code == 200

    saved = admin_client.post(
        "/settings/indexers/hx-save",
        data={"indexer_select": "MyAnonamouse", "mam_session_id": "x", "enabled": "on"},
    )
    assert saved.status_code == 200, saved.text

    unknown = admin_client.post(
        "/settings/indexers/hx-save",
        data={"indexer_select": "Unknown", "x": "y"},
    )
    assert unknown.status_code == 200

    bad_file = admin_client.post(
        "/settings/indexers/hx-read-file", data={"file_path": "/does/not/exist"}
    )
    assert bad_file.status_code == 200


# -- settings: notifications ----------------------------------------------
def test_notifications_page(admin_client: TestClient, mock_server: MockServer) -> None:
    assert admin_client.get("/settings/notifications").status_code == 200

    created = admin_client.post(
        "/settings/notifications/hx-add",
        data={
            "name": "mock",
            "url": f"{mock_server.base_url}/notify/page",
            "event_type": "onNewRequest",
            "body_type": "text",
            "body": "hello",
            "headers": "{}",
        },
    )
    assert created.status_code == 200, created.text

    listed = json_list(admin_client.get("/api/settings/notifications"))
    notif_id = as_dict(listed[0])["id"]

    tested = admin_client.post(f"/settings/notifications/hx-test/{notif_id}")
    assert tested.status_code == 204, tested.text
    assert mock_server.requests_to("/notify/page")

    updated = admin_client.put(
        f"/settings/notifications/hx-update/{notif_id}",
        data={
            "name": "mock2",
            "url": f"{mock_server.base_url}/notify/page",
            "event_type": "onNewRequest",
            "body_type": "text",
            "body": "hello2",
            "headers": "{}",
        },
    )
    assert updated.status_code == 200, updated.text

    toggled = admin_client.patch(f"/settings/notifications/hx-enable/{notif_id}")
    assert toggled.status_code == 200

    deleted = admin_client.delete(f"/settings/notifications/hx-delete/{notif_id}")
    assert deleted.status_code == 200


# -- settings: prowlarr ----------------------------------------------------
def test_prowlarr_page(admin_client: TestClient, prowlarr: MockServer) -> None:
    assert admin_client.get("/settings/prowlarr").status_code == 200
    assert (
        admin_client.put(
            "/settings/prowlarr/hx-api-key", data={"api_key": "new-key"}
        ).status_code
        == 204
    )
    assert (
        admin_client.put(
            "/settings/prowlarr/hx-base-url",
            data={"base_url": f"{prowlarr.base_url}/prowlarr"},
        ).status_code
        == 204
    )
    assert (
        admin_client.put(
            "/settings/prowlarr/hx-category", data={"c": ["3030"]}
        ).status_code
        == 200
    )
    assert (
        admin_client.put(
            "/settings/prowlarr/hx-indexers", data={"i": ["1"]}
        ).status_code
        == 200
    )


# -- settings: security ----------------------------------------------------
def test_security_page(admin_client: TestClient) -> None:
    assert admin_client.get("/settings/security").status_code == 200

    updated = admin_client.post(
        "/settings/security/hx-update",
        data={
            "login_type": "basic",
            "access_token_expiry": "120",
            "min_password_length": "3",
        },
    )
    assert updated.status_code == 200, updated.text

    reset = admin_client.post("/settings/security/hx-reset-auth")
    assert reset.status_code == 204


# -- settings: users -------------------------------------------------------
def test_users_page(admin_client: TestClient) -> None:
    assert admin_client.get("/settings/users").status_code == 200

    created = admin_client.post(
        "/settings/users/hx-add",
        data={"username": "ui-user", "password": "pw", "group": "trusted"},
    )
    assert created.status_code == 200, created.text

    updated = admin_client.patch(
        "/settings/users/hx-update/ui-user", data={"group": "untrusted"}
    )
    assert updated.status_code == 200, updated.text

    deleted = admin_client.delete("/settings/users/hx-delete/ui-user")
    assert deleted.status_code == 200, deleted.text


# -- settings: logs --------------------------------------------------------
def test_logs_page(admin_client: TestClient) -> None:
    logger.info("ui-logs-marker")
    logger.error("ui-logs-<b>marker</b>")

    response = admin_client.get("/settings/logs")
    assert response.status_code == 200
    assert "ui-logs-marker" in response.text
    assert "ui-logs-&lt;b&gt;marker&lt;/b&gt;" in response.text
    assert response.text.count('aria-pressed="true"') == 4

    filtered = admin_client.get("/settings/logs?level=error")
    assert "ui-logs-&lt;b&gt;marker&lt;/b&gt;" in filtered.text
    assert "ui-logs-marker" not in filtered.text

    for i in range(260):
        logger.error(f"log-page-marker-{i}")

    newest = admin_client.get("/settings/logs?level=error")
    assert "log-page-marker-259" in newest.text
    assert "log-page-marker-0" not in newest.text
    assert "Load more (older logs)" in newest.text

    older = admin_client.get("/settings/logs?level=error&offset=250")
    assert "log-page-marker-0" in older.text
    assert "log-page-marker-259" not in older.text
    assert "Show newer logs" in older.text
    assert "Top of the 10,000 log history reached" in older.text
    assert older.text.index('id="log-lines"') < older.text.index(
        "Top of the 10,000 log history reached"
    )
    assert "Load more (older logs)" not in older.text


# -- static ----------------------------------------------------------------
