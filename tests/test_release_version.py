"""网页填版本号发布前的校验规则。"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_release_version import ReleaseCheckError, check_release


def _pyproject(tmp_path: Path, version: str) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(f'[project]\nname = "lanimals"\nversion = "{version}"\n', encoding="utf-8")
    return path


def test_accepts_a_new_version_that_matches_pyproject_on_main(tmp_path: Path) -> None:
    check_release("v0.3.0", ref="refs/heads/main", pyproject=_pyproject(tmp_path, "0.3.0"), existing_tags={"v0.2.0"})


@pytest.mark.parametrize("version", ["0.3.0", "v0.3", "v0.3.0-beta", "V0.3.0", " v0.3.0", "v0.3.0\n"])
def test_rejects_malformed_versions(tmp_path: Path, version: str) -> None:
    with pytest.raises(ReleaseCheckError, match="格式"):
        check_release(version, ref="refs/heads/main", pyproject=_pyproject(tmp_path, "0.3.0"), existing_tags=set())


def test_rejects_a_version_that_differs_from_pyproject(tmp_path: Path) -> None:
    with pytest.raises(ReleaseCheckError, match="pyproject.toml"):
        check_release("v0.3.0", ref="refs/heads/main", pyproject=_pyproject(tmp_path, "0.2.0"), existing_tags=set())


def test_rejects_an_existing_tag(tmp_path: Path) -> None:
    with pytest.raises(ReleaseCheckError, match="已存在"):
        check_release("v0.2.0", ref="refs/heads/main", pyproject=_pyproject(tmp_path, "0.2.0"), existing_tags={"v0.2.0"})


def test_rejects_releases_from_other_branches(tmp_path: Path) -> None:
    with pytest.raises(ReleaseCheckError, match="main"):
        check_release("v0.3.0", ref="refs/heads/feature", pyproject=_pyproject(tmp_path, "0.3.0"), existing_tags=set())


def test_repository_version_is_readable() -> None:
    """真实仓库的 pyproject.toml 必须能被读取，否则网页发布永远无法通过校验。"""
    from scripts.check_release_version import project_version

    assert project_version(Path(__file__).resolve().parent.parent / "pyproject.toml")
