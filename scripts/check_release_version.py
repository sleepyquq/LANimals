"""网页手动发布前的版本校验：在花十分钟打包之前挡住填错的版本号。

用法（发布工作流中使用）：
    python scripts/check_release_version.py v0.3.0 --ref refs/heads/main
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VERSION_PATTERN = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


class ReleaseCheckError(Exception):
    """校验失败，消息直接展示在工作流日志里。"""


def project_version(pyproject: Path) -> str:
    with pyproject.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def remote_tags() -> set[str]:
    output = subprocess.run(
        ["git", "ls-remote", "--tags", "origin"], check=True, capture_output=True, text=True
    ).stdout
    tags = set()
    for line in output.splitlines():
        ref = line.split("\t")[-1]
        tags.add(ref.removeprefix("refs/tags/").removesuffix("^{}"))
    return tags


def check_release(version: str, *, ref: str, pyproject: Path, existing_tags: set[str]) -> None:
    if not _VERSION_PATTERN.fullmatch(version):
        raise ReleaseCheckError(f"版本号格式应为 v主.次.补丁（例如 v0.3.0），收到：{version!r}")
    if ref != "refs/heads/main":
        raise ReleaseCheckError(f"只能从 main 分支发布，当前是 {ref}；请在 Run workflow 中选择 main。")
    expected = project_version(pyproject)
    if version.removeprefix("v") != expected:
        raise ReleaseCheckError(
            f"版本号 {version} 与 pyproject.toml 中的 {expected} 不一致；请先把 pyproject.toml 改成 "
            f"{version.removeprefix('v')} 并合并到 main。"
        )
    if version in existing_tags:
        raise ReleaseCheckError(f"标签 {version} 已存在；如需重新发布，请换一个新版本号。")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a manual LANimals release version")
    parser.add_argument("version")
    parser.add_argument("--ref", required=True, help="触发工作流的 git ref，例如 refs/heads/main")
    args = parser.parse_args()
    try:
        check_release(args.version, ref=args.ref, pyproject=PROJECT_ROOT / "pyproject.toml", existing_tags=remote_tags())
    except ReleaseCheckError as error:
        print(f"::error::{error}", flush=True)
        return 1
    print(f"[OK] 将在 main 上发布 {args.version}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
