"""可选 HTTPS：自签名证书、配置开关与桌面端地址。"""

from __future__ import annotations

import datetime
import os
import socket
import ssl
import threading
import time
from pathlib import Path

import pytest
from cryptography import x509

from lanimals.config import (
    create_config,
    load_config,
    update_gui_settings,
    update_max_upload_size,
    update_password,
)
from lanimals.main import create_app
from lanimals.tls import ensure_certificate


def _load(cert_path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(cert_path.read_bytes())


def _san(cert: x509.Certificate) -> tuple[set[str], set[str]]:
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return (
        set(names.get_values_for_type(x509.DNSName)),
        {str(value) for value in names.get_values_for_type(x509.IPAddress)},
    )


def test_certificate_covers_domain_and_bind_address(tmp_path: Path) -> None:
    cert_path, key_path = ensure_certificate(tmp_path, "192.168.1.20")

    assert cert_path.parent == tmp_path / "tls"
    cert = _load(cert_path)
    dns_names, ip_addresses = _san(cert)
    assert {"lanimals.local", "localhost"} <= dns_names
    assert {"192.168.1.20", "127.0.0.1"} <= ip_addresses
    # Apple 平台拒绝有效期超过 825 天的服务器证书。
    lifetime = cert.not_valid_after_utc - cert.not_valid_before_utc
    assert lifetime <= datetime.timedelta(days=825)
    assert b"PRIVATE KEY" in key_path.read_bytes()
    if os.name == "posix":
        assert key_path.stat().st_mode & 0o077 == 0


def test_certificate_is_reused_so_devices_are_not_warned_again(tmp_path: Path) -> None:
    cert_path, _ = ensure_certificate(tmp_path, "192.168.1.20")
    first = cert_path.read_bytes()

    ensure_certificate(tmp_path, "192.168.1.20")
    ensure_certificate(tmp_path, "127.0.0.1")

    assert cert_path.read_bytes() == first


def test_certificate_is_regenerated_for_a_new_lan_address(tmp_path: Path) -> None:
    cert_path, _ = ensure_certificate(tmp_path, "192.168.1.20")
    first = cert_path.read_bytes()

    ensure_certificate(tmp_path, "10.0.0.8")

    assert cert_path.read_bytes() != first
    assert "10.0.0.8" in _san(_load(cert_path))[1]


def test_damaged_certificate_files_are_replaced(tmp_path: Path) -> None:
    cert_path, key_path = ensure_certificate(tmp_path, "192.168.1.20")
    cert_path.write_text("broken", encoding="utf-8")

    ensure_certificate(tmp_path, "192.168.1.20")

    assert _load(cert_path)
    assert key_path.exists()


def test_https_setting_defaults_off_and_survives_other_updates(tmp_path: Path) -> None:
    create_config(tmp_path, password="host-password")
    assert load_config(tmp_path).https is False

    update_gui_settings(
        tmp_path, local_only=False, selected_adapter=None, max_upload_size="2GB", https=True
    )
    assert load_config(tmp_path).https is True

    update_max_upload_size(tmp_path, "1GB")
    update_password(tmp_path, "another-password")
    update_gui_settings(tmp_path, local_only=False, selected_adapter=None, max_upload_size="2GB")
    assert load_config(tmp_path).https is True

    update_gui_settings(
        tmp_path, local_only=False, selected_adapter=None, max_upload_size="2GB", https=False
    )
    assert load_config(tmp_path).https is False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_server_answers_over_tls_with_the_generated_certificate(tmp_path: Path) -> None:
    import http.client

    import uvicorn

    cert_path, key_path = ensure_certificate(tmp_path, "127.0.0.1")
    port = _free_port()
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            ssl_certfile=str(cert_path),
            ssl_keyfile=str(key_path),
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started

        context = ssl.create_default_context(cafile=str(cert_path))
        connection = http.client.HTTPSConnection("127.0.0.1", port, context=context, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        assert b"<html" in response.read().lower()
        connection.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture
def https_controller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from lanimals.gui.controller import ServerController
    from lanimals.network import LanCandidate, LanSelection

    monkeypatch.setattr(
        "lanimals.gui.controller.discover_lan_ipv4",
        lambda: LanSelection(
            address="192.168.1.100",
            adapter="Wi-Fi",
            candidates=(LanCandidate(address="192.168.1.100", adapter="Wi-Fi", score=120),),
        ),
    )
    monkeypatch.setattr("lanimals.gui.controller.advertise_mdns", lambda *_a, **_k: None)
    monkeypatch.setattr("lanimals.gui.controller.mdns_name_matches", lambda *_a, **_k: False)
    data_dir = tmp_path / "data"
    create_config(data_dir, password="pwd-test")
    (data_dir / ".mdns_cache.json").write_text('{"address": "192.168.1.100"}', encoding="utf-8")
    return ServerController, data_dir


def test_controller_switches_join_addresses_to_https(https_controller, monkeypatch) -> None:
    ServerController, data_dir = https_controller
    ctrl = ServerController(data_dir=data_dir)
    assert ctrl.https is False
    assert ctrl.join_url == "http://lanimals.local:8787/"

    ctrl.is_running = True
    monkeypatch.setattr(ctrl, "restart", lambda: None)
    ctrl.apply_settings(local_only=False, adapter_name=None, max_upload_size="2GB", https=True)
    ctrl._update_network_targets_fast()

    assert ctrl.https is True
    assert ctrl.join_url == "https://lanimals.local:8787/"
    assert ctrl.ip_url == "https://192.168.1.100:8787/"
    assert ServerController(data_dir=data_dir).ip_url == "https://192.168.1.100:8787/"

    ctrl.is_running = False
    ctrl.set_local_only(True)
    assert ctrl.join_url == "https://127.0.0.1:8787/"
