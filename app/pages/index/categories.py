from htpy import a, div, fragment, h2

from app.components.book_card import book_card
from app.internal.env_settings import Settings
from app.internal.models import Audiobook


def categories():
    base_url = Settings().app.base_url
    return div(
        hx_get=f"{base_url}/hx/categories",
        hx_trigger="load",
        hx_swap="outerHTML",
    )


def categories_hx(*, recommendations: dict[str, list[Audiobook]]):
    base_url = Settings().app.base_url

    def category_title(key: str) -> str:
        match key:
            case "trending":
                return "Trending This Week"
            case "fiction":
                return "Fiction & Literature"
            case "biography":
                return "Biography & History"
            case "science":
                return "Science & Technology"
            case "recent_releases":
                return "New Releases"
            case _:
                return key.capitalize()

    def search_link(key: str) -> str:
        match key:
            case "trending":
                return "trending"
            case "fiction":
                return "fiction"
            case "biography":
                return "biography"
            case "science":
                return "science"
            case "recent_releases":
                return "new+release"
            case _:
                return key.lower().replace(" ", "+")

    return fragment[
        (
            div(".w-full.max-w-7xl.mb-8")[
                div(".flex.justify-between.items-center.mb-4")[
                    h2(".text-2xl.font-bold")[category_title(category)],
                    a(
                        ".link.link-primary",
                        href=f"{base_url}/search?q={search_link(category)}",
                    )["View all →"],
                ],
                div(".overflow-x-auto")[
                    div(".flex.gap-4.pb-4", style="width: max-content;")[
                        (
                            div(".flex.gap-4.pb-4")[
                                div(
                                    ".flex-none.w-32.sm:w-40",
                                )[book_card(book=book)]
                            ]
                            for book in books
                        )
                    ]
                ],
            ]
            for category, books in recommendations.items()
        )
    ]
