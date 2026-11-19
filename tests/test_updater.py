"""一键升级：版本判断、安装包解压、程序文件替换与回滚。"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from lanimals import __version__, updater


def _release(**overrides) -> updater.ReleaseInfo:
    values = dict(
        version="v99.0.0",
        page_url="https://github.com/sleepyquq/LANimals/releases/tag/v99.0.0",
        asset_name="pkg",
        asset_url="https://example.invalid/pkg",
        asset_size=0,
        asset_sha256=None,
    )
    values.update(overrides)
    return updater.ReleaseInfo(**values)


def test_parse_version_and_comparison() -> None:
    assert updater.parse_version("v0.2.10") == (0, 2, 10)
    assert updater.parse_version("1.0.0") == (1, 0, 0)
    with pytest.raises(updater.UpdateError):
        updater.parse_version("v1.0")
    assert _release(version="v99.0.0").is_newer
    assert not _release(version=f"v{__version__}").is_newer
    assert not _release(version="v0.0.1").is_newer


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("win32", "AMD64", "LANimals-windows-x64.zip"),
        ("linux", "x86_64", "LANimals-linux-x64.tar.gz"),
        ("darwin", "arm64", "LANimals-macos.zip"),
        ("linux", "aarch64", None),
        ("win32", "ARM64", None),
    ],
)
def test_asset_name_matches_release_workflow(system: str, machine: str, expected: str | None) -> None:
    assert updater.asset_name_for_platform(system, machine) == expected


def test_release_workflow_uploads_the_expected_asset_names() -> None:
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "build-release.yml").read_text(encoding="utf-8")
    for name in ("LANimals-windows-x64.zip", "LANimals-linux-x64.tar.gz", "LANimals-macos.zip"):
        assert f"artifact_name: {name}" in workflow


def test_parse_release_picks_platform_asset_and_digest() -> None:
    payload = {
        "tag_name": "v0.3.0",
        "html_url": "https://github.com/sleepyquq/LANimals/releases/tag/v0.3.0",
        "assets": [
            {"name": "other.zip", "browser_download_url": "https://x/other.zip", "size": 1},
            {
                "name": "LANimals-linux-x64.tar.gz",
                "browser_download_url": "https://x/linux.tar.gz",
                "size": 1234,
                "digest": "sha256:ABCDEF",
            },
        ],
    }
    release = updater.parse_release(payload, "LANimals-linux-x64.tar.gz")
    assert release.version == "v0.3.0"
    assert release.asset_url == "https://x/linux.tar.gz"
    assert release.asset_size == 1234
    assert release.asset_sha256 == "abcdef"

    missing = updater.parse_release(payload, "LANimals-macos.zip")
    assert missing.asset_url is None and missing.asset_name is None


def test_source_run_cannot_self_update() -> None:
    with pytest.raises(updater.UpdateError) as error:
        updater.current_layout(frozen=False)
    assert error.value.code == "sourceRun"


def test_layout_for_portable_folder(tmp_path: Path) -> None:
    exe = tmp_path / "LANimals" / "LANimals.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    layout = updater.current_layout(frozen=True, executable=str(exe), system="win32")
    assert layout.kind == "dir"
    assert layout.target == exe.parent.resolve()
    assert layout.relaunch == exe.resolve()


def test_layout_for_macos_app(tmp_path: Path) -> None:
    exe = tmp_path / "LANimals.app" / "Contents" / "MacOS" / "LANimals"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    layout = updater.current_layout(frozen=True, executable=str(exe), system="darwin")
    assert layout.kind == "app"
    assert layout.target == (tmp_path / "LANimals.app").resolve()


def test_translocated_macos_app_is_rejected(tmp_path: Path) -> None:
    exe = tmp_path / "AppTranslocation" / "X" / "LANimals.app" / "Contents" / "MacOS" / "LANimals"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    with pytest.raises(updater.UpdateError) as error:
        updater.current_layout(frozen=True, executable=str(exe), system="darwin")
    assert error.value.code == "translocated"


def test_child_environment_drops_pyinstaller_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "/old")
    monkeypatch.setenv("_MEIPASS2", "/old")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/old/_internal")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib")
    env = updater.clean_child_environment()
    assert "_PYI_APPLICATION_HOME_DIR" not in env and "_MEIPASS2" not in env
    assert env["LD_LIBRARY_PATH"] == "/usr/lib"
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


# ---- 端到端：用当前系统的真实安装包格式模拟一次升级 ----


def _write_program(root: Path, marker: str) -> None:
    """按当前平台的打包结构写一个假的程序目录。"""
    exe = updater.executable_in_package(root)
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text(marker, encoding="utf-8")
    exe.chmod(0o755)
    internal = (root / "Contents" / "Frameworks") if sys.platform == "darwin" else (root / "_internal")
    internal.mkdir(parents=True, exist_ok=True)
    (internal / f"{marker}.txt").write_text(marker, encoding="utf-8")


def _build_archive(tmp_path: Path) -> tuple[Path, str]:
    build = tmp_path / "build"
    package = build / updater.package_root_name()
    _write_program(package, "new")
    name = updater.asset_name_for_platform(machine="x86_64")
    archive = tmp_path / name
    if name.endswith(".tar.gz"):
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(package, arcname=package.name)
    elif sys.platform == "darwin":
        subprocess.run(["/usr/bin/ditto", "-c", "-k", "--keepParent", str(package), str(archive)], check=True)
    else:
        with zipfile.ZipFile(archive, "w") as bundle:
            for path in sorted(package.rglob("*")):
                bundle.write(path, path.relative_to(build).as_posix())
    return archive, name


def _install(tmp_path: Path) -> tuple[updater.InstallLayout, Path]:
    """返回旧版安装位置与它实际使用的数据目录。"""
    install = tmp_path / "install"
    app_root = install / updater.package_root_name()
    _write_program(app_root, "old")
    if sys.platform == "darwin":
        data_dir = tmp_path / "Application Support" / "LANimals"
        layout = updater.InstallLayout(kind="app", target=app_root, relaunch=app_root)
    else:
        data_dir = app_root / "data"
        layout = updater.InstallLayout(kind="dir", target=app_root, relaunch=updater.executable_in_package(app_root))
    data_dir.mkdir(parents=True)
    (data_dir / "chat.db").write_text("messages", encoding="utf-8")
    return layout, data_dir


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[updater.InstallLayout, Path, Path]:
    archive, name = _build_archive(tmp_path)
    payload = archive.read_bytes()
    monkeypatch.setattr(updater, "_open", lambda url, **_kwargs: _FakeResponse(payload))
    layout, data_dir = _install(tmp_path)
    import hashlib

    release = _release(asset_name=name, asset_size=len(payload), asset_sha256=hashlib.sha256(payload).hexdigest())
    progress: list[int] = []
    plan_path = updater.prepare_update(release, data_dir, layout, progress=progress.append)
    assert progress and progress[-1] == 100
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    # 用一个已经退出的进程代替旧版程序。
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    plan["pid"] = finished.pid
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return layout, data_dir, plan_path


class _FakeResponse(io.BytesIO):
    headers: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def _internal_dir(root: Path) -> Path:
    return (root / "Contents" / "Frameworks") if sys.platform == "darwin" else (root / "_internal")


def test_full_update_replaces_program_and_keeps_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout, data_dir, plan_path = _prepare(tmp_path, monkeypatch)
    relaunched: list[Path] = []
    monkeypatch.setattr(updater, "relaunch", lambda path, kind, system=sys.platform: relaunched.append(path))

    from lanimals.__main__ import main

    assert main(["--apply-update", str(plan_path)]) == 0

    root = layout.target
    assert updater.executable_in_package(root).read_text(encoding="utf-8") == "new"
    assert (_internal_dir(root) / "new.txt").exists()
    assert not (_internal_dir(root) / "old.txt").exists()
    assert (data_dir / "chat.db").read_text(encoding="utf-8") == "messages"
    if sys.platform != "win32":
        assert updater.executable_in_package(root).stat().st_mode & 0o111
    assert relaunched == [layout.relaunch]

    result = updater.pop_update_result(data_dir)
    assert result == {"version": "v99.0.0", "ok": True}
    assert not updater.update_workspace(data_dir).exists()
    assert (data_dir / "chat.db").exists()


def test_failed_copy_rolls_back_to_old_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout, data_dir, plan_path = _prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(updater, "relaunch", lambda *args, **kwargs: None)
    real_copy = updater._copy
    calls = {"count": 0}

    def flaky_copy(source: Path, target: Path) -> None:
        calls["count"] += 1
        real_copy(source, target)
        if calls["count"] == 1:
            raise OSError("disk full")

    monkeypatch.setattr(updater, "_copy", flaky_copy)
    assert updater.apply_update(plan_path) == 1

    root = layout.target
    assert updater.executable_in_package(root).read_text(encoding="utf-8") == "old"
    assert (_internal_dir(root) / "old.txt").exists()
    assert not (_internal_dir(root) / "new.txt").exists()
    assert (data_dir / "chat.db").read_text(encoding="utf-8") == "messages"
    assert updater.pop_update_result(data_dir)["ok"] is False


def test_corrupted_download_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive, name = _build_archive(tmp_path)
    payload = archive.read_bytes()
    monkeypatch.setattr(updater, "_open", lambda url, **_kwargs: _FakeResponse(payload))
    layout, data_dir = _install(tmp_path)
    release = _release(asset_name=name, asset_size=len(payload), asset_sha256="0" * 64)
    with pytest.raises(updater.UpdateError) as error:
        updater.prepare_update(release, data_dir, layout)
    assert error.value.code == "corrupt"


def test_zip_with_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.txt", "x")
    with pytest.raises(updater.UpdateError):
        updater.extract_package(archive, tmp_path / "out", system="win32")
    assert not (tmp_path / "escape.txt").exists()
