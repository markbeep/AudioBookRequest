from typing import final
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.util.time import Second


@final
class DynamicSessionMiddleware:
    """
    A wrapper around the Starlette SessionMiddleware with the ability to
    change options during run-time
    https://www.starlette.io/middleware/#sessionmiddleware
    """

    def __init__(
        self,
        app: ASGIApp,
        secret_key: str,
        linker: "DynamicMiddlewareLinker",
        max_age: Second | None = None,
    ):
        self.app = app
        self.secret_key = secret_key
        self.expiry = max_age
        self.session_middleware = SessionMiddleware(
            app,
            secret_key,
            same_site="strict",
            max_age=max_age or Second(60 * 60 * 24 * 14),
        )
        linker.add_middleware(self)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        return await self.session_middleware(scope, receive, send)

    def update_secret(self, secret_key: str):
        self.secret_key = secret_key
        self.session_middleware = SessionMiddleware(
            self.app,
            secret_key,
            same_site="strict",
            max_age=self.expiry,
        )

    def update_max_age(self, max_age: Second):
        self.expiry = max_age
        self.session_middleware = SessionMiddleware(
            self.app,
            self.secret_key,
            same_site="strict",
            max_age=max_age,
        )


class DynamicMiddlewareLinker:
    """
    Linker is passed in as an argument to the DynamicSessionMiddleware so
    wherever FastAPI initializes the middleware, we can update
    the options to take effect immediately instead of having to restart the server
    """

    def __init__(self) -> None:
        self.middlewares: list[DynamicSessionMiddleware] = []

    def add_middleware(self, middleware: DynamicSessionMiddleware):
        self.middlewares.append(middleware)

    def update_secret(self, secret_key: str):
        for middleware in self.middlewares:
            middleware.update_secret(secret_key)

    def update_max_age(self, expiry: Second):
        for middleware in self.middlewares:
            middleware.update_max_age(expiry)


middleware_linker = DynamicMiddlewareLinker()
