from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from lanimals.cli import change_password
from lanimals.config import create_config, load_config
from lanimals.main import create_app


def test_host_password_rotation_is_immediate_and_revokes_existing_sessions(tmp_path):
    create_config(tmp_path, password="old-password")
    app = create_app(
        data_dir=tmp_path,
        password_hash_provider=lambda: load_config(tmp_path).password_hash,
    )

    with TestClient(app) as browser:
        assert browser.post(
            "/api/login", json={"password": "old-password", "incognito": False}
        ).status_code == 200
        assert browser.get("/api/me").status_code == 200

        change_password(tmp_path, "new-password")

        assert browser.get("/api/me").status_code == 401
        assert browser.post(
            "/api/login", json={"password": "old-password", "incognito": False}
        ).status_code == 401
        assert browser.post(
            "/api/login", json={"password": "new-password", "incognito": False}
        ).status_code == 200


def test_password_rotation_stops_old_websocket_from_receiving_new_messages(tmp_path):
    create_config(tmp_path, password="old-password")
    app = create_app(
        data_dir=tmp_path,
        password_hash_provider=lambda: load_config(tmp_path).password_hash,
    )

    with TestClient(app) as old_browser, TestClient(app) as new_browser:
        assert old_browser.post(
            "/api/login", json={"password": "old-password", "incognito": False}
        ).status_code == 200
        with old_browser.websocket_connect("/ws") as websocket:
            assert websocket.receive_json()["type"] == "connected"
            change_password(tmp_path, "new-password")
            assert new_browser.post(
                "/api/login", json={"password": "new-password", "incognito": False}
            ).status_code == 200
            assert new_browser.post("/api/messages", json={"body": "轮换后的消息"}).status_code == 201
            try:
                websocket.receive_json()
                raise AssertionError("revoked websocket received a message")
            except WebSocketDisconnect as error:
                assert error.code == 4401
