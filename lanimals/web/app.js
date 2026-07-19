"use strict";

let translations = {};
let currentLocale = "en";
let socket = null;
let reconnectTimer = null;
let currentIdentityId = null;
let unseenMessageCount = 0;
let oldestLoadedMessageId = null;
let newestLoadedMessageId = null;
let hasMoreHistory = true;
let loadingOlderMessages = false;
let initialHistoryLoaded = false;
let messageScrollbarHideTimer = null;
let messageScrollbarPointerNearEdge = false;
let messageScrollbarDrag = null;
let pendingFiles = [];
let currentMaxUploadBytes = null;
let sending = false;
let activeUploadRequest = null;
let activeUploadId = null;
let uploadStatusDelayTimer = null;
let uploadStatusVisible = false;
let latestUploadProgress = 0;
let dragDepth = 0;
const messageCache = new Map();

const loginView = document.querySelector("#login-view");
const chatView = document.querySelector("#chat-view");
const loginForm = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");
const passwordInput = document.querySelector("#password");
const incognitoInput = document.querySelector("#incognito");
const identityLabel = document.querySelector("#identity");
const connectionLabel = document.querySelector("#connection");
const messages = document.querySelector("#messages");
const messagesScrollbar = document.querySelector("#messages-scrollbar");
const messagesScrollbarThumb = document.querySelector("#messages-scrollbar-thumb");
const newMessagesButton = document.querySelector("#new-messages-button");
const newMessagesLabel = document.querySelector("#new-messages-label");
const emptyState = document.querySelector("#empty-state");
const dropZone = document.querySelector("#drop-zone");
const chatHeader = document.querySelector(".chat-header");
const messageForm = document.querySelector("#message-form");
const messageInput = document.querySelector("#message-input");
const expandComposerButton = document.querySelector("#expand-composer");
const fileInput = document.querySelector("#file-input");
const filePreview = document.querySelector("#file-preview");
const attachmentStatus = document.querySelector("#attachment-status");
const uploadStatus = document.querySelector("#upload-status");
const uploadProgress = document.querySelector("#upload-progress");
const uploadProgressBar = document.querySelector("#upload-progress-bar");
const uploadProgressLabel = document.querySelector("#upload-progress-label");
const cancelUploadButton = document.querySelector("#cancel-upload");
const retryUploadButton = document.querySelector("#retry-upload");
const sendButton = document.querySelector("#send-button");
const mediaViewer = document.querySelector("#media-viewer");
const mediaViewerStage = document.querySelector("#media-viewer-stage");
const mediaViewerClose = document.querySelector("#media-viewer-close");
const mediaViewerPrevious = document.querySelector("#media-viewer-previous");
const mediaViewerNext = document.querySelector("#media-viewer-next");
const mediaViewerPosition = document.querySelector("#media-viewer-position");
const mediaViewerSystemOpen = document.querySelector("#media-viewer-system-open");
let mediaViewerTrigger = null;
let mediaViewerIndex = -1;
let mediaViewerSwipe = null;
let mediaViewerTouch = null;
let mediaViewerLastSwipeAt = 0;
let mediaViewerPositionHideTimer = null;

const MAX_ATTACHMENTS_PER_MESSAGE = 12;
const MESSAGE_SCROLLBAR_EDGE_ZONE = 18;
const MESSAGE_SCROLLBAR_HIDE_DELAY = 700;
const NEW_MESSAGE_AUTOSCROLL_THRESHOLD = 96;
const HISTORY_PAGE_SIZE = 200;
const HISTORY_LOAD_THRESHOLD = 240;
const UPLOAD_STATUS_DELAY = 250;
const UPLOAD_STATUS_FADE_DURATION = 150;
const MEDIA_VIEWER_POSITION_HIDE_DELAY = 1400;
const PREVIEWABLE_IMAGE_TYPES = new Set([
  "image/avif", "image/bmp", "image/gif", "image/jpeg", "image/jpg", "image/png", "image/webp",
]);
const PREVIEWABLE_VIDEO_TYPES = new Set([
  "video/mp4", "video/ogg", "video/quicktime", "video/webm",
]);
const PREVIEWABLE_AUDIO_TYPES = new Set([
  "audio/aac", "audio/flac", "audio/mp4", "audio/mpeg", "audio/ogg", "audio/wav",
  "audio/webm", "audio/x-flac", "audio/x-wav",
]);

function revealMessageScrollbar() {
  clearTimeout(messageScrollbarHideTimer);
  messages.classList.add("scrollbar-active");
}

function scheduleMessageScrollbarHide(delay = MESSAGE_SCROLLBAR_HIDE_DELAY) {
  clearTimeout(messageScrollbarHideTimer);
  if (messageScrollbarPointerNearEdge || messageScrollbarDrag) return;
  messageScrollbarHideTimer = setTimeout(() => {
    messages.classList.remove("scrollbar-active");
  }, delay);
}

function hasDesktopMessageScrollbar() {
  return matchMedia("(min-width: 621px)").matches;
}

function syncMessageScrollbar() {
  if (!hasDesktopMessageScrollbar()) {
    clearTimeout(messageScrollbarHideTimer);
    messageScrollbarPointerNearEdge = false;
    messagesScrollbar.hidden = true;
    messagesScrollbar.classList.remove("dragging");
    messages.classList.remove("scrollbar-active");
    return;
  }

  const viewportHeight = messages.clientHeight;
  const contentHeight = messages.scrollHeight;
  const scrollRange = Math.max(0, contentHeight - viewportHeight);
  messagesScrollbar.hidden = !viewportHeight || scrollRange <= 1;
  if (messagesScrollbar.hidden) {
    messages.classList.remove("scrollbar-active");
    return;
  }

  const trackHeight = messagesScrollbar.clientHeight || viewportHeight;
  const thumbHeight = Math.min(trackHeight, Math.max(28, trackHeight * (viewportHeight / contentHeight)));
  const thumbTravel = Math.max(0, trackHeight - thumbHeight);
  const thumbTop = scrollRange ? (messages.scrollTop / scrollRange) * thumbTravel : 0;
  messagesScrollbarThumb.style.height = `${thumbHeight}px`;
  messagesScrollbarThumb.style.transform = `translateY(${thumbTop}px)`;
}

function scrollMessagesFromScrollbarPointer(clientY, thumbOffset) {
  const trackBounds = messagesScrollbar.getBoundingClientRect();
  const thumbHeight = messagesScrollbarThumb.getBoundingClientRect().height;
  const thumbTravel = Math.max(0, trackBounds.height - thumbHeight);
  const scrollRange = Math.max(0, messages.scrollHeight - messages.clientHeight);
  if (!thumbTravel || !scrollRange) return;

  const thumbTop = Math.max(
    0,
    Math.min(thumbTravel, clientY - trackBounds.top - thumbOffset),
  );
  messages.scrollTop = (thumbTop / thumbTravel) * scrollRange;
  syncMessageScrollbar();
}

