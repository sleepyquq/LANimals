from fastapi.testclient import TestClient

from lanimals.config import create_config
from lanimals.main import create_app


def test_correct_password_logs_in_and_reuses_persistent_animal_name(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as first_browser:
        first_login = first_browser.post("/api/login", json={"password": "shared-secret", "incognito": False})
        first_me = first_browser.get("/api/me")

    assert first_login.status_code == 200
    assert first_login.cookies.get("lan_device")
    assert first_login.cookies.get("lan_session")
    assert first_me.json()["temporary"] is False

    with TestClient(app) as returning_browser:
        returning_browser.cookies.set("lan_device", first_login.cookies["lan_device"])
        second_login = returning_browser.post("/api/login", json={"password": "shared-secret", "incognito": False})
        second_me = returning_browser.get("/api/me")

    assert second_login.status_code == 200
    assert second_me.json()["name"] == first_me.json()["name"]


def test_wrong_password_does_not_create_a_session(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        response = browser.post("/api/login", json={"password": "wrong", "incognito": False})

    assert response.status_code == 401
    assert "lan_session" not in response.cookies


def test_app_can_authenticate_with_host_configured_password_hash(tmp_path):
    config = create_config(tmp_path, password="host-password")
    app = create_app(data_dir=tmp_path, password_hash=config.password_hash)

    with TestClient(app) as browser:
        accepted = browser.post("/api/login", json={"password": "host-password", "incognito": False})
        rejected = browser.post("/api/login", json={"password": "wrong", "incognito": False})

    assert accepted.status_code == 200
    assert rejected.status_code == 401


def test_incognito_login_does_not_overwrite_existing_persistent_device_cookie(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        persistent = browser.post("/api/login", json={"password": "shared-secret", "incognito": False})
        persistent_token = persistent.cookies["lan_device"]
        persistent_name = persistent.json()["name"]

        temporary = browser.post("/api/login", json={"password": "shared-secret", "incognito": True})
        assert temporary.json()["temporary"] is True
        assert browser.cookies["lan_device"] == persistent_token

        again = browser.post("/api/login", json={"password": "shared-secret", "incognito": False})
        assert again.json()["name"] == persistent_name
