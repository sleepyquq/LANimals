"""生成 LANimals 猫咪图标资产 (PNG 与 Windows ICO)。"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from lanimals.gui.theme import create_cat_logo_image


def generate_icon(assets_dir: Path) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)
    img = create_cat_logo_image(256)

    png_path = assets_dir / "icon.png"
    ico_path = assets_dir / "icon.ico"

    img.save(png_path, format="PNG")
    img.save(ico_path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Generated {png_path} and {ico_path}")


if __name__ == "__main__":
    generate_icon(project_root / "lanimals" / "gui" / "assets")
