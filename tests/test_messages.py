from fastapi.testclient import TestClient

from lanimals.main import create_app


def login(client: TestClient) -> None:
    response = client.post("/api/login", json={"password": "shared-secret", "incognito": False})
    assert response.status_code == 200


def test_message_is_visible_to_another_logged_in_browser_and_survives_restart(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as sender, TestClient(app) as reader:
        login(sender)
        login(reader)
        send_response = sender.post("/api/messages", json={"body": "你好，局域网！"})
        history_response = reader.get("/api/messages")

    assert send_response.status_code == 201
    assert history_response.status_code == 200
    assert history_response.json()[0]["body"] == "你好，局域网！"
    assert "小" in history_response.json()[0]["sender_name"] or "獭" in history_response.json()[0]["sender_name"]

    restarted_app = create_app(data_dir=tmp_path, chat_password="shared-secret")
    with TestClient(restarted_app) as browser:
        login(browser)
        history_after_restart = browser.get("/api/messages")

    assert [message["body"] for message in history_after_restart.json()] == ["你好，局域网！"]


def test_blank_message_is_rejected(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        login(browser)
        response = browser.post("/api/messages", json={"body": "   "})

    assert response.status_code == 422