function finishMessageScrollbarDrag(event) {
  if (!messageScrollbarDrag || event.pointerId !== messageScrollbarDrag.pointerId) return;
  if (messagesScrollbarThumb.hasPointerCapture(event.pointerId)) {
    messagesScrollbarThumb.releasePointerCapture(event.pointerId);
  }
  messageScrollbarDrag = null;
  messagesScrollbar.classList.remove("dragging");
  const bounds = messages.getBoundingClientRect();
  messageScrollbarPointerNearEdge = (
    event.clientX >= bounds.right - MESSAGE_SCROLLBAR_EDGE_ZONE
    && event.clientX <= bounds.right + 2
  );
  scheduleMessageScrollbarHide();
}

function translation(key) {
  return key.split(".").reduce((value, part) => value?.[part], translations) ?? key;
}

function t(key, variables = {}) {
  return Object.entries(variables).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    translation(key),
  );
}

async function fetchLocale(locale) {
  const response = await fetch(`/static/locales/${locale}.json`, { cache: "no-store" });
  if (!response.ok) throw new Error(`locale:${response.status}`);
  return response.json();
}

function resolveLocale(savedLocale, browserLanguages) {
  if (new Set(["zh-CN", "en"]).has(savedLocale)) return savedLocale;
  for (const language of browserLanguages || []) {
    const normalized = String(language).trim().toLowerCase();
    if (normalized === "zh" || normalized.startsWith("zh-")) return "zh-CN";
    if (normalized === "en" || normalized.startsWith("en-")) return "en";
  }
  return "en";
}

async function loadTranslations() {
  const saved = localStorage.getItem("lanimals-locale");
  const browserLanguages = navigator.languages?.length ? navigator.languages : [navigator.language];
  currentLocale = resolveLocale(saved, browserLanguages);
  try {
    translations = await fetchLocale(currentLocale);
  } catch (error) {
    currentLocale = "en";
    translations = await fetchLocale("en");
  }
  document.documentElement.lang = currentLocale;
  applyTranslations();
}

function applyTranslations() {
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-title]").forEach((element) => {
    element.title = t(element.dataset.i18nTitle);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
  });
  syncComposerPlaceholder();
  updateNewMessagesButton();
}

function syncComposerPlaceholder() {
  const key = window.matchMedia("(max-width: 620px)").matches
    ? "composer.placeholderMobile"
    : "composer.placeholder";
  messageInput.placeholder = t(key);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    const error = new Error(t("errors.requestFailed", { status: response.status }));
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

function setConnection(key, online) {
  const label = t(key);
  connectionLabel.textContent = "";
  connectionLabel.setAttribute("aria-label", label);
  connectionLabel.classList.toggle("offline", !online);
}

function showLogin(errorKey = null) {
  clearTimeout(reconnectTimer);
  currentIdentityId = null;
  currentMaxUploadBytes = null;
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
  chatView.hidden = true;
  loginView.hidden = false;
  setComposerFullscreen(false);
  loginError.textContent = errorKey ? t(errorKey) : "";
  passwordInput.value = "";
  requestAnimationFrame(() => passwordInput.focus());
}

function resetHistoryState() {
  messageCache.clear();
  oldestLoadedMessageId = null;
  newestLoadedMessageId = null;
  hasMoreHistory = true;
  loadingOlderMessages = false;
  initialHistoryLoaded = false;
  unseenMessageCount = 0;
  updateNewMessagesButton();
  emptyState.hidden = false;
  messages.replaceChildren(emptyState);
  messages.scrollTop = 0;
}

async function showChat(identity) {
  resetHistoryState();
  loginView.hidden = true;
  chatView.hidden = false;
  currentIdentityId = identity.identity_id;
  currentMaxUploadBytes = Number(identity.max_upload_bytes) || null;
  syncChatHeaderHeight();
  resizeTextarea();
  loginError.textContent = "";
  const temporarySuffix = identity.temporary ? ` · ${t("chat.temporary")}` : "";
  identityLabel.textContent = `${t("chat.identity", { name: identity.name })}${temporarySuffix}`;
  connectWebSocket();
  await loadHistory();
  syncVisualViewport();
}

function formatBytes(value) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = Number(value);
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${new Intl.NumberFormat(currentLocale, { maximumFractionDigits: unit ? 1 : 0 }).format(size)} ${units[unit]}`;
}

function calendarDayKey(date) {
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

function createMessageTime(message) {
  const time = document.createElement("time");
  const date = new Date(message.created_at);
  time.className = "message-time";
  time.dateTime = message.created_at;
  time.textContent = date.toLocaleTimeString(currentLocale, { hour: "2-digit", minute: "2-digit" });
  return time;
}

function createDownloadIcon() {
  const namespace = "http://www.w3.org/2000/svg";
  const icon = document.createElementNS(namespace, "svg");
  icon.classList.add("attachment-download-icon");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");

  const arrow = document.createElementNS(namespace, "path");
  arrow.setAttribute("d", "M12 3v12m0 0 5-5m-5 5-5-5");
  const tray = document.createElementNS(namespace, "path");
  tray.setAttribute("d", "M5 20h14");
  icon.append(arrow, tray);
  return icon;
}

function applyMediaAspectRatio(media, width, height) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return;
  media.style.setProperty("--media-aspect-ratio", `${width} / ${height}`);
}

function createMediaPreview(item) {
  const contentType = String(item.content_type || "").split(";", 1)[0].trim().toLowerCase();
  let media = null;
  if (PREVIEWABLE_IMAGE_TYPES.has(contentType)) {
    media = document.createElement("img");
    media.alt = item.original_name;
    media.loading = "lazy";
    media.decoding = "async";
    media.className = "attachment-media attachment-image";
    media.addEventListener("load", () => {
      applyMediaAspectRatio(media, media.naturalWidth, media.naturalHeight);
    });
  } else if (PREVIEWABLE_VIDEO_TYPES.has(contentType)) {
    media = document.createElement("video");
    media.controls = true;
    media.playsInline = true;
    media.preload = "metadata";
    media.className = "attachment-media attachment-video";
    media.setAttribute("aria-label", item.original_name);
    media.addEventListener("loadedmetadata", () => {
      applyMediaAspectRatio(media, media.videoWidth, media.videoHeight);
    });
  } else if (PREVIEWABLE_AUDIO_TYPES.has(contentType)) {
    media = document.createElement("audio");
    media.controls = true;
    media.preload = "metadata";
    media.className = "attachment-media attachment-audio";
    media.setAttribute("aria-label", item.original_name);
  }
  if (!media) return null;
  const previewUrl = `/api/files/${encodeURIComponent(item.id)}/preview`;
  media.src = media.matches("video") ? `${previewUrl}#t=0.001` : previewUrl;
  return media;
}

function createMediaOpenIcon() {
  const namespace = "http://www.w3.org/2000/svg";
  const icon = document.createElementNS(namespace, "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(namespace, "path");
  path.setAttribute("d", "M13 6h5v5M11 18H6v-5");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "2");
  path.setAttribute("stroke-linecap", "round");
  icon.append(path);
  return icon;
}

function getMediaViewerItems() {
  return [...messages.querySelectorAll(".attachment-viewer-trigger")];
}

