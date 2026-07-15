"""SQLite persistence for shared text and file messages."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class ChatStore:
    def __init__(self, database: Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_name TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    message_id INTEGER NOT NULL UNIQUE,
                    storage_name TEXT NOT NULL UNIQUE,
                    original_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
                );
                """
            )

    def create_message(self, *, sender_name: str, body: str) -> dict[str, object]:
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO messages (sender_name, body, created_at) VALUES (?, ?, ?)",
                (sender_name, body, created_at),
            )
            message_id = cursor.lastrowid
        return {
            "id": message_id,
            "sender_name": sender_name,
            "body": body,
            "created_at": created_at,
            "attachment": None,
        }

    def create_file_message(
        self,
        *,
        attachment_id: str,
        sender_name: str,
        body: str,
        storage_name: str,
        original_name: str,
        content_type: str,
        size: int,
    ) -> dict[str, object]:
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO messages (sender_name, body, created_at) VALUES (?, ?, ?)",
                (sender_name, body, created_at),
            )
            message_id = int(cursor.lastrowid or 0)
            connection.execute(
                """INSERT INTO attachments
                   (id, message_id, storage_name, original_name, content_type, size, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (attachment_id, message_id, storage_name, original_name, content_type, size, created_at),
            )
        attachment = {
            "id": attachment_id,
            "original_name": original_name,
            "content_type": content_type,
            "size": size,
        }
        return {
            "id": message_id,
            "sender_name": sender_name,
            "body": body,
            "created_at": created_at,
            "attachment": attachment,
        }

    def list_messages(self, *, limit: int = 100, before: int | None = None) -> list[dict[str, object]]:
        query = """
            SELECT m.id, m.sender_name, m.body, m.created_at,
                   a.id, a.original_name, a.content_type, a.size
            FROM messages m
            LEFT JOIN attachments a ON a.message_id = m.id
        """
        parameters: list[object] = []
        if before is not None:
            query += " WHERE m.id < ?"
            parameters.append(before)
        query += " ORDER BY m.id DESC LIMIT ?"
        parameters.append(max(1, min(limit, 200)))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        messages = []
        for row in reversed(rows):
            attachment = None
            if row[4] is not None:
                attachment = {
                    "id": row[4],
                    "original_name": row[5],
                    "content_type": row[6],
                    "size": row[7],
                }
            messages.append(
                {
                    "id": row[0],
                    "sender_name": row[1],
                    "body": row[2],
                    "created_at": row[3],
                    "attachment": attachment,
                }
            )
        return messages

    def get_attachment(self, attachment_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT storage_name, original_name, content_type, size FROM attachments WHERE id = ?",
                (attachment_id,),
            ).fetchone()
        if not row:
            return None
        return {"storage_name": row[0], "original_name": row[1], "content_type": row[2], "size": row[3]}

    def clear_messages(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM attachments")
            connection.execute("DELETE FROM messages")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
