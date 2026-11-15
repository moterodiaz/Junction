"""Make macbeth_dagger.png, the picture the canned demo card shows (backend/app/demo.py).

    python backend/app/demo_assets/make_dagger.py            # draw a placeholder offline (needs Pillow)
    GEMINI_API_KEY=... python backend/app/demo_assets/make_dagger.py --gemini   # the real thing

The lens adds light, so black is see-through: both modes make a bright subject on pure black.
Run it from the repo root. Either way it overwrites macbeth_dagger.png next to this file.
"""

from __future__ import annotations

import asyncio
import math
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "macbeth_dagger.png"
SIZE = 768

PROMPT = (
    "A single dagger floating in mid-air in the dark, blade pointing up and away, handle turned toward the "
    "viewer as if offered to a hand. Spectral pale light, a faint ghostly aura around it, a few drops of "
    "blood on the blade. Eerie and still, Shakespeare's Macbeth, Act 2 Scene 1."
)


def placeholder() -> bytes:
    from io import BytesIO

    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    angle = math.radians(-50)  # blade points up and to the right, handle toward the lower left
    d = (math.cos(angle), math.sin(angle))
    n = (-d[1], d[0])
    centre = SIZE / 2

    def pt(u: float, v: float) -> tuple[float, float]:
        u -= 280  # the dagger runs from u=0 (pommel) to u=560 (tip); centre it
        return (centre + u * d[0] + v * n[0], centre + u * d[1] + v * n[1])

    def draw_dagger(canvas: Image.Image, blade: tuple[int, int, int], metal: tuple[int, int, int]) -> None:
        g = ImageDraw.Draw(canvas)
        g.polygon([pt(170, -34), pt(560, 0), pt(170, 34)], fill=blade)  # blade
        g.line([pt(185, 0), pt(470, 0)], fill=(150, 170, 220), width=4)  # fuller
        g.polygon([pt(150, -78), pt(172, -78), pt(172, 78), pt(150, 78)], fill=metal)  # crossguard
        g.polygon([pt(22, -14), pt(150, -16), pt(150, 16), pt(22, 14)], fill=metal)  # grip
        for u in range(40, 146, 18):
            g.line([pt(u, -15), pt(u + 8, 15)], fill=(120, 80, 20), width=3)  # binding
        x, y = pt(10, 0)
        g.ellipse([x - 24, y - 24, x + 24, y + 24], fill=metal)  # pommel

    shape = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    draw_dagger(shape, (255, 255, 255), (255, 255, 255))
    silhouette = shape.convert("L")
    aura = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    for radius, colour in ((38, (110, 130, 255)), (14, (200, 215, 255))):
        glow = silhouette.filter(ImageFilter.GaussianBlur(radius))
        aura = ImageChops.add(aura, Image.merge("RGB", [glow.point(lambda p, c=c: p * c // 255) for c in colour]))

    image = aura
    draw_dagger(image, (238, 244, 255), (255, 205, 90))
    g = ImageDraw.Draw(image)
    for u, v in ((330, 6), (400, -4), (455, 3), (300, -10)):  # blood on the blade
        x, y = pt(u, v)
        g.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(255, 70, 70))
    rng = random.Random(5)  # a few motes of light, the same ones every run
    for _ in range(70):
        x, y, r = rng.uniform(0, SIZE), rng.uniform(0, SIZE), rng.uniform(1, 3)
        g.ellipse([x - r, y - r, x + r, y + r], fill=(220, 225, 255))

    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def gemini() -> bytes:
    sys.path.insert(0, str(HERE.parents[1]))  # backend/, for the ai package
    from ai.image import DEFAULT_MODEL_IMAGE, GeminiImageClient, format_display_prompt

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        sys.exit("Set GEMINI_API_KEY (and pay-as-you-go billing, which image models need).")
    model = os.environ.get("MODEL_IMAGE", "").strip() or DEFAULT_MODEL_IMAGE
    return asyncio.run(GeminiImageClient(api_key=key, model=model).generate_image(model, format_display_prompt(PROMPT)))


if __name__ == "__main__":
    OUT.write_bytes(gemini() if "--gemini" in sys.argv[1:] else placeholder())
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
