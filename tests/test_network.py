import socket
from types import SimpleNamespace

from lanimals import network


def _address(value):
    return SimpleNamespace(family=socket.AF_INET, address=value)


def _stats(*, up=True, speed=1000):
    return SimpleNamespace(isup=up, speed=speed)


def test_physical_default_adapter_is_preferred_and_other_candidates_are_reported(monkeypatch):
    monkeypatch.setattr(
        network.psutil,
        "net_if_addrs",
        lambda: {
            "以太网": [_address("192.168.0.103")],
            "Wi-Fi": [_address("192.168.0.88")],
            "Loopback": [_address("127.0.0.1")],
        },
    )
    monkeypatch.setattr(
        network.psutil,
        "net_if_stats",
        lambda: {"以太网": _stats(), "Wi-Fi": _stats(speed=866), "Loopback": _stats()},
    )
    monkeypatch.setattr(network, "_default_route_ipv4", lambda: "192.168.0.88")

    selection = network.discover_lan_ipv4()

    assert selection.address == "192.168.0.88"
    assert selection.adapter == "Wi-Fi"
    assert [(item.adapter, item.address) for item in selection.candidates] == [
        ("Wi-Fi", "192.168.0.88"),
        ("以太网", "192.168.0.103"),
    ]


def test_vpn_virtual_and_disconnected_adapters_are_rejected(monkeypatch):
    monkeypatch.setattr(
        network.psutil,
        "net_if_addrs",
        lambda: {
            "Tailscale VPN": [_address("100.64.0.8")],
            "vEthernet (WSL)": [_address("172.20.0.1")],
            "Wi-Fi": [_address("192.168.1.25")],
            "Ethernet": [_address("10.1.1.5")],
        },
    )
    monkeypatch.setattr(
        network.psutil,
        "net_if_stats",
        lambda: {
            "Tailscale VPN": _stats(),
            "vEthernet (WSL)": _stats(),
            "Wi-Fi": _stats(),
            "Ethernet": _stats(up=False),
        },
    )
    monkeypatch.setattr(network, "_default_route_ipv4", lambda: "172.20.0.1")

    selection = network.discover_lan_ipv4()

    assert selection.address == "192.168.1.25"
    assert [item.adapter for item in selection.candidates] == ["Wi-Fi"]


def test_no_safe_private_adapter_falls_back_to_loopback(monkeypatch):
    monkeypatch.setattr(
        network.psutil,
        "net_if_addrs",
        lambda: {"WireGuard VPN": [_address("10.7.0.2")]},
    )
    monkeypatch.setattr(network.psutil, "net_if_stats", lambda: {"WireGuard VPN": _stats()})
    monkeypatch.setattr(network, "_default_route_ipv4", lambda: "10.7.0.2")

    selection = network.discover_lan_ipv4()

    assert selection.address == "127.0.0.1"
    assert selection.adapter is None
    assert selection.candidates == ()


def test_terminal_qr_encodes_only_the_join_url():
    url = "http://lanimals.local:8787/"

    rendered = network.terminal_qr(url)

    assert rendered.strip()
    assert "shared-secret" not in rendered


def test_mdns_service_info_advertises_stable_local_name_and_current_ip():
    info = network.build_mdns_service_info("192.168.0.103", 8787)

    assert info.type == "_http._tcp.local."
    assert info.name == "LANimals._http._tcp.local."
    assert info.server == "lanimals.local."
    assert info.parsed_addresses() == ["192.168.0.103"]
    assert info.port == 8787


def test_local_name_is_trusted_only_when_it_resolves_to_selected_lan_ip(monkeypatch):
    monkeypatch.setattr(
        network.socket,
        "gethostbyname_ex",
        lambda _host: ("lanimals.local", [], ["198.18.0.211"]),
    )
    assert not network.mdns_name_matches("192.168.0.103")

    monkeypatch.setattr(
        network.socket,
        "gethostbyname_ex",
        lambda _host: ("lanimals.local", [], ["192.168.0.103"]),
    )
    assert network.mdns_name_matches("192.168.0.103")
