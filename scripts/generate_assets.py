#!/usr/bin/env python3
"""Generate marketing screenshots and demo GIF for Dot."""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import imageio

OUT = Path(os.environ.get("DOT_PROJECT", "/mnt/c/dot-context-engine-new")) / "docs" / "assets" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

# Field Notes theme (light)
PAPER = "#f4efe4"
PAPER2 = "#faf6ec"
PAPER_EDGE = "#e7dfcd"
INK = "#1f1b16"
INK2 = "#6b6357"
INK3 = "#9a9384"
RULE = "#e7dfcd"
VIOLET = "#6a4ff0"
VIOLET_WASH = "#ece8fd"
TERRA = "#c8612f"
GREEN = "#3f7d4f"

FONT_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_SANS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def get_fonts():
    """Find usable fonts."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    sans = next((p for p in candidates if os.path.exists(p)), candidates[0])
    sans_bold = sans.replace("Sans.ttf", "Sans-Bold.ttf").replace("Regular", "Bold")
    if not os.path.exists(sans_bold):
        sans_bold = sans
    mono_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]
    mono = next((p for p in mono_candidates if os.path.exists(p)), mono_candidates[0])
    return sans, sans_bold, mono


SANS, SANS_BOLD, MONO = get_fonts()


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    path = MONO if mono else (SANS_BOLD if bold else SANS)
    return ImageFont.truetype(path, size)


def rounded_rect(draw, xy, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_card(draw, xy, fill=PAPER2):
    rounded_rect(draw, xy, radius=6, fill=fill, outline=PAPER_EDGE, width=1)


def make_cli_status() -> Image.Image:
    w, h = 800, 460
    img = Image.new("RGB", (w, h), PAPER)
    draw = ImageDraw.Draw(img)

    # subtle grid
    for y in range(0, h, 28):
        draw.line([(0, y), (w, y)], fill=RULE, width=1)
    for x in range(0, w, 28):
        draw.line([(x, 0), (x, h)], fill=RULE, width=1)

    # terminal window
    rounded_rect(draw, (40, 40, w - 40, h - 40), radius=10, fill=INK, outline=PAPER_EDGE, width=2)
    # title bar
    draw.rounded_rectangle((40, 40, w - 40, 74), radius=10, fill="#2c2824")
    draw.ellipse((58, 52, 72, 66), fill="#ff5f57")
    draw.ellipse((80, 52, 94, 66), fill="#febc2e")
    draw.ellipse((102, 52, 116, 66), fill="#28c840")
    draw.text((140, 50), "aryan@wsl:~/dot-context-engine", font=font(13), fill=INK3)

    y = 96
    draw.text((60, y), "$ dot status", font=font(15, mono=True), fill="#e9e3d6")
    y += 34

    # title
    draw.text((60, y), "Dot - dot-context-engine", font=font(18, bold=True), fill=VIOLET)
    y += 40

    rows = [
        ("daemon", "running (http://127.0.0.1:7337)", GREEN),
        ("project root", "/home/aryan/dot-context-engine", "#e9e3d6"),
        ("files indexed", "84", "#e9e3d6"),
        ("chunks", "541", "#e9e3d6"),
        ("memories", "12", "#e9e3d6"),
        ("vector store", "sqlite", "#e9e3d6"),
        ("embeddings", "feature-hashing", "#e9e3d6"),
    ]
    for label, value, color in rows:
        draw.text((60, y), label, font=font(14, mono=True), fill=INK3)
        draw.text((230, y), value, font=font(14, mono=True), fill=color)
        y += 26

    y += 16
    draw.text((60, y), "Top contexts", font=font(15, bold=True), fill=VIOLET)
    y += 28
    for item in ["auth middleware", "release workflow", "conversation capture"]:
        draw.text((60, y), f"  - {item}", font=font(14, mono=True), fill="#e9e3d6")
        y += 24

    y += 20
    draw.text((60, y), "● ready", font=font(14, mono=True), fill=GREEN)

    return img


def make_dashboard() -> Image.Image:
    w, h = 900, 560
    img = Image.new("RGB", (w, h), PAPER)
    draw = ImageDraw.Draw(img)

    # grid
    for y in range(0, h, 28):
        draw.line([(0, y), (w, y)], fill=RULE, width=1)
    for x in range(0, w, 28):
        draw.line([(x, 0), (x, h)], fill=RULE, width=1)

    # header
    draw.rectangle((0, 0, w, 64), fill=PAPER2)
    draw.line((0, 64, w, 64), fill=PAPER_EDGE, width=1)
    draw.text((30, 22), "● Dot Dashboard", font=font(22, bold=True), fill=INK)
    draw.text((780, 28), "v0.1.0-alpha", font=font(13), fill=INK3)

    # stats cards
    cards = [
        (30, 90, 200, 90, "Files indexed", "1,247"),
        (250, 90, 200, 90, "Chunks", "8,932"),
        (470, 90, 200, 90, "Memories", "42"),
        (690, 90, 170, 90, "Status", "Healthy", GREEN),
    ]
    for x, y, cw, ch, label, value, *color in cards:
        color = color[0] if color else INK
        draw_card(draw, (x, y, x + cw, y + ch), fill=PAPER2)
        draw.text((x + 18, y + 18), label, font=font(13), fill=INK2)
        draw.text((x + 18, y + 44), value, font=font(28, bold=True), fill=color)

    # search box
    draw_card(draw, (30, 200, w - 30, 256), fill=PAPER2)
    rounded_rect(draw, (50, 218, w - 50, 260), radius=6, fill=PAPER, outline=PAPER_EDGE, width=1)
    draw.text((66, 228), "how does auth middleware work?", font=font(15), fill=INK)

    # results
    draw.text((50, 280), "Top matches", font=font(16, bold=True), fill=INK)
    y = 310
    results = [
        ("dot/integrations/claude.py", "Claude Code SessionStart hook injects context via CLAUDE.md."),
        ("dot/context/assembler.py", "Ranks chunks by similarity, file proximity, and recency."),
        ("Decision", "Use JWT with refresh tokens for auth middleware"),
    ]
    for title, desc in results:
        rounded_rect(draw, (50, y, w - 50, y + 64), radius=6, fill=PAPER, outline=PAPER_EDGE, width=1)
        draw.text((66, y + 12), title, font=font(13, bold=True), fill=VIOLET)
        draw.text((66, y + 36), desc, font=font(12), fill=INK2)
        y += 76

    return img


def make_extension() -> Image.Image:
    w, h = 340, 520
    img = Image.new("RGB", (w, h), "#252526")
    draw = ImageDraw.Draw(img)

    # sidebar header
    draw.rectangle((0, 0, w, 48), fill="#333333")
    draw.text((16, 16), "What Dot Knows", font=font(15, bold=True), fill="#e9e3d6")

    y = 64
    # active file
    draw.text((16, y), "Current file", font=font(12), fill="#858585")
    y += 22
    draw.text((16, y), "dot/daemon.py", font=font(13, mono=True), fill=VIOLET)
    y += 40

    # decisions section
    draw.text((16, y), "Decisions", font=font(13, bold=True), fill="#e9e3d6")
    y += 26
    decisions = [
        "Use uvicorn for the REST API",
        "Store memories in SQLite + ChromaDB",
        "Degrade gracefully without ML extras",
    ]
    for d in decisions:
        rounded_rect(draw, (16, y, w - 16, y + 44), radius=4, fill="#333333", outline="#3c3c3c", width=1)
        draw.text((28, y + 8), "●", font=font(10), fill=TERRA)
        # wrap text roughly
        draw.text((44, y + 8), d[:36], font=font(12), fill="#e9e3d6")
        y += 54

    # related code section
    y += 16
    draw.text((16, y), "Related code", font=font(13, bold=True), fill="#e9e3d6")
    y += 26
    code_items = [
        ("dot/daemon.py:247", "shutdown handler"),
        ("dot/api.py:112", "/context endpoint"),
    ]
    for path, desc in code_items:
        draw.text((16, y), path, font=font(12, mono=True), fill=VIOLET)
        y += 18
        draw.text((16, y), desc, font=font(11), fill="#858585")
        y += 28

    # footer buttons
    y = h - 48
    draw.rectangle((0, y, w, h), fill="#333333")
    draw.text((16, y + 15), "● Dot connected", font=font(12), fill=GREEN)

    return img


def make_demo_frame(t: float) -> Image.Image:
    """Animated demo frame at time t (0..1)."""
    w, h = 880, 420
    img = Image.new("RGB", (w, h), PAPER)
    draw = ImageDraw.Draw(img)

    # grid
    for y in range(0, h, 28):
        draw.line([(0, y), (w, y)], fill=RULE, width=1)
    for x in range(0, w, 28):
        draw.line([(x, 0), (x, h)], fill=RULE, width=1)

    # terminal
    rounded_rect(draw, (30, 30, w - 30, h - 30), radius=10, fill=INK, outline=PAPER_EDGE, width=2)
    draw.rounded_rectangle((30, 30, w - 30, 64), radius=10, fill="#2c2824")

    y = 84
    line_height = 26

    commands = [
        ("$ dot init", 0.0),
        ("✓ initialized .dot/", 0.12),
        ("$ dot daemon start", 0.24),
        ("✓ daemon running on 127.0.0.1:7337", 0.36),
        ("$ dot ask \"how does auth work\"", 0.48),
        ("", 0.60),
        ("## Relevant decisions", 0.68),
        ("- Use JWT with refresh tokens", 0.76),
        ("- Auth endpoints get stricter limits", 0.84),
    ]

    for text, trigger in commands:
        if t >= trigger:
            if text.startswith("$"):
                draw.text((52, y), "$", font=font(14, mono=True), fill=VIOLET)
                draw.text((72, y), text[2:], font=font(14, mono=True), fill="#e9e3d6")
            elif text.startswith("✓"):
                draw.text((52, y), "✓", font=font(14, mono=True), fill=GREEN)
                draw.text((72, y), text[2:], font=font(14, mono=True), fill="#b8b0e6")
            elif text.startswith("##"):
                draw.text((52, y), text, font=font(15, bold=True), fill=VIOLET)
            elif text.startswith("-"):
                draw.text((52, y), text, font=font(14, mono=True), fill="#e9e3d6")
            else:
                draw.text((52, y), text, font=font(14, mono=True), fill="#e9e3d6")
            y += line_height

    # cursor blink
    if int(t * 8) % 2 == 0:
        cursor_y = y
        draw.rectangle((52, cursor_y, 64, cursor_y + 18), fill=VIOLET)

    return img


def save(name: str, img: Image.Image):
    path = OUT / name
    img.save(path)
    print("Saved", path)


def main():
    save("screenshot-cli.png", make_cli_status())
    save("screenshot-dashboard.png", make_dashboard())
    save("screenshot-extension.png", make_extension())

    frames = []
    for i in range(60):
        t = i / 59.0
        frames.append(make_demo_frame(t))
    gif_path = OUT / "demo.gif"
    imageio.mimsave(gif_path, [f.convert("P", palette=Image.ADAPTIVE) for f in frames], duration=80, loop=0)
    print("Saved", gif_path)


if __name__ == "__main__":
    main()
