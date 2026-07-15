from pathlib import Path

from lanimals.config import create_config, load_config, parse_size, update_max_upload_size, verify_password
from lanimals.main import create_app
from lanimals.store import ChatStore
from lanimals.cli import clear_data


def test_config_stores_password_hash_and_host_can_change_upload_limit(tmp_path):
    create_config(tmp_path, password="shared-secret", max_upload_size="2GB")

    raw = (tmp_path / "config.toml").read_text(encoding="utf-8")
    config = load_config(tmp_path)

    assert "shared-secret" not in raw
    assert verify_password("shared-secret", config.password_hash)
    assert not verify_password("wrong", config.password_hash)
    assert config.max_upload_bytes == parse_size("2GB")

    update_max_upload_size(tmp_path, "512MB")
    assert load_config(tmp_path).max_upload_bytes == parse_size("512MB")


def test_host_clear_removes_messages_and_files_but_preserves_config(tmp_path):
    create_config(tmp_path, password="shared-secret", max_upload_size="2GB")
    store = ChatStore(tmp_path / "chat.db")
    store.create_message(sender_name="奶油小熊", body="需要清空")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "file.bin").write_bytes(b"content")

    clear_data(tmp_path)

    assert store.list_messages() == []
    assert list(uploads.iterdir()) == []
    assert (tmp_path / "config.toml").is_file()


def test_browser_application_exposes_no_delete_route(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    assert all("DELETE" not in (getattr(route, "methods", set()) or set()) for route in app.routes)
