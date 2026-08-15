"""生成 app.ico 图标（纯 Python 实现，无第三方依赖）。

绘制内容：暖纸色圆角方块底 + 近黑描边 + 包豪斯三原色几何图形（红圆、黄三角、蓝方块）。
输出标准 ICO 文件，包含 16/32/48/64/128/256 多个尺寸（BMP 格式条目）。
"""
from __future__ import annotations

import struct
import sys

BG = (244, 241, 234, 255)      # 暖纸色底
INK = (27, 27, 27, 255)        # 近黑描边
RED = (210, 38, 48, 255)       # 包豪斯红（圆）
YELLOW = (242, 181, 0, 255)    # 包豪斯黄（三角）
BLUE = (30, 90, 168, 255)      # 包豪斯蓝（方块）


def in_rounded_rect(u: float, v: float, margin: float, radius: float) -> bool:
    cx = min(max(u, margin + radius), 1 - margin - radius)
    cy = min(max(v, margin + radius), 1 - margin - radius)
    return (u - cx) ** 2 + (v - cy) ** 2 <= radius * radius


def shape_at(u: float, v: float):
    """包豪斯三原色几何构图：红圆（左）、黄三角（中）、蓝方块（右）。"""
    # 红圆：圆心 (0.28, 0.52)，半径 0.16
    if (u - 0.28) ** 2 + (v - 0.52) ** 2 <= 0.16 ** 2:
        return RED
    # 黄三角：顶点 (0.50, 0.30)，底边 y=0.68（半宽线性增至 0.14）
    if 0.30 <= v <= 0.68:
        half = (v - 0.30) / (0.68 - 0.30) * 0.14
        if abs(u - 0.50) <= half:
            return YELLOW
    # 蓝方块：中心 (0.74, 0.52)，半边长 0.115
    if abs(u - 0.74) <= 0.115 and abs(v - 0.52) <= 0.115:
        return BLUE
    return None


def pixel(u: float, v: float) -> tuple[int, int, int, int]:
    if not in_rounded_rect(u, v, margin=0.03, radius=0.22):
        return (0, 0, 0, 0)  # 透明
    color = shape_at(u, v)
    if color is not None:
        return color
    # 近黑描边：外轮廓向内的一圈环带
    if not in_rounded_rect(u, v, margin=0.065, radius=0.185):
        return INK
    return BG


def render(size: int) -> list[list[tuple[int, int, int, int]]]:
    return [[pixel(x / size, y / size) for x in range(size)] for y in range(size)]


def build_bmp_entry(rows) -> bytes:
    """把像素行打包成 ICO 的 BMP 条目（32bpp + AND 掩码）。"""
    size = len(rows)
    xor = bytearray()
    for row in reversed(rows):  # BMP 行序：自下而上
        for r, g, b, a in row:
            xor += bytes((b, g, r, a))
    and_mask = bytearray()
    for row in reversed(rows):
        acc: list[int] = []
        bits = 0
        for i, (_, _, _, a) in enumerate(row):
            if a < 128:  # 透明像素置位
                bits |= 1 << (7 - i % 8)
            if i % 8 == 7:
                acc.append(bits)
                bits = 0
        while len(acc) % 4:  # 每行补齐到 4 字节
            acc.append(0)
        and_mask += bytes(acc)
    header = struct.pack(
        "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(xor) + len(and_mask), 0, 0, 0, 0
    )
    return header + bytes(xor) + bytes(and_mask)


def main() -> None:
    sizes = (16, 32, 48, 64, 128, 256)
    images = [(s, build_bmp_entry(render(s))) for s in sizes]
    data = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = bytearray()
    for s, blob in images:
        b = 0 if s == 256 else s  # 256 在 ICO 中用 0 表示
        entries += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    data += bytes(entries)
    for _, blob in images:
        data += blob
    out = "app.ico" if len(sys.argv) < 2 else sys.argv[1]
    with open(out, "wb") as fh:
        fh.write(data)
    print(f"已生成 {out}（{len(images)} 个尺寸，{len(data)} 字节）")


if __name__ == "__main__":
    main()
