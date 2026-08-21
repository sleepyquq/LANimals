"""原生 GUI 的轻量缓动函数。"""

from __future__ import annotations


def ease_out_cubic(progress: float) -> float:
    """将零到一的进度转换为先快后慢的自然过渡。"""
    bounded_progress = max(0.0, min(float(progress), 1.0))
    return 1.0 - (1.0 - bounded_progress) ** 3
