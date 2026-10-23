#!/usr/bin/env python3
"""Configure the local compose stack so ABR -> Chaptarr -> Prowlarr -> qBittorrent works.

Run after `docker compose --profile local up`. Idempotent: existing root folders,
clients, indexers and settings are left alone.
"""

# pyright: reportAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

import http.cookiejar
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ABR = os.environ.get("ABR_URL", "http://localhost:8000")
PROWLARR = os.environ.get("PROWLARR_URL", "http://localhost:9696")
CHAPTARR = os.environ.get("CHAPTARR_URL", "http://localhost:8789")
QBITTORRENT = os.environ.get("QBITTORRENT_URL", "http://localhost:8081")

# URLs used between containers.
PROWLARR_INTERNAL = os.environ.get("PROWLARR_INTERNAL_URL", "http://prowlarr:9696")
CHAPTARR_INTERNAL = os.environ.get("CHAPTARR_INTERNAL_URL", "http://chaptarr:8789")

ABR_USER = os.environ.get("ABR_USER", "a")
ABR_PASSWORD = os.environ.get("ABR_PASSWORD", "a")
QBIT_USER = "admin"
QBIT_PASSWORD = "adminadmin"


def request(
    url: str,
    method: str = "GET",
    body: object | None = None,
    headers: dict[str, str] | None = None,
    form: dict[str, str] | None = None,
    opener: urllib.request.OpenerDirector | None = None,
) -> tuple[int, object]:
    headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        open_fn = opener.open if opener else urllib.request.urlopen
        with open_fn(req) as response:
            raw = response.read().decode()
            if not raw.strip():
                return response.status, None
            try:
                return response.status, json.loads(raw)
            except ValueError:
                # Not every 2xx response is JSON: ABR renders toast HTML and old
                # qBittorrent builds return plain text "Ok." on login.
                return response.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def wait_for(
    url: str, headers: dict[str, str] | None = None, label: str | None = None
) -> None:
    name = label or url
    print(f"Waiting for {name} at {url} ...", flush=True)
    for attempt in range(60):
        try:
            status, _ = request(url, headers=headers)
            if status < 500:
                print(f"{name} is ready", flush=True)
                return
        except urllib.error.URLError, ConnectionError:
            pass
        if attempt and attempt % 5 == 0:
            progress = f"  still waiting for {name} after {attempt * 2}s"
            print(progress + " (container may still be starting)", flush=True)
        time.sleep(2)
    raise SystemExit(f"{name} did not become ready at {url}")


def api_key(path: Path) -> str:
    match = re.search(r"<ApiKey>([^<]+)</ApiKey>", path.read_text())
    if not match:
        raise SystemExit(f"no ApiKey in {path}")
    return match.group(1)


def field(resource: dict[str, object], name: str) -> dict[str, object] | None:
    fields = resource.get("fields")
    if not isinstance(fields, list):
        return None
    for f in fields:
        if isinstance(f, dict) and f.get("name") == name:
            return f
    return None


def set_field(resource: dict[str, object], name: str, value: object) -> None:
    f = field(resource, name)
    if f is not None:
        f["value"] = value


def get(base: str, key: str, path: str) -> tuple[int, object]:
    return request(base + path, headers={"X-Api-Key": key})


def post(base: str, key: str, path: str, body: object) -> tuple[int, object]:
    return request(base + path, "POST", body=body, headers={"X-Api-Key": key})


