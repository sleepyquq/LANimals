"""Local host administration helpers for LANimals."""

from __future__ import annotations

import shutil
from pathlib import Path

from lanimals.config import update_password
from lanimals.identity import DeviceRegistry
from lanimals.store import ChatStore


def change_password(data_dir: Path, password: str) -> None:
    data_dir = Path(data_dir)
    update_password(data_dir, password)
    database = data_dir / "chat.db"
    if database.exists():
        DeviceRegistry(database).clear_sessions()


def clear_data(data_dir: Path) -> None:
    """Clear chat records and uploads while preserving configuration and device names."""
    data_dir = Path(data_dir)
    database = data_dir / "chat.db"
    if database.exists():
        ChatStore(database).clear_messages()

    uploads = data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    for entry in uploads.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink(missing_ok=True)
