import re
import tomllib
from pathlib import Path


def test_wheel_package_data_includes_locale_json_files():
    project = Path(__file__).parents[1]
    with (project / "pyproject.toml").open("rb") as source:
        config = tomllib.load(source)

    package_data = config["tool"]["setuptools"]["package-data"]["lanimals"]
    assert "web/locales/*.json" in package_data

    package_discovery = config["tool"]["setuptools"]["packages"]["find"]
    assert package_discovery["include"] == ["lanimals*"]
    assert "data*" in package_discovery["exclude"]


def test_requirements_file_contains_every_runtime_dependency():
    project = Path(__file__).parents[1]
    with (project / "pyproject.toml").open("rb") as source:
        config = tomllib.load(source)

    def package_name(requirement: str) -> str:
        return re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0].strip().lower()

    runtime = {package_name(item) for item in config["project"]["dependencies"]}
    requirements = {
        package_name(line)
        for line in (project / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert runtime <= requirements
