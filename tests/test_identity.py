from lanimals.identity import DeviceRegistry


def test_persistent_token_keeps_its_animal_name_after_restart(tmp_path):
    database = tmp_path / "chat.db"

    first_registry = DeviceRegistry(database)
    first_name = first_registry.get_or_create("persistent-browser-token", temporary=False)

    restarted_registry = DeviceRegistry(database)
    restarted_name = restarted_registry.get_or_create("persistent-browser-token", temporary=False)

    assert first_name == restarted_name
    assert any(animal in first_name for animal in ("小熊", "水獭", "小兔", "小猫", "小狗"))


def test_temporary_token_gets_a_mysterious_animal_name(tmp_path):
    registry = DeviceRegistry(tmp_path / "chat.db")

    name = registry.get_or_create("temporary-browser-token", temporary=True)

    assert any(animal in name for animal in ("夜枭", "雾狐", "月貘"))


def test_many_persistent_devices_receive_unique_animal_names_without_numeric_suffixes(tmp_path):
    registry = DeviceRegistry(tmp_path / "chat.db")

    names = [registry.get_or_create(f"device-{index}", temporary=False) for index in range(20)]

    assert len(set(names)) == 20
    assert all(not any(character.isdigit() for character in name) for name in names)


def test_temporary_animal_pool_can_be_reused_without_login_failure(tmp_path):
    registry = DeviceRegistry(tmp_path / "chat.db")

    names = [registry.get_or_create(f"temporary-{index}", temporary=True) for index in range(50)]

    assert len(names) == 50
    assert all(name for name in names)
