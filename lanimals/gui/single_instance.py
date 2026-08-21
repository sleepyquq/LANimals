"""单实例运行保护与跨进程窗口唤醒模块。

通过在数据目录下维护 .instance.lock 文件及本地 Loopback TCP 端口通信：
1. 防止同一个 LANimals 实例被重复多开；
2. 当用户再次点击/运行 LANimals 时，自动向已运行的实例发送 WAKEUP 指令，
   将后台/托盘中的窗口唤醒并置顶到屏幕最前端，新实例优雅退出。
"""

from __future__ import annotations

import json
import logging
import secrets
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class SingleInstanceLock:
    """管理单实例互斥与唤醒 IPC 通信。"""

    def __init__(self, data_dir: Path | str, on_wakeup: Callable[[], None] | None = None) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.lock_file = self.data_dir / ".instance.lock"
        self.on_wakeup = on_wakeup
        self.token = secrets.token_hex(16)
        self._server_socket: socket.socket | None = None
        self._listen_thread: threading.Thread | None = None
        self._running = False

    def acquire(self) -> bool:
        """尝试获取单实例锁。

        返回 True 表示成功获取锁（当前是唯一运行的实例）；
        返回 False 表示已有实例在运行，并已成功通知其唤醒窗口。
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)

        if self.lock_file.exists():
            try:
                content = json.loads(self.lock_file.read_text(encoding="utf-8"))
                port = content.get("port")
                token = content.get("token")
                if port and token:
                    # 尝试连接已有实例并发送唤醒指令
                    if self._try_wakeup(port, token):
                        logger.info("已检测到正在运行的 LANimals 实例，已发送唤醒通知。")
                        return False
            except Exception as error:
                logger.debug("读取已有锁文件失败或已有实例已崩溃: %s", error)

        # 尝试成为主实例并监听端口
        return self._start_listener()

    def _try_wakeup(self, port: int, token: str) -> bool:
        """连接目标端口发送唤醒指令（毫秒级极速探测）。"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.1)
                sock.connect(("127.0.0.1", port))
                msg = f"WAKEUP {token}\n".encode("utf-8")
                sock.sendall(msg)
                resp = sock.recv(1024).decode("utf-8", errors="ignore").strip()
                return resp == "OK"
        except Exception:
            return False

    def _start_listener(self) -> bool:
        """绑定随机可用本地环回端口并启动监听线程。"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # 绑定到随机可用回环端口
            sock.bind(("127.0.0.1", 0))
            sock.listen(5)
            self._server_socket = sock
            port = sock.getsockname()[1]

            # 写入锁文件
            lock_data = {
                "port": port,
                "token": self.token,
                "platform": sys.platform,
                "timestamp": time.time(),
            }
            self.lock_file.write_text(json.dumps(lock_data), encoding="utf-8")

            self._running = True
            self._listen_thread = threading.Thread(target=self._listener_loop, daemon=True, name="single-instance-ipc")
            self._listen_thread.start()
            return True
        except Exception as error:
            logger.exception("启动单实例监听失败: %s", error)
            return True  # 容错：即使监听失败也允许启动

    def _listener_loop(self) -> None:
        """接收并处理唤醒指令。"""
        while self._running and self._server_socket:
            try:
                conn, _ = self._server_socket.accept()
                with conn:
                    conn.settimeout(2.0)
                    data = conn.recv(1024).decode("utf-8", errors="ignore").strip()
                    parts = data.split()
                    if len(parts) >= 2 and parts[0] == "WAKEUP" and parts[1] == self.token:
                        conn.sendall(b"OK\n")
                        if self.on_wakeup:
                            try:
                                self.on_wakeup()
                            except Exception as err:
                                logger.exception("执行唤醒回调异常: %s", err)
                    else:
                        conn.sendall(b"DENIED\n")
            except Exception:
                if not self._running:
                    break

    def release(self) -> None:
        """释放锁并清理资源。"""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None

        if self.lock_file.exists():
            try:
                self.lock_file.unlink(missing_ok=True)
            except Exception:
                pass
