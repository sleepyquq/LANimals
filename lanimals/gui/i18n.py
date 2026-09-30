"""LANimals GUI 国际化多语言加载器。

继承 Web 界面一致的多语言 JSON 字典与语言回退规则。
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("lanimals.i18n")

_CURRENT_TRANSLATIONS: dict[str, Any] = {}
_FALLBACK_TRANSLATIONS: dict[str, Any] = {}
_INITIALIZED: bool = False


def _get_locales_dir() -> Path:
    """获取 locales 资源目录路径（兼容开发环境、模块导入与 PyInstaller 打包环境）。"""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates.append(meipass / "lanimals" / "web" / "locales")
        candidates.append(meipass / "web" / "locales")

    curr_dir = Path(__file__).resolve().parent
    candidates.append(curr_dir.parent / "web" / "locales")
    candidates.append(curr_dir.parent.parent / "lanimals" / "web" / "locales")
    candidates.append(curr_dir.parent.parent / "web" / "locales")

    for c in candidates:
        if c.exists() and (c / "zh-CN.json").exists():
            return c
    return candidates[0]


def _detect_system_language() -> str:
    """检测当前操作系统首选语言代码。"""
    try:
        if sys.platform == "win32":
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            # 0x0804 是简体中文，0x0404 是繁体中文
            primary_lang = lang_id & 0x3FF
            if primary_lang == 0x04:  # Chinese
                return "zh-CN"
        languages = _system_ui_languages()
        if languages and languages[0].lower().startswith("zh"):
            return "zh-CN"
    except Exception:
        pass
    return "en"


def _system_ui_languages() -> list[str]:
    """按用户偏好顺序返回系统界面语言。

    macOS 从访达启动时通常没有 LANG 环境变量，因此读取系统设置而不是进程 locale。
    """
    from PySide6.QtCore import QLocale

    return list(QLocale.system().uiLanguages())


def _load_json_file(file_path: Path) -> dict[str, Any]:
    try:
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as error:
        logger.warning("加载语言文件失败 %s: %s", file_path, error)
    return {}


def init_i18n(lang_code: str | None = None) -> None:
    """初始化多语言资源。"""
    global _CURRENT_TRANSLATIONS, _FALLBACK_TRANSLATIONS, _INITIALIZED

    locales_dir = _get_locales_dir()
    _FALLBACK_TRANSLATIONS = _load_json_file(locales_dir / "en.json")

    chosen_lang = lang_code or _detect_system_language()
    if chosen_lang == "zh-CN":
        _CURRENT_TRANSLATIONS = _load_json_file(locales_dir / "zh-CN.json")
    else:
        _CURRENT_TRANSLATIONS = _FALLBACK_TRANSLATIONS

    _INITIALIZED = True


def t(key_path: str, default: str = "", **kwargs: Any) -> str:
    """根据点分路径获取翻译文本，支持 {param} 插值与回退规则。

    示例：
        t("gui.scanHint") -> "手机扫码立即加入局域网群聊"
        t("chat.identity", name="橘子小猫") -> "你是：橘子小猫"
    """
    if not _INITIALIZED:
        init_i18n()

    def get_by_path(d: dict[str, Any], path: str) -> Any:
        keys = path.split(".")
        val = d
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return None
        return val

    # 1. 尝试当前语言
    result = get_by_path(_CURRENT_TRANSLATIONS, key_path)
    # 2. 回退到英文
    if result is None:
        result = get_by_path(_FALLBACK_TRANSLATIONS, key_path)
    # 3. 回退到默认值
    if result is None:
        result = default or key_path

    if isinstance(result, str) and kwargs:
        try:
            return result.format(**kwargs)
        except Exception:
            return result
    return str(result)


def button_text(key_path: str, default: str = "", **kwargs: Any) -> str:
    """供 Qt 按钮使用的翻译文本：转义 &，避免被当作键盘助记符吞掉。"""
    return t(key_path, default, **kwargs).replace("&", "&&")
