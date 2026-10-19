"""In-process HTTP doubles for external services.

Prowlarr, Chaptarr (Readarr-compatible), notifications, Audiobookshelf and OIDC
are all reached over HTTP by the application. Tests start one aiohttp server in a
background thread and point the relevant config keys at it, so no real service is
needed.

Usage:
    mock = MockServer().start()
    install_prowlarr(mock)          # /prowlarr/api/v1/*
    install_notifications(mock)     # /notify/*
    configure(...)                  # set service config to mock.base_url
    ...
    mock.stop()
"""

from __future__ import annotations

import asyncio
import socket
import threading
from collections.abc import Awaitable, Callable
from typing import TypedDict, cast

from aiohttp import web

type Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


class MockRequest(TypedDict):
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    body: bytes


class NotificationPayload(TypedDict):
    path: str
    headers: dict[str, str]
    body: bytes


class MockState(TypedDict):
    indexers: list[dict[str, object]]
    search_results: list[dict[str, object]]
    torrent: bytes
    grab_status: int
    grab_body: object
    torrent_redirect: str | None
    notification_status: int
    notification_payloads: list[NotificationPayload]
    abs_libraries: list[dict[str, object]]
    oidc_userinfo: dict[str, object]


DEFAULT_INDEXERS: list[dict[str, object]] = [
    {"id": 1, "name": "MockIndexer", "enable": True, "privacy": "private"},
    {"id": 2, "name": "MockUsenet", "enable": True, "privacy": "private"},
]

DEFAULT_SEARCH_TERM = "Test Book"


def _torrent_bytes() -> bytes:
    import tempfile
    from pathlib import Path

    from torf import Torrent

    path = Path(tempfile.mkdtemp()) / "mock.bin"
    path.write_bytes(b"mock torrent payload")
    torrent = Torrent(path=path, trackers=[])
    torrent.generate()
    return torrent.dump()


class MockServer:
    """Thread-backed aiohttp server that records every request."""

    def __init__(self) -> None:
        self.requests: list[MockRequest] = []
        self.state: MockState = default_state("")
        self.base_url: str = ""
        self._app: web.Application = web.Application(middlewares=[self._record])
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None
        self._ready: threading.Event = threading.Event()

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> MockServer:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("Mock server did not start")
        return self

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(self._app)
        self._runner = runner
        loop.run_until_complete(runner.setup())

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            address = cast(object, sock.getsockname())
        assert isinstance(address, tuple)
        assert isinstance(address[1], int)
        port = address[1]

        site = web.TCPSite(runner, "127.0.0.1", port)
        loop.run_until_complete(site.start())
        self.base_url = f"http://127.0.0.1:{port}"
        self._ready.set()
        loop.run_forever()

    def stop(self) -> None:
        if self._loop is None or self._runner is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._loop.close()

    # -- routing -----------------------------------------------------------
    @web.middleware
    async def _record(
        self, request: web.Request, handler: Handler
    ) -> web.StreamResponse:
        body = await request.read()
        self.requests.append(
            {
                "method": request.method,
                "path": request.path,
                "query": dict(request.query),
                "headers": dict(request.headers),
                "body": body,
            }
        )
        return await handler(request)

    def add(self, method: str, path: str, handler: Handler) -> None:
        self._app.router.add_route(method, path, handler)

    def add_json(
        self,
        method: str,
        path: str,
        data: object | Callable[[], object],
        status: int = 200,
    ) -> None:
        async def handler(_: web.Request) -> web.Response:
            value = data() if callable(data) else data
            return web.json_response(value, status=status)

        self.add(method, path, handler)

    # -- helpers -----------------------------------------------------------
    def reset(self) -> None:
        self.requests.clear()
        self.state = default_state(self.base_url)

    def requests_to(self, path: str) -> list[MockRequest]:
        return [request for request in self.requests if request["path"] == path]


def default_state(base_url: str) -> MockState:
    return {
        "indexers": [dict(indexer) for indexer in DEFAULT_INDEXERS],
        "search_results": [
            {
                "guid": "mock-guid-1",
                "indexerId": 1,
                "indexer": "MockIndexer",
                "title": f"{DEFAULT_SEARCH_TERM} m4b",
                "size": 100_000_000,
                "infoUrl": f"{base_url}/info/1",
                "indexerFlags": ["freeleech"],
                "downloadUrl": f"{base_url}/prowlarr/download/mock.torrent",
                "magnetUrl": "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
                "publishDate": "2026-01-01T00:00:00",
                "protocol": "torrent",
                "seeders": 42,
                "leechers": 1,
            }
        ],
        "torrent": _torrent_bytes(),
        "grab_status": 200,
        "grab_body": {"ok": True},
        "torrent_redirect": None,
        "notification_status": 200,
        "notification_payloads": [],
        "abs_libraries": [{"id": "lib-1", "name": "Audiobooks", "mediaType": "book"}],
        "oidc_userinfo": {
            "sub": "oidc-user",
            "preferred_username": "oidc-user",
            "groups": ["admin"],
        },
    }