function createViewerMedia(trigger) {
  const kind = trigger.dataset.mediaKind;
  const viewerMedia = document.createElement(kind === "image" ? "img" : kind);
  viewerMedia.className = `media-viewer-media media-viewer-${kind}`;
  if (kind === "image") {
    viewerMedia.alt = trigger.dataset.mediaName;
  } else {
    viewerMedia.controls = true;
    viewerMedia.preload = kind === "video" ? "auto" : "metadata";
    viewerMedia.setAttribute("aria-label", trigger.dataset.mediaName);
    if (kind === "video") {
      viewerMedia.playsInline = true;
      viewerMedia.addEventListener("loadedmetadata", () => {
        applyMediaAspectRatio(viewerMedia, viewerMedia.videoWidth, viewerMedia.videoHeight);
      });
    }
  }
  const previewUrl = trigger.dataset.previewUrl;
  viewerMedia.src = kind === "video" ? `${previewUrl}#t=0.001` : previewUrl;
  return viewerMedia;
}

function hideMediaViewerPosition() {
  clearTimeout(mediaViewerPositionHideTimer);
  mediaViewerPositionHideTimer = null;
  mediaViewerPosition.classList.remove("is-visible");
}

function revealMediaViewerPosition() {
  clearTimeout(mediaViewerPositionHideTimer);
  mediaViewerPosition.classList.add("is-visible");
  mediaViewerPositionHideTimer = setTimeout(
    hideMediaViewerPosition,
    MEDIA_VIEWER_POSITION_HIDE_DELAY,
  );
}

function showMediaViewerItem(index, revealPosition = false) {
  const items = getMediaViewerItems();
  if (!items.length) return;
  const nextIndex = Math.max(0, Math.min(index, items.length - 1));
  const trigger = items[nextIndex];
  const viewerMedia = createViewerMedia(trigger);
  mediaViewerIndex = nextIndex;
  mediaViewerTrigger = trigger;
  mediaViewerStage.replaceChildren(viewerMedia);
  mediaViewerPrevious.disabled = nextIndex === 0;
  mediaViewerNext.disabled = nextIndex === items.length - 1;
  // 在独立原件页交给 Safari 原生查看和分享，避免视频播放后长按手势被网页查看器干扰。
  mediaViewerSystemOpen.hidden = !["image", "video"].includes(trigger.dataset.mediaKind);
  mediaViewerSystemOpen.href = trigger.dataset.previewUrl;
  mediaViewerPosition.textContent = t("attachment.imagePosition", {
    current: nextIndex + 1,
    total: items.length,
  });
  if (revealPosition) revealMediaViewerPosition();
  else hideMediaViewerPosition();
}

function moveMediaViewer(step) {
  if (!mediaViewer.open) return;
  const items = getMediaViewerItems();
  const nextIndex = Math.max(0, Math.min(mediaViewerIndex + step, items.length - 1));
  if (nextIndex === mediaViewerIndex) return;
  showMediaViewerItem(nextIndex, true);
}

function openMediaViewer(trigger) {
  const items = getMediaViewerItems();
  const index = items.indexOf(trigger);
  if (index < 0) return;
  showMediaViewerItem(index);
  document.documentElement.classList.add("media-viewer-open");
  mediaViewer.showModal();
}

function closeMediaViewer() {
  if (mediaViewer.open) mediaViewer.close();
}

function createImagePreviewButton(item, media) {
  const previewButton = document.createElement("button");
  previewButton.type = "button";
  previewButton.className = "attachment-image-button";
  previewButton.classList.add("attachment-viewer-trigger");
  previewButton.dataset.previewUrl = `/api/files/${encodeURIComponent(item.id)}/preview`;
  previewButton.dataset.mediaName = item.original_name;
  previewButton.dataset.mediaKind = "image";
  previewButton.setAttribute("aria-label", t("attachment.viewImage", { name: item.original_name }));
  previewButton.append(media);
  previewButton.addEventListener("click", () => openMediaViewer(previewButton));
  return previewButton;
}

function createMediaPreviewShell(item, media) {
  const shell = document.createElement("div");
  shell.className = `attachment-media-shell${media.matches("audio") ? " is-audio" : ""}`;
  const openButton = document.createElement("button");
  openButton.type = "button";
  openButton.className = "attachment-media-open";
  openButton.classList.add("attachment-viewer-trigger");
  openButton.dataset.previewUrl = `/api/files/${encodeURIComponent(item.id)}/preview`;
  openButton.dataset.mediaName = item.original_name;
  openButton.dataset.mediaKind = media.matches("video") ? "video" : "audio";
  const label = t("attachment.viewMedia", { name: item.original_name });
  openButton.setAttribute("aria-label", label);
  openButton.title = label;
  openButton.append(createMediaOpenIcon());
  openButton.addEventListener("click", () => openMediaViewer(openButton));
  shell.append(media, openButton);
  return shell;
}

function shouldStartMediaViewerSwipe(target, clientY) {
  const element = target?.closest ? target : target?.parentElement;
  if (!element || element.closest("button, audio")) return false;
  const video = element.closest("video");
  if (!video) return true;
  const bounds = video.getBoundingClientRect();
  return clientY < bounds.bottom - Math.min(64, bounds.height * 0.25);
}

function completeMediaViewerSwipe(deltaX, deltaY) {
  if (Math.abs(deltaX) < 48 || Math.abs(deltaX) <= Math.abs(deltaY)) return;
  const now = Date.now();
  if (now - mediaViewerLastSwipeAt < 250) return;
  mediaViewerLastSwipeAt = now;
  moveMediaViewer(deltaX < 0 ? 1 : -1);
}

function finishMediaViewerSwipe(event) {
  if (!mediaViewerSwipe || event.pointerId !== mediaViewerSwipe.pointerId) return;
  const deltaX = event.clientX - mediaViewerSwipe.startX;
  const deltaY = event.clientY - mediaViewerSwipe.startY;
  mediaViewerSwipe = null;
  completeMediaViewerSwipe(deltaX, deltaY);
}

function startMediaViewerTouch(event) {
  if (event.touches.length !== 1) return;
  const touch = event.touches[0];
  if (!shouldStartMediaViewerSwipe(event.target, touch.clientY)) return;
  mediaViewerTouch = {
    identifier: touch.identifier,
    startX: touch.clientX,
    startY: touch.clientY,
  };
}

function finishMediaViewerTouch(event) {
  if (!mediaViewerTouch) return;
  const touch = Array.from(event.changedTouches).find(
    (candidate) => candidate.identifier === mediaViewerTouch.identifier,
  );
  if (!touch) return;
  const deltaX = touch.clientX - mediaViewerTouch.startX;
  const deltaY = touch.clientY - mediaViewerTouch.startY;
  mediaViewerTouch = null;
  completeMediaViewerSwipe(deltaX, deltaY);
}

function updateMessageTimeLayouts(root = messages) {
  const scope = root?.querySelectorAll ? root : messages;
  const bubbles = [...scope.querySelectorAll(".bubble")];
  for (const bubble of bubbles) bubble.classList.remove("multiline");
  for (const bubble of bubbles) {
    const body = bubble.querySelector(".message-body");
    if (!body) continue;
    const lineHeight = Number.parseFloat(getComputedStyle(body).lineHeight);
    if (body.getBoundingClientRect().height > lineHeight * 1.5) {
      bubble.classList.add("multiline");
    }
  }
}

