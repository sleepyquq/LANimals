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
    assert "textarea:placeholder-shown { white-space: nowrap; }" in css
    assert "width: min(420px, calc(100% - max(16px, env(safe-area-inset-left)) - max(16px, env(safe-area-inset-right))));" in css


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
        css = browser.get("/static/app.css").text.replace("\r\n", "\n")
        zh = browser.get("/static/locales/zh-CN.json")
        en = browser.get("/static/locales/en.json")

    assert zh.status_code == 200 and en.status_code == 200
    assert zh.json()["composer"]["placeholder"]
    assert zh.json()["composer"]["placeholderMobile"] == "输入消息…"
    assert zh.json()["composer"]["expand"]
    assert zh.json()["composer"]["collapse"]
    assert zh.json()["upload"]["tooMany"]
    assert en.json()["composer"]["placeholder"]
    assert en.json()["composer"]["placeholderMobile"] == "Message…"
    assert en.json()["composer"]["expand"]
    assert en.json()["composer"]["collapse"]
    assert en.json()["upload"]["tooMany"]
    assert 'data-i18n="' in page
    assert 'data-i18n-placeholder="composer.placeholder"' in page
    assert 'id="drop-zone"' in page
    assert 'id="file-preview"' in page
    assert 'id="remove-file"' not in page
    assert 'id="file-input" type="file" multiple hidden' in page
    assert 'id="expand-composer"' in page
    assert 'data-i18n-title="composer.expand"' in page
    assert 'id="composer-note"' not in page
    assert "服务器单文件上限" not in page
    assert "navigator.language" in script
    assert "syncComposerPlaceholder" in script
    assert 'matchMedia("(max-width: 620px)").matches' in script
    assert '"composer.placeholderMobile"' in script
    assert 'addEventListener("drop"' in script
    assert "resizeTextarea" in script
    assert "setComposerFullscreen" in script
    assert 'aria-expanded' in script
    assert 'event.key === "Escape"' in script
    assert 'form.append("body"' in script
    assert "interactive-widget=resizes-content" in page
    assert "visualViewport" in script
    assert "--keyboard-offset" in script
    assert "ResizeObserver" in script
    assert "--composer-space" in script
    assert "let pendingFiles = [];" in script
    assert "appendPendingFiles" in script
    assert "MAX_ATTACHMENTS_PER_MESSAGE = 12" in script
    assert "if (sending) return" in script
    assert "loadHistory();" in script
    assert "fetchLocale" in script
    assert 'cache: "no-store"' in script
    assert 'data-i18n-aria-label="composer.send"' in page
    assert 'data-i18n="composer.send"' not in page
    assert 'class="send-icon"' in page
    assert 'class="add-icon"' in page
    assert 'id="send-button" class="send-button" type="submit" disabled' in page
    assert "updateSendButton" in script
    assert "messageInput.value.trim()" in script
    assert "!pendingFiles.length" in script
    assert "position: absolute" in css
    assert ".chat-header::after" in css
    assert "backdrop-filter" in css
    assert "border-bottom: 0" in css
    assert "bottom: calc(var(--composer-edge-gap) + var(--keyboard-offset))" in css
    assert 'id="connection" class="status offline" role="status"' in page
    assert 'data-i18n="chat.connecting"' not in page
    assert "date-separator" in script
    assert "message-time" in script
    assert "previousSender" in script
    assert ".message.grouped" in css
    assert ".message.grouped { margin-top: 0; }" in css
    assert ".message:has(+ .message.grouped) { margin-bottom: 5px; }" in css
    assert 'class="brand-row"' in page
    assert ".brand-row { display: flex; align-items: center; gap: 10px; }" in css
    assert 'copy.className = "attachment-copy"' in script
    assert ".attachment-copy { min-width: 0; flex: 1; }" in css
    assert "max-width: min(680px, calc(100vw - 52px))" in css
    assert ".file-preview { grid-area: file; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));" in css
    assert ".file-preview-card" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert ".attachment-list" in css
    assert 'form.append("files", file, file.name)' in script
    assert 'removeButton.className = "remove-file"' in script
    assert "uniqueAttachmentNames" in script
    assert "font-size: 9px" in css
    assert "opacity: .68" in css
    assert "transform: translate(2px, 1px)" in css
    assert "updateMessageTimeLayouts" in script
    assert 'classList.add("multiline")' in script
    assert ".bubble.multiline" in css
    assert "padding: 10px 11px 8px 13px" in css
    assert "row-gap: 0" in css
    assert "overflow-y: hidden" in css
    assert ".messages {\n  overflow-y: auto;" in css
    assert "max-height: 180px;\n  resize: none;\n  overflow-y: hidden;" in css
    assert ".composer-bubble.expanded textarea { overflow-y: auto; }" in css
    assert "scrollbar-width: thin" in css
    assert "::-webkit-scrollbar-button:single-button" in css
    assert ".messages::-webkit-scrollbar" in css
    assert ".messages::-webkit-scrollbar-thumb" in css
    assert ".messages::-webkit-scrollbar-button:vertical:decrement" in css
    assert ".messages::-webkit-scrollbar-button:vertical:increment" in css
    assert 'id="messages-scrollbar"' in page
    assert 'id="messages-scrollbar-thumb"' in page
    assert ".messages.scrollbar-active + .messages-scrollbar" in css
    assert ".messages.scrollbar-active" in css
    assert "transition: opacity 280ms ease" in css
    assert "scrollbar-width: none" in css
    assert "syncMessageScrollbar" in script
    assert "@media (min-width: 621px)" in css
    desktop_css = css.split("@media (min-width: 621px)", 1)[1].split("@media", 1)[0]
    assert ".shell { padding: 0; background: var(--cream); }" in desktop_css
    assert "width: 100%;" in desktop_css
    assert "height: 100dvh;" in desktop_css
    assert "border: 0;" in desktop_css
    assert "border-radius: 0;" in desktop_css
    assert "background: transparent;" in desktop_css
    assert "box-shadow: none;" in desktop_css
    assert "padding-right: 22px;" in desktop_css
    assert "padding-left: 22px;" in desktop_css
    assert "max(22px, calc((100vw - 896px) / 2))" in desktop_css
    assert ".composer::before" in css
    assert "backdrop-filter: blur(12px) saturate(1.06);" in css
    assert "--composer-height" in css
    assert "--composer-edge-gap" in css
    assert "height: calc(var(--composer-height) + var(--composer-edge-gap) + var(--composer-edge-gap));" in css
    assert "bottom: var(--keyboard-offset);" in css
    assert "mask-image: linear-gradient(to top, #000 0%, #000 calc(100% - var(--composer-edge-gap) - var(--composer-edge-gap)), rgba(0,0,0,.72) calc(100% - var(--composer-edge-gap)), transparent 100%);" in css
    header_fade_css = css.split(".chat-header::after {", 1)[1].split("}", 1)[0]
    assert "top: 0;" in header_fade_css
    assert "bottom: 0;" in header_fade_css
    assert "height: auto;" in header_fade_css
    assert "mask-image: linear-gradient(to bottom, #000 0%, #000 calc(100% - 32px), rgba(0,0,0,.72) calc(100% - 16px), transparent 100%);" in css
    assert 'setProperty("--composer-height"' in script
    assert "grid-template-rows: minmax(0, 1fr);" in css
    assert "padding: calc(var(--chat-header-height) + 22px) 22px" in css
    assert "background: rgba(255,250,241,.38);" in css
    assert "background: rgba(255,250,241,.26);" in css
    assert "background: rgba(255,255,255,.98);" in css
    composer_bubble_css = css.split(".composer-bubble {", 1)[1].split("}", 1)[0]
    assert "backdrop-filter" not in composer_bubble_css
    assert 'messages.addEventListener("pointermove"' in script
    assert 'messages.addEventListener("pointerleave"' in script
    assert 'messages.addEventListener("wheel"' in script
    assert 'messages.addEventListener("scroll"' in script
    assert 'classList.add("scrollbar-active")' in script
    assert 'classList.remove("scrollbar-active")' in script
    assert "--chat-header-height" in css
    assert ".composer.fullscreen" in css
    assert ".composer-bubble {\n  position: relative;" in css
    assert ".composer-bubble.can-fullscreen .expand-button" in css
    assert ".composer-bubble.expanded .expand-button" not in css
    assert 'classList.toggle("can-fullscreen", reachedMaxHeight)' in script
    assert "messageInput.scrollHeight >= maxHeight - 1" in script
    assert 'class="expand-glyph" d="M13 6h5v5M11 18H6v-5"' in page
    assert 'class="collapse-glyph" d="M14 5v5h5M10 19v-5H5"' in page
    expand_button_css = css.split(".expand-button {", 1)[1].split("}", 1)[0]
    assert "background: transparent;" in expand_button_css
    assert "border-radius" not in expand_button_css
    assert "padding: 14px max(18px, env(safe-area-inset-right)) 0 max(18px, env(safe-area-inset-left));" in css
    fullscreen_composer_css = css.split(".composer.fullscreen {", 1)[1].split("}", 1)[0]
    assert "bottom:" not in fullscreen_composer_css
    fullscreen_bubble_css = css.split(".composer.fullscreen .composer-bubble {", 1)[1].split("}", 1)[0]
    assert "width: min(760px, 100%);" in fullscreen_bubble_css
    assert "margin: 0 auto;" in fullscreen_bubble_css
    assert "border-radius: 30px;" in fullscreen_bubble_css
    assert "border: 0;" not in fullscreen_bubble_css
    assert "box-shadow: none;" not in fullscreen_bubble_css
    assert "chatView.hidden = false;\n  currentIdentityId = identity.identity_id;\n  syncChatHeaderHeight();\n  resizeTextarea();" in script
    assert "let currentIdentityId = null;" in script
    assert "currentIdentityId = identity.identity_id;" in script
    assert "const senderKey = message.sender_id || message.sender_name;" in script
    assert "const isSelf = Boolean(message.sender_id) && message.sender_id === currentIdentityId;" in script
    assert 'if (isSelf) article.classList.add("self");' in script
    assert ".message.self { margin-left: auto; }" in css
    assert ".message.self .message-content { justify-items: end; }" in css
    assert ".message.self .message-meta { text-align: right; }" in css
    assert "border-radius: 17px 5px 17px 17px;" in css
    assert "background: #fff1df;" in css
