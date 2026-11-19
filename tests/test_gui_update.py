"""设置页“检查更新”入口与一键升级卡片。"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from lanimals import __version__, updater
from lanimals.gui.dialogs import UpdateDialog
from lanimals.gui.i18n import t


@pytest.fixture(scope="module")
def qt_application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from lanimals.gui import app as app_module

    monkeypatch.setattr(app_module.SystemTray, "start", lambda _tray: None)
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.LANimalsApp(data_dir=tmp_path)

    def run_synchronously(action, *, on_success=None, on_error=None) -> None:
        try:
            result = action()
        except Exception as error:
            if on_error is not None:
                on_error(error)
        else:
            if on_success is not None:
                on_success(result)

    monkeypatch.setattr(window, "run_controller_action", run_synchronously)
    window.show_settings()
    return window


def _release(version: str) -> updater.ReleaseInfo:
    return updater.ReleaseInfo(
        version=version,
        page_url="https://github.com/sleepyquq/LANimals/releases/latest",
        asset_name="LANimals-windows-x64.zip",
        asset_url="https://example.invalid/pkg.zip",
        asset_size=60 * 1024 * 1024,
        asset_sha256=None,
    )


def test_settings_header_shows_version_and_reports_up_to_date(
    qt_application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = _window(tmp_path, monkeypatch)
    assert window.update_button is not None
    assert f"v{__version__}" in window.update_button.text()

    monkeypatch.setattr(updater, "check_latest", lambda: _release(f"v{__version__}"))
    window.update_button.click()
    assert window.update_button.text() == t("gui.upToDate")
    assert window._modal_overlay is None


def test_network_failure_is_reported_on_the_button(
    qt_application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = _window(tmp_path, monkeypatch)

    def fail():
        raise updater.UpdateError("network")

    monkeypatch.setattr(updater, "check_latest", fail)
    window.check_for_updates()
    assert window.update_button.text() == t("gui.updateCheckFailed")
    assert window.update_button.isEnabled()


def test_source_run_offers_the_download_page_instead(
    qt_application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = _window(tmp_path, monkeypatch)
    monkeypatch.setattr(updater, "check_latest", lambda: _release("v99.0.0"))
    window.check_for_updates()
    card = window._modal_overlay._card
    assert isinstance(card, UpdateDialog)
    assert card.body_label.text() == t("gui.updateSourceRun")
    assert card.notes_label is None


def test_update_now_prepares_launches_helper_and_quits(
    qt_application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = _window(tmp_path, monkeypatch)
    layout = updater.InstallLayout(kind="dir", target=tmp_path, relaunch=tmp_path / "LANimals.exe")
    monkeypatch.setattr(updater, "check_latest", lambda: _release("v99.0.0"))
    monkeypatch.setattr(updater, "current_layout", lambda: layout)
    prepared: list[tuple] = []
    launched: list[Path] = []

    def fake_prepare(release, data_dir, install_layout, *, progress=None):
        progress(50)
        prepared.append((release.version, data_dir, install_layout))
        return tmp_path / "plan.json"

    monkeypatch.setattr(updater, "prepare_update", fake_prepare)
    monkeypatch.setattr(updater, "launch_update_helper", launched.append)

    window.check_for_updates()
    card = window._modal_overlay._card
    assert isinstance(card, UpdateDialog)
    assert "60 MB" in card.body_label.text()
    card.confirm_button.click()
    assert prepared == [("v99.0.0", window.controller.data_dir, layout)]
    assert launched == [tmp_path / "plan.json"]
    assert card.status_label.text() == t("gui.updateRestarting")
    assert not card.confirm_button.isEnabled()


def test_new_version_announces_result_of_previous_update(
    qt_application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = updater.update_workspace(tmp_path)
    workspace.mkdir()
    (workspace / "result.json").write_text('{"version": "v9.9.9", "ok": true}', encoding="utf-8")
    window = _window(tmp_path, monkeypatch)
    assert not workspace.exists()
    window._announce_update_result()
    assert window.main_view.toast.text() == t("gui.updatedTo", version="v9.9.9")
