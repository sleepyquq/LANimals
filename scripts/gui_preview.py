"""离屏渲染桌面控制面板的各个状态并保存截图，供 CI 在三平台上生成预览。

用法：
    QT_QPA_PLATFORM=offscreen python scripts/gui_preview.py --out previews --lang zh-CN
    QT_QPA_PLATFORM=offscreen python scripts/gui_preview.py --out previews --lang en --dark

会启动真实的本地服务（端口取自临时配置，默认 8787），结束时自动停止。
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STATES = (
    "first-launch",
    "main",
    "main-local-only",
    "settings",
    "settings-edited",
    "main-stopped",
)


def _force_dark_theme() -> None:
    """离屏平台无法切换系统配色，这里让主题模块读到深色偏好。"""
    from PySide6.QtCore import Qt

    import lanimals.gui.qt_theme as qt_theme

    class _Hints:
        @staticmethod
        def colorScheme():  # noqa: N802 - 模拟 Qt API
            return Qt.ColorScheme.Dark

    class _GuiApplication:
        @staticmethod
        def styleHints():  # noqa: N802 - 模拟 Qt API
            return _Hints()

    qt_theme.QGuiApplication = _GuiApplication


def render(out_dir: Path, lang: str, dark: bool, timeout: float) -> list[Path]:
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    from lanimals.gui.i18n import init_i18n

    if dark:
        _force_dark_theme()
    init_i18n(lang)

    from lanimals.gui import app as app_module
    from lanimals.gui.dialogs import PasswordDialog

    # 预览不需要托盘；各平台 CI 机器上的托盘支持情况不一。
    app_module.SystemTray.start = lambda _tray: None

    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{lang}-{'dark' if dark else 'light'}"
    saved: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="lanimals-preview-") as temporary:
        window = app_module.LANimalsApp(data_dir=Path(temporary) / "data")
        application = QApplication.instance()
        window.show()

        def pump(seconds: float) -> None:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                application.processEvents()
                # 离屏脚本没有进入 exec()，需手动处理 deleteLater，避免旧标题栏残留。
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                time.sleep(0.01)

        def wait_until(predicate, what: str) -> None:
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                pump(0.05)
                if predicate():
                    pump(0.3)
                    return
            raise TimeoutError(f"等待超时：{what}")

        def snap(state: str) -> None:
            path = out_dir / f"{state}-{suffix}.png"
            window.grab().save(str(path))
            saved.append(path)
            print(f"saved {path}", flush=True)

        try:
            wait_until(lambda: window._modal_overlay is not None, "首次启动密码卡片")
            snap("first-launch")

            card = window._modal_overlay.findChild(PasswordDialog)
            card.entry.setText("preview-password")
            card._submit()
            wait_until(lambda: window.controller.is_running and window._modal_overlay is None, "服务启动")
            snap("main")

            window.main_view.lan_switch.click()
            wait_until(
                lambda: window.controller.local_only and window.main_view.lan_switch.isEnabled(),
                "切换为仅本机",
            )
            snap("main-local-only")

            window.show_settings()
            pump(0.6)
            snap("settings")
            window.settings_view.upload_entry.setText("4")
            pump(0.3)
            snap("settings-edited")
            window.settings_view.refresh_settings(force=True)

            window.show_main()
            pump(0.5)
            window._toggle_server()
            wait_until(lambda: not window.controller.is_running, "服务停止")
            snap("main-stopped")
        finally:
            try:
                window.controller.stop()
            except Exception:
                pass
            window._quitting = True
            window.tray.stop()
            window.close()
            window.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return saved


def contact_sheet(paths: list[Path], target: Path) -> None:
    """把透明圆角窗口合成到中性背景上并排成一行，方便一眼浏览。"""
    from PIL import Image

    images = [Image.open(path).convert("RGBA") for path in paths]
    gap = 16
    width = sum(image.width for image in images) + gap * (len(images) + 1)
    height = max(image.height for image in images) + gap * 2
    sheet = Image.new("RGBA", (width, height), "#9aa3ad")
    x = gap
    for image in images:
        sheet.alpha_composite(image, (x, gap))
        x += image.width + gap
    sheet.convert("RGB").save(target)
    print(f"saved {target}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render LANimals control panel previews")
    parser.add_argument("--out", type=Path, default=Path("previews"))
    parser.add_argument("--lang", choices=["zh-CN", "en"], default="zh-CN")
    parser.add_argument("--dark", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    paths = render(args.out, args.lang, args.dark, args.timeout)
    suffix = f"{args.lang}-{'dark' if args.dark else 'light'}"
    contact_sheet(paths, args.out / f"overview-{suffix}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
