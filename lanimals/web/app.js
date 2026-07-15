"use strict";

let translations = {};
let currentLocale = "en";
let socket = null;
let reconnectTimer = null;
let currentIdentityId = null;
let messageScrollbarHideTimer = null;
let messageScrollbarPointerNearEdge = false;
let pendingFiles = [];
let sending = false;
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
const emptyState = document.querySelector("#empty-state");
const dropZone = document.querySelector("#drop-zone");
const chatHeader = document.querySelector(".chat-header");
const messageForm = document.querySelector("#message-form");
const messageInput = document.querySelector("#message-input");
const expandComposerButton = document.querySelector("#expand-composer");
const fileInput = document.querySelector("#file-input");
const filePreview = document.querySelector("#file-preview");
const uploadStatus = document.querySelector("#upload-status");
const sendButton = document.querySelector("#send-button");

const MAX_ATTACHMENTS_PER_MESSAGE = 12;
const MESSAGE_SCROLLBAR_EDGE_ZONE = 18;
const MESSAGE_SCROLLBAR_HIDE_DELAY = 700;

function revealMessageScrollbar() {
  clearTimeout(messageScrollbarHideTimer);
  messages.classList.add("scrollbar-active");
}

function scheduleMessageScrollbarHide(delay = MESSAGE_SCROLLBAR_HIDE_DELAY) {
  clearTimeout(messageScrollbarHideTimer);
  if (messageScrollbarPointerNearEdge) return;
  messageScrollbarHideTimer = setTimeout(() => {
    messages.classList.remove("scrollbar-active");
  }, delay);
}

function pulseMessageScrollbar() {
  revealMessageScrollbar();
  scheduleMessageScrollbarHide();
}

