from fastapi.testclient import TestClient

from lanimals.main import create_app


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
        assert attachment["original_name"] == "资料.txt"
        assert attachment["size"] == 21
        assert uploaded.json()["body"] == "这是附件说明"
        assert history.json()[-1]["attachment"]["id"] == attachment["id"]
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
