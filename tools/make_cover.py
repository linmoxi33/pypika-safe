"""Render the pypika-safe social preview card (1280x640)."""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 640
OUT = os.path.join(os.path.dirname(__file__), "assets", "cover.png")

# warm editorial palette: espresso brown + amber gold, danger red, safe green
BG_TOP = (26, 18, 16)
BG_BOT = (42, 30, 25)
PANEL = (36, 26, 22)
PANEL_EDGE = (66, 48, 40)
AMBER = (232, 163, 61)
AMBER_DIM = (168, 116, 44)
CREAM = (242, 232, 220)
MUTED = (160, 139, 122)
DANGER = (214, 96, 82)
SAFE = (120, 168, 112)

FONT_DIR = "C:/Windows/Fonts"
# Consolas instead of Cascadia: Cascadia applies programming ligatures, which turns
# "pypika-safe" into "pypika—safe" and ">>" into a single glyph.
F_MONO = os.path.join(FONT_DIR, "consola.ttf")
F_MONO_BOLD = os.path.join(FONT_DIR, "consolab.ttf")
F_DISPLAY = os.path.join(FONT_DIR, "msyhbd.ttc")
F_BODY = os.path.join(FONT_DIR, "msyh.ttc")


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def vgradient(size, top, bottom) -> Image.Image:
    img = Image.new("RGB", (1, size[1]))
    d = ImageDraw.Draw(img)
    for y in range(size[1]):
        t = y / max(1, size[1] - 1)
        d.point((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return img.resize(size, Image.BILINEAR)


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    img = vgradient((W, H), BG_TOP, BG_BOT)
    d = ImageDraw.Draw(img, "RGBA")

    # subtle warm glow, top-right
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r in range(420, 0, -14):
        alpha = int(16 * (1 - r / 420) ** 2)
        gd.ellipse([W - 180 - r, -120 - r, W - 180 + r, -120 + r], fill=(232, 163, 61, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")

    pad = 64

    # ── eyebrow badge ────────────────────────────────────────────────
    badge_text = "FORK OF KAYAK/PYPIKA 0.51.1  ·  APACHE-2.0"
    bf = font(F_MONO, 15)
    bw = d.textlength(badge_text, font=bf)
    d.rounded_rectangle([pad, 54, pad + bw + 32, 54 + 34], radius=6, outline=AMBER_DIM, width=1)
    d.text((pad + 16, 62), badge_text, font=bf, fill=AMBER)

    # ── title ────────────────────────────────────────────────────────
    # Split the name so the hyphen reads as a deliberate mark rather than a dash,
    # and so "-safe" carries the amber accent that the rest of the card uses.
    title_font = font(F_MONO, 76)
    t1, t2 = "pypika", "-safe"
    d.text((pad, 106), t1, font=title_font, fill=CREAM)
    w1 = d.textlength(t1, font=title_font)
    d.text((pad + w1, 106), t2, font=title_font, fill=AMBER)

    # amber rule under the title
    tw = w1 + d.textlength(t2, font=title_font)
    d.rectangle([pad, 202, pad + tw, 206], fill=AMBER)

    d.text(
        (pad, 226),
        "Dialect-aware SQL literal escaping for PyPika",
        font=font(F_BODY, 27),
        fill=MUTED,
    )

    # ── two panels ───────────────────────────────────────────────────
    panel_top = 286
    panel_h = 214
    gap = 40
    panel_w = (W - pad * 2 - gap) // 2
    left_x = pad
    right_x = pad + panel_w + gap

    def panel(x, title, accent, lines):
        d.rounded_rectangle(
            [x, panel_top, x + panel_w, panel_top + panel_h], radius=10, fill=PANEL, outline=PANEL_EDGE, width=1
        )
        # accent tab on the left edge
        d.rounded_rectangle([x, panel_top, x + 4, panel_top + panel_h], radius=2, fill=accent)
        d.text((x + 26, panel_top + 20), title, font=font(F_MONO, 16), fill=accent)
        y = panel_top + 58
        for text, color, fnt in lines:
            d.text((x + 26, y), text, font=fnt, fill=color)
            y += 28

    mono15 = font(F_MONO, 17)
    mono16 = font(F_MONO, 18)

    panel(
        left_x,
        "upstream 0.51.1",
        DANGER,
        [
            ("SELECT * FROM users", MUTED, mono15),
            ("WHERE name='x\\'' OR 1=1 -- '", DANGER, mono15),
            ("", MUTED, mono15),
            (">> returns every row", DANGER, mono16),
        ],
    )

    panel(
        right_x,
        "pypika-safe",
        SAFE,
        [
            ("SELECT * FROM users", MUTED, mono15),
            ("WHERE name='x\\\\'' OR 1=1 -- '", SAFE, mono15),
            ("", MUTED, mono15),
            (">> returns one literal", SAFE, mono16),
        ],
    )

    # ── bottom stats ─────────────────────────────────────────────────
    stats = [
        ("1175", "tests pass"),
        ("15/15", "properties"),
        ("13/13", "payloads"),
        ("2", "upstream test lines changed"),
    ]
    x = pad
    y_num = 548
    num_font = font(F_MONO_BOLD, 27)
    lbl_font = font(F_BODY, 15)
    for num, label in stats:
        d.text((x, y_num), num, font=num_font, fill=AMBER)
        d.text((x, y_num + 34), label, font=lbl_font, fill=MUTED)
        x += max(d.textlength(num, font=num_font), d.textlength(label, font=lbl_font)) + 52

    img.save(OUT, "PNG", optimize=True)
    print("wrote", OUT, img.size)


if __name__ == "__main__":
    main()
