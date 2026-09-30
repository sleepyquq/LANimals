"""启动 PyInstaller 打包后的桌面版，确认它能真正拉起本地服务。

用法（在 scripts/build_app.py --mode onedir 之后）：
    QT_QPA_PLATFORM=offscreen python scripts/smoke_frozen.py --reset-data

脚本会在打包版实际使用的数据目录中预置一份“仅本机”配置，启动可执行文件，
等待 http://127.0.0.1:<port>/ 返回 200，然后结束进程。失败时打印 GUI 日志。
结束后删除这份测试数据，避免被打进发布包。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def frozen_executable(dist_dir: Path) -> Path:
    if sys.platform == "darwin":
        return dist_dir / "LANimals.app" / "Contents" / "MacOS" / "LANimals"
    if sys.platform == "win32":
        return dist_dir / "LANimals" / "LANimals.exe"
    return dist_dir / "LANimals" / "LANimals"


def prepare_data_dir(executable: Path, port: int, *, reset: bool) -> Path:
    from lanimals.__main__ import default_gui_data_dir
    from lanimals.config import create_config, update_gui_network_preferences

    data_dir = default_gui_data_dir(frozen=True, executable=str(executable))
    if data_dir.exists():
        if not reset:
            # macOS 上这是用户真实的 ~/Library/Application Support/LANimals，绝不能默认删除。
            raise SystemExit(
                f"数据目录已存在：{data_dir}\n"
                "冒烟测试会清空它。确认其中没有需要保留的聊天记录后，加 --reset-data 重新运行。"
            )
        shutil.rmtree(data_dir)
    create_config(data_dir, password="smoke-test", port=port)
    # 仅本机模式绑定 127.0.0.1，结果不受 CI 机器的网卡与 mDNS 环境影响。
    update_gui_network_preferences(data_dir, local_only=True, selected_adapter=None)
    return data_dir


def wait_for_http(url: str, process: subprocess.Popen, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            print(f"打包版提前退出，返回码 {process.returncode}", flush=True)
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    print(f"{timeout:.0f} 秒内未能访问 {url}", flush=True)
    return False


def stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the packaged LANimals desktop app")
    parser.add_argument("--dist", type=Path, default=PROJECT_ROOT / "dist")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--reset-data",
        action="store_true",
        help="允许清空打包版的数据目录（CI 使用；本机运行前请确认没有要保留的数据）",
    )
    args = parser.parse_args()

    executable = frozen_executable(args.dist.resolve())
    if not executable.exists():
        print(f"找不到打包产物：{executable}", flush=True)
        return 1
    data_dir = prepare_data_dir(executable, args.port, reset=args.reset_data)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"启动 {executable}\n数据目录 {data_dir}\n等待 {url}", flush=True)

    started = time.monotonic()
    process = subprocess.Popen([str(executable)], env=os.environ.copy())
    try:
        ok = wait_for_http(url, process, args.timeout)
        elapsed = time.monotonic() - started
    finally:
        stop(process)

    log_file = data_dir / "lanimals_gui.log"
    if ok:
        print(f"[OK] 打包版在 {elapsed:.1f} 秒内启动并返回 200", flush=True)
    elif log_file.exists():
        print("---- lanimals_gui.log ----", flush=True)
        print(log_file.read_text(encoding="utf-8", errors="replace"), flush=True)
    # 删除测试配置：Windows/Linux 的数据目录在 dist/LANimals 内，随后会被打进发布包。
    shutil.rmtree(data_dir, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
