import base64
import hashlib
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from lanimals.config import MIN_PASSWORD_LENGTH, create_config, hash_password, load_config, verify_password
from lanimals.identity import DeviceRegistry
from lanimals.main import create_app
from lanimals.throttle import LoginThrottle


class FakeClock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _login(browser: TestClient, password: str):
    return browser.post("/api/login", json={"password": password, "incognito": False})


def test_minimum_password_length_is_eight_characters():
    assert MIN_PASSWORD_LENGTH == 8
    with pytest.raises(ValueError):
        hash_password("1234567")
    assert verify_password("12345678", hash_password("12345678"))


def test_existing_short_password_hash_still_verifies():
    # 已经用旧规则设置的 4 位密码升级后仍然能登录，不强迫用户立即改密码。
    salt = os.urandom(16)
    digest = hashlib.scrypt(b"1234", salt=salt, n=2**14, r=8, p=1, dklen=32)
    legacy = "scrypt$16384$8$1${}${}".format(
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )
    assert verify_password("1234", legacy)


def test_repeated_wrong_passwords_are_locked_out_with_retry_after(tmp_path):
    clock = FakeClock()
    app = create_app(data_dir=tmp_path, chat_password="shared-secret", clock=clock)

    with TestClient(app) as browser:
        for _ in range(LoginThrottle.FREE_ATTEMPTS):
            assert _login(browser, "wrong").status_code == 401

        locked = _login(browser, "wrong")
        assert locked.status_code == 429
        assert int(locked.headers["Retry-After"]) > 0

        # 锁定期间即使密码正确也不放行，否则暴力破解只需忽略 429。
        blocked = _login(browser, "shared-secret")
        assert blocked.status_code == 429
        assert "lan_session" not in blocked.cookies

        clock.now += int(locked.headers["Retry-After"])
        assert _login(browser, "shared-secret").status_code == 200


def test_lockout_doubles_after_each_further_failure():
    clock = FakeClock()
    throttle = LoginThrottle(clock=clock)
    for _ in range(LoginThrottle.FREE_ATTEMPTS):
        throttle.record_failure("10.0.0.5")
    first_wait = throttle.retry_after("10.0.0.5")
    assert first_wait == LoginThrottle.BASE_LOCKOUT_SECONDS

    clock.now += first_wait
    assert throttle.retry_after("10.0.0.5") == 0
    throttle.record_failure("10.0.0.5")
    assert throttle.retry_after("10.0.0.5") == 2 * LoginThrottle.BASE_LOCKOUT_SECONDS

    for _ in range(30):
        clock.now += throttle.retry_after("10.0.0.5")
        throttle.record_failure("10.0.0.5")
    assert throttle.retry_after("10.0.0.5") == LoginThrottle.MAX_LOCKOUT_SECONDS


def test_successful_login_resets_failures_and_other_addresses_are_unaffected():
    clock = FakeClock()
    throttle = LoginThrottle(clock=clock)
    for _ in range(LoginThrottle.FREE_ATTEMPTS - 1):
        throttle.record_failure("10.0.0.5")
    throttle.record_success("10.0.0.5")
    throttle.record_failure("10.0.0.5")
    assert throttle.retry_after("10.0.0.5") == 0

    for _ in range(LoginThrottle.FREE_ATTEMPTS):
        throttle.record_failure("10.0.0.6")
    assert throttle.retry_after("10.0.0.6") > 0
    assert throttle.retry_after("10.0.0.7") == 0


def test_failure_history_is_forgotten_after_a_quiet_period():
    clock = FakeClock()
    throttle = LoginThrottle(clock=clock)
    for _ in range(LoginThrottle.FREE_ATTEMPTS - 1):
        throttle.record_failure("10.0.0.5")
    clock.now += LoginThrottle.FORGET_AFTER_SECONDS + 1
    throttle.record_failure("10.0.0.5")
    assert throttle.retry_after("10.0.0.5") == 0


def test_throttle_memory_is_bounded():
    clock = FakeClock()
    throttle = LoginThrottle(clock=clock, max_tracked=10)
    for index in range(50):
        throttle.record_failure(f"10.0.1.{index}")
    assert len(throttle._entries) <= 10


def test_sessions_expire_after_thirty_days_but_identity_name_is_kept(tmp_path):
    clock = FakeClock()
    app = create_app(data_dir=tmp_path, chat_password="shared-secret", clock=clock)

    with TestClient(app) as browser:
        first = _login(browser, "shared-secret")
        assert browser.get("/api/me").status_code == 200

        clock.now += 30 * 24 * 60 * 60 - 60
        assert browser.get("/api/me").status_code == 200

        clock.now += 120
        assert browser.get("/api/me").status_code == 401
        assert browser.post("/api/messages", json={"body": "hi"}).status_code == 401

        again = _login(browser, "shared-secret")
        assert again.status_code == 200
        assert again.json()["name"] == first.json()["name"]
        assert again.json()["identity_id"] == first.json()["identity_id"]


def test_expired_session_cannot_upload_before_multipart_parsing(tmp_path):
    clock = FakeClock()
    app = create_app(data_dir=tmp_path, chat_password="shared-secret", clock=clock)

    with TestClient(app) as browser:
        _login(browser, "shared-secret")
        clock.now += 31 * 24 * 60 * 60
        response = browser.post("/api/files", files={"file": ("a.txt", b"hello", "text/plain")})
        assert response.status_code == 401


def test_sessions_created_before_upgrade_get_a_fresh_thirty_day_window(tmp_path):
    database = tmp_path / "chat.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE devices (
                token_hash TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                temporary INTEGER NOT NULL,
                public_id TEXT NOT NULL UNIQUE
            );
            CREATE TABLE sessions (
                token_hash TEXT PRIMARY KEY,
                device_token_hash TEXT NOT NULL,
                FOREIGN KEY(device_token_hash) REFERENCES devices(token_hash)
            );
            """
        )
        connection.execute(
            "INSERT INTO devices VALUES (?, ?, 0, ?)",
            (DeviceRegistry._hash("device"), "奶油小熊", "public"),
        )
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?)",
            (DeviceRegistry._hash("session"), DeviceRegistry._hash("device")),
        )

    clock = FakeClock()
    registry = DeviceRegistry(database, clock=clock)
    assert registry.session_identity("session") == ("奶油小熊", False, "public")
    clock.now += 31 * 24 * 60 * 60
    assert registry.session_identity("session") is None


def test_host_configured_password_rejects_short_new_passwords(tmp_path):
    with pytest.raises(ValueError):
        create_config(tmp_path, password="short")
    create_config(tmp_path, password="long-enough")
    assert verify_password("long-enough", load_config(tmp_path).password_hash)
