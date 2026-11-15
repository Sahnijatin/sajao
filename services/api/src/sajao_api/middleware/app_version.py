"""Minimum app version: old apps are told to update instead of failing oddly."""

import re

from starlette.types import ASGIApp, Receive, Scope, Send

from sajao_api.errors import error_response

APP_VERSION_HEADER = "x-app-version"
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION.match(text)
    if match is None:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return (major, minor, patch)


class MinimumAppVersionMiddleware:
    """Checks X-App-Version when a client sends it. Web and admin clients do not."""

    def __init__(self, app: ASGIApp, minimum: str) -> None:
        parsed = parse_version(minimum)
        if parsed is None:
            raise ValueError(f"Invalid minimum app version: {minimum!r}")
        self.app = app
        self.minimum = parsed
        self.minimum_text = minimum

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            raw = dict(scope["headers"]).get(APP_VERSION_HEADER.encode())
            if raw is not None:
                version = parse_version(raw.decode("latin-1"))
                if version is None:
                    response = error_response(
                        400, "invalid_app_version", "X-App-Version must look like 1.2.3."
                    )
                    await response(scope, receive, send)
                    return
                if version < self.minimum:
                    response = error_response(
                        426,
                        "app_update_required",
                        "Please update the app to continue.",
                        min_version=self.minimum_text,
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)
