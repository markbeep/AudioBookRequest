import json

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError


async def model_from_request[T: BaseModel](request: Request, model: type[T]) -> T:
    """Parse a JSON object or form body into `model`, based on the content type."""
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body: object = await request.json()  # pyright: ignore[reportAny]
        except json.JSONDecodeError as e:
            raise RequestValidationError(
                [
                    {
                        "type": "json_invalid",
                        "loc": ("body",),
                        "msg": "Invalid JSON body",
                        "input": None,
                    }
                ]
            ) from e
        if not isinstance(body, dict):
            raise RequestValidationError(
                [
                    {
                        "type": "model_attributes_type",
                        "loc": ("body",),
                        "msg": "Body must be a JSON object",
                        "input": body,
                    }
                ]
            )
        try:
            return model.model_validate(body)
        except ValidationError as e:
            raise RequestValidationError(e.errors()) from e

    try:
        return model.model_validate(await request.form())
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from e


def form_or_json_openapi(model: type[BaseModel]) -> dict[str, object]:
    """Describe a route body that accepts either JSON or form encoding."""
    schema: dict[str, object] = model.model_json_schema()
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": schema},
                "application/x-www-form-urlencoded": {"schema": schema},
            },
        }
    }