function createDateSeparator(message) {
  const date = new Date(message.created_at);
  const separator = document.createElement("div");
  separator.className = "date-separator";
  const dateLabel = document.createElement("time");
  dateLabel.dateTime = calendarDayKey(date);
  dateLabel.textContent = date.toLocaleDateString(currentLocale, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  separator.append(dateLabel);
  return separator;
}

function createMessageArticle(message, sameSender) {
    const isSelf = Boolean(message.sender_id) && message.sender_id === currentIdentityId;
    const article = document.createElement("article");
    article.className = sameSender ? "message grouped" : "message";
    if (isSelf) article.classList.add("self");
    article.dataset.messageId = String(message.id);

    if (!sameSender) {
      const meta = document.createElement("div");
      meta.className = "message-meta";
      const sender = document.createElement("strong");
      sender.textContent = message.sender_name;
      meta.append(sender);
      article.append(meta);
    }

    const content = document.createElement("div");
    content.className = "message-content";
    if (message.body) {
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      const body = document.createElement("span");
      body.className = "message-body";
      body.textContent = message.body;
      bubble.append(body, createMessageTime(message));
      content.append(bubble);
    }

    const attachments = Array.isArray(message.attachments)
      ? message.attachments
      : (message.attachment ? [message.attachment] : []);
    if (attachments.length) {
      const attachmentList = document.createElement("div");
      attachmentList.className = "attachment-list";
      attachments.forEach((item, index) => {
        const attachment = document.createElement("div");
        attachment.className = "attachment";
        attachment.innerHTML = '<span class="attachment-icon" aria-hidden="true">📄</span>';
        const media = createMediaPreview(item);
        if (media) {
          attachment.classList.add("has-preview");
          const previewNode = media.matches("img")
            ? createImagePreviewButton(item, media)
            : createMediaPreviewShell(item, media);
          media.addEventListener("error", () => {
            previewNode.remove();
            attachment.classList.remove("has-preview");
          });
          attachment.prepend(previewNode);
        }
        const copy = document.createElement("span");
        copy.className = "attachment-copy";
        const name = document.createElement("strong");
        name.className = "attachment-name";
        name.textContent = item.original_name;
        const size = document.createElement("small");
        size.className = "attachment-size";
        size.textContent = formatBytes(item.size);
        copy.append(name, size);
        attachment.append(copy);
        if (!message.body && index === attachments.length - 1) {
          attachment.classList.add("has-time");
          attachment.append(createMessageTime(message));
        }
        const downloadLink = document.createElement("a");
        downloadLink.className = "attachment-download";
        downloadLink.href = `/api/files/${encodeURIComponent(item.id)}`;
        downloadLink.download = item.original_name;
        const downloadLabel = t("attachment.download", { name: item.original_name });
        downloadLink.setAttribute("aria-label", downloadLabel);
        downloadLink.title = downloadLabel;
        downloadLink.append(createDownloadIcon());
        attachment.append(downloadLink);
        attachmentList.append(attachment);
      });
      content.append(attachmentList);
    }

    article.append(content);
    return article;
}

function appendRenderedMessage(message, previousMessage) {
  if (emptyState.parentNode === messages) emptyState.remove();
  emptyState.hidden = true;
  const day = calendarDayKey(new Date(message.created_at));
  const previousDay = previousMessage
    ? calendarDayKey(new Date(previousMessage.created_at))
    : null;
  if (day !== previousDay) messages.append(createDateSeparator(message));
  const senderKey = message.sender_id || message.sender_name;
  const previousSenderKey = previousMessage
    ? (previousMessage.sender_id || previousMessage.sender_name)
    : null;
  const sameSender = day === previousDay && senderKey === previousSenderKey;
  const article = createMessageArticle(message, sameSender);
  messages.append(article);
  updateMessageTimeLayouts(article);
  requestAnimationFrame(syncMessageScrollbar);
}

function renderMessages() {
  const ordered = [...messageCache.values()].sort((left, right) => left.id - right.id);
  messages.replaceChildren();
  if (!ordered.length) {
    emptyState.hidden = false;
    messages.append(emptyState);
    requestAnimationFrame(syncMessageScrollbar);
    return;
  }

  let previousMessage = null;
  for (const message of ordered) {
    const day = calendarDayKey(new Date(message.created_at));
    const previousDay = previousMessage
      ? calendarDayKey(new Date(previousMessage.created_at))
      : null;
    if (day !== previousDay) messages.append(createDateSeparator(message));
    const senderKey = message.sender_id || message.sender_name;
    const previousSenderKey = previousMessage
      ? (previousMessage.sender_id || previousMessage.sender_name)
      : null;
    const sameSender = day === previousDay && senderKey === previousSenderKey;
    messages.append(createMessageArticle(message, sameSender));
    previousMessage = message;
  }
  updateMessageTimeLayouts();
  requestAnimationFrame(syncMessageScrollbar);
}

function appendMessage(message) {
  if (messageCache.has(message.id)) return false;
  const previousMessage = newestLoadedMessageId === null
    ? null
    : messageCache.get(newestLoadedMessageId);
  const canAppend = newestLoadedMessageId === null || message.id > newestLoadedMessageId;
  messageCache.set(message.id, message);
  if (canAppend) {
    appendRenderedMessage(message, previousMessage);
    newestLoadedMessageId = message.id;
    if (oldestLoadedMessageId === null) oldestLoadedMessageId = message.id;
  } else {
    syncLoadedMessageBounds();
    renderMessages();
  }
  return true;
}

function isNearLatest() {
  const distanceFromLatest = messages.scrollHeight - messages.clientHeight - messages.scrollTop;
  return distanceFromLatest <= NEW_MESSAGE_AUTOSCROLL_THRESHOLD;
}

function updateNewMessagesButton() {
  const hasUnseenMessages = unseenMessageCount > 0;
  newMessagesButton.hidden = !hasUnseenMessages;
  if (!hasUnseenMessages) return;
  newMessagesLabel.textContent = t("chat.newMessages", { count: unseenMessageCount });
  const actionLabel = t("chat.jumpToLatest");
  newMessagesButton.title = actionLabel;
}

function clearUnseenMessages() {
  if (!unseenMessageCount) return;
  unseenMessageCount = 0;
  updateNewMessagesButton();
}

function appendIncomingMessage(message) {
  const shouldFollowLatest = isNearLatest();
  const previousScrollTop = messages.scrollTop;
  if (!appendMessage(message)) return;
  if (shouldFollowLatest) {
    scrollToLatest();
    return;
  }
  messages.scrollTop = previousScrollTop;
  unseenMessageCount += 1;
  updateNewMessagesButton();
  syncMessageScrollbar();
}

function scrollToLatest() {
  messages.scrollTop = messages.scrollHeight;
  clearUnseenMessages();
  syncMessageScrollbar();
}

async function loadHistory() {
  if (initialHistoryLoaded) {
    await loadNewerMessages();
    return;
  }
  const batch = await api(`/api/messages?limit=${HISTORY_PAGE_SIZE}`);
  batch.forEach((message) => messageCache.set(message.id, message));
  syncLoadedMessageBounds();
  hasMoreHistory = batch.length === HISTORY_PAGE_SIZE;
  initialHistoryLoaded = true;
  renderMessages();
  scrollToLatest();
}

function syncLoadedMessageBounds() {
  oldestLoadedMessageId = null;
  newestLoadedMessageId = null;
  for (const id of messageCache.keys()) {
    if (oldestLoadedMessageId === null || id < oldestLoadedMessageId) oldestLoadedMessageId = id;
    if (newestLoadedMessageId === null || id > newestLoadedMessageId) newestLoadedMessageId = id;
  }
}

function captureHistoryAnchor() {
  const viewportTop = messages.getBoundingClientRect().top + chatHeader.getBoundingClientRect().height;
  const anchor = [...messages.querySelectorAll(".message")].find(
    (article) => article.getBoundingClientRect().bottom > viewportTop,
  );
  if (!anchor) return null;
  return {
    messageId: anchor.dataset.messageId,
    offsetTop: anchor.getBoundingClientRect().top - viewportTop,
  };
}

function restoreHistoryAnchor(anchor) {
  if (!anchor) return false;
  const article = messages.querySelector(`[data-message-id="${anchor.messageId}"]`);
  if (!article) return false;
  const viewportTop = messages.getBoundingClientRect().top + chatHeader.getBoundingClientRect().height;
  const nextOffsetTop = article.getBoundingClientRect().top - viewportTop;
  messages.scrollTop += nextOffsetTop - anchor.offsetTop;
  return true;
}

async function loadOlderMessages() {
  if (!initialHistoryLoaded || loadingOlderMessages || !hasMoreHistory || oldestLoadedMessageId === null) {
    return;
  }
  loadingOlderMessages = true;
  const anchor = captureHistoryAnchor();
  const previousScrollTop = messages.scrollTop;
  const previousScrollHeight = messages.scrollHeight;
  try {
    const query = `?limit=${HISTORY_PAGE_SIZE}&before=${oldestLoadedMessageId}`;
    const batch = await api(`/api/messages${query}`);
    hasMoreHistory = batch.length === HISTORY_PAGE_SIZE;
    if (!batch.length) return;
    batch.forEach((message) => messageCache.set(message.id, message));
    syncLoadedMessageBounds();
    renderMessages();
    messages.scrollTop = previousScrollTop;
    if (!restoreHistoryAnchor(anchor)) {
      messages.scrollTop = previousScrollTop + messages.scrollHeight - previousScrollHeight;
    }
    syncMessageScrollbar();
  } finally {
    loadingOlderMessages = false;
  }
}

function maybeLoadOlderMessages() {
  if (messages.scrollTop <= HISTORY_LOAD_THRESHOLD) {
    loadOlderMessages().catch((error) => {
      if (error.status === 401) showLogin("errors.sessionExpired");
    });
  }
}

async function loadNewerMessages() {
  if (newestLoadedMessageId === null) return;
  const shouldFollowLatest = isNearLatest();
  let cursor = newestLoadedMessageId;
  let addedCount = 0;
  let requiresRerender = false;
  while (true) {
    const query = `?limit=${HISTORY_PAGE_SIZE}&after=${cursor}`;
    const batch = await api(`/api/messages${query}`);
    for (const message of batch) {
      if (messageCache.has(message.id)) continue;
      if (message.id > newestLoadedMessageId) {
        appendMessage(message);
      } else {
        messageCache.set(message.id, message);
        requiresRerender = true;
      }
      addedCount += 1;
    }
    if (batch.length < HISTORY_PAGE_SIZE) break;
    cursor = batch[batch.length - 1].id;
  }
  if (!addedCount) return;
  if (requiresRerender) {
    syncLoadedMessageBounds();
    renderMessages();
  }
  if (shouldFollowLatest || isNearLatest()) {
    scrollToLatest();
  } else {
    unseenMessageCount += addedCount;
    updateNewMessagesButton();
    syncMessageScrollbar();
  }
}

function connectWebSocket() {
  clearTimeout(reconnectTimer);
  if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
  setConnection("chat.connecting", false);
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const shouldBackfillOnOpen = initialHistoryLoaded;
  socket = new WebSocket(`${protocol}//${location.host}/ws`);
  socket.onopen = () => {
    setConnection("chat.connected", true);
    if (shouldBackfillOnOpen) loadHistory().catch(() => {});
  };
  socket.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "message_created") {
      appendIncomingMessage(payload.message);
    }
  };
  socket.onclose = (event) => {
    socket = null;
    if (event.code === 4401) {
      showLogin("errors.sessionExpired");
      return;
    }
    if (!chatView.hidden) {
      setConnection("chat.reconnecting", false);
      reconnectTimer = setTimeout(connectWebSocket, 1500);
    }
  };
}

