from fastapi.testclient import TestClient


def test_recommendations_authors(admin_client: TestClient) -> None:
    assert admin_client.get("/api/recommendations/authors?limit=1").status_code == 200


def test_recommendations_narrators(admin_client: TestClient) -> None:
    assert admin_client.get("/api/recommendations/narrators?limit=1").status_code == 200
