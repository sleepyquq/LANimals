"""打包版与源码运行时的数据目录选择。"""

from __future__ import annotations

from pathlib import Path

from lanimals.__main__ import default_gui_data_dir


def test_source_runs_keep_data_in_the_working_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    for platform in ("win32", "darwin", "linux"):
        assert default_gui_data_dir(frozen=False, executable="/usr/bin/python3", platform=platform) == tmp_path / "data"


def test_portable_windows_and_linux_builds_keep_data_beside_the_executable(tmp_path: Path) -> None:
    executable = tmp_path / "LANimals" / "LANimals.exe"
    for platform in ("win32", "linux"):
        assert default_gui_data_dir(frozen=True, executable=str(executable), platform=platform) == executable.parent / "data"


def test_macos_app_bundle_stores_data_in_application_support(tmp_path: Path) -> None:
    """.app 包内部可能是只读的（App Translocation），且会随应用一起被替换，数据必须放在用户目录。"""
    executable = tmp_path / "LANimals.app" / "Contents" / "MacOS" / "LANimals"
    home = tmp_path / "home"

    data_dir = default_gui_data_dir(frozen=True, executable=str(executable), platform="darwin", home=home)

    assert data_dir == home / "Library" / "Application Support" / "LANimals"
    assert "LANimals.app" not in data_dir.parts


def test_desktop_entry_point_does_not_import_the_web_server_up_front() -> None:
    """打包版入口就是 lanimals.__main__；打开控制面板前不应先加载 FastAPI/uvicorn。"""
    import os
    import subprocess
    import sys

    script = "import sys, lanimals.__main__; print(sorted(m for m in ('fastapi', 'uvicorn', 'lanimals.main') if m in sys.modules))"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parent.parent,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
