#!/usr/bin/env python3
"""Generate the repo's brand images from the logo and the gate's real output.

    python3 scripts/make_brand_images.py

Writes, all under docs/assets/:

    banner.png          the README header card (1600x460, shown at 800)
    social-preview.png  GitHub's Open Graph card (1280x640, the size GitHub wants)
    gate-demo.png       a terminal card showing the refusal, text captured from the hook

Why a card and not the bare logo: the wordmark's K is #E2F4F1, so on GitHub's
light theme it disappears against white. Compositing onto the brand navy makes
it legible in both themes and needs no <picture> switch.

The demo text is pasted from a real `read_gate.py` run against example/, never
written by hand. Regenerate it with the command in DEMO_SOURCE below.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
LOGO = ASSETS / "logo.png"

# Brand, from the site's index.css tokens converted to hex.
NAVY = (8, 12, 22)
PANEL = (16, 22, 38)
CYAN = (0, 225, 255)
ORANGE = (255, 148, 26)
FG = (241, 245, 249)
MUTED = (148, 163, 184)
RED = (248, 113, 113)
GREEN = (74, 222, 128)

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SANS = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANS_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

#: How the demo text was captured, so a future edit can reproduce it rather than invent it.
DEMO_SOURCE = (
    "cp -r example /tmp/demo && cd /tmp/demo && git init -q && git add -A && git commit -qm init && "
    "echo '{\"type\":\"user\",...}' > /tmp/t.jsonl && "
    "printf '{\"session_id\":\"demo\",\"transcript_path\":\"/tmp/t.jsonl\",\"tool_name\":\"Edit\","
    "\"tool_input\":{\"file_path\":\"/tmp/demo/src/billing/invoice.py\"}}' | python3 hooks/read_gate.py"
)

DEMO_LINES = [
    ("prompt", "$ claude"),
    ("dim", ""),
    ("user", "> rename CENT to PENNY in src/billing/invoice.py"),
    ("dim", ""),
    ("tool", "● Edit(src/billing/invoice.py)"),
    ("dim", ""),
    ("err", "READ GATE: this edit is refused until the governing ADRs have been read this session."),
    ("plain", "File: src/billing/invoice.py"),
    ("plain", "Read these first, then re-issue the identical edit:"),
    ("cyan", "  - docs/project_notes/decisions/ADR-001-invoice-rounding.md"),
    ("cyan", "  - docs/project_notes/decisions/ADR-002-tax-table-source.md"),
    ("plain", "Name each ADR you read in your reply. This gate does not expire;"),
    ("plain", "there is no second-attempt bypass."),
    ("dim", ""),
    ("ok", "  Read 2 files"),
    ("dim", ""),
    ("ok", "● Edit(src/billing/invoice.py)  ✔ allowed"),
]

COLOURS = {
    "prompt": MUTED, "dim": MUTED, "user": FG, "tool": CYAN,
    "err": RED, "plain": FG, "cyan": CYAN, "ok": GREEN,
}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def rounded_card(size: tuple[int, int], radius: int, fill: tuple[int, int, int]) -> Image.Image:
    """A card with transparent corners, so it sits well on either GitHub theme."""
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=fill + (255,))
    return im


def fit_logo(max_w: int, max_h: int) -> Image.Image:
    logo = Image.open(LOGO).convert("RGBA")
    scale = min(max_w / logo.width, max_h / logo.height)
    return logo.resize((round(logo.width * scale), round(logo.height * scale)), Image.LANCZOS)


def centred(draw: ImageDraw.ImageDraw, y: int, text: str, f: ImageFont.FreeTypeFont, fill, width: int) -> None:
    w = draw.textbbox((0, 0), text, font=f)[2]
    draw.text(((width - w) // 2, y), text, font=f, fill=fill)


def make_banner() -> Path:
    W, H = 1600, 460
    im = rounded_card((W, H), 28, NAVY)
    d = ImageDraw.Draw(im)
    # a thin brand rule under the top edge
    d.rounded_rectangle([(0, 0), (W - 1, 5)], radius=3, fill=CYAN + (255,))
    logo = fit_logo(int(W * 0.56), 250)
    im.alpha_composite(logo, ((W - logo.width) // 2, 62))
    y = 62 + logo.height + 30
    centred(d, y, "Memory and governance for Claude Code sessions", font(SANS, 40), FG, W)
    centred(d, y + 58, "Read the decision before you change the code. The gate refuses until you have.", font(SANS, 27), MUTED, W)
    im.save(ASSETS / "banner.png", optimize=True)
    return ASSETS / "banner.png"


def make_social() -> Path:
    W, H = 1280, 640  # the size GitHub asks for
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle([(0, 0), (W, 7)], fill=CYAN)
    d.rectangle([(0, H - 7), (W, H)], fill=ORANGE)
    logo = fit_logo(int(W * 0.60), 230)
    im.alpha_composite(logo, ((W - logo.width) // 2, 92))
    y = 92 + logo.height + 34
    centred(d, y, "K-mem", font(SANS_BOLD, 66), FG, W)
    centred(d, y + 86, "Memory and governance for Claude Code sessions", font(SANS, 34), CYAN, W)
    centred(d, y + 140, "A read-before-write gate  ·  a context resolver  ·  docs checks that fail", font(SANS, 26), MUTED, W)
    centred(d, H - 74, "github.com/PyGuy2000/k-mem", font(MONO, 25), MUTED, W)
    im.convert("RGB").save(ASSETS / "social-preview.png", optimize=True)
    return ASSETS / "social-preview.png"


def make_gate_demo() -> Path:
    fm, fb = font(MONO, 25), font(MONO_BOLD, 25)
    pad, lh, chrome = 42, 40, 62
    W = 1360
    H = chrome + pad * 2 + lh * len(DEMO_LINES)
    im = rounded_card((W, H), 18, PANEL)
    d = ImageDraw.Draw(im)
    # window chrome
    d.rounded_rectangle([(0, 0), (W - 1, chrome)], radius=18, fill=(30, 38, 58, 255))
    d.rectangle([(0, chrome - 18), (W - 1, chrome)], fill=(30, 38, 58, 255))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([(28 + i * 30, 23), (44 + i * 30, 39)], fill=c)
    title = "example/  —  a governed repo"
    d.text(((W - d.textbbox((0, 0), title, font=font(MONO, 22))[2]) // 2, 20), title, font=font(MONO, 22), fill=MUTED)

    y = chrome + pad
    for kind, text in DEMO_LINES:
        if text:
            f = fb if kind in ("err", "user", "ok") else fm
            d.text((pad, y), text, font=f, fill=COLOURS[kind])
        y += lh
    im.save(ASSETS / "gate-demo.png", optimize=True)
    return ASSETS / "gate-demo.png"


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for path in (make_banner(), make_social(), make_gate_demo()):
        size = Image.open(path).size
        print(f"{path.relative_to(ROOT)}  {size[0]}x{size[1]}  {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
