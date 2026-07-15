# AGENTS.md

These instructions apply to the entire LANimals repository.

## 1. Product intent

LANimals is a lightweight, local-only LAN group chat. One Windows/Linux/macOS host runs the service; phones, tablets, and computers join through a browser. Do not replace it with Mattermost, Rocket.Chat, a cloud backend, or another large chat platform.

Core product rules:

- One shared room and one shared password; no account registration, channels, or DMs.
- Text, files, and text+file combined messages persist locally across restarts.
- Normal browsers keep a long-lived cute animal identity; incognito sessions use a separate session-only mysterious-animal identity.
- No public internet services, CDN, analytics, advertisements, telemetry, or cloud storage.
- Browser clients must never expose message/file deletion or remote administration.
- Destructive and sensitive administration stays in host-local CLI commands.
- Primary deployment target is a Windows host, but source-run operation must remain cross-platform.

## 2. Stack and source layout

- Python 3.11+
- FastAPI + Uvicorn
- Standard-library `sqlite3`, WAL mode
- WebSocket fan-out in one process
- Native HTML/CSS/JavaScript (no frontend build system)
- Simplified Chinese and English locale JSON files

Important paths:

```text
lanimals/
├── __main__.py       # CLI entrypoint: serve / clear / password / config
├── cli.py            # host-local administration helpers
├── config.py         # TOML, upload-size parsing, scrypt password hashes
├── identity.py       # device/session cookies and animal-name allocation
├── limits.py         # pre-multipart authentication and request-size guard
├── main.py           # FastAPI routes, messages, files, WebSocket
├── realtime.py       # single-process WebSocket hub
├── store.py          # SQLite messages and attachment metadata
└── web/
    ├── index.html
    ├── app.css
    ├── app.js
    └── locales/
        ├── zh-CN.json
        └── en.json

tests/                # pytest suite
data/                 # runtime data; gitignored; never commit
```

Treat `build/`, `*.egg-info/`, `__pycache__/`, wheels, databases, uploads, and runtime config as generated/runtime artifacts. Do not edit generated copies instead of source files.

## 3. Security and administration invariants

Do not weaken these without explicit user approval:

- Passwords are stored only as scrypt hashes; never commit plaintext passwords, cookies, tokens, or credentials.
- Login/session cookies are opaque and HttpOnly/SameSite.
- Persistent and temporary device identities use separate cookies. Incognito login must not overwrite the persistent identity cookie.
- Upload authentication and raw request-size checks happen before Starlette multipart parsing.
- Downloads require authentication, force `Content-Disposition: attachment`, and send `X-Content-Type-Options: nosniff`.
- Render sender names, text, and filenames with `textContent`, not dynamic `innerHTML`.
- The only current `innerHTML` usage is a fixed built-in attachment icon; do not interpolate user input into it.
- Password rotation clears sessions and invalidates already-connected WebSockets.
- There must be no browser DELETE route, hidden admin panel, remote clear API, or webpage clear button.
- `python -m lanimals clear` is host-local and requires the exact confirmation `DELETE ALL`.
- Automatic binding accepts only RFC1918 IPv4 addresses and otherwise falls back to `127.0.0.1`; never silently bind a public/VPN address.
- Production uses one Uvicorn worker because `RealtimeHub` is in-memory. Do not increase workers without adding a cross-process event bus.

## 4. Persistence and concurrency

- Runtime data lives in `data/config.toml`, `data/chat.db`, and `data/uploads/`.
- SQLite uses WAL, `busy_timeout=10000`, foreign keys, and short write transactions.
- Text and attachment metadata must be atomically committed; failed uploads must not leave visible rows or orphaned files.
- Persistent animal allocation uses `BEGIN IMMEDIATE` so simultaneous first logins cannot receive duplicate names.
- The concurrency suite covers mixed text/file metadata writes and simultaneous identity allocation.
- This architecture targets a household or small office, not hundreds of continuously active users.
- When changing database logic, rerun concurrency tests repeatedly and check for `database is locked`, missing rows, duplicate IDs/names, and failed rollback cleanup.

## 5. Animal identity behavior

Persistent identities combine 12 prefixes with 12 animals (144 names). Allocation intentionally rotates both prefix and animal so early devices are diverse, e.g.:

```text
奶油小熊 → 云朵水獭 → 薄荷小兔 → 橘子小猫
```

Existing saved identities must remain stable. Temporary sessions use the fixed mysterious-animal pool and may reuse names across unrelated sessions after the pool cycles.

## 6. Frontend interaction contract

The UI is a warm, lightweight LAN chat—not a full Discord clone.

### Header and messages

