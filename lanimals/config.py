"""Host-only LANimals configuration and password hashing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_SIZE_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)\s*$", re.IGNORECASE)
_SIZE_MULTIPLIERS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    max_upload_size: str
    max_upload_bytes: int
    password_hash: str
    gui_local_only: bool = False
    gui_selected_adapter: str | None = None
    # 桌面端是否广播并在主页展示固定域名 lanimals.local；旧配置缺省为启用。
    gui_use_domain: bool = True
    # 可选 HTTPS：使用本机生成的自签名证书加密局域网流量；默认关闭。
    https: bool = False


def parse_size(value: str) -> int:
    match = _SIZE_PATTERN.fullmatch(value)
    if not match:
        raise ValueError("大小格式应为数字加 B、KB、MB 或 GB，例如 512MB")
    amount = float(match.group(1))
    if amount <= 0:
        raise ValueError("文件大小上限必须大于 0")
    return int(amount * _SIZE_MULTIPLIERS[match.group(2).upper()])


MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"群聊密码至少需要 {MIN_PASSWORD_LENGTH} 个字符")
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_config(
    data_dir: Path,
    *,
    password: str,
    max_upload_size: str = "2GB",
    host: str = "auto",
    port: int = 8787,
) -> Config:
    parse_size(max_upload_size)
    config = Config(
        host=host,
        port=port,
        max_upload_size=max_upload_size.upper(),
        max_upload_bytes=parse_size(max_upload_size),
        password_hash=hash_password(password),
        gui_local_only=False,
        gui_selected_adapter=None,
    )
    _write_config(Path(data_dir), config)
    return config


def load_config(data_dir: Path) -> Config:
    path = Path(data_dir) / "config.toml"
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    size = str(raw.get("max_upload_size", "2GB"))
    selected_adapter = raw.get("gui_selected_adapter")
    if not isinstance(selected_adapter, str) or not selected_adapter.strip():
        selected_adapter = None
    return Config(
        host=str(raw.get("host", "auto")),
        port=int(raw.get("port", 8787)),
        max_upload_size=size,
        max_upload_bytes=parse_size(size),
        password_hash=str(raw["password_hash"]),
        gui_local_only=raw.get("gui_local_only") is True,
        gui_selected_adapter=selected_adapter,
        gui_use_domain=raw.get("gui_use_domain") is not False,
        https=raw.get("https") is True,
    )


def update_max_upload_size(data_dir: Path, value: str) -> Config:
    current = load_config(data_dir)
    updated = Config(
        host=current.host,
        port=current.port,
        max_upload_size=value.upper(),
        max_upload_bytes=parse_size(value),
        password_hash=current.password_hash,
        gui_local_only=current.gui_local_only,
        gui_selected_adapter=current.gui_selected_adapter,
        gui_use_domain=current.gui_use_domain,
        https=current.https,
    )
    _write_config(Path(data_dir), updated)
    return updated


def update_password(data_dir: Path, password: str) -> Config:
    current = load_config(data_dir)
    updated = Config(
        host=current.host,
        port=current.port,
        max_upload_size=current.max_upload_size,
        max_upload_bytes=current.max_upload_bytes,
        password_hash=hash_password(password),
        gui_local_only=current.gui_local_only,
        gui_selected_adapter=current.gui_selected_adapter,
        gui_use_domain=current.gui_use_domain,
        https=current.https,
    )
    _write_config(Path(data_dir), updated)
    return updated


def update_gui_network_preferences(
    data_dir: Path,
    *,
    local_only: bool,
    selected_adapter: str | None,
) -> Config:
    """保存桌面端的网络偏好，同时保留 CLI 使用的 host/port 语义。"""
    current = load_config(data_dir)
    updated = Config(
        host=current.host,
        port=current.port,
        max_upload_size=current.max_upload_size,
        max_upload_bytes=current.max_upload_bytes,
        password_hash=current.password_hash,
        gui_local_only=local_only,
        gui_selected_adapter=selected_adapter,
        gui_use_domain=current.gui_use_domain,
        https=current.https,
    )
    _write_config(Path(data_dir), updated)
    return updated


def update_gui_settings(
    data_dir: Path,
    *,
    local_only: bool,
    selected_adapter: str | None,
    max_upload_size: str,
    use_domain: bool | None = None,
    https: bool | None = None,
) -> Config:
    """原子保存设置页的网络偏好与上传上限，供一次“保存并重启”使用。"""
    current = load_config(data_dir)
    updated = Config(
        host=current.host,
        port=current.port,
        max_upload_size=max_upload_size.upper(),
        max_upload_bytes=parse_size(max_upload_size),
        password_hash=current.password_hash,
        gui_local_only=local_only,
        gui_selected_adapter=selected_adapter,
        gui_use_domain=current.gui_use_domain if use_domain is None else use_domain,
        https=current.https if https is None else https,
    )
    _write_config(Path(data_dir), updated)
    return updated


def _write_config(data_dir: Path, config: Config) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "config.toml"
    temporary = data_dir / ".config.toml.tmp"
    selected_adapter_line = ""
    if config.gui_selected_adapter:
        # JSON 字符串转义与 TOML 基本字符串兼容，可安全保留网卡名称中的引号和 Unicode。
        selected_adapter_line = f"gui_selected_adapter = {json.dumps(config.gui_selected_adapter, ensure_ascii=False)}\n"
    content = (
        f'host = "{config.host}"\n'
        f"port = {config.port}\n"
        f'max_upload_size = "{config.max_upload_size}"\n'
        f'password_hash = "{config.password_hash}"\n'
        f"gui_local_only = {'true' if config.gui_local_only else 'false'}\n"
        f"gui_use_domain = {'true' if config.gui_use_domain else 'false'}\n"
        f"https = {'true' if config.https else 'false'}\n"
        f"{selected_adapter_line}"
    )
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)
