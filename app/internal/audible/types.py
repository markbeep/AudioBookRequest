from abc import ABCMeta, abstractmethod
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from typing_extensions import override

from app.internal.env_settings import Settings
from app.internal.models import Audiobook

REFETCH_TTL = 60 * 60 * 24 * 7  # 1 week

audible_region_type = Literal[
    "us",
    "ca",
    "uk",
    "au",
    "fr",
    "de",
    "jp",
    "it",
    "in",
    "es",
    "br",
]
audible_regions: dict[audible_region_type, str] = {
    "us": ".com",
    "ca": ".ca",
    "uk": ".co.uk",
    "au": ".com.au",
    "fr": ".fr",
    "de": ".de",
    "jp": ".co.jp",
    "it": ".it",
    "in": ".in",
    "es": ".es",
    "br": ".com.br",
}


def get_region_from_settings() -> audible_region_type:
    region = Settings().app.default_region
    if region not in audible_regions:
        return "us"
    return region


def get_region_tld_from_settings() -> str:
    region = get_region_from_settings()
    return audible_regions[region]


class AudibleProduct(BaseModel):
    class _Author(BaseModel):
        name: str

    asin: str
    authors: list[_Author] = []
    narrators: list[_Author] = []
    product_images: dict[str, str] = {}
    runtime_length_min: int = 0
    release_date: str
    title: str
    subtitle: str | None = None

    def to_audiobook(self) -> Audiobook:
        return Audiobook(
            asin=self.asin,
            title=self.title,
            subtitle=self.subtitle,
            authors=[author.name for author in self.authors],
            narrators=[narrator.name for narrator in self.narrators],
            cover_image=self.product_images.get("500")
            or list(self.product_images.values())[0],
            release_date=datetime.fromisoformat(self.release_date),
            runtime_length_min=self.runtime_length_min,
        )


class _Response(BaseModel, metaclass=ABCMeta):
    @abstractmethod
    def audiobooks(self) -> list[Audiobook]:
        pass


class AudibleSearchResponse(_Response):
    products: list[AudibleProduct]

    @override
    def audiobooks(self) -> list[Audiobook]:
        return [product.to_audiobook() for product in self.products]


class AudibleSimilarResponse(_Response):
    similar_products: list[AudibleProduct]

    @override
    def audiobooks(self) -> list[Audiobook]:
        return [sim.to_audiobook() for sim in self.similar_products]


class AudibleSingleResponse(_Response):
    product: AudibleProduct

    @override
    def audiobooks(self) -> list[Audiobook]:
        return [self.product.to_audiobook()]
