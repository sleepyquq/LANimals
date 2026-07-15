"""Cookie-token backed device identities and login sessions."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from pathlib import Path

_PERSISTENT_PREFIXES = ("奶油", "云朵", "薄荷", "橘子", "松饼", "星糖", "桃子", "栗子", "棉花", "蜂蜜", "雨滴", "森林")
_PERSISTENT_ANIMALS = ("小熊", "水獭", "小兔", "小猫", "小狗", "松鼠", "海豹", "企鹅", "刺猬", "浣熊", "羊驼", "熊猫")
PERSISTENT_NAMES = tuple(f"{prefix}{animal}" for prefix in _PERSISTENT_PREFIXES for animal in _PERSISTENT_ANIMALS)
TEMPORARY_NAMES = (
    "夜枭", "雾狐", "月貘", "星鸦", "影猫", "霜狼", "梦鹿", "云豹", "玄鹤", "暮兔",
    "夜獭", "雾熊", "月鲸", "星狐", "影貘", "霜鸮", "梦狸", "云鹿", "玄猫", "暮鸦",
)


class DeviceRegistry:
    def __init__(self, database: Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    token_hash TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    temporary INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    device_token_hash TEXT NOT NULL,
                    FOREIGN KEY(device_token_hash) REFERENCES devices(token_hash)
                );
                """
            )

    def get_or_create(self, token: str, *, temporary: bool) -> str:
        token_hash = self._hash(token)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT display_name FROM devices WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            if row:
                return str(row[0])

            names = TEMPORARY_NAMES if temporary else PERSISTENT_NAMES
            used_names = {
                row[0]
                for row in connection.execute(
                    "SELECT display_name FROM devices WHERE temporary = ?", (int(temporary),)
                )
            }
            if temporary:
                assigned_count = int(
                    connection.execute("SELECT COUNT(*) FROM devices WHERE temporary = 1").fetchone()[0]
                )
                name = names[assigned_count % len(names)]
            else:
                try:
                    name = next(candidate for candidate in names if candidate not in used_names)
                except StopIteration as error:
                    raise RuntimeError("动物名称池已用完，请在主机上扩充名称列表") from error
            connection.execute(
                "INSERT INTO devices (token_hash, display_name, temporary) VALUES (?, ?, ?)",
                (token_hash, name, int(temporary)),
            )
            return name

    def create_session(self, device_token: str) -> str:
        session_token = secrets.token_urlsafe(32)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions (token_hash, device_token_hash) VALUES (?, ?)",
                (self._hash(session_token), self._hash(device_token)),
            )
        return session_token

    def clear_sessions(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions")

    def session_identity(self, session_token: str) -> tuple[str, bool] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT devices.display_name, devices.temporary
                FROM sessions
                JOIN devices ON devices.token_hash = sessions.device_token_hash
                WHERE sessions.token_hash = ?
                """,
                (self._hash(session_token),),
            ).fetchone()
        return (str(row[0]), bool(row[1])) if row else None

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database)
