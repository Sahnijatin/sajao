"""One error shape for every non-2xx response: {"error": {"code", "message"}}."""

from starlette.requests import Request
from starlette.responses import JSONResponse


def error_response(status_code: int, code: str, message: str, **extra: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, **extra}},
    )


class ApiError(Exception):
    """Raise from a handler or dependency to return the standard error shape."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


async def api_error_handler(_request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ApiError)  # noqa: S101
    return error_response(error.status_code, error.code, error.message)
