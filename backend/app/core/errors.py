import logging
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PianovaError(Exception):
    code: str
    message: str
    status_code: int
    details: dict[str, object] | None = None


def error_payload(error: PianovaError) -> dict[str, object]:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "details": error.details or {},
        }
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PianovaError)
    async def handle_pianova_error(_request: Request, error: PianovaError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content=error_payload(error))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        safe_errors = [
            {
                "location": [str(part) for part in item["loc"]],
                "message": item["msg"],
                "type": item["type"],
            }
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload(
                PianovaError(
                    code="validation_error",
                    message="The request contains invalid data.",
                    status_code=422,
                    details={"fields": safe_errors},
                )
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, error: Exception) -> JSONResponse:
        logger.exception("Unhandled API error", exc_info=error)
        return JSONResponse(
            status_code=500,
            content=error_payload(
                PianovaError(
                    code="internal_error",
                    message="An unexpected internal error occurred.",
                    status_code=500,
                )
            ),
        )
