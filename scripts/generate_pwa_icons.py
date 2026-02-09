#!/usr/bin/env python3
"""生成 PWA 所需的应用图标 (192x192 和 512x512)"""

import os
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("请先安装 Pillow: pip install Pillow")
    exit(1)

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "frontend" / "icons"

def create_icon(size: int) -> Image.Image:
    """创建投资追踪器App图标 - 简约图表风格"""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # 主色: 暖琥珀色 #E8A317
    primary = (232, 163, 23, 255)
    # 辅助色: 深琥珀
    secondary = (199, 138, 18, 230)
    
    # 绘制简约上升折线图
    margin = size // 5
    w, h = size - 2 * margin, size - 2 * margin
    
    # 折线路径 (模拟上涨趋势)
    points = [
        (margin, margin + int(h * 0.75)),
        (margin + int(w * 0.25), margin + int(h * 0.6)),
        (margin + int(w * 0.5), margin + int(h * 0.5)),
        (margin + int(w * 0.75), margin + int(h * 0.3)),
        (margin + w, margin + int(h * 0.15)),
    ]
    
    # 画线宽
    line_width = max(2, size // 48)
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=primary, width=line_width)
    
    # 画端点圆
    dot_r = max(2, size // 32)
    for x, y in points:
        draw.ellipse([x - dot_r, y - dot_r, x + dot_r, y + dot_r], 
                     fill=secondary, outline=primary)
    
    return img

def main():
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    
    for sz in (192, 512):
        icon = create_icon(sz)
        path = ICONS_DIR / f"icon-{sz}.png"
        icon.save(path, "PNG")
        print(f"已生成: {path}")

if __name__ == "__main__":
    main()
