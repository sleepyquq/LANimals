"""测试 GUI 国际化多语言加载与对称性。"""

from __future__ import annotations

import json
from pathlib import Path

from lanimals.gui.i18n import init_i18n, t


def test_locale_files_key_symmetry() -> None:
    """验证 zh-CN.json 和 en.json 的所有键集合 100% 对称相同。"""
    locales_dir = Path(__file__).resolve().parent.parent / "lanimals" / "web" / "locales"
    with open(locales_dir / "zh-CN.json", "r", encoding="utf-8") as f:
        zh = json.load(f)
    with open(locales_dir / "en.json", "r", encoding="utf-8") as f:
        en = json.load(f)

    def extract_keys(d: dict, prefix: str = "") -> set[str]:
        keys = set()
        for k, v in d.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.update(extract_keys(v, full_key))
            else:
                keys.add(full_key)
        return keys

    zh_keys = extract_keys(zh)
    en_keys = extract_keys(en)

    missing_in_en = zh_keys - en_keys
    missing_in_zh = en_keys - zh_keys

    assert not missing_in_en, f"en.json 缺少以下键: {missing_in_en}"
    assert not missing_in_zh, f"zh-CN.json 缺少以下键: {missing_in_zh}"


def test_i18n_translation_and_fallback() -> None:
    """测试不同语言下的文本获取及回退。"""
    # 切换为中文
    init_i18n("zh-CN")
    assert t("gui.scanHint") == "手机扫码立即加入局域网群聊"
    assert t("gui.clearConfirmPrompt") == "请输入 DELETE ALL 确认清除："
    assert t("chat.identity", name="橘子小猫") == "你是：橘子小猫"

    # 切换为英文
    init_i18n("en")
    assert t("gui.scanHint") == "Scan QR code to join LAN chat room"
    assert t("gui.clearConfirmPrompt") == "Type DELETE ALL to confirm:"
    assert t("chat.identity", name="Orange Cat") == "You are Orange Cat"

    # 不存在的键回退
    assert t("non.existent.key", default="Default Val") == "Default Val"
