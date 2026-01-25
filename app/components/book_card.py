from htpy import a, button, div, img, span

from app.components.icons.checkmark import checkmark_icon
from app.components.icons.download import download_icon
from app.components.icons.plus import plus_icon
from app.internal.auth.authentication import DetailedUser
from app.internal.env_settings import Settings
from app.internal.models import Audiobook
from app.components.icons.photo_off import photo_off_icon


def book_card(
    *,
    book: Audiobook,
    already_requested: bool = False,
    auto_download_enabled: bool = False,
    user: DetailedUser | None = None,
):
    base_url = Settings().app.base_url

    if book.downloaded or already_requested:
        icon = checkmark_icon()
        color = ".btn-ghost.bg-success.text-neutral/20"
    elif auto_download_enabled and user and user.can_download():
        icon = download_icon()
        color = ".btn-info"
    else:
        icon = plus_icon()
        color = ".btn-info"

    return div(".flex.flex-col.book-card")[
        div(
            ".relative.w-32.h-32.sm:w-40.sm:h-40.rounded-md.overflow-hidden.shadow.shadow-black.items-center.justify-center.flex"
        )[
            img(
                ".object-cover.w-full.h-full.hover:scale-110.transition-transform.duration-500.ease-in-out",
                height="128",
                width="128",
                src=book.cover_image,
                alt=book.title,
            )
            if book.cover_image
            else photo_off_icon(),
            # request button
            button(
                f"{color}.absolute.top-0.right-0.rounded-none.rounded-bl-md.btn-sm.btn.btn-square.items-center.justify-center.flex",
                hx_post=f"{base_url}/search/hx/request/{book.asin}",
                hx_swap="outerHTML",
                hx_target="closest .book-card",
                disabled=book.downloaded or already_requested,
            )[icon],
        ],
        # book info
        a(
            ".text-sm.text-primary.font-bold.pt-1.line-clamp-2",
            href=f"https://audible.com/pd/{book.asin}?ipRedirectOverride=true",
            title=book.title,
            target="_blank",
        )[book.title],
        div(".opacity-60.font-semibold.text-xs.line-clamp-1", title=book.subtitle)[
            book.subtitle
        ],
        # authors
        div(
            ".text-xs.font-semibold.line-clamp-1",
            title=", ".join(book.authors),
        )[
            (
                a(
                    ".hover:underline",
                    href=f"{base_url}/search?q={author}",
                    title=f"Search for books by {author}",
                )[
                    f"{author}{',' if i < len(book.authors) - 1 else ''}",
                    (
                        span(".opacity-60")[f"{len(book.authors)} more"]
                        if len(book.authors) > 2
                        else None
                    ),
                ]
                for i, author in enumerate(book.authors[:2])
            )
        ],
        # runtime
        div(".text-xs.opacity-60.mt-1")[f"{book.runtime_length_hrs}h"],
    ]
