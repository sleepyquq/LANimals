"""控制面板启动速度与 lanimals.local 地址切换的回归测试。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from lanimals.config import create_config
from lanimals.gui import controller as controller_module
from lanimals.gui.controller import ServerController
from lanimals.gui.i18n import t
from lanimals.network import LanCandidate, LanSelection


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAN_IP = "192.168.1.100"
MDNS_URL = "http://lanimals.local:8787/"
IP_URL = f"http://{LAN_IP}:8787/"


@pytest.fixture(autouse=True)
def lan_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        controller_module,
        "discover_lan_ipv4",
        lambda: LanSelection(address=LAN_IP, adapter="Wi-Fi", candidates=(LanCandidate(LAN_IP, "Wi-Fi", 120),)),
    )


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    path = tmp_path / "data"
    create_config(path, password="test-password")
    return path


class _FakeAdvertisement:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _cache(data_dir: Path) -> Path:
    return data_dir / ".mdns_cache.json"


def test_verified_mdns_name_is_shown_immediately_on_the_next_launch(data_dir: Path) -> None:
    """上次已确认 lanimals.local 指向同一地址时，启动即显示域名，不再等待数秒的注册与解析。"""
    _cache(data_dir).write_text(json.dumps({"address": LAN_IP}), encoding="utf-8")

    controller = ServerController(data_dir=data_dir)

    assert controller.join_url == MDNS_URL
    assert controller.ip_url == IP_URL


def test_cached_name_for_a_different_address_is_ignored(data_dir: Path) -> None:
    _cache(data_dir).write_text(json.dumps({"address": "192.168.1.55"}), encoding="utf-8")

    controller = ServerController(data_dir=data_dir)

    assert controller.join_url == IP_URL


def test_corrupt_cache_falls_back_to_the_ip_address(data_dir: Path) -> None:
    _cache(data_dir).write_text("{not json", encoding="utf-8")

    assert ServerController(data_dir=data_dir).join_url == IP_URL


def test_successful_verification_switches_to_the_name_and_remembers_it(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(controller_module, "advertise_mdns", lambda *_a: _FakeAdvertisement())
    monkeypatch.setattr(controller_module, "mdns_name_matches", lambda address: address == LAN_IP)
    controller = ServerController(data_dir=data_dir)
    statuses: list[str] = []
    controller.add_status_listener(lambda status, _detail: statuses.append(status))
    assert controller.join_url == IP_URL

    controller._advertise_and_verify_mdns(LAN_IP, 8787)

    assert controller.join_url == MDNS_URL
    assert json.loads(_cache(data_dir).read_text(encoding="utf-8")) == {"address": LAN_IP}
    assert statuses == ["updated"]


def test_failed_verification_reverts_an_optimistic_name_and_forgets_it(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """代理/TUN 劫持 .local 或网络变化时，乐观显示的域名必须退回 IP，避免手机扫码失败。"""
    _cache(data_dir).write_text(json.dumps({"address": LAN_IP}), encoding="utf-8")
    monkeypatch.setattr(controller_module, "advertise_mdns", lambda *_a: _FakeAdvertisement())
    monkeypatch.setattr(controller_module, "mdns_name_matches", lambda _address: False)
    controller = ServerController(data_dir=data_dir)
    statuses: list[str] = []
    controller.add_status_listener(lambda status, _detail: statuses.append(status))
    assert controller.join_url == MDNS_URL

    controller._advertise_and_verify_mdns(LAN_IP, 8787)

    assert controller.join_url == IP_URL
    assert not _cache(data_dir).exists()
    assert statuses == ["updated"]


def test_already_confirmed_name_does_not_trigger_a_redundant_refresh(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cache(data_dir).write_text(json.dumps({"address": LAN_IP}), encoding="utf-8")
    monkeypatch.setattr(controller_module, "advertise_mdns", lambda *_a: _FakeAdvertisement())
    monkeypatch.setattr(controller_module, "mdns_name_matches", lambda _address: True)
    controller = ServerController(data_dir=data_dir)
    statuses: list[str] = []
    controller.add_status_listener(lambda status, _detail: statuses.append(status))

    controller._advertise_and_verify_mdns(LAN_IP, 8787)

    assert controller.join_url == MDNS_URL
    assert statuses == []


def test_gui_import_does_not_load_mdns_or_qr_libraries() -> None:
    """zeroconf 与 segno 只在服务启动/生成二维码时才需要，不应拖慢窗口出现。"""
    script = "import sys, lanimals.gui.app; print(sorted(m for m in ('zeroconf', 'segno') if m in sys.modules))"
    environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=PROJECT_ROOT, env=environment, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


@pytest.fixture(scope="module")
def qt_application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_home_page_shows_the_qr_code_while_the_service_is_starting(
    qt_application: QApplication, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """窗口出现时服务尚在后台启动：应直接显示二维码，而不是先闪“服务已停止”。"""
    from PySide6.QtCore import QEvent

    from lanimals.gui import app as app_module

    monkeypatch.setattr(app_module.SystemTray, "start", lambda _tray: None)
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.LANimalsApp(data_dir=data_dir)
    try:
        assert not window.controller.is_running
        label = window.main_view.qr_label
        assert label.text() != t("gui.statusStopped")
        assert label.pixmap() is not None and not label.pixmap().isNull()
        assert window.main_view.link_label.text() == IP_URL

        # 启动失败时才显示“已停止”。
        window._on_start_failed(RuntimeError("端口被占用"))
        assert label.text() == t("gui.statusStopped")
    finally:
        window._quitting = True
        window.close()
        window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
