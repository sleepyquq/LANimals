"""系统托盘延迟初始化回归测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_importing_gui_tray_does_not_select_a_native_backend() -> None:
    """无显示服务器时，仅导入 GUI 模块不应连接 X11 或创建系统托盘。"""
    script = """
import builtins

original_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'pystray' or name.startswith('pystray.'):
        raise RuntimeError('pystray must not load while importing lanimals.gui.tray')
    return original_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import
from lanimals.gui.tray import SystemTray
assert SystemTray
"""
    environment = os.environ.copy()
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
