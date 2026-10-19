"""Exercise every /api endpoint against mock external services."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.constants import ASIN, DOWNLOADED_ASIN, MANUAL_ID
from tests.http import as_dict, as_list, json_list, json_object
from tests.mock_services import MockServer


def test_health(admin_client: TestClient) -> None:
    assert admin_client.get("/api/health").status_code == 200


# -- users -----------------------------------------------------------------
def test_users(admin_client: TestClient, trusted_client: TestClient) -> None:
    assert admin_client.get("/api/users/").status_code == 200
    assert trusted_client.get("/api/users/").status_code == 403
    assert json_object(admin_client.get("/api/users/me"))["username"] == "root"
    assert admin_client.get("/api/users/root").status_code == 200
    assert admin_client.get("/api/users/missing").status_code == 404

    created = admin_client.post(
        "/api/users/",
        json={"username": "new", "password": "pw", "group": "trusted"},
    )
    assert created.status_code == 201
    assert json_object(created)["username"] == "new"

    duplicate = admin_client.post(
        "/api/users/", json={"username": "new", "password": "pw"}
    )
    assert duplicate.status_code == 409

    updated = admin_client.put(
        "/api/users/new", json={"group": "untrusted", "extra_data": "x"}
    )
    assert updated.status_code == 200
    assert json_object(updated)["group"] == "untrusted"

    assert (
        admin_client.put("/api/users/root", json={"group": "trusted"}).status_code
        == 400
    )
    assert admin_client.delete("/api/users/root").status_code == 400
    assert admin_client.delete("/api/users/new").status_code == 204
    assert admin_client.delete("/api/users/new").status_code == 404


# -- account ---------------------------------------------------------------
def test_account_api_keys(trusted_client: TestClient) -> None:
    assert json_list(trusted_client.get("/api/settings/account/api-keys")) == []

    created = trusted_client.post(
        "/api/settings/account/api-keys", json={"name": "test"}
    )
    assert created.status_code == 200
    key_id = json_object(created)["key"]
    assert key_id

    duplicate = trusted_client.post(
        "/api/settings/account/api-keys", json={"name": "test"}
    )
    assert duplicate.status_code == 400

    keys = json_list(trusted_client.get("/api/settings/account/api-keys"))
    assert len(keys) == 1
    kid = as_dict(keys[0])["id"]
    assert (
        trusted_client.patch(f"/api/settings/account/api-keys/{kid}/toggle").status_code
        == 204
    )
    assert (
        trusted_client.delete(f"/api/settings/account/api-keys/{kid}").status_code
        == 204
    )
    assert (
        trusted_client.patch(
            "/api/settings/account/api-keys/not-a-uuid/toggle"
        ).status_code
        == 400
    )
    assert (
        trusted_client.patch(
            f"/api/settings/account/api-keys/{uuid.uuid4()}/toggle"
        ).status_code
        == 404
    )


def test_account_password(trusted_client: TestClient) -> None:
    bad = trusted_client.put(
        "/api/settings/account/password",
        json={
            "old_password": "wrong",
            "new_password": "newpw",
            "confirm_password": "newpw",
        },
    )
    assert bad.status_code == 400

    changed = trusted_client.put(
        "/api/settings/account/password",
        json={
            "old_password": "trustedpass",
            "new_password": "newpw",
            "confirm_password": "newpw",
        },
    )
    assert changed.status_code == 204


# -- download settings -----------------------------------------------------
def test_download_settings(admin_client: TestClient) -> None:
    body = {
        "auto_download": True,
        "flac_range": {"from_kbits": 1, "to_kbits": 1000},
        "m4b_range": {"from_kbits": 1, "to_kbits": 1000},
        "mp3_range": {"from_kbits": 1, "to_kbits": 1000},
        "unknown_audio_range": {"from_kbits": 1, "to_kbits": 1000},
        "unknown_range": {"from_kbits": 1, "to_kbits": 1000},
        "min_seeders": 3,
        "name_ratio": 70,
        "title_ratio": 80,
    }
    assert admin_client.patch("/api/settings/download", json=body).status_code == 204
    got = json_object(admin_client.get("/api/settings/download"))
    assert got["auto_download"] is True
    assert got["min_seeders"] == 3
    assert got["name_ratio"] == 70


# -- security --------------------------------------------------------------
def test_security_basic(admin_client: TestClient) -> None:
    got = admin_client.get("/api/settings/security")
    assert got.status_code == 200
    assert json_object(got)["login_type"] == "basic"

    updated = admin_client.patch(
        "/api/settings/security",
        json={
            "login_type": "basic",
            "access_token_expiry": 120,
            "min_password_length": 3,
        },
    )
    assert updated.status_code == 204
    got = json_object(admin_client.get("/api/settings/security"))
    assert got["access_token_expiry"] == 120
    assert got["min_password_length"] == 3

    invalid = admin_client.patch(
        "/api/settings/security",
        json={"login_type": "basic", "min_password_length": 0},
    )
    assert invalid.status_code == 400

    assert admin_client.post("/api/settings/security/reset-auth").status_code == 204


def test_security_oidc(admin_client: TestClient, oidc_service: MockServer) -> None:
    body = {
        "login_type": "oidc",
        "oidc_endpoint": f"{oidc_service.base_url}/oidc/config",
        "oidc_client_id": "mock-client",
        "oidc_client_secret": "mock-secret",
        "oidc_scope": "openid profile",
        "oidc_username_claim": "preferred_username",
        "oidc_group_claim": "groups",
        "oidc_redirect_scheme": "auto",
    }
    response = admin_client.patch("/api/settings/security", json=body)
    assert response.status_code == 204, response.text
    assert oidc_service.requests_to("/oidc/config")


# -- audiobookshelf --------------------------------------------------------
def test_audiobookshelf(admin_client: TestClient, abs_service: MockServer) -> None:
    got = admin_client.get("/api/settings/audiobookshelf")
    assert got.status_code == 200
    assert len(as_list(json_object(got)["abs_libraries"])) == 1

    assert (
        admin_client.put(
            "/api/settings/audiobookshelf/base-url",
            data={"base_url": f"{abs_service.base_url}/abs"},
        ).status_code
        == 204
    )
    assert (
        admin_client.put(
            "/api/settings/audiobookshelf/api-token", data={"api_token": "mock-token"}
        ).status_code
        == 204
    )
    assert (
        admin_client.put(
            "/api/settings/audiobookshelf/library", data={"library_id": "lib-1"}
        ).status_code
        == 204
    )
    assert (
        admin_client.put(
            "/api/settings/audiobookshelf/check-downloaded",
            data={"check_downloaded": "true"},
        ).status_code
        == 204
    )

    tested = admin_client.get("/api/settings/audiobookshelf/test-connection")
    assert tested.status_code == 200, tested.text
    tested_body = json_object(tested)
    assert tested_body["library_count"] == 1
    assert tested_body["triggered_scan"] is True


@pytest.mark.xfail(
    strict=True, reason="unhandled AudiobookshelfMisconfigured -> 500 instead of 400"
)
def test_audiobookshelf_unconfigured(admin_client: TestClient) -> None:
    assert admin_client.get("/api/settings/audiobookshelf").status_code == 200
    # No config: the client raises an unhandled AudiobookshelfMisconfigured.
    tested = admin_client.get("/api/settings/audiobookshelf/test-connection")
    assert tested.status_code == 400, tested.text


# -- prowlarr --------------------------------------------------------------
def test_prowlarr_settings(admin_client: TestClient, prowlarr: MockServer) -> None:
    got = admin_client.get("/api/settings/prowlarr")
    assert got.status_code == 200, got.text
    data = json_object(got)
    assert isinstance(data["base_url"], str)
    assert data["base_url"].endswith("/prowlarr")
    indexers = as_dict(data["indexers"])
    assert indexers["state"] == "ok"
    assert "1" in as_dict(indexers["indexers"])

    assert (
        admin_client.put(
            "/api/settings/prowlarr/api-key", json={"api_key": "new-key"}
        ).status_code
        == 204
    )
    assert (
        admin_client.put(
            "/api/settings/prowlarr/base-url",
            json={"base_url": prowlarr.base_url + "/prowlarr"},
        ).status_code
        == 204
    )
    assert (
        admin_client.put(
            "/api/settings/prowlarr/categories", json={"categories": [3030, 3040]}
        ).status_code
        == 204
    )


def test_prowlarr_unconfigured(admin_client: TestClient) -> None:
    got = admin_client.get("/api/settings/prowlarr")
    assert got.status_code == 200
    indexers = as_dict(json_object(got)["indexers"])
    assert indexers["state"] == "failedFetch"


# -- notifications ---------------------------------------------------------
def test_notifications(admin_client: TestClient, mock_server: MockServer) -> None:
    assert admin_client.get("/api/settings/notifications").status_code == 200

    created = admin_client.post(
        "/api/settings/notifications",
        json={
            "name": "mock",
            "url": f"{mock_server.base_url}/notify/hook",
            "event_type": "onNewRequest",
            "body": '{"text": "{bookTitle}"}',
            "body_type": "json",
            "headers": '{"X-Test": "yes"}',
        },
    )
    assert created.status_code == 200, created.text
    notification = json_object(created)
    notif_id = notification["id"]
    assert notification["enabled"] is True

    assert len(json_list(admin_client.get("/api/settings/notifications"))) == 1

    tested = admin_client.post(f"/api/settings/notifications/{notif_id}/test")
    assert tested.status_code == 200, tested.text
    posted = mock_server.requests_to("/notify/hook")
    assert posted
    assert posted[-1]["headers"].get("X-Test") == "yes"

    toggled = admin_client.patch(f"/api/settings/notifications/{notif_id}/enable")
    assert toggled.status_code == 200
    assert json_object(toggled)["enabled"] is False

    inline = admin_client.post(
        "/api/settings/notifications/test",
        json={
            "name": "inline",
            "url": f"{mock_server.base_url}/notify/inline",
            "event_type": "onNewRequest",
            "body": "hello",
            "body_type": "text",
            "headers": "{}",
        },
    )
    assert inline.status_code == 200, inline.text
    assert mock_server.requests_to("/notify/inline")

    deleted = admin_client.delete(f"/api/settings/notifications/{notif_id}")
    assert deleted.status_code == 204
    assert (
        admin_client.delete(f"/api/settings/notifications/{notif_id}").status_code
        == 404
    )


def test_notifications_validation(admin_client: TestClient) -> None:
    invalid_headers = admin_client.post(
        "/api/settings/notifications",
        json={
            "name": "bad",
            "url": "http://example.com",
            "event_type": "onNewRequest",
            "body": "{}",
            "body_type": "json",
            "headers": "not json",
        },
    )
    assert invalid_headers.status_code == 400

    invalid_event = admin_client.post(
        "/api/settings/notifications",
        json={
            "name": "bad",
            "url": "http://example.com",
            "event_type": "nope",
            "body": "{}",
            "body_type": "json",
        },
    )
    assert invalid_event.status_code == 400

    invalid_body = admin_client.post(
        "/api/settings/notifications",
        json={
            "name": "bad",
            "url": "http://example.com",
            "event_type": "onNewRequest",
            "body": "[1]",
            "body_type": "json",
        },
    )
    assert invalid_body.status_code == 422


# -- indexers --------------------------------------------------------------
def test_indexer_configurations(admin_client: TestClient) -> None:
    got = admin_client.get("/api/indexers/configurations")
    assert got.status_code == 200
    assert "MyAnonamouse" in json_object(got)


def test_update_indexer(admin_client: TestClient) -> None:
    updated = admin_client.patch(
        "/api/indexers/MyAnonamouse",
        json={"mam_session_id": "session", "enabled": "on"},
    )
    assert updated.status_code == 204, updated.text

    unknown = admin_client.patch("/api/indexers/Unknown", json={"x": "y"})
    assert unknown.status_code == 400

    bad_body = admin_client.patch("/api/indexers/MyAnonamouse", json=[1, 2])
    assert bad_body.status_code == 400


# -- requests --------------------------------------------------------------
def test_requests_list(admin_client: TestClient, trusted_client: TestClient) -> None:
    assert admin_client.get("/api/requests").status_code == 200
    assert admin_client.get("/api/requests?filter=downloaded").status_code == 200
    assert admin_client.get("/api/requests?filter=not_downloaded").status_code == 200
    assert trusted_client.get("/api/requests").status_code == 200


def test_create_request(admin_client: TestClient) -> None:
    created = admin_client.post(f"/api/requests/{ASIN}")
    assert created.status_code == 200, created.text
    assert as_dict(json_object(created)["book"])["asin"] == ASIN

    duplicate = admin_client.post(f"/api/requests/{ASIN}")
    assert duplicate.status_code == 409

    invalid_region = admin_client.post(f"/api/requests/{ASIN}?region=zz")
    assert invalid_region.status_code == 422

    missing = admin_client.post("/api/requests/B00MISSING")
    assert missing.status_code == 404


def test_manual_requests(admin_client: TestClient) -> None:
    created = admin_client.post(
        "/api/requests/manual",
        json={"title": "New Manual", "author": "A,B", "narrator": "C"},
    )
    assert created.status_code == 201

    listed = admin_client.get("/api/requests/manual")
    assert listed.status_code == 200
    ids = [as_dict(item)["id"] for item in json_list(listed)]
    assert str(MANUAL_ID) in ids

    updated = admin_client.put(
        f"/api/requests/manual/{MANUAL_ID}",
        json={"title": "Updated", "author": "X"},
    )
    assert updated.status_code == 204

    downloaded = admin_client.patch(f"/api/requests/manual/{MANUAL_ID}/downloaded")
    assert downloaded.status_code == 204

    deleted = admin_client.delete(f"/api/requests/manual/{MANUAL_ID}")
    assert deleted.status_code == 204
    assert admin_client.delete(f"/api/requests/manual/{MANUAL_ID}").status_code == 404


def test_manual_request_permissions(trusted_client: TestClient) -> None:
    response = trusted_client.put(
        f"/api/requests/manual/{MANUAL_ID}",
        json={"title": "Updated", "author": "X"},
    )
    assert response.status_code == 403


def test_refresh_and_sources(admin_client: TestClient, prowlarr: MockServer) -> None:
    assert prowlarr.base_url
    refreshed = admin_client.post(f"/api/requests/{ASIN}/refresh")
    assert refreshed.status_code == 202, refreshed.text

    sources = admin_client.get(f"/api/requests/{ASIN}/sources")
    assert sources.status_code == 200, sources.text
    body = json_object(sources)
    assert body["state"] == "ok"
    assert as_dict(as_list(body["sources"])[0])["guid"] == "mock-guid-1"


def test_sources_unconfigured(admin_client: TestClient) -> None:
    response = admin_client.get(f"/api/requests/{ASIN}/sources")
    assert response.status_code == 400


def test_sources_missing_book(admin_client: TestClient, prowlarr: MockServer) -> None:
    assert prowlarr.base_url
    response = admin_client.get("/api/requests/does-not-exist/sources")
    assert response.status_code == 404


def test_download(
    admin_client: TestClient, prowlarr: MockServer, mock_server: MockServer
) -> None:
    assert prowlarr.base_url
    response = admin_client.post(
        f"/api/requests/{ASIN}/download",
        json={"guid": "mock-guid-1", "indexer_id": 1},
    )
    assert response.status_code == 204, response.text
    grabs = mock_server.requests_to("/prowlarr/api/v1/search")
    assert any(request["method"] == "POST" for request in grabs)


def test_auto_download(
    admin_client: TestClient, prowlarr: MockServer, mock_server: MockServer
) -> None:
    assert prowlarr.base_url
    response = admin_client.post(f"/api/requests/{ASIN}/auto-download")
    assert response.status_code == 204, response.text
    assert any(
        request["method"] == "POST"
        for request in mock_server.requests_to("/prowlarr/api/v1/search")
    )


def test_mark_downloaded(admin_client: TestClient, trusted_client: TestClient) -> None:
    response = admin_client.patch(f"/api/requests/{ASIN}/downloaded")
    assert response.status_code == 204
    assert admin_client.patch("/api/requests/missing/downloaded").status_code == 404
    assert (
        trusted_client.patch(f"/api/requests/{DOWNLOADED_ASIN}/downloaded").status_code
        == 403
    )


def test_delete_request(admin_client: TestClient, trusted_client: TestClient) -> None:
    assert trusted_client.delete(f"/api/requests/{ASIN}").status_code == 204
    assert admin_client.delete(f"/api/requests/{DOWNLOADED_ASIN}").status_code == 204


# -- search ----------------------------------------------------------------
def test_search(admin_client: TestClient) -> None:
    assert json_list(admin_client.get("/api/search")) == []
    assert admin_client.get("/api/search?q=doesnotexist&region=zz").status_code == 422

    results = admin_client.get("/api/search?q=harry+potter&num_results=1")
    assert results.status_code == 200, results.text
    assert json_list(results)


def test_search_suggestions(admin_client: TestClient) -> None:
    suggestions = admin_client.get("/api/search/suggestions?q=harry")
    assert suggestions.status_code == 200, suggestions.text
    assert json_list(suggestions)


def test_search_abs_marking(admin_client: TestClient, abs_service: MockServer) -> None:
    results = admin_client.get("/api/search?q=harry+potter&num_results=1")
    assert results.status_code == 200
    assert abs_service.requests_to("/abs/api/libraries/lib-1/search")


# -- recommendations -------------------------------------------------------
def test_recommendations_local(admin_client: TestClient) -> None:
    assert admin_client.get("/api/recommendations/popular").status_code == 200
    assert admin_client.get("/api/recommendations/recent").status_code == 200


def test_recommendations_user(admin_client: TestClient) -> None:
    response = admin_client.get("/api/recommendations/user")
    assert response.status_code == 200, response.text
    assert "recommendations" in json_object(response)


def test_recommendations_fallback(admin_client: TestClient) -> None:
    response = admin_client.get("/api/recommendations/fallback?limit=1")
    assert response.status_code == 200, response.text


def test_recommendations_categories(admin_client: TestClient) -> None:
    response = admin_client.get("/api/recommendations/categories")
    assert response.status_code == 200, response.text


@pytest.mark.xfail(
    strict=True, reason="ZeroDivisionError when the user has no favorite authors"
)
def test_recommendations_authors(admin_client: TestClient) -> None:
    assert admin_client.get("/api/recommendations/authors?limit=1").status_code == 200


@pytest.mark.xfail(
    strict=True, reason="ZeroDivisionError when the user has no favorite narrators"
)
def test_recommendations_narrators(admin_client: TestClient) -> None:
    assert admin_client.get("/api/recommendations/narrators?limit=1").status_code == 200
