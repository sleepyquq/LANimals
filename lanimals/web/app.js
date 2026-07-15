"use strict";

let translations = {};
let currentLocale = "en";
let socket = null;
let reconnectTimer = null;
let pendingFile = null;
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
const emptyState = document.querySelector("#empty-state");
const dropZone = document.querySelector("#drop-zone");
const messageForm = document.querySelector("#message-form");
const messageInput = document.querySelector("#message-input");
const fileInput = document.querySelector("#file-input");
const filePreview = document.querySelector("#file-preview");
const filePreviewName = document.querySelector("#file-preview-name");
const filePreviewSize = document.querySelector("#file-preview-size");
const removeFileButton = document.querySelector("#remove-file");
const uploadStatus = document.querySelector("#upload-status");
const sendButton = document.querySelector("#send-button");

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
  const response = await fetch(`/static/locales/${locale}.json`);
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
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
  chatView.hidden = true;
  loginView.hidden = false;
  loginError.textContent = errorKey ? t(errorKey) : "";
  passwordInput.value = "";
  requestAnimationFrame(() => passwordInput.focus());
}

async function showChat(identity) {
  loginView.hidden = true;
  chatView.hidden = false;
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

function renderMessages() {
  const ordered = [...messageCache.values()].sort((left, right) => left.id - right.id);
  messages.replaceChildren();
  if (!ordered.length) {
    emptyState.hidden = false;
    messages.append(emptyState);
    return;
  }

  let previousSender = null;
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
      previousSender = null;
    }

    const sameSender = previousSender === message.sender_name;
    const article = document.createElement("article");
    article.className = sameSender ? "message grouped" : "message";
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

    if (message.attachment) {
      const attachment = document.createElement("a");
      attachment.className = "attachment";
      attachment.href = `/api/files/${encodeURIComponent(message.attachment.id)}`;
      attachment.innerHTML = '<span class="attachment-icon" aria-hidden="true">📄</span>';
      const copy = document.createElement("span");
      copy.className = "attachment-copy";
      const name = document.createElement("strong");
      name.className = "attachment-name";
      name.textContent = message.attachment.original_name;
      const size = document.createElement("small");
      size.className = "attachment-size";
      size.textContent = formatBytes(message.attachment.size);
      copy.append(name, size);
      attachment.append(copy);
      if (!message.body) attachment.append(createMessageTime(message));
      content.append(attachment);
    }

    article.append(content);
    messages.append(article);
    previousSender = message.sender_name;
    previousDay = day;
  }
}

function appendMessage(message) {
  if (messageCache.has(message.id)) return;
  messageCache.set(message.id, message);
  renderMessages();
}

function scrollToLatest() {
  messages.scrollTop = messages.scrollHeight;
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
  const composerHeight = Math.ceil(messageForm.getBoundingClientRect().height);
  document.documentElement.style.setProperty("--composer-space", `${composerHeight + 40}px`);
}

function updateComposerLayout() {
  const lineHeight = Number.parseFloat(getComputedStyle(messageInput).lineHeight) || 23;
  const hasWrappedText = messageInput.scrollHeight > lineHeight * 1.8;
  messageForm.classList.toggle("expanded", Boolean(pendingFile) || hasWrappedText || !uploadStatus.hidden);
  requestAnimationFrame(syncComposerSpace);
}

function updateSendButton() {
  sendButton.disabled = sending || (!messageInput.value.trim() && !pendingFile);
}

function resizeTextarea() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 180)}px`;
  updateComposerLayout();
  updateSendButton();
}

function setPendingFile(file) {
  if (sending) return;
  if (!file) return;
  pendingFile = file;
  filePreviewName.textContent = file.name;
  filePreviewSize.textContent = formatBytes(file.size);
  filePreview.hidden = false;
  uploadStatus.hidden = true;
  fileInput.value = "";
  resizeTextarea();
}

function clearPendingFile(force = false) {
  if (sending && !force) return;
  pendingFile = null;
  filePreview.hidden = true;
  filePreviewName.textContent = "";
  filePreviewSize.textContent = "";
  fileInput.value = "";
  updateComposerLayout();
  updateSendButton();
}

function setSending(value) {
  sending = value;
  fileInput.disabled = value;
  messageInput.disabled = value;
  removeFileButton.disabled = value;
  dropZone.classList.toggle("sending", value);
  updateSendButton();
}

function uploadCombinedMessage(body, file) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("body", body);
    form.append("file", file);
    const request = new XMLHttpRequest();
    request.open("POST", "/api/files");
    uploadStatus.hidden = false;
    uploadStatus.textContent = t("upload.uploading", { name: file.name });
    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      const progress = Math.round((event.loaded / event.total) * 100);
      uploadStatus.textContent = t("upload.progress", { name: file.name, progress });
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
  const file = pendingFile;
  if (!body && !file) return;

  setSending(true);
  try {
    const message = file
      ? await uploadCombinedMessage(body, file)
      : await api("/api/messages", { method: "POST", body: JSON.stringify({ body }) });
    appendMessage(message);
    messageInput.value = "";
    uploadStatus.hidden = true;
    if (pendingFile === file) clearPendingFile(true);
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
fileInput.addEventListener("change", () => setPendingFile(fileInput.files?.[0]));
removeFileButton.addEventListener("click", () => clearPendingFile());

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
  if (files[0]) setPendingFile(files[0]);
  if (files.length > 1) {
    uploadStatus.hidden = false;
    uploadStatus.textContent = t("upload.singleFile");
  }
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

if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", syncVisualViewport);
  window.visualViewport.addEventListener("scroll", syncVisualViewport);
}
window.addEventListener("resize", syncVisualViewport);
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
