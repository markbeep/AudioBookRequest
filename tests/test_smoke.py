from fastapi.testclient import TestClient

from tests.http import json_object


def test_health(admin_client: TestClient) -> None:
    response = admin_client.get("/api/health")
    assert response.status_code == 200


def test_me(admin_client: TestClient) -> None:
    response = admin_client.get("/api/users/me")
    assert response.status_code == 200
    assert json_object(response)["username"] == "root"
