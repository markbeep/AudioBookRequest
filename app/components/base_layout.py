from htpy import (
    Node,
    a,
    body,
    button,
    div,
    head,
    header,
    html,
    link,
    meta,
    nav,
    script,
    span,
    title,
    with_children,
)
from markupsafe import Markup

from app.components.icons.door_exit import door_exit_icon
from app.components.icons.gift import gift_icon
from app.components.icons.gift_solid import gift_solid_icon
from app.components.icons.moon import moon_icon
from app.components.icons.search import search_icon
from app.components.icons.settings import settings_icon
from app.components.icons.sun import sun_icon
from app.components.toast_script import toast_script
from app.internal.env_settings import Settings

with open("app/components/scripts/theme.js", "r") as f:
    theme_script = f.read()


@with_children
def base_layout(
    children: Node,
    *,
    user_can_logout: bool,
    hide_navbar: bool = False,
    meta_title: str = "AudioBookRequest",
    meta_description: str = "AudioBookRequest - Your platform for managing audiobook requests.",
):
    base_url = Settings().app.base_url
    version = Settings().app.version

    if hide_navbar:
        navbar = None
    else:
        logout_button = (
            button(
                ".button.btn-ghost.btn-square",
                hx_post=f"{base_url}/auth/logout",
                title="Logout",
            )[door_exit_icon()]
            if user_can_logout
            else None
        )

        navbar = header(".shadow-lg")[
            nav(".navbar")[
                div(".flex-1")[
                    a(
                        ".btn.btn-ghost.text-lg.hidden.sm:inline-flex",
                        preload=True,
                        href=f"{base_url}/",
                    )["AudioBookRequest"],
                    a(
                        ".btn.btn-ghost.text-lg.sm:hidden",
                        preload=True,
                        href=f"{base_url}/",
                    )["ABR"],
                    a(
                        ".btn.btn-ghost.btn-square",
                        preload=True,
                        href=f"{base_url}/search",
                        title="Search",
                    )[search_icon()],
                    a(
                        ".btn.btn-ghost.btn-square.group.relative",
                        preload=True,
                        href=f"{base_url}/wishlist",
                        title="Wishlist",
                    )[
                        span(
                            ".opacity-0.group-hover:opacity-100.absolute.left-2.top-2.transition-opacity.duration-500"
                        )[gift_solid_icon()],
                        span(
                            ".opacity-100.group-hover:opacity-0.absolute.left-2.top-2.transition-opacity.duration-500"
                        )[gift_icon()],
                    ],
                ],
                # right-aligned buttons
                div(".flex-none.flex.pr-4")[
                    button(
                        ".btn.btn-ghost.btn-square.light-dark-toggle",
                        onclick="toggleTheme()",
                    )[
                        span(".theme-dark.svg-dark")[moon_icon()],
                        span(".theme-light.svg-light")[sun_icon()],
                    ],
                    logout_button,
                    a(
                        ".btn.btn-ghost.btn-square.group",
                        preload=True,
                        href=f"{base_url}/settings/account",
                        title="Settings",
                    )[
                        span(
                            ".group-hover:rotate-90.transition-all.duration-500.ease-in-out"
                        )[settings_icon()]
                    ],
                ],
            ]
        ]

    return html(lang="en", data_theme="garden")[
        head[
            # meta
            meta(charset="UTF-8"),
            title[meta_title],
            meta(
                name="description",
                content=meta_description,
            ),
            meta(
                name="keywords",
                content="audiobooks, requests, wishlist, search, settings",
            ),
            meta(name="viewport", content="width=device-width, initial-scale=1"),
            # css/js
            link(
                rel="stylesheet",
                href=f"{base_url}/static/globals.css?v={version}",
            ),
            script(src=f"{base_url}/static/htmx.js?v={version}"),
            script(defer=True, src=f"{base_url}/static/htmx-preload.js?v={version}"),
            script[Markup(theme_script)],
            toast_script(base_url=base_url, version=version),
            # favicons
            link(
                rel="apple-touch-icon",
                sizes="180x180",
                href=f"{base_url}/static/apple-touch-icon.png?v={version}",
            ),
            link(
                rel="icon",
                sizes="any",
                type="image/svg+xml",
                href=f"{base_url}/static/favicon.svg?v={version}",
            ),
            link(
                rel="icon",
                type="image/png",
                sizes="32x32",
                href=f"{base_url}/static/favicon-32x32.png?v={version}",
            ),
            link(
                rel="icon",
                type="image/png",
                sizes="16x16",
                href=f"{base_url}/static/favicon-16x16.png?v={version}",
            ),
            link(
                rel="manifest",
                href=f"{base_url}/static/site.webmanifest?v={version}",
            ),
        ],
        body(".w-screen.min-h-screen.overflow-x-hidden", hx_ext="preload")[
            navbar, children
        ],
    ]
