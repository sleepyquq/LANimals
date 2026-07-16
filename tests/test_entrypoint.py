from lanimals import __main__ as command
from lanimals.config import load_config, verify_password
from lanimals.network import LanCandidate, LanSelection


def test_auto_bind_accepts_only_rfc1918_lan_addresses():
    assert command._is_private_lan_ipv4("192.168.1.50")
    assert command._is_private_lan_ipv4("10.20.30.40")
    assert command._is_private_lan_ipv4("172.16.8.9")
    assert not command._is_private_lan_ipv4("8.8.8.8")
    assert not command._is_private_lan_ipv4("127.0.0.1")
    assert not command._is_private_lan_ipv4("203.0.113.5")


def test_first_serve_prompts_host_for_password_and_starts_with_saved_hash(tmp_path, monkeypatch):
    answers = iter(["host-password", "host-password"])
    started = {}

    monkeypatch.setattr(command.getpass, "getpass", lambda _prompt: next(answers))
    monkeypatch.setattr(
        command,
        "discover_lan_ipv4",
        lambda: LanSelection(
            address="192.168.1.50",
            adapter="Wi-Fi",
            candidates=(LanCandidate(address="192.168.1.50", adapter="Wi-Fi", score=125),),
        ),
    )
    monkeypatch.setattr(command, "advertise_mdns", lambda *_args: None)
    monkeypatch.setattr(command, "mdns_name_matches", lambda *_args: False)
    monkeypatch.setattr(command, "terminal_qr", lambda url: f"QR:{url}\n")
    monkeypatch.setattr(
        command.uvicorn,
        "run",
        lambda app, **options: started.update({"app": app, "options": options}),
    )

    result = command.main(["serve", "--data-dir", str(tmp_path)])

    config = load_config(tmp_path)
    assert result == 0
    assert verify_password("host-password", config.password_hash)
    assert started["app"].title == "LANimals"
    assert started["options"]["host"] == "192.168.1.50"
    assert started["options"]["port"] == 8787


def test_serve_prints_local_name_ip_fallback_qr_and_network_guidance(tmp_path, monkeypatch, capsys):
    from lanimals.config import create_config

    create_config(tmp_path, password="host-password")
    closed = []

    class FakeAdvertisement:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(
        command,
        "discover_lan_ipv4",
        lambda: LanSelection(
            address="192.168.0.103",
            adapter="Wi-Fi",
            candidates=(
                LanCandidate(address="192.168.0.103", adapter="Wi-Fi", score=125),
                LanCandidate(address="192.168.0.104", adapter="以太网", score=25),
            ),
        ),
    )
    monkeypatch.setattr(command, "advertise_mdns", lambda *_args: FakeAdvertisement())
    monkeypatch.setattr(command, "mdns_name_matches", lambda *_args: True)
    monkeypatch.setattr(command, "terminal_qr", lambda url: f"QR:{url}\n")
    monkeypatch.setattr(command.uvicorn, "run", lambda *_args, **_options: None)

    assert command.main(["serve", "--data-dir", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "已选择网卡: Wi-Fi (192.168.0.103)" in output
    assert "其他可用地址: 以太网 (192.168.0.104)" in output
    assert "推荐访问: http://lanimals.local:8787/" in output
    assert "备用地址: http://192.168.0.103:8787/" in output
    assert "QR:http://lanimals.local:8787/" in output
    assert "Windows 防火墙" in output
    assert "访客 Wi-Fi" in output
    assert closed == [True]


def test_clear_command_requires_exact_local_confirmation(tmp_path, monkeypatch):
    from lanimals.config import create_config
    from lanimals.store import ChatStore

    create_config(tmp_path, password="host-password")
    store = ChatStore(tmp_path / "chat.db")
    store.create_message(sender_name="小熊", body="保留或删除")

    monkeypatch.setattr("builtins.input", lambda _prompt: "not confirmed")
    assert command.main(["clear", "--data-dir", str(tmp_path)]) == 1
    assert len(store.list_messages()) == 1

    monkeypatch.setattr("builtins.input", lambda _prompt: "DELETE ALL")
    assert command.main(["clear", "--data-dir", str(tmp_path)]) == 0
    assert store.list_messages() == []


def test_no_command_opens_host_management_menu(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _prompt: "0")

    assert command.main([]) == 0

    output = capsys.readouterr().out
    assert "LANimals 主机管理" in output
    assert "启动聊天室" in output
    assert "修改群聊密码" in output
    assert "清空聊天记录和附件" in output


def test_management_menu_reuses_config_and_clear_commands(tmp_path, monkeypatch, capsys):
    from lanimals.config import create_config, parse_size
    from lanimals.store import ChatStore

    create_config(tmp_path, password="host-password")
    store = ChatStore(tmp_path / "chat.db")
    store.create_message(sender_name="小熊", body="通过菜单清空")
    answers = iter(["3", "512MB", "4", "DELETE ALL", "0"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    assert command.main(["manage", "--data-dir", str(tmp_path)]) == 0

    assert load_config(tmp_path).max_upload_bytes == parse_size("512MB")
    assert store.list_messages() == []
    output = capsys.readouterr().out
    assert "重启服务后生效" in output
    assert "建议先停止正在运行的服务" in output
