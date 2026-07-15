"""Cross-platform LANimals command-line entry point."""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
from typing import Sequence

import uvicorn

from lanimals.cli import change_password, clear_data
from lanimals.config import create_config, load_config, update_max_upload_size
from lanimals.main import create_app
from lanimals.network import (
    advertise_mdns,
    discover_lan_ipv4,
    is_private_lan_ipv4 as _is_private_lan_ipv4,
    mdns_name_matches,
    terminal_qr,
)


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


def _lan_ip() -> str:
    return discover_lan_ipv4().address


def _print_join_information(bind_host: str, port: int, selection, mdns_available: bool) -> None:
    if selection is not None:
        if selection.adapter:
            print(f"已选择网卡: {selection.adapter} ({selection.address})")
        else:
            print("未检测到可靠的局域网网卡，仅允许本机访问。")
        if len(selection.candidates) > 1:
            alternatives = "、".join(
                f"{candidate.adapter} ({candidate.address})" for candidate in selection.candidates[1:]
            )
            print(f"其他可用地址: {alternatives}")

    ip_url = f"http://{bind_host}:{port}/"
    join_url = f"http://lanimals.local:{port}/" if mdns_available else ip_url
    print(f"推荐访问: {join_url}")
    if join_url != ip_url:
        print(f"备用地址: {ip_url}")
    print("手机扫码加入（二维码只包含访问地址，不包含群聊密码）:")
    try:
        print(terminal_qr(join_url), end="")
    except (OSError, UnicodeError, ValueError):
        print("当前终端无法显示二维码，请手动输入上方地址。")
    print("若其他设备无法访问，请允许 Python 通过 Windows 防火墙的专用网络。")
    print("访客 Wi-Fi、客户端隔离或跨 VLAN 网络可能阻止设备互访。")


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
        selection = discover_lan_ipv4() if config.host == "auto" else None
        bind_host = selection.address if selection is not None else config.host
        advertisement = None
        if _is_private_lan_ipv4(bind_host):
            try:
                advertisement = advertise_mdns(bind_host, config.port)
            except Exception as error:
                print(f"局域网名称广播不可用，将使用 IP 地址访问：{error}")
        mdns_available = advertisement is not None and mdns_name_matches(bind_host)
        if advertisement is not None and not mdns_available:
            print("lanimals.local 未解析到当前局域网地址，二维码将使用 IP。")
            print("若正在使用代理/TUN，请将 *.local 和局域网地址设为直连。")
        _print_join_information(bind_host, config.port, selection, mdns_available)
        print(f"数据目录: {data_dir}")
        try:
            uvicorn.run(app, host=bind_host, port=config.port)
        finally:
            if advertisement is not None:
                advertisement.close()
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
