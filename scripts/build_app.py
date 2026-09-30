"""LANimals 跨平台一键打包脚本 (PyInstaller)。

支持 Windows (.exe / 便携绿色目录)、macOS (.app) 和 Linux (独立二进制包)。
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="LANimals build tool")
    parser.add_argument(
        "--mode",
        choices=["onedir", "onefile"],
        default="onedir",
        help="打包模式：onedir (便携绿色文件夹，秒开推荐) 或 onefile (单文件版)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    print("=== [1/4] 生成高分辨率图标资产 ===")
    from scripts.generate_assets import generate_icon

    assets_dir = project_root / "lanimals" / "gui" / "assets"
    generate_icon(assets_dir)

    print(f"\n=== [2/4] 配置 PyInstaller 打包参数 (平台: {platform.system()}) ===")
    path_sep = ";" if sys.platform == "win32" else ":"

    # 包含 Web 静态前端资源与 GUI 图标
    web_data = f"lanimals/web{path_sep}lanimals/web"
    assets_data = f"lanimals/gui/assets{path_sep}lanimals/gui/assets"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=LANimals",
        "--noconsole",
        "--clean",
        "--noconfirm",
        f"--add-data={web_data}",
        f"--add-data={assets_data}",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
    ]

    if args.mode == "onefile":
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    if sys.platform == "win32":
        ico_file = assets_dir / "icon.ico"
        if ico_file.exists():
            cmd.append(f"--icon={ico_file}")
    elif sys.platform == "darwin":
        png_file = assets_dir / "icon.png"
        if png_file.exists():
            cmd.append(f"--icon={png_file}")

    cmd.append("lanimals/__main__.py")

    print("执行命令:", " ".join(cmd))
    print("\n=== [3/4] 开始构建打包 ===")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("❌ 打包构建失败！", file=sys.stderr)
        return result.returncode

    print("\n=== [4/4] 整理输出产物 ===")
    dist_dir = project_root / "dist"
    if args.mode == "onedir":
        # macOS 的 --windowed onedir 产物是 .app 包；Windows/Linux 才是同名目录。
        app_dist = dist_dir / ("LANimals.app" if sys.platform == "darwin" else "LANimals")
        if app_dist.exists():
            # 拷贝说明文档
            documentation_dir = app_dist / "Contents" / "Resources" if sys.platform == "darwin" else app_dist
            for doc in ["README.zh-CN.md", "README.md"]:
                doc_path = project_root / doc
                if doc_path.exists():
                    shutil.copy2(doc_path, documentation_dir / doc)
            print(f"[OK] 便携绿色版构建完成！目录位置: {app_dist.resolve()}")
            if sys.platform == "win32":
                print(f"[Run] 双击运行: {app_dist / 'LANimals.exe'}")
    else:
        print(f"[OK] 单文件版构建完成！产物位置: {dist_dir.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