- The header stays fixed/sticky with no hard divider line.
- A subtle masked backdrop-blur gradient separates scrolling messages from the header.
- Connection state is only a 10px dot beside `LANimals`: green when connected, gray otherwise. Do not display “已连接/Connected” text; keep status text only in `aria-label`.
- The dot has a 10px gap from the title and is vertically centered.
- Consecutive messages from the same animal show the sender name only on the first message in the run.
- A new local calendar day inserts exactly one date separator before that day’s first message and resets sender grouping.
- Message times are Telegram-like: 9px, low-opacity, and tight to the bubble’s bottom-right corner.
- Short one-line messages keep time inline at the lower right.
- If the rendered body wraps, the body must reclaim the full bubble width and the time must move to a separate bottom row. Determine this from actual rendered height (`updateMessageTimeLayouts`), never character count. Recompute after viewport changes.
- Message ordering/deduplication uses message IDs. WebSocket connects before history load, and opening/reconnecting backfills history.

### Floating composer

- The composer floats over the page; do not restore a separated footer bar or hard divider.
- In true single-line state: add icon, text input, and send icon share one row.
- When the textarea really wraps or a file is attached: content expands upward and add/send icons occupy a bottom action row.
- Textarea height follows rendered content, capped at the current maximum.
- Files can be selected or dragged into the composer.
- Text and one file can be sent as one message.
- Empty/whitespace-only input with no file keeps the send icon gray and disabled. A file alone enables send.
- During upload, replacing/removing/dropping another file is blocked to avoid pending-file races.
- Do not show the configured upload limit permanently in the composer; configuration details belong in a future settings/properties view.
- Mobile composer side gaps are 16px; bottom breathing room is 18px plus safe area and keyboard offset.
- Preserve `interactive-widget=resizes-content`, `visualViewport`, dynamic `--keyboard-offset`, and `ResizeObserver` composer-space measurement.
- Maintain approximately 44px mobile touch targets and a 16px textarea font to avoid iOS input zoom.

### Attachments and responsive constraints

- Mobile attachment width is constrained by `min(520px, calc(100vw - 52px))`.
- `.attachment-copy` must remain shrinkable (`min-width: 0; flex: 1`) so adding a time element cannot make long filenames overflow.
- Long filenames use ellipsis; the document and card must not gain horizontal scrolling.
- Test desktop and mobile separately. A media query alone is not proof of working mobile layout.

## 7. Internationalization

- Do not hard-code visible UI strings in `index.html` or `app.js`.
- Use `data-i18n`, `data-i18n-placeholder`, and ARIA translation keys.
- User-visible generated strings come from:
  - `lanimals/web/locales/zh-CN.json`
  - `lanimals/web/locales/en.json`
- Keep both locale key sets identical.
- Browser language chooses the initial locale; unsupported or failed locale loading falls back to English.
- If adding locale files or nested static assets, ensure `pyproject.toml` package-data includes them and verify the built wheel contents.

## 8. Development workflow

Use test-driven changes:

1. Add or strengthen a regression test and observe it fail.
2. Implement the smallest correct change.
3. Run focused tests.
4. Run the full verification suite.
5. For UI changes, verify in a real browser at both desktop and mobile viewports and inspect the screenshots.
6. Review the staged diff before committing.

Primary commands:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q lanimals tests
node --check lanimals/web/app.js
.venv/bin/python -m pip check
git diff --check
git diff --cached --check
```

Package verification:

```bash
.venv/bin/python -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/lanimals-wheel
```

The current suite baseline is 32 passing tests. A Starlette/httpx deprecation warning is currently known and non-blocking; do not hide new warnings or failures behind it.

For browser verification, useful target viewports are:

```text
mobile:  390 × 844, deviceScaleFactor 2
desktop: 1440 × 900
```

Save generated previews under `/home/ovo/图片/Hermes/`, not in the repository or `/home/ovo` root. Headless Chromium/Puppeteer paths under `/tmp` are ephemeral and may need to be reinstalled.

## 9. Git and delivery

- Repository: `git@github.com:sleepyquq/LANimals.git`
- Branch: `main`
- Do not force-push or rewrite published history.
- Before a push: run the full suite, JS syntax check, staged diff check, and verify the remote commit after push.
- Keep commits focused and descriptive.
- Never commit `data/`, `.env`, credentials, screenshots, preview databases, build output, or temporary browser tooling.

## 10. Host-local commands

```bash
python -m lanimals serve
python -m lanimals password
python -m lanimals clear
python -m lanimals config --max-upload-size 2GB
```

The default port is 8787. First production startup prompts for a password in the host terminal.

## 11. Before declaring work complete

Confirm all of the following:

- The requested behavior works in source, not only in generated `build/` copies.
- Focused and full tests pass.
- No secret/runtime data is staged.
- Desktop and mobile UI are both verified for frontend changes.
- Long text, long unbroken text, long filenames, file-only messages, text+file messages, and empty composer state were considered.
- Test servers and browser processes are stopped.
- Git working tree and remote state are reported accurately.
- Claims in the final response are backed by actual command/browser output.