# -- service installers ----------------------------------------------------
def install_prowlarr(mock: MockServer, prefix: str = "/prowlarr") -> None:
    """Prowlarr v1 API surface used by the app."""

    async def indexers(_: web.Request) -> web.Response:
        return web.json_response(mock.state["indexers"])

    async def search(_: web.Request) -> web.Response:
        return web.json_response(mock.state["search_results"])

    async def grab(_: web.Request) -> web.Response:
        return web.json_response(
            mock.state["grab_body"], status=mock.state["grab_status"]
        )

    async def torrent(_: web.Request) -> web.Response:
        redirect = mock.state["torrent_redirect"]
        if redirect is not None:
            return web.Response(status=302, headers={"Location": redirect})
        return web.Response(
            body=mock.state["torrent"],
            content_type="application/x-bittorrent",
        )

    mock.add("GET", f"{prefix}/api/v1/indexer", indexers)
    mock.add("GET", f"{prefix}/api/v1/search", search)
    mock.add("POST", f"{prefix}/api/v1/search", grab)
    mock.add("GET", f"{prefix}/download/{{name}}", torrent)


def install_chaptarr(mock: MockServer, prefix: str = "/chaptarr") -> None:
    """Readarr-compatible surface for the planned Chaptarr integration.

    Reuses the Prowlarr-shaped handlers so a future Chaptarr client can be
    exercised against the same fixtures.
    """

    install_prowlarr(mock, prefix=prefix)

    async def status(_: web.Request) -> web.Response:
        return web.json_response({"version": "mock", "appName": "Chaptarr"})

    mock.add("GET", f"{prefix}/api/v1/system/status", status)


def install_notifications(mock: MockServer, prefix: str = "/notify") -> None:
    async def receive(request: web.Request) -> web.Response:
        mock.state["notification_payloads"].append(
            {
                "path": request.path,
                "headers": dict(request.headers),
                "body": await request.read(),
            }
        )
        return web.Response(status=mock.state["notification_status"], text="ok")

    mock.add("POST", f"{prefix}/{{name:.*}}", receive)


def install_audiobookshelf(mock: MockServer, prefix: str = "/abs") -> None:
    async def libraries(_: web.Request) -> web.Response:
        return web.json_response({"libraries": mock.state["abs_libraries"]})

    async def scan(_: web.Request) -> web.Response:
        return web.json_response({})

    async def items(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "mediaType": "book",
                "results": [
                    {
                        "id": "item-1",
                        "mediaType": "book",
                        "media": {
                            "duration": 3600,
                            "metadata": {
                                "title": DEFAULT_SEARCH_TERM,
                                "subtitle": None,
                                "authorName": "Mock Author",
                                "narratorName": "Mock Narrator",
                                "publishedDate": "2026-01-01",
                                "asin": "B00TEST01",
                            },
                        },
                    }
                ],
            }
        )

    async def search(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "book": [
                    {
                        "libraryItem": {
                            "id": "item-1",
                            "mediaType": "book",
                            "media": {
                                "id": "item-1",
                                "metadata": {
                                    "title": DEFAULT_SEARCH_TERM,
                                    "subtitle": None,
                                    "authors": [
                                        {"id": "author-1", "name": "Mock Author"}
                                    ],
                                },
                            },
                        }
                    }
                ]
            }
        )

    async def cover(_: web.Request) -> web.Response:
        return web.Response(body=b"\x89PNG\r\n", content_type="image/png")

    mock.add("GET", f"{prefix}/api/libraries", libraries)
    mock.add("POST", f"{prefix}/api/libraries/{{id}}/scan", scan)
    mock.add("GET", f"{prefix}/api/libraries/{{id}}/items", items)
    mock.add("GET", f"{prefix}/api/libraries/{{id}}/search", search)
    mock.add("GET", f"{prefix}/api/items/{{id}}/cover", cover)


def install_oidc(mock: MockServer, prefix: str = "/oidc") -> None:
    base = mock.base_url

    async def config(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "issuer": base,
                "authorization_endpoint": f"{base}{prefix}/authorize",
                "token_endpoint": f"{base}{prefix}/token",
                "userinfo_endpoint": f"{base}{prefix}/userinfo",
                "end_session_endpoint": f"{base}{prefix}/logout",
                "scopes_supported": ["openid", "profile", "email"],
                "claims_supported": [
                    "sub",
                    "preferred_username",
                    "groups",
                ],
            }
        )

    async def token(_: web.Request) -> web.Response:
        return web.json_response(
            {"access_token": "mock-access-token", "expires_in": 3600}
        )

    async def userinfo(_: web.Request) -> web.Response:
        return web.json_response(mock.state["oidc_userinfo"])

    mock.add("GET", f"{prefix}/config", config)
    mock.add("POST", f"{prefix}/token", token)
    mock.add("GET", f"{prefix}/userinfo", userinfo)
