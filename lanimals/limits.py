"""ASGI upload guards applied before multipart parsing."""

from __future__ import annotations

from collections.abc import Callable
from http.cookies import CookieError, SimpleCookie

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestTooLarge(Exception):
    pass


class UploadSizeLimitMiddleware:
    """Authenticate and bound raw uploads before Starlette creates temporary files."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_file_bytes: int,
        session_is_valid: Callable[[str], bool],
        multipart_overhead_bytes: int = 64 * 1024,
    ) -> None:
        self.app = app
        self.session_is_valid = session_is_valid
        self.max_request_bytes = max_file_bytes + multipart_overhead_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/api/files":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        session_token = self._session_token(headers.get(b"cookie", b""))
        if not session_token or not self.session_is_valid(session_token):
            await self._respond(
                scope,
                receive,
                send,
                status_code=401,
                detail="请先登录后上传文件（请求未解析）",
            )
            return

        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_request_bytes:
                    await self._reject_too_large(scope, receive, send)
                    return
            except ValueError:
                await self._reject_too_large(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_request_bytes:
                    raise RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            await self._reject_too_large(scope, receive, send)

    @staticmethod
    def _session_token(raw_cookie: bytes) -> str | None:
        cookies = SimpleCookie()
        try:
            cookies.load(raw_cookie.decode("latin-1"))
        except (CookieError, UnicodeDecodeError):
            return None
        morsel = cookies.get("lan_session")
        return morsel.value if morsel else None

    @classmethod
    async def _reject_too_large(cls, scope: Scope, receive: Receive, send: Send) -> None:
        await cls._respond(
            scope,
            receive,
            send,
            status_code=413,
            detail="上传请求体超过服务器允许的附件总大小上限",
        )

    @staticmethod
    async def _respond(
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        detail: str,
    ) -> None:
        response = JSONResponse({"detail": detail}, status_code=status_code)
        await response(scope, receive, send)
