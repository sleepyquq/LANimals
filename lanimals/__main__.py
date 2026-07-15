"""Cross-platform LANimals command-line entry point."""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import os
import socket
from pathlib import Path
from typing import Sequence

import uvicorn

from lanimals.cli import change_password, clear_data
from lanimals.config import create_config, load_config, update_max_upload_size
from lanimals.main import create_app


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lanimals", description="LANimals local network chat")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="start the LAN chat service")
    serve.add_argument("--data-dir", default="data")

    clear = subparsers.add_parser("clear", help="clear all messages and uploaded files on this host")
    clear.add_argument("--data-dir", default="data")

    password = subparsers.add_parser("password", help="change the browser login password on this host")
    password.add_argument("--data-dir", default="data")

    config = subparsers.add_parser("config", help="change host-only settings")
    config.add_argument("--data-dir", default="data")
    config.add_argument("--max-upload-size", required=True, metavar="SIZE")
    return parser


def _prompt_new_password() -> str:
    first = getpass.getpass("请设置 LANimals 群聊密码：")
    second = getpass.getpass("请再次输入群聊密码：")
    if first != second:
        raise ValueError("两次输入的密码不一致")
    return first


def _is_private_lan_ipv4(value: str) -> bool:
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


def _lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 80))
        candidate = str(sock.getsockname()[0])
        return candidate if _is_private_lan_ipv4(candidate) else "127.0.0.1"
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_dir = Path(args.data_dir).expanduser().resolve()

    if args.command == "serve":
        config_path = data_dir / "config.toml"
        if not config_path.exists():
            print("首次启动 LANimals，配置仅保存在当前服务主机。")
            password = os.environ.get("LANIMALS_PASSWORD") or _prompt_new_password()
            create_config(data_dir, password=password)
        config = load_config(data_dir)
        app = create_app(
            data_dir=data_dir,
            password_hash_provider=lambda: load_config(data_dir).password_hash,
            max_upload_bytes=config.max_upload_bytes,
        )
        bind_host = _lan_ip() if config.host == "auto" else config.host
        print(f"访问地址: http://{bind_host}:{config.port}")
        print(f"数据目录: {data_dir}")
        uvicorn.run(app, host=bind_host, port=config.port)
        return 0

    if args.command == "clear":
        print("这将永久删除所有聊天消息和上传文件，但保留主机配置与设备名称。")
        if input("输入 DELETE ALL 确认：") != "DELETE ALL":
            print("已取消。")
            return 1
        clear_data(data_dir)
        print("消息和上传文件已清空。")
        return 0

    if args.command == "password":
        if not (data_dir / "config.toml").exists():
            print("尚未初始化配置，请先运行 serve。")
            return 1
        change_password(data_dir, _prompt_new_password())
        print("群聊密码已更新。")
        return 0

    if args.command == "config":
        if not (data_dir / "config.toml").exists():
            print("尚未初始化配置，请先运行 serve。")
            return 1
        updated = update_max_upload_size(data_dir, args.max_upload_size)
        print(f"单文件上传上限已设为 {updated.max_upload_size}，重启服务后生效。")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
