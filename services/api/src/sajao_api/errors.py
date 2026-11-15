"""One error shape for every non-2xx response: {"error": {"code", "message"}}."""

from starlette.responses import JSONResponse


def error_response(status_code: int, code: str, message: str, **extra: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, **extra}},
    )
