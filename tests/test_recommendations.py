from fastapi.testclient import TestClient

from tests.http import json_list


def test_recommendations_authors(admin_client: TestClient) -> None:
    assert admin_client.get("/api/recommendations/authors?limit=1").status_code == 200


def test_recommendations_narrators(admin_client: TestClient) -> None:
    assert admin_client.get("/api/recommendations/narrators?limit=1").status_code == 200


def test_popular_recommendations_have_data(admin_client: TestClient) -> None:
    response = admin_client.get("/api/recommendations/popular")
    assert response.status_code == 200
    assert json_list(response)


def test_exclude_downloaded_param_is_accepted(admin_client: TestClient) -> None:
    response = admin_client.get("/api/recommendations/popular?exclude_downloaded=false")
    assert response.status_code == 200
