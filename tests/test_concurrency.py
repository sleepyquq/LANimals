import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import cast

from lanimals.identity import DeviceRegistry
from lanimals.store import ChatStore


def test_concurrent_message_writes_are_complete_and_unique(tmp_path):
    database = tmp_path / "chat.db"
    store = ChatStore(database)
    workers = 16
    total = 120
    barrier = Barrier(workers)

    def write_message(index: int) -> int:
        if index < workers:
            barrier.wait()
        if index % 5 == 0:
            message = store.create_file_message(
                attachment_id=f"attachment-{index}",
                sender_name=f"animal-{index % 8}",
                body=f"message-{index}",
                storage_name=f"storage-{index}.bin",
                original_name=f"file-{index}.txt",
                content_type="text/plain",
                size=index,
            )
        else:
            message = store.create_message(sender_name=f"animal-{index % 8}", body=f"message-{index}")
        return cast(int, message["id"])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        ids = list(pool.map(write_message, range(total)))

    with sqlite3.connect(database) as connection:
        message_count = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        attachment_count = connection.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert message_count == total
    assert attachment_count == total // 5
    assert len(set(ids)) == total
    assert journal_mode == "wal"


def test_concurrent_first_logins_receive_unique_persistent_animal_names(tmp_path):
    registry = DeviceRegistry(tmp_path / "chat.db")
    workers = 16
    barrier = Barrier(workers)

    def create_device(index: int) -> str:
        barrier.wait()
        return registry.get_or_create(f"simultaneous-device-{index}", temporary=False)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        names = list(pool.map(create_device, range(workers)))

    assert len(set(names)) == workers
