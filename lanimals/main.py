"""FastAPI application for LANimals."""

from __future__ import annotations

import hmac
import os
import secrets
import uuid
from pathlib import Path
from collections.abc import Callable

from fastapi import Cookie, FastAPI, File, Form, HTTPException, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from lanimals.config import verify_password
from lanimals.identity import DeviceRegistry
from lanimals.limits import UploadSizeLimitMiddleware
from lanimals.realtime import RealtimeHub
from lanimals.store import ChatStore


class LoginRequest(BaseModel):
    password: str
    incognito: bool = False


class MessageRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


def create_app(
    *,
    data_dir: Path,
    chat_password: str | None = None,
    password_hash: str | None = None,
    password_hash_provider: Callable[[], str] | None = None,
    max_upload_bytes: int = 2 * 1024**3,
) -> FastAPI:
    if chat_password is None and password_hash is None and password_hash_provider is None:
        raise ValueError("chat_password, password_hash, or password_hash_provider is required")
    data_dir = Path(data_dir)
    uploads_dir = data_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    registry = DeviceRegistry(data_dir / "chat.db")
    chat_store = ChatStore(data_dir / "chat.db")
    hub = RealtimeHub()
    app = FastAPI(title="LANimals", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        UploadSizeLimitMiddleware,
        max_file_bytes=max_upload_bytes,
        session_is_valid=lambda token: registry.session_identity(token) is not None,
    )
    web_dir = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    def require_identity(session_token: str | None) -> tuple[str, bool]:
        if not session_token:
            raise HTTPException(status_code=401, detail="请先登录")
        identity = registry.session_identity(session_token)
        if not identity:
            raise HTTPException(status_code=401, detail="会话已失效，请重新登录")
        return identity

    @app.get("/", include_in_schema=False)
    def web_client():
        return FileResponse(web_dir / "index.html", media_type="text/html")

    @app.post("/api/login")
    def login(
        payload: LoginRequest,
        response: Response,
        device_token: str | None = Cookie(default=None, alias="lan_device"),
        temp_device_token: str | None = Cookie(default=None, alias="lan_temp_device"),
    ):
        if chat_password is not None:
            password_matches = hmac.compare_digest(payload.password, chat_password)
        else:
            active_hash = password_hash_provider() if password_hash_provider is not None else (password_hash or "")
            password_matches = verify_password(payload.password, active_hash)
        if not password_matches:
            raise HTTPException(status_code=401, detail="群聊密码不正确")

        temporary = payload.incognito
        if temporary:
            active_device_token = temp_device_token or secrets.token_urlsafe(32)
        else:
            active_device_token = device_token or secrets.token_urlsafe(32)
        name = registry.get_or_create(active_device_token, temporary=temporary)
        session_token = registry.create_session(active_device_token)

        response.set_cookie("lan_session", session_token, httponly=True, samesite="lax")
        if temporary:
            response.set_cookie("lan_temp_device", active_device_token, httponly=True, samesite="lax")
        else:
            response.set_cookie(
                "lan_device",
                active_device_token,
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 365,
            )
        return {"name": name, "temporary": temporary, "max_upload_bytes": max_upload_bytes}

    @app.get("/api/me")
    def me(lan_session: str | None = Cookie(default=None)):
        name, temporary = require_identity(lan_session)
        return {"name": name, "temporary": temporary, "max_upload_bytes": max_upload_bytes}

    @app.post("/api/messages", status_code=201)
    async def create_message(payload: MessageRequest, lan_session: str | None = Cookie(default=None)):
        sender_name, _ = require_identity(lan_session)
        body = payload.body.strip()
        if not body:
            raise HTTPException(status_code=422, detail="消息不能只包含空白字符")
        message = chat_store.create_message(sender_name=sender_name, body=body)
        await hub.broadcast(
            {"type": "message_created", "message": message},
            session_is_valid=lambda token: registry.session_identity(token) is not None,
        )
        return message

    @app.get("/api/messages")
    def list_messages(
        before: int | None = None,
        limit: int = 100,
        lan_session: str | None = Cookie(default=None),
    ):
        require_identity(lan_session)
        return chat_store.list_messages(before=before, limit=limit)

    @app.post("/api/files", status_code=201)
    async def upload_file(
        file: UploadFile = File(...),
        body: str = Form(default=""),
        lan_session: str | None = Cookie(default=None),
    ):
        sender_name, _ = require_identity(lan_session)
        body = body.strip()
        if len(body) > 4000:
            raise HTTPException(status_code=422, detail="消息不能超过 4000 个字符")
        original_name = Path(file.filename or "unnamed-file").name.replace("\x00", "")[:255] or "unnamed-file"
        attachment_id = uuid.uuid4().hex
        storage_name = f"{attachment_id}.bin"
        temporary_path = uploads_dir / f".{storage_name}.part"
        final_path = uploads_dir / storage_name
        size = 0

        try:
            with temporary_path.open("wb") as destination:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_upload_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"文件超过服务器设置的单文件上限（{max_upload_bytes} 字节）",
                        )
                    destination.write(chunk)
            os.replace(temporary_path, final_path)
            try:
                message = chat_store.create_file_message(
                    attachment_id=attachment_id,
                    sender_name=sender_name,
                    body=body,
                    storage_name=storage_name,
                    original_name=original_name,
                    content_type=file.content_type or "application/octet-stream",
                    size=size,
                )
                await hub.broadcast(
                    {"type": "message_created", "message": message},
                    session_is_valid=lambda token: registry.session_identity(token) is not None,
                )
                return message
            except Exception:
                final_path.unlink(missing_ok=True)
                raise
        finally:
            temporary_path.unlink(missing_ok=True)
            await file.close()

    @app.get("/api/files/{attachment_id}")
    def download_file(attachment_id: str, lan_session: str | None = Cookie(default=None)):
        require_identity(lan_session)
        attachment = chat_store.get_attachment(attachment_id)
        if not attachment:
            raise HTTPException(status_code=404, detail="文件不存在")
        path = uploads_dir / str(attachment["storage_name"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="文件已从服务器磁盘移除")
        return FileResponse(
            path,
            media_type=str(attachment["content_type"]),
            filename=str(attachment["original_name"]),
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.websocket("/ws")
    async def realtime(websocket: WebSocket):
        session_token = websocket.cookies.get("lan_session")
        if not session_token or not registry.session_identity(session_token):
            await websocket.close(code=4401)
            return
        await hub.connect(websocket, session_token)
        await websocket.send_json({"type": "connected"})
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            hub.disconnect(websocket)

    return app
