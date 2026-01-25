from htpy import a, div, h2, p, span

from app.components.book_card import book_card
from app.internal.recommendations.local import AudiobookPopularity
from app.internal.recommendations.user_recommendations import UserSimsRecommendation


def for_you(*, title: str, description: str, hx_get: str, link: str | None = None):
    return div(".w-full.max-w-7xl.mb-8")[
        div(".flex.justify-between.items-center.mb-4")[
            div[
                h2(".text-2xl.font-bold")[title],
                p(".text-sm.opacity-70")[description],
            ],
            (a(".link.link-primary", href=link)["Discover more →"] if link else None),
        ],
        div(".overflow-x-auto")[
            div(
                ".w-full.max-w-7xl.mb-8",
                hx_get=hx_get,
                hx_trigger="load",
                hx_swap="outerHTML",
            )[
                div(".w-full.flex.justify-center")[
                    span(".loading.loading-dots.loading-xl")
                ]
            ]
        ],
    ]


def for_you_hx(*, recommendations: UserSimsRecommendation):
    if len(recommendations.recommendations) > 0:
        return [
            div(".flex.gap-4.pb-4")[
                (
                    div(
                        ".flex-none.w-32.sm:w-40",
                        title=f"{rec.reason}",
                    )[book_card(book=rec.book)]
                    for rec in recommendations.recommendations
                )
            ]
        ]
    else:
        return (
            div(".p-6.bg-base-200.rounded-md.text-center")[
                p(".text-sm.opacity-70")[
                    "No recommendations available at this time. Request some books to start getting recommendations."
                ]
            ],
        )


def popular_hx(*, popular: list[AudiobookPopularity]):
    if len(popular) > 0:
        return [
            (
                div(".flex.gap-4.pb-4")[
                    div(
                        ".flex-none.w-32.sm:w-40",
                        title=f"{rec.requested_amount()}",
                    )[book_card(book=rec.book)]
                ]
                for rec in popular
            )
        ]
    else:
        return (
            div(".p-6.bg-base-200.rounded-md.text-center")[
                p(".text-sm.opacity-70")[
                    "No popular recommendations available at this time. Get other users to request some books!"
                ]
            ],
        )
