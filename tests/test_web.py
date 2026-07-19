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


def test_color_scheme_follows_system_dark_mode_and_falls_back_to_light(tmp_path):
    app = create_app(data_dir=tmp_path, chat_password="shared-secret")

    with TestClient(app) as browser:
        page = browser.get("/").text
        css = browser.get("/static/app.css").text.replace("\r\n", "\n")

    assert '<meta name="theme-color" content="#f6a84b">' in page
    assert 'media="(prefers-color-scheme: dark)" content="#1f1b18"' in page
    assert ":root {\n  color-scheme: light;" in css
    assert "@media (prefers-color-scheme: dark)" in css
    dark_css = css.split("@media (prefers-color-scheme: dark)", 1)[1]
    assert "color-scheme: dark;" in dark_css
    assert "body {" in dark_css
    assert ".login-card" in dark_css
    assert ".messages" in dark_css
    assert ".bubble" in dark_css
    assert ".composer-bubble" in dark_css


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
        script = browser.get("/static/app.js").text.replace("\r\n", "\n")
        css = browser.get("/static/app.css").text.replace("\r\n", "\n")
        zh = browser.get("/static/locales/zh-CN.json")
        en = browser.get("/static/locales/en.json")

    assert zh.status_code == 200 and en.status_code == 200
    assert zh.json()["composer"]["placeholder"]
    assert zh.json()["composer"]["placeholderMobile"] == "输入消息…"
    assert zh.json()["composer"]["expand"]
    assert zh.json()["composer"]["collapse"]
    assert zh.json()["upload"]["tooMany"]
    assert zh.json()["upload"]["readFailed"]
    assert zh.json()["upload"]["pastedImage"] == "剪贴板图片"
    assert zh.json()["upload"]["pastedFile"] == "剪贴板附件"
    assert zh.json()["upload"]["retry"]
    assert zh.json()["upload"]["cancel"] == "取消上传"
    assert zh.json()["attachment"]["download"]
    assert zh.json()["attachment"]["viewImage"] == "查看 {name}"
    assert zh.json()["attachment"]["closePreview"] == "关闭媒体查看"
    assert zh.json()["attachment"]["viewMedia"] == "查看 {name}"
    assert zh.json()["attachment"]["previousMedia"] == "上一个媒体"
    assert zh.json()["attachment"]["nextMedia"] == "下一个媒体"
    assert zh.json()["attachment"]["imagePosition"] == "{current} / {total}"
    assert zh.json()["attachment"]["openWithSystem"] == "使用系统打开"
    assert en.json()["composer"]["placeholder"]
    assert en.json()["composer"]["placeholderMobile"] == "Message…"
    assert en.json()["composer"]["expand"]
    assert en.json()["composer"]["collapse"]
    assert en.json()["upload"]["tooMany"]
    assert en.json()["upload"]["readFailed"]
    assert en.json()["upload"]["pastedImage"] == "Pasted image"
    assert en.json()["upload"]["pastedFile"] == "Pasted attachment"
    assert en.json()["upload"]["retry"]
    assert en.json()["upload"]["cancel"] == "Cancel upload"
    assert en.json()["attachment"]["download"]
    assert en.json()["attachment"]["viewImage"] == "View {name}"
    assert en.json()["attachment"]["closePreview"] == "Close media viewer"
    assert en.json()["attachment"]["viewMedia"] == "View {name}"
    assert en.json()["attachment"]["previousMedia"] == "Previous media"
    assert en.json()["attachment"]["nextMedia"] == "Next media"
    assert en.json()["attachment"]["imagePosition"] == "{current} / {total}"
    assert en.json()["attachment"]["openWithSystem"] == "Open with system viewer"
    assert 'data-i18n="' in page
    assert 'data-i18n-placeholder="composer.placeholder"' in page
    assert 'id="drop-zone"' in page
    assert 'id="file-preview"' in page
    assert 'id="attachment-status"' in page
    assert 'id="upload-status"' in page
    assert 'id="upload-progress"' in page
    assert 'id="upload-progress-bar"' in page
    assert 'id="retry-upload"' in page
    assert 'id="cancel-upload"' in page
    assert 'id="media-viewer"' in page
    assert 'id="media-viewer-stage"' in page
    assert 'id="media-viewer-close"' in page
    assert 'id="media-viewer-previous"' in page
    assert 'id="media-viewer-next"' in page
    assert 'id="media-viewer-position"' in page
    assert 'id="media-viewer-system-open"' in page
    assert '<div class="logo" aria-hidden="true">🐱</div>' in page
    assert 'rel="icon"' in page
    assert "%F0%9F%90%B1" in page
    assert "x='50' y='44'" in page
    assert "text-anchor='middle'" in page
    assert "dominant-baseline='central'" in page
    assert ".logo {" in css
    assert "transform: rotate" not in css
    assert 'data-i18n-aria-label="attachment.closePreview"' in page
    assert 'data-i18n-title="upload.cancel"' in page
    assert 'data-i18n-aria-label="upload.cancel"' in page
    assert page.index('id="file-preview"') < page.index('id="attachment-status"') < page.index('id="message-input"')
    assert 'id="remove-file"' not in page
    assert 'id="file-input" type="file" multiple hidden' in page
    assert 'id="expand-composer"' in page
    assert 'data-i18n-title="composer.expand"' in page
    assert 'id="composer-note"' not in page
    assert "服务器单文件上限" not in page
    assert "function resolveLocale(savedLocale, browserLanguages)" in script
    assert "navigator.languages" in script
    assert 'normalized === "zh" || normalized.startsWith("zh-")' in script
    assert 'normalized === "en" || normalized.startsWith("en-")' in script
    assert 'return "en";' in script
    assert "syncComposerPlaceholder" in script
    assert 'matchMedia("(max-width: 620px)").matches' in script
    assert '"composer.placeholderMobile"' in script
    assert 'addEventListener("drop"' in script
    assert 'document.addEventListener("paste"' in script
    assert "clipboardData" in script
    assert "createClipboardFile" in script
    assert "getClipboardFiles" in script
    assert "clipboardFileExtension" in script
    assert "clipboardData?.files" in script
    assert 'type.toLowerCase().startsWith("image/")' in script
    assert "event.preventDefault()" in script
    assert 'appendPendingFiles(files)' in script
    assert "if (chatView.hidden || sending) return;" in script
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
    assert "currentMaxUploadBytes" in script
    assert "validateReadableFiles" in script
    assert "showAttachmentStatus" in script
    assert "clearAttachmentStatus" in script
    assert 'retryUploadButton.addEventListener("click"' in script
    assert 'cancelUploadButton.addEventListener("click"' in script
    assert "let activeUploadRequest = null;" in script
    assert "UPLOAD_STATUS_DELAY = 250" in script
    assert "UPLOAD_STATUS_FADE_DURATION = 150" in script
    assert "scheduleUploadPresentation" in script
    assert "fadeUploadPresentation" in script
    assert "uploadStatusDelayTimer = setTimeout" in script
    assert "activeUploadRequest.abort();" in script
    assert 'request.addEventListener("abort"' in script
    assert "error.cancelled = true;" in script
    assert ".cancel-upload" in css
    assert ".attachment-status.is-leaving" in css
    assert "transition: opacity 150ms ease" in css
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
    assert 'const attachment = document.createElement("div");' in script
    assert 'downloadLink.className = "attachment-download";' in script
    assert 'downloadLink.href = `/api/files/${encodeURIComponent(item.id)}`;' in script
    assert 't("attachment.download", { name: item.original_name })' in script
    assert "attachment.href =" not in script
    assert ".attachment-download" in css
    assert "createDownloadIcon" in script
    assert "function createMediaPreview(item)" in script
    assert "function applyMediaAspectRatio(media, width, height)" in script
    assert 'media.addEventListener("load"' in script
    assert 'media.addEventListener("loadedmetadata"' in script
    assert 'media.style.setProperty("--media-aspect-ratio"' in script
    assert "function createViewerMedia(trigger)" in script
    assert 'mediaViewerSystemOpen.hidden = !["image", "video"].includes(trigger.dataset.mediaKind);' in script
    assert "mediaViewerSystemOpen.href = trigger.dataset.previewUrl;" in script
    assert "function openMediaViewer(trigger)" in script
    assert "function closeMediaViewer()" in script
    assert "function showMediaViewerItem(index, revealPosition = false)" in script
    assert "function moveMediaViewer(step)" in script
    assert "function finishMediaViewerSwipe(event)" in script
    assert "function shouldStartMediaViewerSwipe(target, clientY)" in script
    assert "function completeMediaViewerSwipe(deltaX, deltaY)" in script
    assert "function startMediaViewerTouch(event)" in script
    assert "function finishMediaViewerTouch(event)" in script
    assert '`${previewUrl}#t=0.001`' in script
    assert 'viewerMedia.addEventListener("loadedmetadata"' in script
    assert "applyMediaAspectRatio(viewerMedia, viewerMedia.videoWidth, viewerMedia.videoHeight);" in script
    assert 'mediaViewer.addEventListener("touchstart"' in script
    assert 'mediaViewer.addEventListener("touchend"' in script
    assert "{ passive: true, capture: true }" in script
    assert "MEDIA_VIEWER_POSITION_HIDE_DELAY = 1400" in script
    assert "function revealMediaViewerPosition()" in script
    assert "function hideMediaViewerPosition()" in script
    assert 'mediaViewerPosition.classList.add("is-visible")' in script
    assert 'mediaViewerPosition.classList.remove("is-visible")' in script
    assert "mediaViewerPositionHideTimer = setTimeout" in script
    assert 'previewButton.dataset.previewUrl' in script
    assert 'openButton.className = "attachment-media-open"' in script
    assert 'openButton.dataset.mediaKind' in script
    assert 'viewerMedia.controls = true;' in script
    assert 'mediaViewerStage.replaceChildren(viewerMedia);' in script
    assert 'mediaViewerPrevious.addEventListener("click"' in script
    assert 'mediaViewerNext.addEventListener("click"' in script
    assert 'event.key === "ArrowLeft"' in script
    assert 'event.key === "ArrowRight"' in script
    assert 'mediaViewer.addEventListener("pointerdown"' in script
    assert 'mediaViewer.addEventListener("pointerup"' in script
    assert "Math.abs(deltaX) < 48" in script
    assert 'previewButton.className = "attachment-image-button";' in script
    assert 't("attachment.viewImage", { name: item.original_name })' in script
    assert 'previewButton.addEventListener("click"' in script
    assert "mediaViewer.showModal();" in script
    assert 'mediaViewerClose.addEventListener("click", closeMediaViewer);' in script
    assert 'mediaViewer.addEventListener("cancel"' in script
    assert 'event.target === mediaViewer' in script
    assert 'document.createElement("img")' in script
    assert 'document.createElement("video")' in script
    assert 'document.createElement("audio")' in script
    assert 'const previewUrl = `/api/files/${encodeURIComponent(item.id)}/preview`;' in script
    assert "media.controls = true;" in script
    assert 'media.preload = "metadata";' in script
    assert 'attachment.classList.add("has-preview")' in script
    assert 'media.addEventListener("error"' in script
    assert ".attachment-media" in css
    assert "aspect-ratio: var(--media-aspect-ratio, auto);" in css
    assert "aspect-ratio: 16 / 10" not in css
    assert "max-height: min(65vh, 640px);" in css
    assert ".attachment-image-button" in css
    assert ".attachment-media-shell" in css
    assert ".attachment-media-open" in css
    assert ".media-viewer" in css
    assert ".media-viewer::backdrop" in css
    assert ".media-viewer-close" in css
    assert ".media-viewer-nav" in css
    assert ".media-viewer-position" in css
    assert ".media-viewer-system-open" in css
    assert ".media-viewer-media" in css
    assert "aspect-ratio: var(--media-aspect-ratio, 16 / 9);" in css
    assert "background: #000;" in css
    assert "--media-viewer-vertical-gap: max(54px, env(safe-area-inset-top), env(safe-area-inset-bottom));" in css
    assert "padding: var(--media-viewer-vertical-gap)" in css
    assert "max-height: calc(100dvh - var(--media-viewer-vertical-gap) - var(--media-viewer-vertical-gap));" in css
    assert ".media-viewer-position.is-visible" in css
    assert "transition: opacity 220ms ease, transform 220ms ease;" in css
    assert "touch-action: pan-y;" in css
    assert "max-width: calc(100vw - 36px);" in css
    assert "width: auto;" in css
    assert "height: auto;" in css
    assert ".attachment.has-preview" in css
    assert 'attachment.classList.add("has-time");' in script
    assert ".attachment.has-time { min-height: 64px; }" in css
    assert ".attachment.has-time .message-time" in css
    assert "position: absolute; right: 9px; bottom: 6px;" in css
    assert ".attachment.has-preview.has-time .message-time { right: 9px; bottom: 7px; }" in css
    assert ".attachment.has-time { min-height: 78px; }" in css
    assert 'attachmentList.className = "attachment-list";' in script
    assert "attachment-columns-" not in script
    assert "grid-template-columns: minmax(0, 1fr);" in css
    assert "width: min(420px, calc(100vw - 52px));" in css
    assert ".file-preview { grid-area: file; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));" in css
    assert ".file-preview-card" in css
    assert ".attachment-status { grid-area: status;" in css
    assert ".attachment-progress-bar" in css
    assert ".attachment-status.error" in css
    assert ".retry-upload" in css
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
    assert "const scope = root?.querySelectorAll ? root : messages;" in script
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
    assert 'id="new-messages-button"' in page
    assert 'id="new-messages-label"' in page
    assert zh.json()["chat"]["newMessages"] == "{count} 条新消息"
    assert zh.json()["chat"]["jumpToLatest"] == "跳到最新消息"
    assert en.json()["chat"]["newMessages"] == "{count} new messages"
    assert en.json()["chat"]["jumpToLatest"] == "Jump to latest message"
    assert "NEW_MESSAGE_AUTOSCROLL_THRESHOLD" in script
    assert "HISTORY_PAGE_SIZE = 200" in script
    assert "HISTORY_LOAD_THRESHOLD = 240" in script
    assert "let oldestLoadedMessageId = null;" in script
    assert "let newestLoadedMessageId = null;" in script
    assert "let hasMoreHistory = true;" in script
    assert "function loadOlderMessages()" in script
    assert "function captureHistoryAnchor()" in script
    assert "function restoreHistoryAnchor(anchor)" in script
    assert "function appendRenderedMessage(message, previousMessage)" in script
    assert "appendRenderedMessage(message, previousMessage);" in script
    assert '`?limit=${HISTORY_PAGE_SIZE}&before=${oldestLoadedMessageId}`' in script
    assert '`?limit=${HISTORY_PAGE_SIZE}&after=${cursor}`' in script
    assert "messages.scrollTop <= HISTORY_LOAD_THRESHOLD" in script
    assert "function isNearLatest()" in script
    assert "function appendIncomingMessage(message)" in script
    assert "let unseenMessageCount = 0;" in script
    assert 'appendIncomingMessage(payload.message);' in script
    assert 'newMessagesButton.addEventListener("click", scrollToLatest);' in script
    assert ".new-messages-button" in css
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
    assert 'if (matchMedia("(min-width: 621px)").matches) return;' in script
    assert 'classList.add("scrollbar-active")' in script
    assert 'classList.remove("scrollbar-active")' in script
    assert 'messagesScrollbarThumb.addEventListener("pointerdown"' in script
    assert 'messagesScrollbar.addEventListener("pointerdown"' in script
    assert 'window.addEventListener("pointermove"' in script
    assert 'window.addEventListener("pointerup"' in script
    assert 'window.addEventListener("pointercancel"' in script
    assert "setPointerCapture" in script
    assert "releasePointerCapture" in script
    assert ".messages-scrollbar-thumb::before" in css
    assert "pointer-events: auto" in css
    assert "cursor: grab" in css
    assert "cursor: grabbing" in css
    assert "touch-action: none" in css
    assert ".messages-scrollbar { opacity: 1; pointer-events: auto; }" in desktop_css
    assert ".messages-scrollbar-thumb::before { width: 3px;" in desktop_css
    assert ".messages.scrollbar-active + .messages-scrollbar .messages-scrollbar-thumb::before" in desktop_css
    assert ".messages-scrollbar:hover .messages-scrollbar-thumb::before" in desktop_css
    assert ".messages-scrollbar.dragging .messages-scrollbar-thumb::before" in desktop_css
    assert "width: 8px;" in desktop_css
    assert "transition: width 180ms ease, right 180ms ease, background 180ms ease;" in desktop_css
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
    assert "chatView.hidden = false;\n  currentIdentityId = identity.identity_id;\n  currentMaxUploadBytes = Number(identity.max_upload_bytes) || null;\n  syncChatHeaderHeight();\n  resizeTextarea();" in script
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
