"""局域网地址选择、mDNS 广播与终端二维码。"""

from __future__ import annotations

import io
import ipaddress
import socket
from dataclasses import dataclass

import psutil
import segno
from zeroconf import IPVersion, ServiceInfo, Zeroconf

_VIRTUAL_ADAPTER_HINTS = (
    "vpn",
    "virtual",
    "vethernet",
    "hyper-v",
    "wsl",
    "vmware",
    "virtualbox",
    "tailscale",
    "zerotier",
    "wireguard",
    "docker",
    "loopback",
    "bluetooth",
    "蓝牙",
    "虚拟",
)
_PHYSICAL_ADAPTER_HINTS = ("wi-fi", "wifi", "wlan", "wireless", "ethernet", "以太网", "无线")
_PHYSICAL_ADAPTER_PREFIXES = ("eth", "en", "wl")


@dataclass(frozen=True)
class LanCandidate:
    address: str
    adapter: str
    score: int


@dataclass(frozen=True)
class LanSelection:
    address: str
    adapter: str | None
    candidates: tuple[LanCandidate, ...]


def is_private_lan_ipv4(value: str) -> bool:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return False
    private_networks = (
        ipaddress.IPv4Network("10.0.0.0/8"),
        ipaddress.IPv4Network("172.16.0.0/12"),
        ipaddress.IPv4Network("192.168.0.0/16"),
    )
    return any(address in network for network in private_networks)


def _default_route_ipv4() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # TEST-NET-1 不需要真正可达，connect 只让系统选择默认出站路由。
        sock.connect(("192.0.2.1", 80))
        candidate = str(sock.getsockname()[0])
        return candidate if is_private_lan_ipv4(candidate) else None
    except OSError:
        return None
    finally:
        sock.close()


def _is_virtual_adapter(name: str) -> bool:
    normalized = name.casefold()
    return any(hint in normalized for hint in _VIRTUAL_ADAPTER_HINTS)


def _looks_physical(name: str) -> bool:
    normalized = name.casefold()
    return normalized.startswith(_PHYSICAL_ADAPTER_PREFIXES) or any(
        hint in normalized for hint in _PHYSICAL_ADAPTER_HINTS
    )


def discover_lan_ipv4() -> LanSelection:
    """选择安全的 RFC1918 网卡地址，找不到时仅绑定回环地址。"""

    default_address = _default_route_ipv4()
    addresses = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    candidates: list[LanCandidate] = []
    seen: set[str] = set()

    for adapter, adapter_addresses in addresses.items():
        adapter_stats = stats.get(adapter)
        if adapter_stats is not None and not adapter_stats.isup:
            continue
        if _is_virtual_adapter(adapter):
            continue

        for item in adapter_addresses:
            if item.family != socket.AF_INET or not is_private_lan_ipv4(item.address):
                continue
            if item.address in seen:
                continue
            seen.add(item.address)
            score = 0
            if item.address == default_address:
                score += 100
            if _looks_physical(adapter):
                score += 20
            if adapter_stats is not None and (adapter_stats.speed or 0) > 0:
                score += 5
            candidates.append(LanCandidate(address=item.address, adapter=adapter, score=score))

    candidates.sort(
        key=lambda item: (-item.score, item.adapter.casefold(), int(ipaddress.IPv4Address(item.address)))
    )
    if not candidates:
        return LanSelection(address="127.0.0.1", adapter=None, candidates=())
    selected = candidates[0]
    return LanSelection(
        address=selected.address,
        adapter=selected.adapter,
        candidates=tuple(candidates),
    )


def terminal_qr(url: str) -> str:
    """生成适合 PowerShell、Windows Terminal 和类 Unix 终端的紧凑二维码。"""

    output = io.StringIO()
    segno.make(url, error="m", micro=False).terminal(out=output, compact=True, border=2)
    return output.getvalue()


def build_mdns_service_info(address: str, port: int) -> ServiceInfo:
    return ServiceInfo(
        "_http._tcp.local.",
        "LANimals._http._tcp.local.",
        addresses=[socket.inet_aton(address)],
        port=port,
        properties={"path": "/"},
        server="lanimals.local.",
    )


def mdns_name_matches(address: str, hostname: str = "lanimals.local") -> bool:
    """防止代理 fake-IP 或不支持 mDNS 的解析器把固定名称导向错误地址。"""

    try:
        resolved = socket.gethostbyname_ex(hostname)[2]
    except OSError:
        return False
    return address in resolved


class MdnsAdvertisement:
    def __init__(self, zeroconf: Zeroconf, info: ServiceInfo) -> None:
        self._zeroconf = zeroconf
        self._info = info

    def close(self) -> None:
        try:
            self._zeroconf.unregister_service(self._info)
        finally:
            self._zeroconf.close()


def advertise_mdns(address: str, port: int) -> MdnsAdvertisement:
    zeroconf = Zeroconf(interfaces=[address], ip_version=IPVersion.V4Only)
    info = build_mdns_service_info(address, port)
    try:
        zeroconf.register_service(info, allow_name_change=True)
    except Exception:
        zeroconf.close()
        raise
    return MdnsAdvertisement(zeroconf, info)
