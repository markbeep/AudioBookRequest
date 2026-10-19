from fastapi.testclient import TestClient

from tests.http import json_list


def test_index_recommendation_fragments(
    admin_client: TestClient, trusted_client: TestClient
) -> None:
    # The API returns data for this user...
    popular = admin_client.get("/api/recommendations/popular")
    assert popular.status_code == 200
    assert json_list(popular)

    fragment = admin_client.get("/hx-popular")
    assert fragment.status_code == 200
    assert "Test Book" in fragment.text

    assert trusted_client.get("/hx-for-you").status_code == 200


def test_index_recent_fragment(trusted_client: TestClient) -> None:
    assert trusted_client.get("/hx-recent").status_code == 200


def test_index_fallback_fragment(admin_client: TestClient) -> None:
    assert admin_client.get("/hx-fallback?limit=1").status_code == 200


def test_index_categories(admin_client: TestClient) -> None:
    response = admin_client.get("/hx-categories")
    assert response.status_code == 200, response.text


def test_index_authors_fragment(trusted_client: TestClient) -> None:
    assert trusted_client.get("/hx-authors?limit=1").status_code == 200


def test_index_narrators_fragment(trusted_client: TestClient) -> None:
    assert trusted_client.get("/hx-narrators?limit=1").status_code == 200


def test_popular_fragment_renders_reasons(admin_client: TestClient) -> None:
    assert "Test Book" in admin_client.get("/hx-popular").text


def test_popular_shown_when_another_user_has_request(admin_client: TestClient) -> None:
    response = admin_client.get("/")
    assert response.status_code == 200
    assert "/hx-popular" in response.text


def test_popular_hidden_when_user_is_sole_requester(
    trusted_client: TestClient,
) -> None:
    response = trusted_client.get("/")
    assert response.status_code == 200
    assert "/hx-popular" not in response.text


def test_popular_hidden_when_other_requests_are_downloaded(
    admin_client: TestClient,
) -> None:
    assert admin_client.patch("/api/requests/B00TEST01/downloaded").status_code == 204
    response = admin_client.get("/")
    assert response.status_code == 200
    assert "/hx-popular" not in response.text
