from typing import Literal, final


@final
class ToastException(Exception):
    """Shows a toast on the frontend if raised on an HTMX endpoint"""

    def __init__(
        self,
        message: str,
        type: Literal["error", "success", "info"] = "error",
        cause_refresh: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.type = type
        self.force_refresh = cause_refresh
