"""桌面打包版的一键升级：只在主机用户点击“检查更新”时访问 GitHub Releases。

流程：
1. ``check_latest`` 读取最新 Release，选出当前平台的安装包。
2. ``prepare_update`` 下载、校验并解压到数据目录下的 ``.update/``，写出升级计划。
3. ``launch_update_helper`` 以“升级助手”模式启动新版程序本身，然后旧版退出。
4. 助手（``apply_update``）等待旧进程退出，备份旧程序文件、复制新文件，失败则回滚，
   最后重新启动程序。``data/`` 目录始终原样保留。

这里不做任何后台轮询或遥测；没有点击就不会联网。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lanimals import __version__

logger = logging.getLogger("lanimals.updater")

GITHUB_REPO = "sleepyquq/LANimals"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
# 升级助手由“新版”程序执行、读取“旧版”写出的 plan.json：
# 以后改动这个参数或 plan.json 字段时，必须继续兼容旧版写出的格式。
APPLY_UPDATE_FLAG = "--apply-update"
UPDATE_DIR_NAME = ".update"
_USER_AGENT = f"LANimals-updater/{__version__}"
_VERSION_PATTERN = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
# 这些名字属于用户数据或升级工作区，替换程序文件时绝不触碰。
_PRESERVED_NAMES = frozenset({"data", UPDATE_DIR_NAME})


class UpdateError(Exception):
    """可直接展示给用户的升级失败原因（code 对应 GUI 文案）。"""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    page_url: str
    asset_name: str | None
    asset_url: str | None
    asset_size: int
    asset_sha256: str | None

    @property
    def is_newer(self) -> bool:
        return parse_version(self.version) > parse_version(__version__)


@dataclass(frozen=True)
class InstallLayout:
    """当前打包版的安装形态。kind 为 ``dir``（Windows/Linux 便携目录）或 ``app``（macOS 包）。"""

    kind: str
    target: Path
    relaunch: Path


def parse_version(text: str) -> tuple[int, int, int]:
    match = _VERSION_PATTERN.fullmatch(text.strip())
    if not match:
        raise UpdateError("badRelease", f"无法识别的版本号：{text!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def asset_name_for_platform(system: str = sys.platform, machine: str | None = None) -> str | None:
    """与 build-release.yml 上传的文件名一一对应；没有对应安装包的平台返回 None。"""
    machine = (machine if machine is not None else platform.machine()).lower()
    if system == "darwin":
        return "LANimals-macos.zip"
    if machine not in {"x86_64", "amd64"}:
        return None
    if system == "win32":
        return "LANimals-windows-x64.zip"
    if system.startswith("linux"):
        return "LANimals-linux-x64.tar.gz"
    return None


def package_root_name(system: str = sys.platform) -> str:
    return "LANimals.app" if system == "darwin" else "LANimals"


def executable_in_package(root: Path, system: str = sys.platform) -> Path:
    if system == "darwin":
        return root / "Contents" / "MacOS" / "LANimals"
    if system == "win32":
        return root / "LANimals.exe"
    return root / "LANimals"


def ssl_context() -> ssl.SSLContext:
    """系统证书（含公司代理自签的根证书）加上随包携带的 certifi 证书。

    打包版里的 Python 在 macOS/Linux 上常常找不到系统证书，certifi 保证能连上 GitHub。
    """
    context = ssl.create_default_context()
    try:
        import certifi

        context.load_verify_locations(cafile=certifi.where())
    except Exception as error:
        logger.debug("加载 certifi 证书失败: %s", error)
    return context


def _open(url: str, *, accept: str, timeout: float):
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": accept})
    return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())


def parse_release(payload: dict, asset_name: str | None) -> ReleaseInfo:
    tag = str(payload.get("tag_name") or "")
    parse_version(tag)
    asset = None
    if asset_name:
        asset = next((item for item in payload.get("assets") or [] if item.get("name") == asset_name), None)
    digest = str((asset or {}).get("digest") or "")
    sha256 = digest.removeprefix("sha256:").lower() if digest.startswith("sha256:") else None
    return ReleaseInfo(
        version=tag if tag.startswith("v") else f"v{tag}",
        page_url=str(payload.get("html_url") or RELEASES_PAGE),
        asset_name=asset_name if asset else None,
        asset_url=str(asset["browser_download_url"]) if asset else None,
        asset_size=int((asset or {}).get("size") or 0),
        asset_sha256=sha256,
    )


def check_latest(timeout: float = 15.0) -> ReleaseInfo:
    try:
        with _open(LATEST_RELEASE_API, accept="application/vnd.github+json", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except UpdateError:
        raise
    except Exception as error:
        raise UpdateError("network", str(error)) from error
    return parse_release(payload, asset_name_for_platform())


def current_layout(
    *,
    frozen: bool | None = None,
    executable: str | None = None,
    system: str = sys.platform,
) -> InstallLayout:
    """确认当前进程是可以原地升级的打包版，并返回要替换的位置。"""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen:
        raise UpdateError("sourceRun")
    exe = Path(executable or sys.executable).resolve()
    if system == "darwin":
        app = exe.parent.parent.parent
        if app.suffix != ".app":
            raise UpdateError("unsupported", f"找不到 .app 包：{exe}")
        if "AppTranslocation" in str(app):
            raise UpdateError("translocated")
        layout = InstallLayout(kind="app", target=app, relaunch=app)
        writable = [app.parent, app]
    else:
        layout = InstallLayout(kind="dir", target=exe.parent, relaunch=exe)
        writable = [exe.parent]
    for path in writable:
        if not os.access(path, os.W_OK):
            raise UpdateError("notWritable", str(path))
    return layout


def update_workspace(data_dir: Path) -> Path:
    return Path(data_dir) / UPDATE_DIR_NAME


def cleanup_workspace(data_dir: Path) -> None:
    """删除上一次升级留下的下载包、备份和临时文件；失败（文件仍被占用）时下次再删。"""
    workspace = update_workspace(data_dir)
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)


def pop_update_result(data_dir: Path) -> dict | None:
    """读取升级助手留下的结果（供新版启动后提示），读取后清理工作区。"""
    result_path = update_workspace(data_dir) / "result.json"
    result = None
    if result_path.exists():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            result = None
    cleanup_workspace(data_dir)
    return result


def _download(release: ReleaseInfo, destination: Path, progress: Callable[[int], None] | None) -> None:
    assert release.asset_url
    digest = hashlib.sha256()
    received = 0
    last_percent = -1
    try:
        with _open(release.asset_url, accept="application/octet-stream", timeout=60) as response, destination.open(
            "wb"
        ) as output:
            total = release.asset_size or int(response.headers.get("Content-Length") or 0)
            while chunk := response.read(1024 * 256):
                output.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if progress and total:
                    percent = min(100, received * 100 // total)
                    if percent != last_percent:
                        last_percent = percent
                        progress(percent)
    except Exception as error:
        raise UpdateError("network", str(error)) from error
    if release.asset_size and received != release.asset_size:
        raise UpdateError("corrupt", f"下载大小 {received} 与 Release 记录的 {release.asset_size} 不一致")
    if release.asset_sha256 and digest.hexdigest() != release.asset_sha256:
        raise UpdateError("corrupt", "SHA-256 校验失败")


def _safe_member_path(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if target != root and root not in target.parents:
        raise UpdateError("corrupt", f"安装包含有越界路径：{name}")
    return target


def extract_package(archive: Path, destination: Path, system: str = sys.platform) -> Path:
    """解压安装包并返回其中的程序根目录（``LANimals/`` 或 ``LANimals.app``）。"""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    try:
        if archive.name.endswith(".tar.gz"):
            with tarfile.open(archive, "r:gz") as bundle:
                for member in bundle.getmembers():
                    _safe_member_path(root, member.name)
                bundle.extractall(root, filter="tar")
        elif system == "darwin":
            # ditto 能保留 .app 内的可执行权限与符号链接，这是 Finder 解压用的同一工具。
            subprocess.run(["/usr/bin/ditto", "-x", "-k", str(archive), str(root)], check=True)
        else:
            with zipfile.ZipFile(archive) as bundle:
                for info in bundle.infolist():
                    target = _safe_member_path(root, info.filename)
                    bundle.extract(info, root)
                    mode = (info.external_attr >> 16) & 0o777
                    if mode and not info.is_dir():
                        os.chmod(target, mode | 0o600)
    except UpdateError:
        raise
    except Exception as error:
        raise UpdateError("corrupt", f"解压失败：{error}") from error
    package = root / package_root_name(system)
    if not executable_in_package(package, system).is_file():
        raise UpdateError("corrupt", f"安装包里没有找到 {package_root_name(system)}")
    return package


def prepare_update(
    release: ReleaseInfo,
    data_dir: Path,
    layout: InstallLayout,
    *,
    progress: Callable[[int], None] | None = None,
    system: str = sys.platform,
) -> Path:
    """下载并解压新版，写出升级计划，返回升级计划文件路径。"""
    if not release.asset_url or not release.asset_name:
        raise UpdateError("noAsset")
    cleanup_workspace(data_dir)
    workspace = update_workspace(data_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    archive = workspace / release.asset_name
    _download(release, archive, progress)
    package = extract_package(archive, workspace / "new", system)
    archive.unlink(missing_ok=True)
    plan = {
        "pid": os.getpid(),
        "version": release.version,
        "kind": layout.kind,
        "source": str(package),
        "target": str(layout.target),
        "relaunch": str(layout.relaunch),
        "backup": str(workspace / "backup"),
        "result": str(workspace / "result.json"),
        "log": str(workspace / "update.log"),
    }
    plan_path = workspace / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan_path


def clean_child_environment() -> dict[str, str]:
    """去掉 PyInstaller 引导程序注入的变量，让被启动的程序像双击一样独立运行。"""
    env = {key: value for key, value in os.environ.items() if not key.startswith(("_PYI", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for name in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        original = env.pop(f"{name}_ORIG", None)
        if original is not None:
            env[name] = original
        else:
            env.pop(name, None)
    return env


def _spawn_detached(command: list[str]) -> None:
    kwargs: dict = {
        "env": clean_child_environment(),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)


def launch_update_helper(plan_path: Path, system: str = sys.platform) -> None:
    """用解压出的新版程序担任升级助手；调用方随后应立即退出当前程序。"""
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    helper = executable_in_package(Path(plan["source"]), system)
    _spawn_detached([str(helper), APPLY_UPDATE_FLAG, str(plan_path)])


def relaunch(path: Path, kind: str, system: str = sys.platform) -> None:
    if system == "darwin" and kind == "app":
        _spawn_detached(["/usr/bin/open", "-n", str(path)])
    else:
        _spawn_detached([str(path)])


def _wait_for_exit(pid: int, timeout: float) -> bool:
    import psutil

    try:
        psutil.Process(pid).wait(timeout=timeout)
    except psutil.NoSuchProcess:
        return True
    except psutil.TimeoutExpired:
        return False
    return True


def _retry(action: Callable[[], None], attempts: int = 20, delay: float = 0.5) -> None:
    """Windows 上杀毒软件或资源管理器可能短暂占用文件，稍等再试。"""
    for attempt in range(attempts):
        try:
            action()
            return
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _copy(source: Path, target: Path) -> None:
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target, follow_symlinks=False)


def replace_program_files(source: Path, target: Path, backup: Path, kind: str) -> None:
    """用 source 替换 target 中的程序文件；任何一步失败都把旧文件放回原处。"""
    backup.mkdir(parents=True, exist_ok=True)
    if kind == "app":
        pairs = [(source, target, backup / target.name)]
    else:
        pairs = [
            (item, target / item.name, backup / item.name)
            for item in sorted(source.iterdir())
            if item.name not in _PRESERVED_NAMES
        ]
    moved: list[tuple[Path, Path]] = []
    copied: list[Path] = []
    try:
        for new_item, old_item, backup_item in pairs:
            if old_item.exists() or old_item.is_symlink():
                _retry(lambda old=old_item, bak=backup_item: shutil.move(str(old), str(bak)))
                moved.append((old_item, backup_item))
            copied.append(old_item)
            _copy(new_item, old_item)
    except Exception:
        logger.exception("替换程序文件失败，开始回滚")
        for path in copied:
            try:
                _remove(path)
            except Exception:
                logger.exception("回滚时删除 %s 失败", path)
        for old_item, backup_item in reversed(moved):
            try:
                shutil.move(str(backup_item), str(old_item))
            except Exception:
                logger.exception("回滚时恢复 %s 失败", old_item)
        raise


def apply_update(plan_path: Path, *, wait_timeout: float = 60.0, do_relaunch: bool = True) -> int:
    """升级助手入口：由新版程序以 ``--apply-update <plan.json>`` 启动。"""
    plan_path = Path(plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    handler = logging.FileHandler(plan["log"], encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    source, target = Path(plan["source"]), Path(plan["target"])
    result: dict = {"version": plan["version"], "ok": False}
    try:
        logger.info("等待旧版进程 %s 退出", plan["pid"])
        if not _wait_for_exit(int(plan["pid"]), wait_timeout):
            raise UpdateError("busy", "旧版程序没有退出")
        replace_program_files(source, target, Path(plan["backup"]), plan["kind"])
        result["ok"] = True
        logger.info("已升级到 %s", plan["version"])
    except Exception as error:
        result["error"] = getattr(error, "code", "failed")
        logger.exception("升级失败，已保留旧版本")
    finally:
        Path(plan["result"]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        logger.removeHandler(handler)
        handler.close()
    if do_relaunch:
        try:
            relaunch(Path(plan["relaunch"]), plan["kind"])
        except Exception as error:
            # 文件已经替换完毕；启动失败时用户手动打开即可，不影响升级结果。
            with open(plan["log"], "a", encoding="utf-8") as log:
                log.write(f"重新启动失败：{error}\n")
    return 0 if result["ok"] else 1
