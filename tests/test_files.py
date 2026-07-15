import sqlite3

from fastapi.testclient import TestClient

from lanimals.main import create_app
from lanimals.store import ChatStore


def login(client: TestClient) -> None:
    response = client.post("/api/login", json={"password": "shared-secret", "incognito": False})
    assert response.status_code == 200


def test_file_upload_is_persisted_and_downloadable_by_another_browser(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret", max_upload_bytes=1024)

    with TestClient(app) as sender, TestClient(app) as reader:
        login(sender)
        login(reader)
        uploaded = sender.post(
            "/api/files",
            data={"body": "这是附件说明"},
            files={"file": ("资料.txt", b"LANimals file content", "text/plain")},
        )
        history = reader.get("/api/messages")

        assert uploaded.status_code == 201
        attachment = uploaded.json()["attachment"]
        assert uploaded.json()["attachments"] == [attachment]
        assert attachment["original_name"] == "资料.txt"
        assert attachment["size"] == 21
        assert uploaded.json()["body"] == "这是附件说明"
        assert history.json()[-1]["attachment"]["id"] == attachment["id"]
        assert history.json()[-1]["attachments"] == [attachment]
        assert history.json()[-1]["body"] == "这是附件说明"

        downloaded = reader.get(f"/api/files/{attachment['id']}")
        assert downloaded.status_code == 200
        assert downloaded.content == b"LANimals file content"
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert downloaded.headers["content-disposition"].startswith("attachment;")
        assert "attachment" in downloaded.headers["content-disposition"]

    restarted = create_app(data_dir=tmp_path, chat_password="shared-secret", max_upload_bytes=1024)
    with TestClient(restarted) as browser:
        login(browser)
        history_after_restart = browser.get("/api/messages")
        attachment_id = history_after_restart.json()[-1]["attachment"]["id"]
        assert browser.get(f"/api/files/{attachment_id}").content == b"LANimals file content"


def test_multiple_files_are_one_atomic_message_and_duplicate_names_are_disambiguated(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret", max_upload_bytes=4096)

    with TestClient(app) as sender, TestClient(app) as reader:
        login(sender)
        login(reader)
        uploaded = sender.post(
            "/api/files",
            data={"body": "三份附件"},
            files=[
                ("files", ("报告.txt", b"first", "text/plain")),
                ("files", ("报告.TXT", b"second", "text/plain")),
                ("files", ("图片.png", b"third", "image/png")),
            ],
        )

        assert uploaded.status_code == 201
        message = uploaded.json()
        assert message["body"] == "三份附件"
        assert [item["original_name"] for item in message["attachments"]] == [
            "报告.txt",
            "报告 (2).TXT",
            "图片.png",
        ]
        assert message["attachment"] == message["attachments"][0]

        history = reader.get("/api/messages", params={"limit": 1}).json()
        assert len(history) == 1
        assert history[0]["attachments"] == message["attachments"]
        assert [reader.get(f"/api/files/{item['id']}").content for item in message["attachments"]] == [
            b"first",
            b"second",
            b"third",
        ]


def test_more_than_twelve_attachments_are_rejected_without_history_or_orphans(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret", max_upload_bytes=4096)

    with TestClient(app) as browser:
        login(browser)
        response = browser.post(
            "/api/files",
            files=[("files", (f"{index}.txt", b"", "text/plain")) for index in range(13)],
        )

        assert response.status_code == 422
        assert browser.get("/api/messages").json() == []
        assert list((tmp_path / "uploads").glob("*")) == []


def test_existing_single_attachment_database_is_migrated_without_data_loss(tmp_path):
    database = tmp_path / "chat.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_name TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE attachments (
                id TEXT PRIMARY KEY,
                message_id INTEGER NOT NULL UNIQUE,
                storage_name TEXT NOT NULL UNIQUE,
                original_name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
            );
            INSERT INTO messages VALUES (1, '旧动物', '旧消息', '2026-01-01T00:00:00+00:00');
            INSERT INTO attachments VALUES (
                'old-id', 1, 'old.bin', '旧文件.txt', 'text/plain', 3,
                '2026-01-01T00:00:00+00:00'
            );
            """
        )

    store = ChatStore(database)
    created = store.create_message_with_attachments(
        sender_name="新动物",
        body="新消息",
        attachments=[
            {
                "id": "new-1",
                "storage_name": "new-1.bin",
                "original_name": "一.txt",
                "content_type": "text/plain",
                "size": 1,
            },
            {
                "id": "new-2",
                "storage_name": "new-2.bin",
                "original_name": "二.txt",
                "content_type": "text/plain",
                "size": 1,
            },
        ],
    )

    assert len(created["attachments"]) == 2
    history = store.list_messages()
    assert history[0]["attachments"][0]["original_name"] == "旧文件.txt"
    assert [item["original_name"] for item in history[1]["attachments"]] == ["一.txt", "二.txt"]


def test_file_larger_than_host_limit_is_rejected_without_history_or_orphan(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret", max_upload_bytes=4)

    with TestClient(app) as browser:
        login(browser)
        response = browser.post(
            "/api/files",
            files={"file": ("too-large.bin", b"12345", "application/octet-stream")},
        )

        assert response.status_code == 413
        assert browser.get("/api/messages").json() == []
        assert list((tmp_path / "uploads").glob("*")) == []


def test_grossly_oversized_request_is_rejected_before_multipart_file_processing(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret", max_upload_bytes=4)

    with TestClient(app) as browser:
        login(browser)
        response = browser.post(
            "/api/files",
            files={"file": ("attack.bin", b"x" * (70 * 1024), "application/octet-stream")},
        )

    assert response.status_code == 413
    assert "请求体" in response.json()["detail"]
    assert list((tmp_path / "uploads").glob("*")) == []


def test_unauthenticated_upload_is_rejected_before_multipart_parsing(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret", max_upload_bytes=2 * 1024**3)

    with TestClient(app) as browser:
        response = browser.post(
            "/api/files",
            files={"file": ("unauthorized.bin", b"x" * (2 * 1024 * 1024), "application/octet-stream")},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录后上传文件（请求未解析）"
    assert list((tmp_path / "uploads").glob("*")) == []
