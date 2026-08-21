"""LANimals GUI 主题配置与现代字体系统。

支持自动跟随系统的浅色与深色模式，视觉风格与 Web 聊天界面保持一致的暖色质感。
提供跨平台自适应的高清无衬线字体体系与纯矢量图标生成。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Literal
from PIL import Image, ImageDraw

# ==========================================
# 1. 调色板 (深浅二元组 (Light, Dark))
# ==========================================

# 页面底色与纯净背景
BG_COLOR = ("#faf6ee", "#181614")
CARD_BG = ("#ffffff", "#23201c")
CARD_BORDER = ("#ebdcc7", "#3b342b")

# 文字颜色
TEXT_MAIN = ("#2c2520", "#f6f1eb")
TEXT_MUTED = ("#82756a", "#a89c91")
TEXT_SUBTLE = ("#a99c90", "#73685e")

# 蓝色超链接颜色
LINK_NORMAL = ("#5c534a", "#a89c91")
LINK_HOVER = ("#2563eb", "#60a5fa")

# 齿轮图标颜色
GEAR_COLOR = ("#786c60", "#a3978b")
GEAR_HOVER = ("#2c2520", "#f6f1eb")

# 品牌活力橙 (主按钮)
ACCENT_ORANGE = ("#f08c35", "#f08c35")
ACCENT_ORANGE_HOVER = ("#d9751e", "#e07e24")

# 辅助浅色按钮 / 次要操作
SECONDARY_BTN = ("#f4ebd9", "#302b25")
SECONDARY_BTN_HOVER = ("#e8dcc6", "#3f3830")
SECONDARY_BTN_TEXT = ("#5c4a38", "#dfd3c4")
TOP_CONTROL_HOVER = ("#eee4d6", "#39332c")

# 状态指示 (与 Web 端 10px 状态点一致)
STATUS_GREEN = "#55c46b"
STATUS_GRAY = "#b2a89f"

# 危险警示操作
DANGER_RED = ("#c62828", "#ef5350")
DANGER_RED_HOVER = ("#b71c1c", "#e53935")
DANGER_BG = ("#fdeeed", "#341f1e")

ENTRY_BG = ("#fdfbf7", "#2b2722")
ENTRY_BORDER = ("#e5d7c3", "#423b32")


# ==========================================
# 2. 现代跨平台字体系统 (Typography)
# ==========================================

def _detect_best_font_family() -> str:
    if sys.platform == "win32":
        return "Microsoft YaHei UI"
    elif sys.platform == "darwin":
        return "PingFang SC"
    else:
        return "Noto Sans CJK SC"


FONT_FAMILY = _detect_best_font_family()
MONO_FONT_FAMILY = "Consolas" if sys.platform == "win32" else "Menlo"


def font_main(size: int = 12, weight: Literal["normal", "bold"] = "normal") -> tuple[str, int, str]:
    return (FONT_FAMILY, size, weight)


def font_mono(size: int = 11, weight: Literal["normal", "bold"] = "normal") -> tuple[str, int, str]:
    return (MONO_FONT_FAMILY, size, weight)


# 常用预设字阶
FONT_HERO = font_main(15, "bold")      # 顶部 Brand 标题
FONT_TITLE = font_main(14, "bold")     # 分组卡片标题
FONT_BODY = font_main(12, "normal")    # 正文/主要文本
FONT_BODY_BOLD = font_main(12, "bold") # 按钮/重点操作
FONT_CAPTION = font_main(11, "normal") # 副文本/说明
FONT_SMALL = font_main(10, "normal")   # 极小标签
FONT_LINK = font_mono(12, "normal")    # 访问地址链接字体


# ==========================================
# 3. 矢量图标绘制 (Cat, Gear, Minimize, Close)
# ==========================================

def create_cat_logo_image(size: int = 64) -> Image.Image:
    """绘制与 Web 端一致的暖橙小猫 Logo 图标（8x 超采样确保小尺寸锐利清晰）。"""
    scale = 8
    img_size = size * scale
    img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = img_size * 0.08
    cx, cy = img_size / 2, img_size / 2
    r = (img_size - 2 * pad) / 2

    # 圆形暖橙底
    draw.ellipse([pad, pad, img_size - pad, img_size - pad], fill="#f6a84b")

    # 左耳
    draw.polygon([
        (cx - r * 0.65, cy - r * 0.1),
        (cx - r * 0.8, cy - r * 0.75),
        (cx - r * 0.25, cy - r * 0.55),
    ], fill="#d9751e")

    # 右耳
    draw.polygon([
        (cx + r * 0.65, cy - r * 0.1),
        (cx + r * 0.8, cy - r * 0.75),
        (cx + r * 0.25, cy - r * 0.55),
    ], fill="#d9751e")

    # 头部主体
    draw.ellipse([cx - r * 0.68, cy - r * 0.5, cx + r * 0.68, cy + r * 0.55], fill="#fedb9b")

    # 眼睛
    eye_r = r * 0.11
    draw.ellipse([cx - r * 0.35, cy - r * 0.08, cx - r * 0.35 + eye_r * 2, cy - r * 0.08 + eye_r * 2], fill="#3d2a1d")
    draw.ellipse([cx + r * 0.35 - eye_r * 2, cy - r * 0.08, cx + r * 0.35, cy - r * 0.08 + eye_r * 2], fill="#3d2a1d")

    # 鼻子与嘴巴
    draw.polygon([
        (cx - r * 0.08, cy + r * 0.12),
        (cx + r * 0.08, cy + r * 0.12),
        (cx, cy + r * 0.22),
    ], fill="#e26d5c")

    # 脸颊红晕
    draw.ellipse([cx - r * 0.55, cy + r * 0.1, cx - r * 0.35, cy + r * 0.25], fill="#f9b282")
    draw.ellipse([cx + r * 0.35, cy + r * 0.1, cx + r * 0.55, cy + r * 0.25], fill="#f9b282")

    return img.resize((size, size), Image.Resampling.LANCZOS)


def load_app_icon_image(size: int) -> Image.Image:
    """从窗口/任务栏的同一张品牌资源加载图标，缺失时才回退到矢量绘制。"""
    asset_path = Path(__file__).resolve().parent / "assets" / "icon.png"
    try:
        with Image.open(asset_path) as source:
            return source.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    except (OSError, ValueError):
        # 源码开发或资源损坏时仍可启动；正式包始终携带该资源。
        return create_cat_logo_image(size)


def create_gear_image(size: int = 16, color: str = "#82756a") -> Image.Image:
    """绘制现代扁平、线条规整的标准设置齿轮（8 个方平机械齿 + 中间通透轴孔，绝不像太阳）。"""
    scale = 4
    img_size = size * scale
    img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = img_size / 2, img_size / 2
    r_outer = img_size * 0.44   # 齿顶圆半径
    r_root = img_size * 0.33    # 齿根圆半径
    r_hole = img_size * 0.15    # 中心通透正圆孔半径
    teeth_count = 8             # 8 个标准机械齿

    # 1. 绘制齿根圆主体
    draw.ellipse([cx - r_root, cy - r_root, cx + r_root, cy + r_root], fill=color)

    # 2. 绘制 8 个标准平顶方齿（平整有力，绝非尖芒）
    tooth_half_angle = (2 * math.pi / teeth_count) * 0.22  # 齿宽适中
    for i in range(teeth_count):
        mid_angle = i * (2 * math.pi / teeth_count)
        a1 = mid_angle - tooth_half_angle
        a2 = mid_angle + tooth_half_angle

        p1 = (cx + math.cos(a1) * (r_root - 1), cy + math.sin(a1) * (r_root - 1))
        p2 = (cx + math.cos(a1) * r_outer, cy + math.sin(a1) * r_outer)
        p3 = (cx + math.cos(a2) * r_outer, cy + math.sin(a2) * r_outer)
        p4 = (cx + math.cos(a2) * (r_root - 1), cy + math.sin(a2) * (r_root - 1))

        draw.polygon([p1, p2, p3, p4], fill=color)

    # 3. 挖出中心正圆通透轴孔
    draw.ellipse([cx - r_hole, cy - r_hole, cx + r_hole, cy + r_hole], fill=(0, 0, 0, 0))

    return img.resize((size, size), Image.Resampling.LANCZOS)


def create_minimize_icon(size: int = 12, color: str = "#82756a", thickness: int = 2) -> Image.Image:
    """矢量绘制高清最小化横线图标（绝不依赖系统字体符号）。"""
    scale = 4
    img_size = size * scale
    img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad_x = img_size * 0.15
    cy = img_size * 0.55
    h = thickness * scale
    draw.rounded_rectangle([pad_x, cy - h / 2, img_size - pad_x, cy + h / 2], radius=h // 2, fill=color)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def create_close_icon(size: int = 12, color: str = "#82756a", thickness: int = 2) -> Image.Image:
    """矢量绘制高清关闭 X 图标（绝不依赖系统字体符号，无方框乱码）。"""
    scale = 4
    img_size = size * scale
    img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = img_size * 0.22
    line_w = int(thickness * scale)

    # 绘制两条斜线
    draw.line([(pad, pad), (img_size - pad, img_size - pad)], fill=color, width=line_w)
    draw.line([(pad, img_size - pad), (img_size - pad, pad)], fill=color, width=line_w)

    return img.resize((size, size), Image.Resampling.LANCZOS)
