from fastapi.testclient import TestClient

from lanimals.main import create_app


def test_logged_in_websocket_receives_new_text_message(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        assert browser.post(
            "/api/login", json={"password": "shared-secret", "incognito": False}
        ).status_code == 200

        with browser.websocket_connect("/ws") as websocket:
            assert websocket.receive_json()["type"] == "connected"
            sent = browser.post("/api/messages", json={"body": "实时消息"})
            event = websocket.receive_json()

        assert sent.status_code == 201
        assert event["type"] == "message_created"
        assert event["message"]["body"] == "实时消息"


def test_websocket_without_login_is_rejected(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        try:
            with browser.websocket_connect("/ws"):
                raise AssertionError("unauthenticated websocket unexpectedly connected")
        except Exception as error:
            assert getattr(error, "code", None) == 4401
