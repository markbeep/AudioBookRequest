"""Typed accessors for TestClient responses.

`httpx2.Response.json()` is intentionally typed as `Any` because the payload is
arbitrary JSON. These helpers narrow it once at the boundary so tests stay typed.
"""

from typing import cast

from httpx2 import Response


def json_object(response: Response) -> dict[str, object]:
    value = cast(object, response.json())
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def json_list(response: Response) -> list[object]:
    value = cast(object, response.json())
    assert isinstance(value, list)
    return cast(list[object], value)


def as_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def as_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast(list[object], value)
