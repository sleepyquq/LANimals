# LANimals

LANimals 是一个只运行在本地局域网里的轻量共享聊天室。运行服务的电脑保存全部消息和文件，手机、平板及其他电脑只需浏览器。

## 功能

- 单一共享房间与统一群聊密码，无账号注册
- 普通设备使用长期 Cookie 保留可爱动物名称
- 无痕/临时设备使用会话 Cookie 和神秘动物名称
- 文字与任意格式文件可在同一条消息中实时发送，支持点击选择和拖入输入框
- 悬浮式自适应输入气泡：单行时按钮同排，多行/附件时按钮移至底部
- 简体中文与英语界面，前端文案从 `web/locales/*.json` 加载
- 桌面与移动端响应式布局，移动键盘弹出时输入框跟随可视视口上移
- SQLite WAL 消息历史与本地文件跨重启持久化，短写事务支持多设备同时发送
- 网页端没有删除能力
- 仅服务主机命令行可清空消息和文件、改密码和上传上限
- 无 CDN、广告、统计、云存储或外部服务

> LANimals 默认使用普通 HTTP，适合可信任的家庭或办公局域网，不建议直接暴露到公网。

## 环境

- Python 3.11 或更高版本
- Windows、Linux 或 macOS

## Linux / macOS 启动

```bash
cd /path/to/lanimals
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m lanimals
```

终端会打开主机管理菜单，选择“启动聊天室”即可。第一次启动会要求输入并确认群聊密码；密码不回显，`data/config.toml` 只保存 scrypt 哈希。

## Windows 启动

在 PowerShell 中：

```powershell
cd C:\path\to\lanimals
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m lanimals
```

首次出现 Windows Defender 防火墙提示时，只允许在**专用网络**中通信，不要为公用网络开放。

服务启动后终端会显示自动检测到的局域网地址：

```text
访问地址: http://192.168.x.x:8787
```

本机和其他局域网设备都在浏览器打开该地址即可。默认只接受自动检测到的 RFC1918 私有地址（`10.x`、`172.16-31.x`、`192.168.x`）并只监听这一张接口；若找不到私有 LAN 地址，自动退回 `127.0.0.1`，不会绑定公网接口。如主机网络结构特殊，可在本机 `data/config.toml` 中明确设置 `host`。

## 主机本地管理

在保存源码和数据的服务主机上运行：

```bash
python -m lanimals
```

即可通过编号菜单启动聊天室、修改密码、调整上传上限或清空记录。服务正在运行时，建议另开一个终端进入管理菜单；启动服务的终端继续专门显示日志。网页没有管理按钮或删除 API。

原有子命令继续保留，适合脚本和高级用户直接调用。

### 修改单文件上传上限

```bash
python -m lanimals config --max-upload-size 2GB
```

支持 `B`、`KB`、`MB`、`GB`，修改后重启服务生效。也可在主机上编辑 `data/config.toml` 的：

```toml
max_upload_size = "2GB"
```

### 修改群聊密码

```bash
python -m lanimals password
```

然后终端要求输入并确认新密码。修改立即影响运行中的服务，并撤销已有 HTTP 与 WebSocket 会话，所有浏览器需要使用新密码重新进入。

### 清空全部消息和上传文件

建议先停止服务，再运行：

```bash
python -m lanimals clear
```

必须在本地输入 `DELETE ALL` 才会执行。此操作保留 `data/config.toml` 和已分配的长期设备名称。

## 数据目录

```text
data/
├── config.toml    # 主机配置与密码哈希
├── chat.db        # 设备、会话、消息与附件元数据
└── uploads/       # 实际上传文件
```

备份时停止服务并复制整个 `data/`。该目录已被 Git 忽略，不应提交。

## 开发与测试

```bash
.venv/bin/python -m pytest -q
```

项目结构：

```text
lanimals/
├── __main__.py    # serve / clear / password / config
├── config.py      # TOML 配置、大小解析、密码哈希
├── identity.py    # 设备 Cookie、会话、动物名称
├── main.py        # FastAPI、消息、文件和 WebSocket
├── realtime.py    # 在线浏览器实时广播
├── store.py       # SQLite 持久化
└── web/           # 原生 HTML/CSS/JavaScript 与中英文 locale JSON
```

## 当前边界

- 只有一个共享房间，不提供频道、私聊和账号系统。
- SQLite 会串行执行写事务并等待最多 10 秒，适合家庭或小办公室局域网；不定位为数百人持续高并发聊天服务。
- 实时 WebSocket 广播当前使用单个服务进程；不要直接启动多个 Uvicorn worker，除非后续加入跨进程事件总线。
- 不提供消息编辑、逐条删除或网页清空功能。
- 文件按主机磁盘容量保存，不做云端同步、病毒扫描或转码。
- 普通 HTTP 不抵御同一不可信网络中的流量窃听；需要更强安全性时，应在可信反向代理后启用 HTTPS。
