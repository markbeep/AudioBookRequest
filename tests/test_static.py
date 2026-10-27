from fastapi.testclient import TestClient


def test_static_files(anon_client: TestClient) -> None:
    paths = [
        "/static/globals.css",
        "/static/nouislider.css",
        "/static/nouislider.js",
        "/static/apple-touch-icon.png",
        "/static/favicon-32x32.png",
        "/static/favicon-16x16.png",
        "/static/site.webmanifest",
        "/static/htmx.js",
        "/static/htmx-preload.js",
        "/static/alpine.js",
        "/static/toastify.js",
        "/static/toastify.css",
        "/static/favicon.svg",
    ]
    for path in paths:
        response = anon_client.get(path)
        assert response.status_code == 200, path
        assert "etag" in response.headers, path
    # jsDelivr's /sm/<hash>.map URL does not exist locally; a stale reference
    # makes browsers request a 404 on every page load.
    assert "sourceMappingURL" not in anon_client.get("/static/toastify.js").text