function syncComposerSpace() {
  syncChatHeaderHeight();
  const composerHeight = Math.ceil(messageForm.getBoundingClientRect().height);
  document.documentElement.style.setProperty("--composer-height", `${composerHeight}px`);
  document.documentElement.style.setProperty("--composer-space", `${composerHeight + 40}px`);
}

function syncChatHeaderHeight() {
  const headerHeight = Math.ceil(chatHeader.getBoundingClientRect().height);
  if (headerHeight) document.documentElement.style.setProperty("--chat-header-height", `${headerHeight}px`);
}

function updateComposerLayout() {
  const inputStyle = getComputedStyle(messageInput);
  const lineHeight = Number.parseFloat(inputStyle.lineHeight) || 23;
  const maxHeight = Number.parseFloat(inputStyle.maxHeight) || 180;
  const hasWrappedText = messageInput.scrollHeight > lineHeight * 1.8;
  const reachedMaxHeight = messageInput.scrollHeight >= maxHeight - 1;
  messageForm.classList.toggle("expanded", Boolean(pendingFiles.length) || hasWrappedText || !attachmentStatus.hidden);
  messageForm.classList.toggle("can-fullscreen", reachedMaxHeight);
  requestAnimationFrame(syncComposerSpace);
}

function updateSendButton() {
  sendButton.disabled = sending || (!messageInput.value.trim() && !pendingFiles.length);
}

