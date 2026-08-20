from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: str | None = None,
        retryable: bool = False,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        self.retryable = retryable


def api_error(
    code: str,
    message: str,
    status_code: int = 400,
    details: str | None = None,
    retryable: bool = False,
) -> ApiError:
    return ApiError(code, message, status_code, details, retryable)


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    body = {
        "code": exc.code,
        "message": exc.message,
        "retryable": exc.retryable,
    }
    if exc.details:
        body["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=body)
