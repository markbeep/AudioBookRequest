from fastapi.testclient import TestClient


def test_indexers_clear_file_path(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/settings/indexers/hx-read-file", data={"file_path": ""}
    )
    assert response.status_code == 200
