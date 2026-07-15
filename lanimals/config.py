"""Host-only LANimals configuration and password hashing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_SIZE_PATTERN = re.compile(r"^\s*(\d+)\s*(B|KB|MB|GB)\s*$", re.IGNORECASE)
_SIZE_MULTIPLIERS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    max_upload_size: str
    max_upload_bytes: int
    password_hash: str


def parse_size(value: str) -> int:
    match = _SIZE_PATTERN.fullmatch(value)
    if not match:
        raise ValueError("大小格式应为数字加 B、KB、MB 或 GB，例如 512MB")
    amount = int(match.group(1))
    if amount <= 0:
        raise ValueError("文件大小上限必须大于 0")
    return amount * _SIZE_MULTIPLIERS[match.group(2).upper()]


def hash_password(password: str) -> str:
    if len(password) < 4:
        raise ValueError("群聊密码至少需要 4 个字符")
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
    )
    _write_config(Path(data_dir), config)
    return config


def load_config(data_dir: Path) -> Config:
    path = Path(data_dir) / "config.toml"
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    size = str(raw.get("max_upload_size", "2GB"))
    return Config(
        host=str(raw.get("host", "auto")),
        port=int(raw.get("port", 8787)),
        max_upload_size=size,
        max_upload_bytes=parse_size(size),
        password_hash=str(raw["password_hash"]),
    )


def update_max_upload_size(data_dir: Path, value: str) -> Config:
    current = load_config(data_dir)
    updated = Config(
        host=current.host,
        port=current.port,
        max_upload_size=value.upper(),
        max_upload_bytes=parse_size(value),
        password_hash=current.password_hash,
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
    )
    _write_config(Path(data_dir), updated)
    return updated


def _write_config(data_dir: Path, config: Config) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "config.toml"
    temporary = data_dir / ".config.toml.tmp"
    content = (
        f'host = "{config.host}"\n'
        f"port = {config.port}\n"
        f'max_upload_size = "{config.max_upload_size}"\n'
        f'password_hash = "{config.password_hash}"\n'
    )
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)
