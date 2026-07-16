import sqlite3

from fastapi.testclient import TestClient

from lanimals.identity import DeviceRegistry
from lanimals.main import create_app
from lanimals.store import ChatStore


def login(client: TestClient) -> dict[str, object]:
    response = client.post("/api/login", json={"password": "shared-secret", "incognito": False})
    assert response.status_code == 200
    return response.json()


def test_message_is_visible_to_another_logged_in_browser_and_survives_restart(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as sender, TestClient(app) as reader:
        sender_identity = login(sender)
        login(reader)
        send_response = sender.post("/api/messages", json={"body": "你好，局域网！"})
        history_response = reader.get("/api/messages")

    assert send_response.status_code == 201
    assert history_response.status_code == 200
    assert history_response.json()[0]["body"] == "你好，局域网！"
    assert history_response.json()[0]["attachments"] == []
    assert history_response.json()[0]["attachment"] is None
    assert send_response.json()["sender_id"] == sender_identity["identity_id"]
    assert history_response.json()[0]["sender_id"] == sender_identity["identity_id"]
    assert "小" in history_response.json()[0]["sender_name"] or "獭" in history_response.json()[0]["sender_name"]

    restarted_app = create_app(data_dir=tmp_path, chat_password="shared-secret")
    with TestClient(restarted_app) as browser:
        login(browser)
        history_after_restart = browser.get("/api/messages")

    assert [message["body"] for message in history_after_restart.json()] == ["你好，局域网！"]
    assert history_after_restart.json()[0]["sender_id"] == sender_identity["identity_id"]


def test_blank_message_is_rejected(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        login(browser)
        response = browser.post("/api/messages", json={"body": "   "})

    assert response.status_code == 422


def test_message_history_can_page_backward_and_forward_by_id(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        login(browser)
        created = [
            browser.post("/api/messages", json={"body": f"消息 {index}"}).json()
            for index in range(1, 7)
        ]

        latest = browser.get("/api/messages", params={"limit": 2})
        older = browser.get(
            "/api/messages",
            params={"limit": 2, "before": created[4]["id"]},
        )
        newer = browser.get(
            "/api/messages",
            params={"limit": 2, "after": created[1]["id"]},
        )
        conflicting = browser.get(
            "/api/messages",
            params={"before": created[4]["id"], "after": created[1]["id"]},
        )

    assert [message["body"] for message in latest.json()] == ["消息 5", "消息 6"]
    assert [message["body"] for message in older.json()] == ["消息 3", "消息 4"]
    assert [message["body"] for message in newer.json()] == ["消息 3", "消息 4"]
    assert conflicting.status_code == 400


def test_legacy_messages_are_backfilled_when_sender_name_maps_to_one_identity(tmp_path):
    database = tmp_path / "chat.db"
    registry = DeviceRegistry(database)
    name = registry.get_or_create("legacy-device", temporary=False)
    session = registry.create_session("legacy-device")
    identity = registry.session_identity(session)
    assert identity is not None
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_name TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            "INSERT INTO messages (sender_name, body, created_at) VALUES (?, '旧消息', '2026-01-01')",
            (name,),
        )

    history = ChatStore(database).list_messages()

    assert history[0]["sender_id"] == identity[2]
