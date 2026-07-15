from lanimals import __main__ as command
from lanimals.config import load_config, verify_password


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
    monkeypatch.setattr(command, "_lan_ip", lambda: "192.168.1.50")
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
