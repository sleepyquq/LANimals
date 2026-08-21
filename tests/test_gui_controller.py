"""GUI 控制器生命周期与网络模式切换测试。"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from lanimals.config import create_config, load_config
from lanimals.gui.controller import ServerController
from lanimals.network import LanCandidate, LanSelection


@pytest.fixture(autouse=True)
def mock_lan_network(monkeypatch):
    """隔离真实网络探测与 mDNS 广播，确保单元测试快速稳定。"""
    monkeypatch.setattr(
        "lanimals.gui.controller.discover_lan_ipv4",
        lambda: LanSelection(
            address="192.168.1.100",
            adapter="Wi-Fi",
            candidates=(
                LanCandidate(address="192.168.1.100", adapter="Wi-Fi", score=120),
                LanCandidate(address="192.168.1.101", adapter="以太网", score=30),
            ),
        ),
    )
    monkeypatch.setattr("lanimals.gui.controller.advertise_mdns", lambda *_a, **_k: None)
    monkeypatch.setattr("lanimals.gui.controller.mdns_name_matches", lambda *_a, **_k: False)


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


def _available_local_port() -> int:
    """为会启动真实 Uvicorn 的生命周期测试分配临时端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_controller_init_and_lifecycle(temp_data_dir: Path) -> None:
    ctrl = ServerController(data_dir=temp_data_dir)
    assert not ctrl.has_config()
    assert not ctrl.is_running

    # 初始化配置
    ctrl.init_config_with_password("secret-pwd-123")
    assert ctrl.has_config()
    create_config(temp_data_dir, password="secret-pwd-123", port=_available_local_port())

    # 设为仅本机模式
    ctrl.set_local_only(True)
    assert ctrl.local_only is True
    assert "127.0.0.1" in ctrl.join_url

    # 状态监听器
    events = []
    ctrl.add_status_listener(lambda status, detail: events.append(status))

    # 启动服务
    ctrl.start()
    assert ctrl.is_running is True
    assert "running" in events

    # 验证上传大小配置
    assert ctrl.get_max_upload_size() == "2GB"
    ctrl.set_max_upload_size("1GB")
    assert ctrl.get_max_upload_size() == "1GB"

    # 验证修改密码
    ctrl.update_password("new-secret-456")
    config = load_config(temp_data_dir)
    assert config.password_hash != ""

    # 验证清空数据
    ctrl.clear_all_data()

    # 停止服务
    ctrl.stop()
    assert ctrl.is_running is False
    assert "stopped" in events


def test_controller_local_only_switch(temp_data_dir: Path) -> None:
    ctrl = ServerController(data_dir=temp_data_dir)
    ctrl.init_config_with_password("pwd-test")

    ctrl.set_local_only(True)
    assert ctrl.bind_host == "127.0.0.1"
    assert "127.0.0.1" in ctrl.join_url

    ctrl.set_local_only(False)
    assert ctrl.local_only is False
    assert ctrl.bind_host == "192.168.1.100"

    candidates = ctrl.get_lan_candidates()
    assert len(candidates) == 2
    assert candidates[0][0] == "Wi-Fi"


def test_network_preferences_survive_reopening_the_gui_controller(temp_data_dir: Path) -> None:
    """局域网模式与指定网卡是设置页选项，重开桌面端后不能静默回到默认值。"""
    ctrl = ServerController(data_dir=temp_data_dir)
    ctrl.init_config_with_password("pwd-test")
    ctrl.set_adapter("以太网")
    ctrl.set_local_only(True)

    reopened = ServerController(data_dir=temp_data_dir)

    assert reopened.local_only is True
    assert reopened.selected_adapter == "以太网"


def test_save_and_restart_applies_network_and_upload_settings_together(
    temp_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """设置页保存应只触发一次重启，并将三个字段写入同一份配置。"""
    ctrl = ServerController(data_dir=temp_data_dir)
    ctrl.init_config_with_password("pwd-test")
    ctrl.is_running = True
    restarts: list[str] = []
    monkeypatch.setattr(ctrl, "restart", lambda: restarts.append("restart"))

    assert ctrl.apply_settings(local_only=True, adapter_name="以太网", max_upload_size="1.5GB") == "1.5GB"

    stored = load_config(temp_data_dir)
    assert stored.gui_local_only is True
    assert stored.gui_selected_adapter == "以太网"
    assert stored.max_upload_size == "1.5GB"
    assert restarts == ["restart"]


def test_running_controller_restarts_after_upload_limit_change(
    temp_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上传限制属于 FastAPI 启动配置，运行中修改后必须重启才会生效。"""
    ctrl = ServerController(data_dir=temp_data_dir)
    ctrl.init_config_with_password("pwd-test")
    ctrl.is_running = True
    restarts: list[str] = []
    monkeypatch.setattr(ctrl, "restart", lambda: restarts.append("restart"))

    assert ctrl.set_max_upload_size("1GB") == "1GB"
    assert restarts == ["restart"]


def test_password_rotation_restarts_an_active_server_and_drops_websockets(
    temp_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """改密码清掉会话后必须重启活动服务，以立刻断开已有 WebSocket。"""
    ctrl = ServerController(data_dir=temp_data_dir)
    ctrl.init_config_with_password("old-password")
    ctrl.is_running = True
    restarts: list[str] = []
    monkeypatch.setattr(ctrl, "restart", lambda: restarts.append("restart"))

    ctrl.update_password("new-password")

    assert restarts == ["restart"]


def test_clearing_data_stops_and_restarts_an_active_server(
    temp_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """清空本机数据不能与活动中的消息/上传写入并发进行。"""
    ctrl = ServerController(data_dir=temp_data_dir)
    ctrl.init_config_with_password("pwd-test")
    ctrl.is_running = True
    calls: list[str] = []

    def fake_stop() -> None:
        calls.append("stop")
        ctrl.is_running = False

    def fake_start() -> None:
        calls.append("start")
        ctrl.is_running = True

    monkeypatch.setattr(ctrl, "stop", fake_stop)
    monkeypatch.setattr(ctrl, "start", fake_start)
    monkeypatch.setattr("lanimals.gui.controller.clear_data", lambda _data_dir: calls.append("clear"))

    ctrl.clear_all_data()

    assert calls == ["stop", "clear", "start"]
