"""Smoke tests for the reusable external-service doubles."""

from __future__ import annotations

from typing import cast

import aiohttp
import pytest

from tests.mock_services import MockServer


@pytest.mark.anyio
async def test_prowlarr_double(mock_server: MockServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{mock_server.base_url}/prowlarr/api/v1/indexer") as r:
            assert r.status == 200
            data = cast(object, await r.json())
            assert isinstance(data, list)
            indexers = cast(list[object], data)
            first = cast(dict[str, object], indexers[0])
            assert first["name"] == "MockIndexer"

        async with session.get(
            f"{mock_server.base_url}/prowlarr/api/v1/search", params={"query": "x"}
        ) as r:
            assert r.status == 200
            data = cast(object, await r.json())
            assert isinstance(data, list)
            assert len(cast(list[object], data)) == 1


@pytest.mark.anyio
async def test_chaptarr_double(mock_server: MockServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{mock_server.base_url}/chaptarr/api/v1/system/status"
        ) as r:
            assert r.status == 200
            data = cast(object, await r.json())
            assert isinstance(data, dict)
            status = cast(dict[str, object], data)
            assert status["appName"] == "Chaptarr"

        async with session.get(f"{mock_server.base_url}/chaptarr/api/v1/indexer") as r:
            assert r.status == 200


@pytest.mark.anyio
async def test_notification_double(mock_server: MockServer) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{mock_server.base_url}/notify/test", json={"hello": "world"}
        ) as r:
            assert r.status == 200

    assert mock_server.requests_to("/notify/test")
    assert (
        mock_server.state["notification_payloads"][-1]["body"] == b'{"hello": "world"}'
    )
