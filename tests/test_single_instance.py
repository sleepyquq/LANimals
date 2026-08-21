"""单实例锁与唤醒机制测试套件。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from lanimals.gui.single_instance import SingleInstanceLock


def test_single_instance_basic(tmp_path: Path):
    """测试单个实例成功获取锁并能正常释放。"""
    lock1 = SingleInstanceLock(data_dir=tmp_path)
    assert lock1.acquire() is True
    assert (tmp_path / ".instance.lock").exists()

    lock1.release()
    assert not (tmp_path / ".instance.lock").exists()


def test_single_instance_duplicate_and_wakeup(tmp_path: Path):
    """测试已有实例在运行时，第二实例 acquire 返回 False 并触发主实例唤醒。"""
    woken_up = []

    def on_wakeup():
        woken_up.append(True)

    lock1 = SingleInstanceLock(data_dir=tmp_path, on_wakeup=on_wakeup)
    assert lock1.acquire() is True

    # 尝试启动第二实例
    lock2 = SingleInstanceLock(data_dir=tmp_path)
    assert lock2.acquire() is False

    # 给唤醒回调一点时间执行
    for _ in range(20):
        if woken_up:
            break
        time.sleep(0.05)

    assert len(woken_up) == 1

    # 释放第一实例
    lock1.release()

    # 第一实例释放后，第二实例应能正常获取锁
    assert lock2.acquire() is True
    lock2.release()


def test_single_instance_stale_lock_recovery(tmp_path: Path):
    """测试残留崩溃锁文件（端口未在监听）时能自动接管。"""
    lock_file = tmp_path / ".instance.lock"
    # 写入一个不可能连接的无效端口
    lock_file.write_text(
        json.dumps({"port": 59999, "token": "invalid_token", "timestamp": time.time()}),
        encoding="utf-8",
    )

    lock = SingleInstanceLock(data_dir=tmp_path)
    assert lock.acquire() is True
    lock.release()
