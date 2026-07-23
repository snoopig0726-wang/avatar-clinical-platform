from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers or {}
        super().__init__(message)


def error_payload(request: Request, error: ApiError) -> dict[str, Any]:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "request_id": getattr(request.state, "request_id", "unknown"),
            "details": error.details,
        }
    }


async def api_error_handler(request: Request, error: ApiError) -> JSONResponse:
    return JSONResponse(
        error_payload(request, error),
        status_code=error.status_code,
        headers=error.headers,
    )


async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    api_error = ApiError(
        422,
        "VALIDATION_ERROR",
        "请求字段不符合接口约束",
        {"fields": [".".join(map(str, item["loc"])) for item in error.errors()]},
    )
    return JSONResponse(error_payload(request, api_error), status_code=422)
