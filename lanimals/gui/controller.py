"""后台服务生命周期控制器与网络状态机。"""

from __future__ import annotations

import io
import logging
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from lanimals.cli import change_password, clear_data
from lanimals.config import (
    create_config,
    load_config,
    update_gui_network_preferences,
    update_gui_settings,
    update_max_upload_size,
)
from lanimals.network import (
    MdnsAdvertisement,
    advertise_mdns,
    discover_lan_ipv4,
    is_private_lan_ipv4,
    mdns_name_matches,
)

if TYPE_CHECKING:
    import uvicorn

logger = logging.getLogger("lanimals.controller")


class NullWriter:
    """在无终端（--noconsole）环境下安全替代 sys.stdout / sys.stderr。"""

    def write(self, s: str) -> int:
        return len(s)

    def flush(self) -> None:
        pass


def _ensure_stdio() -> None:
    """确保 sys.stdout 和 sys.stderr 在 PyInstaller --noconsole 下不为 None。"""
    if sys.stdout is None:
        sys.stdout = NullWriter()  # type: ignore
    if sys.stderr is None:
        sys.stderr = NullWriter()  # type: ignore
    if sys.stdin is None:
        sys.stdin = io.StringIO()  # type: ignore


class ServerController:
    """管理 Uvicorn 后台服务生命周期、网络切换与主机配置的线程控制器。"""

    def __init__(self, data_dir: Path | str = "data") -> None:
        _ensure_stdio()
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._server: uvicorn.Server | None = None
        self._server_thread: threading.Thread | None = None
        self._advertisement: MdnsAdvertisement | None = None
        self._lock = threading.RLock()
        # 启动线程尚未构造 Uvicorn 实例时，也必须能收到停止请求。
        self._stop_requested = threading.Event()

        self.is_running = False
        self.local_only = False
        self.selected_adapter: str | None = None
        self.bind_host: str = "127.0.0.1"
        self.port: int = 8787
        self.join_url: str = f"http://127.0.0.1:{self.port}/"
        self.ip_url: str = self.join_url
        self.mdns_available: bool = False
        self.status_listeners: list[Callable[[str, str | None], None]] = []

        if self.has_config():
            config = load_config(self.data_dir)
            self.local_only = config.gui_local_only
            self.selected_adapter = config.gui_selected_adapter

        # 快速计算 IP 目标（主线程 0 阻塞）
        self._update_network_targets_fast()

    def add_status_listener(self, listener: Callable[[str, str | None], None]) -> None:
        with self._lock:
            self.status_listeners.append(listener)

    def _notify_status(self, status: str, detail: str | None = None) -> None:
        logger.info("服务状态变更: status=%s, detail=%s", status, detail)
        for listener in list(self.status_listeners):
            try:
                listener(status, detail)
            except Exception:
                logger.exception("执行状态监听回调异常")

    def has_config(self) -> bool:
        return (self.data_dir / "config.toml").exists()

    def init_config_with_password(self, password: str) -> None:
        with self._lock:
            create_config(self.data_dir, password=password)

    def get_max_upload_size(self) -> str:
        with self._lock:
            if not self.has_config():
                return "512MB"
            return load_config(self.data_dir).max_upload_size

    def set_max_upload_size(self, size_str: str) -> str:
        """保存上传限制；服务运行中时重启以载入 FastAPI 的新请求上限。"""
        with self._lock:
            if not self.has_config():
                raise RuntimeError("配置尚未初始化")
            updated = update_max_upload_size(self.data_dir, size_str)
            was_running = self.is_running

        # max_upload_bytes 在 create_app 时固定传入，单纯更新 TOML 不会影响已运行服务。
        if was_running:
            self.restart()
        else:
            self._notify_status("updated")
        return updated.max_upload_size

    def apply_settings(
        self,
        *,
        local_only: bool,
        adapter_name: str | None,
        max_upload_size: str,
    ) -> str:
        """一次保存设置页的所有常规选项，并且只重启服务一次。"""
        with self._lock:
            if not self.has_config():
                raise RuntimeError("配置尚未初始化")
            updated = update_gui_settings(
                self.data_dir,
                local_only=local_only,
                selected_adapter=adapter_name,
                max_upload_size=max_upload_size,
            )
            self.local_only = local_only
            self.selected_adapter = adapter_name
            was_running = self.is_running

        if was_running:
            self.restart()
        else:
            self._update_network_targets_fast()
            # “保存并重启”在服务已停时承担启动职责，避免留下仅写入配置的假成功状态。
            self.start()
        return updated.max_upload_size

    def update_password(self, new_password: str) -> None:
        with self._lock:
            if not self.has_config():
                raise RuntimeError("配置尚未初始化")
            change_password(self.data_dir, new_password)
            was_running = self.is_running

        # 清掉会话数据库并不足以立即踢掉已连上的 WebSocket；重启会关闭连接，
        # 使改密码在桌面端与命令行中都满足“立即失效”的安全约束。
        if was_running:
            self.restart()
        else:
            self._notify_status("updated")

    def clear_all_data(self) -> None:
        """在服务停止期间清除消息和附件，随后恢复原有的运行状态。"""
        with self._lock:
            was_running = self.is_running

        if was_running:
            self.stop()

        try:
            clear_data(self.data_dir)
        except Exception:
            # 即使清除失败，也尽量恢复原先服务，避免一次管理操作把聊天室永久停掉。
            if was_running:
                try:
                    self.start()
                except Exception:
                    logger.exception("清除失败后恢复服务也失败")
            raise

        if was_running:
            self.start()
        else:
            self._notify_status("updated")

    def get_lan_candidates(self) -> list[tuple[str, str]]:
        """返回所有可用的局域网适配器列表 [(adapter_name, ip_address), ...]"""
        try:
            selection = discover_lan_ipv4()
            return [(c.adapter, c.address) for c in selection.candidates]
        except Exception:
            return []

    def _update_network_targets_fast(self) -> None:
        """主线程快速更新网络地址（毫秒级无阻塞）。"""
        if not self.has_config():
            config_port = 8787
        else:
            config = load_config(self.data_dir)
            config_port = config.port

        self.port = config_port

        if self.local_only:
            self.bind_host = "127.0.0.1"
            self.ip_url = f"http://127.0.0.1:{config_port}/"
            self.join_url = self.ip_url
            self.mdns_available = False
            return

        # 局域网模式（仅枚举本地网卡，不发网络请求）
        try:
            selection = discover_lan_ipv4()
            if self.selected_adapter:
                matched = next((c.address for c in selection.candidates if c.adapter == self.selected_adapter), None)
                self.bind_host = matched if matched else selection.address
            else:
                self.bind_host = selection.address
        except Exception:
            self.bind_host = "127.0.0.1"

        self.ip_url = f"http://{self.bind_host}:{config_port}/"
        if not self.mdns_available:
            self.join_url = self.ip_url

    def start(self) -> None:
        """非阻塞启动后台服务，mDNS 在独立线程后台探测。"""
        _ensure_stdio()

        # 首次导入 FastAPI 可能耗时数秒。若把它留在服务器线程中，刚点击“保存并
        # 重启”就会遇到还没有 Uvicorn 实例可停止的窗口，从而造成端口竞争。启动
        # 操作本身由 GUI 工作线程调用，故在此预热并同步构造服务对象不会阻塞界面。
        import asyncio
        import uvicorn
        from lanimals.main import create_app

        with self._lock:
            if self.is_running or (self._server_thread is not None and self._server_thread.is_alive()):
                return

            if not self.has_config():
                raise RuntimeError("首次启动需要先配置群聊密码")

            config = load_config(self.data_dir)
            self._update_network_targets_fast()
            self._stop_requested.clear()

            logger.info("启动后台服务: host=%s, port=%s", self.bind_host, self.port)

            bind_host = self.bind_host
            target_port = self.port
            data_dir = self.data_dir
            max_upload = config.max_upload_bytes
            should_advertise = not self.local_only and is_private_lan_ipv4(bind_host)

            app = create_app(
                data_dir=data_dir,
                password_hash_provider=lambda: load_config(data_dir).password_hash,
                max_upload_bytes=max_upload,
            )
            uvicorn_config = uvicorn.Config(
                app=app,
                host=bind_host,
                port=target_port,
                log_level="warning",
                access_log=False,
                log_config=None,
            )
            server = uvicorn.Server(uvicorn_config)
            server.install_signal_handlers = lambda: None
            self._server = server

            def run_server():
                _ensure_stdio()
                with self._lock:
                    if self._stop_requested.is_set():
                        server.should_exit = True

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(server.serve())
                except (Exception, SystemExit) as err:
                    logger.exception("Uvicorn 服务在子线程异常退出: %s", err)
                finally:
                    try:
                        loop.close()
                    except Exception:
                        pass
                    with self._lock:
                        if self._advertisement:
                            try:
                                self._advertisement.close()
                            except Exception:
                                pass
                            self._advertisement = None
                        self.is_running = False
                        self._server = None
                        self._server_thread = None
                        self._stop_requested.set()
                    self._notify_status("stopped")

            thread = threading.Thread(target=run_server, daemon=True, name="lanimals-server")
            self._server_thread = thread
            self.is_running = True

        # 绝不在持有控制器锁时等待/启动子线程，否则子线程无法写入 _server，
        # 紧接着的设置变更也就无法向它发出停止请求。
        thread.start()

        # 启动独立 mDNS 广播与解析探测线程（绝不阻塞主界面）。
        if should_advertise:
            def async_mdns_setup():
                try:
                    ad = advertise_mdns(bind_host, target_port)
                    with self._lock:
                        if self._stop_requested.is_set():
                            ad.close()
                            return
                        self._advertisement = ad
                    if mdns_name_matches(bind_host):
                        with self._lock:
                            if self._stop_requested.is_set():
                                return
                            self.join_url = f"http://lanimals.local:{target_port}/"
                            self.mdns_available = True
                        self._notify_status("updated")
                except Exception as error:
                    logger.debug("异步 mDNS 探测或注册失败: %s", error)

            threading.Thread(target=async_mdns_setup, daemon=True, name="mdns-setup").start()

        with self._lock:
            still_starting = self._server_thread is thread and self.is_running
        if still_starting:
            self._notify_status("running")

    def stop(self) -> None:
        """优雅停止后台服务与广播。"""
        with self._lock:
            thread = self._server_thread
            if not self.is_running and not (thread and thread.is_alive()):
                return

            self._stop_requested.set()
            server = self._server
            if server:
                server.should_exit = True

            if self._advertisement:
                try:
                    self._advertisement.close()
                except Exception:
                    pass
                self._advertisement = None

            self.is_running = False

        if thread and thread.is_alive():
            # 先给正常请求一个短暂的收尾机会；如果有长连接未退出，再强制退出，
            # 这样重启不会与旧监听端口重叠，也能立即断开被撤销的会话。
            thread.join(timeout=2.0)
            if thread.is_alive():
                with self._lock:
                    if self._server is not None:
                        self._server.force_exit = True
                thread.join(timeout=1.5)
            if thread.is_alive():
                raise RuntimeError("服务未能在 3.5 秒内停止，已取消后续重启以避免端口冲突")
        self._notify_status("stopped")

    def restart(self) -> None:
        """平滑重启后台服务。"""
        self.stop()
        self.start()

    def set_local_only(self, local_only: bool) -> None:
        """切换局域网 / 仅本机访问模式。"""
        with self._lock:
            if self.local_only == local_only:
                return
            previous_local_only = self.local_only
            self.local_only = local_only
            try:
                self._save_network_preferences_locked()
            except Exception:
                self.local_only = previous_local_only
                raise

        if self.is_running:
            self.restart()
        else:
            self._update_network_targets_fast()
            self._notify_status("updated")

    def set_adapter(self, adapter_name: str | None) -> None:
        """切换绑定的局域网网卡。"""
        with self._lock:
            if self.selected_adapter == adapter_name:
                return
            previous_adapter = self.selected_adapter
            self.selected_adapter = adapter_name
            try:
                self._save_network_preferences_locked()
            except Exception:
                self.selected_adapter = previous_adapter
                raise

        if self.is_running:
            self.restart()
        else:
            self._update_network_targets_fast()
            self._notify_status("updated")

    def _save_network_preferences_locked(self) -> None:
        """仅在已有配置时持久化 GUI 网络选择；调用方必须持有 _lock。"""
        if self.has_config():
            update_gui_network_preferences(
                self.data_dir,
                local_only=self.local_only,
                selected_adapter=self.selected_adapter,
            )
