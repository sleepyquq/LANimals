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
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_name TEXT NOT NULL,
                    sender_id TEXT,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    message_id INTEGER NOT NULL,
                    storage_name TEXT NOT NULL UNIQUE,
                    original_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
                );
                """
            )
            self._migrate_single_attachment_schema(connection)
            self._migrate_sender_ids(connection)

    def create_message(
        self, *, sender_name: str, body: str, sender_id: str | None = None
    ) -> dict[str, object]:
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO messages (sender_name, sender_id, body, created_at)
                   VALUES (?, ?, ?, ?)""",
                (sender_name, sender_id, body, created_at),
            )
            message_id = cursor.lastrowid
        return {
            "id": message_id,
            "sender_name": sender_name,
            "sender_id": sender_id,
            "body": body,
            "created_at": created_at,
            "attachment": None,
            "attachments": [],
        }

    def create_message_with_attachments(
        self,
        *,
        sender_name: str,
        body: str,
        attachments: list[dict[str, object]],
        sender_id: str | None = None,
    ) -> dict[str, object]:
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO messages (sender_name, sender_id, body, created_at)
                   VALUES (?, ?, ?, ?)""",
                (sender_name, sender_id, body, created_at),
            )
            message_id = int(cursor.lastrowid or 0)
            connection.executemany(
                """INSERT INTO attachments
                   (id, message_id, storage_name, original_name, content_type, size, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        attachment["id"],
                        message_id,
                        attachment["storage_name"],
                        attachment["original_name"],
                        attachment["content_type"],
                        attachment["size"],
                        created_at,
                    )
                    for attachment in attachments
                ],
            )

        public_attachments = [self._public_attachment(attachment) for attachment in attachments]
        return self._message_payload(
            message_id=message_id,
            sender_name=sender_name,
            sender_id=sender_id,
            body=body,
            created_at=created_at,
            attachments=public_attachments,
        )

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
        sender_id: str | None = None,
    ) -> dict[str, object]:
        return self.create_message_with_attachments(
            sender_name=sender_name,
            sender_id=sender_id,
            body=body,
            attachments=[
                {
                    "id": attachment_id,
                    "storage_name": storage_name,
                    "original_name": original_name,
                    "content_type": content_type,
                    "size": size,
                }
            ],
        )

    def list_messages(
        self,
        *,
        limit: int = 100,
        before: int | None = None,
        after: int | None = None,
    ) -> list[dict[str, object]]:
        query = "SELECT id, sender_name, sender_id, body, created_at FROM messages"
        parameters: list[object] = []
        if after is not None:
            query += " WHERE id > ?"
            parameters.append(after)
            query += " ORDER BY id ASC LIMIT ?"
        else:
            if before is not None:
                query += " WHERE id < ?"
                parameters.append(before)
            query += " ORDER BY id DESC LIMIT ?"
        parameters.append(max(1, min(limit, 200)))
        with self._connect() as connection:
            message_rows = connection.execute(query, parameters).fetchall()
            if after is None:
                message_rows = list(reversed(message_rows))
            if not message_rows:
                return []
            message_ids = [row[0] for row in message_rows]
            placeholders = ",".join("?" for _ in message_ids)
            attachment_rows = connection.execute(
                f"""SELECT message_id, id, original_name, content_type, size
                    FROM attachments
                    WHERE message_id IN ({placeholders})
                    ORDER BY message_id, rowid""",
                message_ids,
            ).fetchall()

        attachments_by_message: dict[int, list[dict[str, object]]] = {
            int(message_id): [] for message_id in message_ids
        }
        for row in attachment_rows:
            attachments_by_message[int(row[0])].append(
                {
                    "id": row[1],
                    "original_name": row[2],
                    "content_type": row[3],
                    "size": row[4],
                }
            )
        return [
            self._message_payload(
                message_id=int(row[0]),
                sender_name=str(row[1]),
                sender_id=str(row[2]) if row[2] is not None else None,
                body=str(row[3]),
                created_at=str(row[4]),
                attachments=attachments_by_message[int(row[0])],
            )
            for row in message_rows
        ]

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

    @staticmethod
    def _public_attachment(attachment: dict[str, object]) -> dict[str, object]:
        return {
            "id": attachment["id"],
            "original_name": attachment["original_name"],
            "content_type": attachment["content_type"],
            "size": attachment["size"],
        }

    @staticmethod
    def _message_payload(
        *,
        message_id: int,
        sender_name: str,
        sender_id: str | None,
        body: str,
        created_at: str,
        attachments: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "id": message_id,
            "sender_name": sender_name,
            "sender_id": sender_id,
            "body": body,
            "created_at": created_at,
            # 保留单附件字段，让尚未刷新的旧页面仍能显示第一个附件。
            "attachment": attachments[0] if attachments else None,
            "attachments": attachments,
        }

    @staticmethod
    def _migrate_single_attachment_schema(connection: sqlite3.Connection) -> None:
        unique_message_index = False
        for index in connection.execute("PRAGMA index_list('attachments')").fetchall():
            if not index[2]:
                continue
            columns = [
                row[2]
                for row in connection.execute(f'PRAGMA index_info("{index[1]}")').fetchall()
            ]
            if columns == ["message_id"]:
                unique_message_index = True
                break
        if not unique_message_index:
            return

        connection.executescript(
            """
            PRAGMA foreign_keys = OFF;
            BEGIN IMMEDIATE;
            ALTER TABLE attachments RENAME TO attachments_single;
            CREATE TABLE attachments (
                id TEXT PRIMARY KEY,
                message_id INTEGER NOT NULL,
                storage_name TEXT NOT NULL UNIQUE,
                original_name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
            );
            INSERT INTO attachments
                (id, message_id, storage_name, original_name, content_type, size, created_at)
            SELECT id, message_id, storage_name, original_name, content_type, size, created_at
            FROM attachments_single;
            DROP TABLE attachments_single;
            COMMIT;
            PRAGMA foreign_keys = ON;
            """
        )

    @staticmethod
    def _migrate_sender_ids(connection: sqlite3.Connection) -> None:
        columns = {row[1] for row in connection.execute("PRAGMA table_info('messages')")}
        if "sender_id" not in columns:
            connection.execute("ALTER TABLE messages ADD COLUMN sender_id TEXT")
        has_devices = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'devices'"
        ).fetchone()
        if not has_devices:
            return
        device_columns = {row[1] for row in connection.execute("PRAGMA table_info('devices')")}
        if "public_id" not in device_columns:
            return
        connection.execute(
            """UPDATE messages
               SET sender_id = (
                   SELECT MIN(devices.public_id)
                   FROM devices
                   WHERE devices.display_name = messages.sender_name
                   GROUP BY devices.display_name
                   HAVING COUNT(*) = 1
               )
               WHERE sender_id IS NULL"""
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
