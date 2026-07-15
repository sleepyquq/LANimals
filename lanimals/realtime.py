"""In-process WebSocket fan-out for LANimals."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import WebSocket


class RealtimeHub:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, session_token: str) -> None:
        await websocket.accept()
        self._connections[websocket] = session_token

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    async def broadcast(
        self,
        payload: dict[str, object],
        *,
        session_is_valid: Callable[[str], bool],
    ) -> None:
        failed: list[WebSocket] = []
        for connection, session_token in tuple(self._connections.items()):
            try:
                if not session_is_valid(session_token):
                    await connection.close(code=4401)
                    failed.append(connection)
                    continue
                await connection.send_json(payload)
            except Exception:
                failed.append(connection)
        for connection in failed:
            self.disconnect(connection)