def list_of(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    return [x for x in value if isinstance(x, dict)]


def configure_qbittorrent() -> None:
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

    def login(password: str) -> bool:
        status, _ = request(
            f"{QBITTORRENT}/api/v2/auth/login",
            "POST",
            form={"username": QBIT_USER, "password": password},
            opener=opener,
        )
        return status in (200, 204)

    if login(QBIT_PASSWORD):
        return

    logs = subprocess.run(
        ["docker", "compose", "logs", "qbittorrent"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    # Compose logs keep every boot; only the last temporary password is valid.
    passwords = re.findall(r"temporary password is provided for this session: (\S+)", logs)
    if not passwords:
        raise SystemExit("could not find qBittorrent temporary password")
    if not login(passwords[-1]):
        raise SystemExit("could not log in to qBittorrent")
    request(
        f"{QBITTORRENT}/api/v2/app/setPreferences",
        "POST",
        form={"json": json.dumps({"web_ui_password": QBIT_PASSWORD})},
        opener=opener,
    )
    print("qBittorrent: password set")


def configure_chaptarr(key: str) -> None:
    _, roots = get(CHAPTARR, key, "/api/v1/rootfolder?mediaType=audiobook")
    if not list_of(roots):
        _, quality = get(CHAPTARR, key, "/api/v1/qualityprofile")
        quality_profiles = list_of(quality)
        audiobook = [
            p for p in quality_profiles if p.get("profileType") == "audiobook"
        ] or quality_profiles
        _, metadata = get(CHAPTARR, key, "/api/v1/metadataprofile")
        metadata_profiles = list_of(metadata)
        if not audiobook or not metadata_profiles:
            raise SystemExit("Chaptarr has no quality/metadata profiles")
        status, body = post(
            CHAPTARR,
            key,
            "/api/v1/rootfolder",
            {
                "name": "Audiobooks",
                "path": "/audiobooks",
                "folderType": 1,
                "audiobook": {
                    "qualityProfileId": audiobook[0]["id"],
                    "metadataProfileId": metadata_profiles[0]["id"],
                    "monitored": True,
                },
            },
        )
        if status >= 400:
            raise SystemExit(f"failed to add Chaptarr root folder: {body}")
        print("Chaptarr: audiobook root folder added")

    _, clients = get(CHAPTARR, key, "/api/v1/downloadclient")
    if not any(c.get("implementation") == "QBittorrent" for c in list_of(clients)):
        _, schemas = get(CHAPTARR, key, "/api/v1/downloadclient/schema")
        client = next(
            c for c in list_of(schemas) if c.get("implementation") == "QBittorrent"
        )
        client.update(name="qBittorrent", enable=True, protocol="torrent", tags=[])
        set_field(client, "host", "qbittorrent")
        set_field(client, "port", 8081)
        set_field(client, "username", QBIT_USER)
        set_field(client, "password", QBIT_PASSWORD)
        set_field(client, "audiobookCategory", "chaptarr")
        status, body = post(
            CHAPTARR, key, "/api/v1/downloadclient?forceSave=true", client
        )
        if status >= 400:
            raise SystemExit(f"failed to add qBittorrent: {body}")
        print("Chaptarr: qBittorrent download client added")


def configure_prowlarr(key: str, chaptarr_key: str) -> None:
    _, profiles = get(PROWLARR, key, "/api/v1/appprofile")
    app_profiles = list_of(profiles)

    _, indexers = get(PROWLARR, key, "/api/v1/indexer")
    if not any(i.get("name") == "The Pirate Bay" for i in list_of(indexers)):
        _, schemas = get(PROWLARR, key, "/api/v1/indexer/schema")
        indexer = next(i for i in list_of(schemas) if i.get("name") == "The Pirate Bay")
        indexer.update(
            name="The Pirate Bay",
            enable=True,
            priority=25,
            appProfileId=app_profiles[0]["id"] if app_profiles else None,
            tags=[],
        )
        urls = indexer.get("indexerUrls")
        if isinstance(urls, list) and urls:
            set_field(indexer, "baseUrl", urls[0])
        set_field(indexer, "top100", 0)
        status, body = post(PROWLARR, key, "/api/v1/indexer", indexer)
        if status >= 400:
            raise SystemExit(f"failed to add The Pirate Bay: {body}")
        print("Prowlarr: The Pirate Bay added")

    _, applications = get(PROWLARR, key, "/api/v1/applications")
    if not any(a.get("name") == "Chaptarr" for a in list_of(applications)):
        _, schemas = get(PROWLARR, key, "/api/v1/applications/schema")
        application = next(
            a for a in list_of(schemas) if a.get("implementation") == "Readarr"
        )
        application.update(name="Chaptarr", syncLevel="addOnly", tags=[])
        set_field(application, "prowlarrUrl", PROWLARR_INTERNAL)
        set_field(application, "baseUrl", CHAPTARR_INTERNAL)
        set_field(application, "apiKey", chaptarr_key)
        set_field(application, "syncCategories", [3030])
        status, body = post(PROWLARR, key, "/api/v1/applications", application)
        if status >= 400:
            raise SystemExit(f"failed to add Chaptarr application: {body}")
        print("Prowlarr: Chaptarr application added")

    # Give Prowlarr a moment to push indexers to Chaptarr.
    for _ in range(30):
        _, indexers = get(CHAPTARR, chaptarr_key, "/api/v1/indexer")
        if list_of(indexers):
            print("Prowlarr: indexers synced to Chaptarr")
            return
        time.sleep(2)
    raise SystemExit("Prowlarr did not sync indexers to Chaptarr")


def configure_abr(chaptarr_key: str) -> None:
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    status, body = request(
        f"{ABR}/auth/login/hx-login",
        "POST",
        form={"username": ABR_USER, "password": ABR_PASSWORD, "redirect_uri": "/"},
        opener=opener,
    )
    if status >= 400:
        raise SystemExit(f"could not log in to ABR: {status} {body}")

    def abr(path: str, method: str = "GET", body: object | None = None):
        return request(ABR + path, method, body=body, opener=opener)

    def write(path: str, payload: object) -> None:
        status, response_body = abr(path, "PUT", payload)
        if status >= 400:
            raise SystemExit(f"ABR rejected {path}: {status} {response_body}")

    # A failed login renders a toast page with status 200, so check an
    # authenticated endpoint instead of trusting the login status.
    status, settings = abr("/api/settings/download")
    if status >= 400 or not isinstance(settings, dict):
        raise SystemExit(
            "could not log in to ABR; set ABR_USER/ABR_PASSWORD to an admin account"
        )

    write("/api/settings/chaptarr/base-url", {"base_url": CHAPTARR_INTERNAL})
    write("/api/settings/chaptarr/api-key", {"api_key": chaptarr_key})
    write("/api/settings/prowlarr/backend", {"backend": "chaptarr"})

    if not settings.get("auto_download"):
        settings["auto_download"] = True
        status, body = abr("/api/settings/download", "PATCH", settings)
        if status >= 400:
            raise SystemExit(f"ABR rejected /api/settings/download: {status} {body}")
    print("ABR: Chaptarr configured and auto-download enabled")


def main() -> None:
    print(
        "Waiting for the local stack (first start can take a few minutes) ...",
        flush=True,
    )
    wait_for(PROWLARR + "/ping", label="Prowlarr")
    wait_for(CHAPTARR + "/ping", label="Chaptarr")
    wait_for(ABR + "/api/health", label="ABR")
    wait_for(QBITTORRENT + "/api/v2/app/version", label="qBittorrent")

    prowlarr_key = api_key(ROOT / "data/prowlarr/config.xml")
    chaptarr_key = api_key(ROOT / "data/chaptarr/config.xml")

    print("Configuring qBittorrent ...", flush=True)
    configure_qbittorrent()
    print("Configuring Chaptarr ...", flush=True)
    configure_chaptarr(chaptarr_key)
    print("Configuring Prowlarr ...", flush=True)
    configure_prowlarr(prowlarr_key, chaptarr_key)
    print("Configuring ABR ...", flush=True)
    configure_abr(chaptarr_key)
    print("local stack ready: request a book in ABR to download it through Chaptarr")


if __name__ == "__main__":
    sys.exit(main())
