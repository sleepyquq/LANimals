from fastapi.testclient import TestClient

from lanimals.main import create_app


def test_responsive_web_client_is_served_without_external_dependencies(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        page = browser.get("/")
        script = browser.get("/static/app.js")
        stylesheet = browser.get("/static/app.css")

    assert page.status_code == 200
    assert "LANimals" in page.text
    assert 'data-i18n="login.incognito"' in page.text
    assert browser.get("/static/locales/zh-CN.json").json()["login"]["incognito"] == "无痕/临时设备"
    assert 'id="message-form"' in page.text
    assert "http://" not in page.text and "https://" not in page.text
    assert script.status_code == 200
    assert "WebSocket" in script.text
    assert "textContent" in script.text
    assert stylesheet.status_code == 200
    assert "@media" in stylesheet.text


def test_mobile_layout_has_safe_areas_touch_targets_and_shrinkable_composer(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        page = browser.get("/").text
        css = browser.get("/static/app.css").text

    assert "viewport-fit=cover" in page
    assert "safe-area-inset-top" in css
    assert "safe-area-inset-bottom" in css
    assert "minmax(0, 1fr)" in css
    assert "min-width: 0" in css
    assert "font-size: 16px" in css
    assert "44px" in css


def test_hidden_views_and_empty_state_cannot_be_overridden_by_component_display_rules(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        css = browser.get("/static/app.css").text

    assert "[hidden] { display: none !important; }" in css


def test_composer_is_floating_combined_drop_zone_and_ui_uses_locale_files(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        page = browser.get("/").text
        script = browser.get("/static/app.js").text
        css = browser.get("/static/app.css").text
        zh = browser.get("/static/locales/zh-CN.json")
        en = browser.get("/static/locales/en.json")

    assert zh.status_code == 200 and en.status_code == 200
    assert zh.json()["composer"]["placeholder"]
    assert en.json()["composer"]["placeholder"]
    assert 'data-i18n="' in page
    assert 'data-i18n-placeholder="composer.placeholder"' in page
    assert 'id="drop-zone"' in page
    assert 'id="file-preview"' in page
    assert 'id="remove-file"' in page
    assert 'id="composer-note"' not in page
    assert "服务器单文件上限" not in page
    assert "navigator.language" in script
    assert 'addEventListener("drop"' in script
    assert "resizeTextarea" in script
    assert 'form.append("body"' in script
    assert "interactive-widget=resizes-content" in page
    assert "visualViewport" in script
    assert "--keyboard-offset" in script
    assert "ResizeObserver" in script
    assert "--composer-space" in script
    assert "pendingFile === file" in script
    assert "if (sending) return" in script
    assert "loadHistory();" in script
    assert "fetchLocale" in script
    assert 'data-i18n-aria-label="composer.send"' in page
    assert 'data-i18n="composer.send"' not in page
    assert 'class="send-icon"' in page
    assert 'id="send-button" class="send-button" type="submit" disabled' in page
    assert "updateSendButton" in script
    assert "messageInput.value.trim()" in script
    assert "!pendingFile" in script
    assert "position: sticky" in css
    assert ".chat-header::after" in css
    assert "backdrop-filter" in css
    assert "border-bottom: 0" in css
    assert "bottom: calc(18px + env(safe-area-inset-bottom) + var(--keyboard-offset))" in css
    assert 'id="connection" class="status offline" role="status"' in page
    assert 'data-i18n="chat.connecting"' not in page
    assert "date-separator" in script
    assert "message-time" in script
    assert "previousSender" in script
    assert ".message.grouped" in css
    assert 'class="brand-row"' in page
    assert ".brand-row { display: flex; align-items: center; gap: 10px; }" in css
    assert 'copy.className = "attachment-copy"' in script
    assert ".attachment-copy { min-width: 0; flex: 1; }" in css
    assert "width: min(520px, calc(100vw - 52px))" in css
    assert "font-size: 9px" in css
    assert "opacity: .68" in css
    assert "transform: translate(2px, 1px)" in css
