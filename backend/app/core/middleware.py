from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import PianovaError, error_payload

MULTIPART_OVERHEAD_BYTES = 1024 * 1024


class RequestBodyTooLarge(Exception):
    pass


class UploadSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_upload_bytes: int, max_upload_mb: int) -> None:
        self.app = app
        self.max_request_bytes = max_upload_bytes + MULTIPART_OVERHEAD_BYTES
        self.max_upload_mb = max_upload_mb

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or not str(scope.get("path", "")).endswith("/upload")
        ):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length and int(content_length) > self.max_request_bytes:
            await self._reject(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_request_bytes:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content=error_payload(
                PianovaError(
                    code="upload_too_large",
                    message=f"The upload exceeds the {self.max_upload_mb} MB limit.",
                    status_code=413,
                )
            ),
        )
        await response(scope, receive, send)
