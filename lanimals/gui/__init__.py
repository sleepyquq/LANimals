"""LANimals GUI 模块入口。"""

from __future__ import annotations

from pathlib import Path

from lanimals.gui.app import LANimalsApp
from lanimals.gui.single_instance import SingleInstanceLock


def run_gui(data_dir: Path | str = "data") -> int:
    """启动 LANimals GUI 原生控制面板（含单实例互斥与前置唤醒）。"""
    resolved_data_dir = Path(data_dir).expanduser().resolve()
    lock = SingleInstanceLock(data_dir=resolved_data_dir)
    if not lock.acquire():
        # 已有实例在运行，并已成功向其发送唤醒通知将其拉至前台，当前新进程直接退出
        return 0

    try:
        app = LANimalsApp(data_dir=resolved_data_dir, instance_lock=lock)
        app.mainloop()
    finally:
        lock.release()
    return 0


__all__ = ["run_gui", "LANimalsApp", "SingleInstanceLock"]
