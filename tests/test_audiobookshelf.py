from fastapi.testclient import TestClient


def test_audiobookshelf_unconfigured(admin_client: TestClient) -> None:
    assert admin_client.get("/api/settings/audiobookshelf").status_code == 200
    tested = admin_client.get("/api/settings/audiobookshelf/test-connection")
    assert tested.status_code == 400, tested.text