function resizeTextarea() {
  if (dropZone.classList.contains("fullscreen")) {
    messageInput.style.height = "";
  } else {
    messageInput.style.height = "auto";
    const maxHeight = Number.parseFloat(getComputedStyle(messageInput).maxHeight) || 180;
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, maxHeight)}px`;
  }
  updateComposerLayout();
  updateSendButton();
}

function setComposerFullscreen(value) {
  const fullscreen = Boolean(value);
  dropZone.classList.toggle("fullscreen", fullscreen);
  expandComposerButton.setAttribute("aria-expanded", String(fullscreen));
  const label = t(fullscreen ? "composer.collapse" : "composer.expand");
  expandComposerButton.title = label;
  expandComposerButton.setAttribute("aria-label", label);
  resizeTextarea();
  requestAnimationFrame(() => {
    syncComposerSpace();
    if (!chatView.hidden && !messageInput.disabled) messageInput.focus();
  });
}

function uniqueAttachmentNames(files) {
  const used = new Set();
  return files.map((file) => {
    const original = file.name || "unnamed-file";
    const dot = original.lastIndexOf(".");
    const hasSuffix = dot > 0;
    const stem = hasSuffix ? original.slice(0, dot) : original;
    const suffix = hasSuffix ? original.slice(dot) : "";
    let candidate = original;
    let counter = 2;
    while (used.has(candidate.normalize("NFKC").toLocaleLowerCase())) {
      candidate = `${stem} (${counter})${suffix}`;
      counter += 1;
    }
    used.add(candidate.normalize("NFKC").toLocaleLowerCase());
    return candidate;
  });
}

function clearAttachmentStatus() {
  clearTimeout(uploadStatusDelayTimer);
  uploadStatusDelayTimer = null;
  uploadStatusVisible = false;
  attachmentStatus.hidden = true;
  attachmentStatus.classList.remove("error");
  attachmentStatus.classList.remove("is-leaving");
  uploadStatus.textContent = "";
  uploadProgress.hidden = true;
  uploadProgress.removeAttribute("aria-valuenow");
  uploadProgressBar.style.width = "0%";
  uploadProgressLabel.hidden = true;
  uploadProgressLabel.textContent = "";
  cancelUploadButton.hidden = true;
  cancelUploadButton.disabled = false;
  retryUploadButton.hidden = true;
  updateComposerLayout();
}

function showAttachmentStatus(
  message,
  { tone = "neutral", progress = null, retry = false, cancellable = false } = {},
) {
  uploadStatus.textContent = message;
  attachmentStatus.hidden = false;
  attachmentStatus.classList.toggle("error", tone === "error");
  attachmentStatus.classList.remove("is-leaving");
  cancelUploadButton.hidden = !cancellable;
  cancelUploadButton.disabled = !cancellable;
  retryUploadButton.hidden = !retry;
  retryUploadButton.disabled = sending;

  const hasProgress = Number.isFinite(progress);
  uploadProgress.hidden = !hasProgress;
  uploadProgressLabel.hidden = !hasProgress;
  if (hasProgress) {
    const normalizedProgress = Math.max(0, Math.min(100, Math.round(progress)));
    uploadProgress.setAttribute("aria-valuenow", String(normalizedProgress));
    uploadProgressBar.style.width = `${normalizedProgress}%`;
    uploadProgressLabel.textContent = `${normalizedProgress}%`;
  }
  updateComposerLayout();
}

function scheduleUploadPresentation(request, uploadName) {
  clearTimeout(uploadStatusDelayTimer);
  uploadStatusVisible = false;
  latestUploadProgress = 0;
  uploadStatusDelayTimer = setTimeout(() => {
    if (activeUploadRequest !== request) return;
    uploadStatusVisible = true;
    showAttachmentStatus(t("upload.uploading", { name: uploadName }), {
      progress: latestUploadProgress,
      cancellable: true,
    });
  }, UPLOAD_STATUS_DELAY);
}

function fadeUploadPresentation() {
  clearTimeout(uploadStatusDelayTimer);
  uploadStatusDelayTimer = null;
  if (!uploadStatusVisible || attachmentStatus.hidden) {
    clearAttachmentStatus();
    return Promise.resolve();
  }
  cancelUploadButton.disabled = true;
  attachmentStatus.classList.add("is-leaving");
  return new Promise((resolve) => {
    setTimeout(() => {
      clearAttachmentStatus();
      resolve();
    }, UPLOAD_STATUS_FADE_DURATION);
  });
}

async function validateReadableFiles(files) {
  const results = await Promise.all(files.map(async (file) => {
    try {
      await file.slice(0, Math.min(file.size, 1)).arrayBuffer();
      return { file, readable: true };
    } catch (error) {
      return { file, readable: false };
    }
  }));
  return {
    readable: results.filter((result) => result.readable).map((result) => result.file),
    failed: results.filter((result) => !result.readable).map((result) => result.file),
  };
}

function clipboardFileExtension(type) {
  const normalizedType = type.toLowerCase();
  const knownExtensions = {
    "application/json": "json",
    "application/octet-stream": "bin",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/x-7z-compressed": "7z",
    "application/x-rar-compressed": "rar",
    "application/zip": "zip",
    "image/jpeg": "jpg",
    "image/svg+xml": "svg",
    "text/csv": "csv",
    "text/plain": "txt",
  };
  if (knownExtensions[normalizedType]) return knownExtensions[normalizedType];

  const subtype = normalizedType.split("/", 2)[1]?.split("+", 1)[0] || "";
  return /^[a-z0-9]{1,16}$/.test(subtype) ? subtype : "bin";
}

function createClipboardFile(file, index, declaredType = "") {
  if (!file) return null;
  if (file.name) return file;

  const type = file.type || declaredType || "application/octet-stream";
  const label = type.toLowerCase().startsWith("image/")
    ? t("upload.pastedImage")
    : t("upload.pastedFile");
  return new File([file], `${label}-${index + 1}.${clipboardFileExtension(type)}`, {
    type,
    lastModified: Date.now(),
  });
}

function getClipboardFiles(clipboardData) {
  const sources = [];
  const seen = new Set();
  const add = (file, declaredType = "") => {
    if (!file) return;
    const key = [file.name, file.size, file.lastModified, file.type || declaredType].join("\u0000");
    if (seen.has(key)) return;
    seen.add(key);
    sources.push({ file, declaredType });
  };

  for (const item of clipboardData?.items || []) {
    if (item.kind === "file") add(item.getAsFile(), item.type);
  }
  for (const file of clipboardData?.files || []) add(file);
  return sources
    .map(({ file, declaredType }, index) => createClipboardFile(file, index, declaredType))
    .filter(Boolean);
}

function renderPendingFiles() {
  filePreview.replaceChildren();
  const displayNames = uniqueAttachmentNames(pendingFiles);
  pendingFiles.forEach((file, index) => {
    const card = document.createElement("div");
    card.className = "file-preview-card";
    const icon = document.createElement("span");
    icon.className = "file-preview-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "📎";
    const copy = document.createElement("span");
    copy.className = "file-preview-copy";
    const name = document.createElement("strong");
    name.textContent = displayNames[index];
    const size = document.createElement("small");
    size.textContent = formatBytes(file.size);
    copy.append(name, size);
    const removeButton = document.createElement("button");
    removeButton.className = "remove-file";
    removeButton.type = "button";
    removeButton.disabled = sending;
    removeButton.title = t("composer.removeFile");
    removeButton.setAttribute("aria-label", `${t("composer.removeFile")} · ${displayNames[index]}`);
    removeButton.textContent = "×";
    removeButton.addEventListener("click", () => removePendingFile(index));
    card.append(icon, copy, removeButton);
    filePreview.append(card);
  });
  filePreview.hidden = !pendingFiles.length;
}

async function appendPendingFiles(files) {
  if (sending) return;
  const additions = [...files];
  if (!additions.length) return;
  const { readable, failed } = await validateReadableFiles(additions);
  if (sending) return;

  const accepted = [];
  let totalBytes = pendingFiles.reduce((total, file) => total + file.size, 0);
  let rejectedByCount = false;
  let rejectedBySize = false;
  readable.forEach((file) => {
    if (pendingFiles.length + accepted.length >= MAX_ATTACHMENTS_PER_MESSAGE) {
      rejectedByCount = true;
      return;
    }
    if (currentMaxUploadBytes && totalBytes + file.size > currentMaxUploadBytes) {
      rejectedBySize = true;
      return;
    }
    accepted.push(file);
    totalBytes += file.size;
  });
  pendingFiles.push(...accepted);
  fileInput.value = "";

  const issues = [];
  if (rejectedByCount) issues.push(t("upload.tooMany", { count: MAX_ATTACHMENTS_PER_MESSAGE }));
  if (rejectedBySize) issues.push(t("upload.tooLarge"));
  if (failed.length) {
    issues.push(t("upload.readFailed", { name: failed.map((file) => file.name).join(", ") }));
  }
  if (issues.length) {
    showAttachmentStatus(issues.join(" · "), { tone: "error" });
  } else {
    clearAttachmentStatus();
  }
  renderPendingFiles();
  resizeTextarea();
}

function removePendingFile(index, force = false) {
  if (sending && !force) return;
  pendingFiles.splice(index, 1);
  renderPendingFiles();
  fileInput.value = "";
  clearAttachmentStatus();
  updateComposerLayout();
  updateSendButton();
}

function clearPendingFiles(force = false) {
  if (sending && !force) return;
  pendingFiles = [];
  renderPendingFiles();
  fileInput.value = "";
  clearAttachmentStatus();
  updateComposerLayout();
  updateSendButton();
}

function setSending(value) {
  sending = value;
  fileInput.disabled = value;
  messageInput.disabled = value;
  retryUploadButton.disabled = value;
  dropZone.classList.toggle("sending", value);
  renderPendingFiles();
  updateSendButton();
}

function createUploadId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function uploadCombinedMessage(body, files) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("body", body);
    files.forEach((file) => form.append("files", file, file.name));
    const request = new XMLHttpRequest();
    request.open("POST", "/api/files");
    const uploadId = createUploadId();
    request.setRequestHeader("X-Upload-ID", uploadId);
    request.uploadId = uploadId;
    const uploadName = files.length === 1
      ? files[0].name
      : t("upload.fileCount", { count: files.length });
    activeUploadRequest = request;
    activeUploadId = uploadId;
    scheduleUploadPresentation(request, uploadName);

    const finishRequest = () => {
      clearTimeout(uploadStatusDelayTimer);
      uploadStatusDelayTimer = null;
      if (activeUploadRequest === request) {
        activeUploadRequest = null;
        activeUploadId = null;
      }
    };
    const rejectCancelledUpload = () => {
      finishRequest();
      const error = new Error("upload-cancelled");
      error.cancelled = true;
      fadeUploadPresentation().then(() => reject(error));
    };
    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      latestUploadProgress = Math.round((event.loaded / event.total) * 100);
      if (uploadStatusVisible) {
        showAttachmentStatus(t("upload.uploading", { name: uploadName }), {
          progress: latestUploadProgress,
          cancellable: true,
        });
      }
    });
    request.addEventListener("load", () => {
      if (request.lanimalsCancelled) {
        rejectCancelledUpload();
        return;
      }
      if (request.status >= 200 && request.status < 300) {
        try {
          const message = JSON.parse(request.responseText);
          finishRequest();
          fadeUploadPresentation().then(() => resolve(message));
        } catch (error) {
          finishRequest();
          reject(new Error(t("errors.invalidResponse")));
        }
        return;
      }
      const error = new Error(
        request.status === 413
          ? t("upload.tooLarge")
          : t("upload.failed", { status: request.status }),
      );
      error.status = request.status;
      finishRequest();
      reject(error);
    });
    request.addEventListener("error", () => {
      finishRequest();
      reject(new Error(t("upload.networkError")));
    });
    request.addEventListener("abort", () => {
      rejectCancelledUpload();
    });
    try {
      request.send(form);
    } catch (error) {
      finishRequest();
      reject(error);
    }
  });
}

messageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (sending) return;
  const body = messageInput.value.trim();
  const files = [...pendingFiles];
  if (!body && !files.length) return;

  setSending(true);
  try {
    const message = files.length
      ? await uploadCombinedMessage(body, files)
      : await api("/api/messages", { method: "POST", body: JSON.stringify({ body }) });
    appendMessage(message);
    messageInput.value = "";
    clearAttachmentStatus();
    if (pendingFiles.length === files.length && files.every((file, index) => pendingFiles[index] === file)) {
      clearPendingFiles(true);
    }
    resizeTextarea();
    scrollToLatest();
  } catch (error) {
    if (error.status === 401) {
      showLogin("errors.sessionExpired");
    } else if (error.cancelled) {
      clearAttachmentStatus();
    } else {
      showAttachmentStatus(error.message || t("errors.sendFailed"), {
        tone: "error",
        retry: Boolean(files.length),
      });
    }
  } finally {
    setSending(false);
    if (!chatView.hidden) messageInput.focus();
  }
});

messageInput.addEventListener("input", resizeTextarea);
document.addEventListener("paste", (event) => {
  // 附件粘贴不应依赖 textarea 已经获得焦点；只在已登录聊天室中接管文件剪贴板。
  if (chatView.hidden || sending) return;
  const files = getClipboardFiles(event.clipboardData);
  if (!files.length) return;

  // 文件剪贴板可能携带文件路径等文本表示；不让它混入聊天正文。
  event.preventDefault();
  void appendPendingFiles(files).then(() => {
    if (!sending && !chatView.hidden) messageInput.focus();
  });
});
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    messageForm.requestSubmit();
  }
});
expandComposerButton.addEventListener("click", () => {
  setComposerFullscreen(!dropZone.classList.contains("fullscreen"));
});
mediaViewerClose.addEventListener("click", closeMediaViewer);
mediaViewerPrevious.addEventListener("click", () => moveMediaViewer(-1));
mediaViewerNext.addEventListener("click", () => moveMediaViewer(1));
mediaViewer.addEventListener("click", (event) => {
  if (event.target === mediaViewer) closeMediaViewer();
});
mediaViewer.addEventListener("pointerdown", (event) => {
  if (event.pointerType !== "touch" || !shouldStartMediaViewerSwipe(event.target, event.clientY)) return;
  mediaViewerSwipe = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY };
}, true);
mediaViewer.addEventListener("pointerup", finishMediaViewerSwipe, true);
mediaViewer.addEventListener("pointercancel", () => {
  mediaViewerSwipe = null;
}, true);
mediaViewer.addEventListener("touchstart", startMediaViewerTouch, { passive: true, capture: true });
mediaViewer.addEventListener("touchend", finishMediaViewerTouch, { passive: true, capture: true });
mediaViewer.addEventListener("touchcancel", () => {
  mediaViewerTouch = null;
}, { passive: true, capture: true });
mediaViewer.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeMediaViewer();
});
mediaViewer.addEventListener("close", () => {
  document.documentElement.classList.remove("media-viewer-open");
  mediaViewerStage.replaceChildren();
  hideMediaViewerPosition();
  mediaViewerPosition.textContent = "";
  mediaViewerSystemOpen.hidden = true;
  mediaViewerSystemOpen.removeAttribute("href");
  mediaViewerIndex = -1;
  mediaViewerSwipe = null;
  mediaViewerTouch = null;
  const trigger = mediaViewerTrigger;
  mediaViewerTrigger = null;
  if (trigger?.isConnected) trigger.focus();
});
document.addEventListener("keydown", (event) => {
  if (mediaViewer.open) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      moveMediaViewer(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      moveMediaViewer(1);
    }
    return;
  }
  if (event.key === "Escape" && dropZone.classList.contains("fullscreen")) {
    event.preventDefault();
    setComposerFullscreen(false);
  }
});
fileInput.addEventListener("change", () => appendPendingFiles(fileInput.files || []));
retryUploadButton.addEventListener("click", () => {
  if (!sending) messageForm.requestSubmit();
});
cancelUploadButton.addEventListener("click", async () => {
  const request = activeUploadRequest;
  const uploadId = activeUploadId;
  if (!request || !uploadId) return;
  request.lanimalsCancelled = true;
  cancelUploadButton.disabled = true;
  try {
    await fetch(`/api/uploads/${encodeURIComponent(uploadId)}/cancel`, { method: "POST" });
  } finally {
    if (activeUploadRequest === request) activeUploadRequest.abort();
  }
});

for (const eventName of ["dragenter", "dragover", "dragleave", "drop"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    event.stopPropagation();
  });
}
dropZone.addEventListener("dragenter", () => {
  if (sending) return;
  dragDepth += 1;
  messageForm.classList.add("dragging");
});
dropZone.addEventListener("dragleave", () => {
  if (sending) return;
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) messageForm.classList.remove("dragging");
});
dropZone.addEventListener("drop", (event) => {
  if (sending) return;
  dragDepth = 0;
  messageForm.classList.remove("dragging");
  const files = [...(event.dataTransfer?.files || [])];
  appendPendingFiles(files);
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  try {
    const identity = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ password: passwordInput.value, incognito: incognitoInput.checked }),
    });
    await showChat(identity);
  } catch (error) {
    loginError.textContent = error.status === 401 ? t("errors.wrongPassword") : error.message;
  }
});

messages.addEventListener("pointermove", (event) => {
  if (!hasDesktopMessageScrollbar()) return;
  if (event.pointerType && event.pointerType !== "mouse" && event.pointerType !== "pen") return;
  const bounds = messages.getBoundingClientRect();
  const pointerNearEdge = event.clientX >= bounds.right - MESSAGE_SCROLLBAR_EDGE_ZONE;
  if (pointerNearEdge === messageScrollbarPointerNearEdge) return;
  messageScrollbarPointerNearEdge = pointerNearEdge;
  if (pointerNearEdge) revealMessageScrollbar();
  else scheduleMessageScrollbarHide(180);
});
messages.addEventListener("pointerleave", () => {
  if (!hasDesktopMessageScrollbar()) return;
  messageScrollbarPointerNearEdge = false;
  scheduleMessageScrollbarHide(180);
});
messages.addEventListener("wheel", (event) => {
  if (event.deltaY < 0) maybeLoadOlderMessages();
}, { passive: true });
messages.addEventListener("scroll", () => {
  syncMessageScrollbar();
  if (isNearLatest()) clearUnseenMessages();
  maybeLoadOlderMessages();
}, { passive: true });
newMessagesButton.addEventListener("click", scrollToLatest);

messagesScrollbar.addEventListener("pointerenter", (event) => {
  if (event.pointerType && event.pointerType !== "mouse" && event.pointerType !== "pen") return;
  messageScrollbarPointerNearEdge = true;
  revealMessageScrollbar();
});
messagesScrollbar.addEventListener("pointerleave", () => {
  if (messageScrollbarDrag) return;
  messageScrollbarPointerNearEdge = false;
  scheduleMessageScrollbarHide(180);
});
messagesScrollbar.addEventListener("pointerdown", (event) => {
  if (event.target === messagesScrollbarThumb || event.button !== 0) return;
  event.preventDefault();
  const thumbHeight = messagesScrollbarThumb.getBoundingClientRect().height;
  scrollMessagesFromScrollbarPointer(event.clientY, thumbHeight / 2);
  revealMessageScrollbar();
});
messagesScrollbarThumb.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  const thumbBounds = messagesScrollbarThumb.getBoundingClientRect();
  messageScrollbarDrag = {
    pointerId: event.pointerId,
    thumbOffset: event.clientY - thumbBounds.top,
  };
  messageScrollbarPointerNearEdge = true;
  messagesScrollbar.classList.add("dragging");
  messagesScrollbarThumb.setPointerCapture(event.pointerId);
  revealMessageScrollbar();
});
window.addEventListener("pointermove", (event) => {
  if (!messageScrollbarDrag || event.pointerId !== messageScrollbarDrag.pointerId) return;
  event.preventDefault();
  scrollMessagesFromScrollbarPointer(event.clientY, messageScrollbarDrag.thumbOffset);
});
window.addEventListener("pointerup", finishMessageScrollbarDrag);
window.addEventListener("pointercancel", finishMessageScrollbarDrag);

function syncVisualViewport() {
  const visualViewport = window.visualViewport;
  const visualBottom = visualViewport
    ? visualViewport.height + visualViewport.offsetTop
    : window.innerHeight;
  const keyboardOffset = Math.max(0, window.innerHeight - visualBottom);
  document.documentElement.style.setProperty("--keyboard-offset", `${keyboardOffset}px`);
  if (document.activeElement === messageInput) requestAnimationFrame(scrollToLatest);
}

const composerResizeObserver = "ResizeObserver" in window
  ? new ResizeObserver(syncComposerSpace)
  : null;
composerResizeObserver?.observe(messageForm);
composerResizeObserver?.observe(chatHeader);
const messageScrollbarResizeObserver = "ResizeObserver" in window
  ? new ResizeObserver(syncMessageScrollbar)
  : null;
messageScrollbarResizeObserver?.observe(messages);

function handleWindowResize() {
  syncChatHeaderHeight();
  syncComposerPlaceholder();
  syncVisualViewport();
  syncMessageScrollbar();
  requestAnimationFrame(updateMessageTimeLayouts);
}

if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", handleWindowResize);
  window.visualViewport.addEventListener("scroll", syncVisualViewport);
}
window.addEventListener("resize", handleWindowResize);
messageInput.addEventListener("focus", () => setTimeout(syncVisualViewport, 80));
messageInput.addEventListener("blur", () => setTimeout(syncVisualViewport, 80));

async function start() {
  await loadTranslations();
  resizeTextarea();
  syncVisualViewport();
  try {
    const identity = await api("/api/me");
    await showChat(identity);
  } catch (error) {
    showLogin();
  }
}

start();