function syncMessageScrollbar() {
  const viewportHeight = messages.clientHeight;
  const contentHeight = messages.scrollHeight;
  const scrollRange = Math.max(0, contentHeight - viewportHeight);
  messagesScrollbar.hidden = !viewportHeight || scrollRange <= 1;
  if (messagesScrollbar.hidden) {
    messages.classList.remove("scrollbar-active");
    return;
  }

  const thumbHeight = Math.max(28, viewportHeight * (viewportHeight / contentHeight));
  const thumbTravel = Math.max(0, viewportHeight - thumbHeight);
  const thumbTop = scrollRange ? (messages.scrollTop / scrollRange) * thumbTravel : 0;
  messagesScrollbarThumb.style.height = `${thumbHeight}px`;
  messagesScrollbarThumb.style.transform = `translateY(${thumbTop}px)`;
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

async function loadTranslations() {
  const saved = localStorage.getItem("lanimals-locale");
  currentLocale = saved || (navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en");
  if (!new Set(["zh-CN", "en"]).has(currentLocale)) currentLocale = "en";
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

async function showChat(identity) {
  loginView.hidden = true;
  chatView.hidden = false;
  currentIdentityId = identity.identity_id;
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

function updateMessageTimeLayouts() {
  const bubbles = [...messages.querySelectorAll(".bubble")];
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

function renderMessages() {
  const ordered = [...messageCache.values()].sort((left, right) => left.id - right.id);
  messages.replaceChildren();
  if (!ordered.length) {
    emptyState.hidden = false;
    messages.append(emptyState);
    requestAnimationFrame(syncMessageScrollbar);
    return;
  }

  let previousSenderKey = null;
  let previousDay = null;
  for (const message of ordered) {
    const date = new Date(message.created_at);
    const day = calendarDayKey(date);
    if (day !== previousDay) {
      const separator = document.createElement("div");
      separator.className = "date-separator";
      const dateLabel = document.createElement("time");
      dateLabel.dateTime = day;
      dateLabel.textContent = date.toLocaleDateString(currentLocale, {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
      separator.append(dateLabel);
      messages.append(separator);
      previousSenderKey = null;
    }

    const senderKey = message.sender_id || message.sender_name;
    const sameSender = previousSenderKey === senderKey;
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
      attachmentList.className = `attachment-list attachment-columns-${Math.min(attachments.length, 4)}`;
      attachments.forEach((item, index) => {
        const attachment = document.createElement("a");
        attachment.className = "attachment";
        attachment.href = `/api/files/${encodeURIComponent(item.id)}`;
        attachment.innerHTML = '<span class="attachment-icon" aria-hidden="true">📄</span>';
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
          attachment.append(createMessageTime(message));
        }
        attachmentList.append(attachment);
      });
      content.append(attachmentList);
    }

    article.append(content);
    messages.append(article);
    previousSenderKey = senderKey;
    previousDay = day;
  }
  updateMessageTimeLayouts();
  requestAnimationFrame(syncMessageScrollbar);
}

function appendMessage(message) {
  if (messageCache.has(message.id)) return;
  messageCache.set(message.id, message);
  renderMessages();
}

function scrollToLatest() {
  messages.scrollTop = messages.scrollHeight;
  syncMessageScrollbar();
}

async function loadHistory() {
  const collected = [];
  let before = null;
  while (true) {
    const query = before ? `?limit=200&before=${before}` : "?limit=200";
    const batch = await api(`/api/messages${query}`);
    collected.unshift(...batch);
    if (batch.length < 200) break;
    before = batch[0].id;
  }
  collected.forEach((message) => messageCache.set(message.id, message));
  renderMessages();
  scrollToLatest();
}

function connectWebSocket() {
  clearTimeout(reconnectTimer);
  if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
  setConnection("chat.connecting", false);
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(`${protocol}//${location.host}/ws`);
  socket.onopen = () => {
    setConnection("chat.connected", true);
    loadHistory().catch(() => {});
  };
  socket.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "message_created") {
      appendMessage(payload.message);
      scrollToLatest();
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
  messageForm.classList.toggle("expanded", Boolean(pendingFiles.length) || hasWrappedText || !uploadStatus.hidden);
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

function appendPendingFiles(files) {
  if (sending) return;
  const additions = [...files];
  if (!additions.length) return;
  const available = Math.max(0, MAX_ATTACHMENTS_PER_MESSAGE - pendingFiles.length);
  pendingFiles.push(...additions.slice(0, available));
  fileInput.value = "";
  if (additions.length > available) {
    uploadStatus.hidden = false;
    uploadStatus.textContent = t("upload.tooMany", { count: MAX_ATTACHMENTS_PER_MESSAGE });
  } else {
    uploadStatus.hidden = true;
  }
  renderPendingFiles();
  resizeTextarea();
}

function removePendingFile(index, force = false) {
  if (sending && !force) return;
  pendingFiles.splice(index, 1);
  renderPendingFiles();
  fileInput.value = "";
  updateComposerLayout();
  updateSendButton();
}

function clearPendingFiles(force = false) {
  if (sending && !force) return;
  pendingFiles = [];
  renderPendingFiles();
  fileInput.value = "";
  updateComposerLayout();
  updateSendButton();
}

function setSending(value) {
  sending = value;
  fileInput.disabled = value;
  messageInput.disabled = value;
  dropZone.classList.toggle("sending", value);
  renderPendingFiles();
  updateSendButton();
}

function uploadCombinedMessage(body, files) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("body", body);
    files.forEach((file) => form.append("files", file, file.name));
    const request = new XMLHttpRequest();
    request.open("POST", "/api/files");
    uploadStatus.hidden = false;
    const uploadName = files.length === 1
      ? files[0].name
      : t("upload.fileCount", { count: files.length });
    uploadStatus.textContent = t("upload.uploading", { name: uploadName });
    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      const progress = Math.round((event.loaded / event.total) * 100);
      uploadStatus.textContent = t("upload.progress", { name: uploadName, progress });
    });
    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        try {
          resolve(JSON.parse(request.responseText));
        } catch (error) {
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
      reject(error);
    });
    request.addEventListener("error", () => reject(new Error(t("upload.networkError"))));
    request.send(form);
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
    uploadStatus.hidden = true;
    if (pendingFiles.length === files.length && files.every((file, index) => pendingFiles[index] === file)) {
      clearPendingFiles(true);
    }
    resizeTextarea();
    scrollToLatest();
  } catch (error) {
    if (error.status === 401) {
      showLogin("errors.sessionExpired");
    } else {
      uploadStatus.hidden = false;
      uploadStatus.textContent = error.message || t("errors.sendFailed");
    }
  } finally {
    setSending(false);
    if (!chatView.hidden) messageInput.focus();
  }
});

messageInput.addEventListener("input", resizeTextarea);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    messageForm.requestSubmit();
  }
});
expandComposerButton.addEventListener("click", () => {
  setComposerFullscreen(!dropZone.classList.contains("fullscreen"));
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && dropZone.classList.contains("fullscreen")) {
    event.preventDefault();
    setComposerFullscreen(false);
  }
});
fileInput.addEventListener("change", () => appendPendingFiles(fileInput.files || []));

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
  if (event.pointerType && event.pointerType !== "mouse" && event.pointerType !== "pen") return;
  const bounds = messages.getBoundingClientRect();
  const pointerNearEdge = event.clientX >= bounds.right - MESSAGE_SCROLLBAR_EDGE_ZONE;
  if (pointerNearEdge === messageScrollbarPointerNearEdge) return;
  messageScrollbarPointerNearEdge = pointerNearEdge;
  if (pointerNearEdge) revealMessageScrollbar();
  else scheduleMessageScrollbarHide(180);
});
messages.addEventListener("pointerleave", () => {
  messageScrollbarPointerNearEdge = false;
  scheduleMessageScrollbarHide(180);
});
messages.addEventListener("wheel", pulseMessageScrollbar, { passive: true });
messages.addEventListener("scroll", () => {
  syncMessageScrollbar();
  pulseMessageScrollbar();
}, { passive: true });

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
