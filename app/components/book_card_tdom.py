from dataclasses import dataclass
from tdom import Node, html

from app.components.icons.checkmark import checkmark_icon
from app.components.icons.download import download_icon
from app.components.icons.plus import plus_icon
from app.internal.auth.authentication import DetailedUser
from app.internal.env_settings import Settings
from app.internal.models import Audiobook
from app.components.icons.photo_off import photo_off_icon


@dataclass
class BookCard:
    book: Audiobook
    already_requested: bool = False
    auto_download_enabled: bool = False
    user: DetailedUser | None = None

    def __call__(self) -> Node:
        base_url = Settings().app.base_url

        request_btn_classes = [
            "absolute",
            "top-0",
            "right-0",
            "rounded-none",
            "rounded-bl-md",
            "btn-sm",
            "btn",
            "btn-square",
            "items-center",
            "justify-center",
            "flex",
        ]
        if self.book.downloaded or self.already_requested:
            icon = checkmark_icon()
            request_btn_classes += ["btn-ghost", "bg-success", "text-neutral/20"]
        elif self.auto_download_enabled and self.user and self.user.can_download():
            icon = download_icon()
            request_btn_classes += ["btn-primary"]
        else:
            icon = plus_icon()
            request_btn_classes += ["btn-info"]

        cover_image = (
            t'<img class="object-cover w-full h-full hover:scale-110 transition-transform duration-500 ease-in-out" height="128" width="128" src="{self.book.cover_image}" alt="{self.book.title}" />'
            if self.book.cover_image
            else photo_off_icon()
        )

        authors = [
            html(t"""
            <a href="{base_url}/search?q={author}" title="Search for {author}" class="hover:underline">
                {author}{"," if i < len(self.book.authors) - 1 else ""})
            </a>""")
            for i, author in enumerate(self.book.authors[:2])
        ]
        if len(self.book.authors) > 2:
            authors.append(
                html(
                    t'<span class="opacity-60">+{len(self.book.authors) - 2} more</span>'
                )
            )

        return html(t"""
            <div class="book-card flex flex-col">
                <div
                    class="relative w-32 h-32 sm:w-40 sm:h-40 rounded-md overflow-hidden shadow shadow-black items-center justify-center flex">
                    {cover_image}

                    <!-- Request Button -->
                    <button
                        class="{request_btn_classes}"
                        hx-post="{base_url}/search/hx/request/{self.book.asin}"
                        hx-disabled-elt="this"
                        hx-target="closest div.book-card"
                        hx-swap="outerHTML"
                        disabled={self.book.downloaded or self.already_requested}
                    >
                        {icon:unsafe}
                    </button>
                </div>

                <!-- Book Info -->
                <a class="text-sm text-primary font-bold pt-1 line-clamp-2" title="{self.book.title}" target="_blank"
                    href="https://audible.com/pd/{self.book.asin}?ipRedirectOverride=true"
                    title={self.book.title}
                >
                    {self.book.title}
                </a>

                {t'<div class="opacity-60 font-semibold text-xs" title="{self.book.subtitle}">{self.book.subtitle}</div>' if self.book.subtitle else ""}

                <div class="text-xs font-semibold line-clamp-1" title="Authors: {", ".join(self.book.authors)}">
                    {authors}
                </div>

                <!-- Runtime -->
                <div class="text-xs opacity-60 mt-1">
                    {self.book.runtime_length_hrs}h
                </div>
            </div>
        """)
