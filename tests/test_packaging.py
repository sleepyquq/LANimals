import tomllib
from pathlib import Path


def test_wheel_package_data_includes_locale_json_files():
    project = Path(__file__).parents[1]
    with (project / "pyproject.toml").open("rb") as source:
        config = tomllib.load(source)

    package_data = config["tool"]["setuptools"]["package-data"]["lanimals"]
    assert "web/locales/*.json" in package_data
