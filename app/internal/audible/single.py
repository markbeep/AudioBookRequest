from aiohttp import ClientSession

from app.internal.audible.types import (
    AudibleSingleResponse,
    audible_region_type,
    audible_regions,
    get_region_from_settings,
)


async def get_single_book(
    client_session: ClientSession,
    asin: str,
    audible_region: audible_region_type | None = None,
):
    if audible_region is None:
        audible_region = get_region_from_settings()

    base_url = f"https://api.audible{audible_regions[audible_region]}/1.0/catalog/products/{asin}"
    params = {
        "asin": asin,
        "response_groups": ["media"],
    }

    async with client_session.get(
        base_url,
        params=params,
    ) as response:
        response.raise_for_status()
        product = AudibleSingleResponse.model_validate(await response.json())
        return product.product.to_audiobook()
