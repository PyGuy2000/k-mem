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


def make_fallacy() -> Path:
    """The belief, and the two steps under it that nothing confirms.

    A separate image from make_diagram on purpose. This one corrects a belief;
    that one explains a mechanism, and a picture doing both does neither.
    """
    W, H = 1500, 1320
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    f_title, f_band = font(SANS_BOLD, 40), font(SANS_BOLD, 23)
    f_box, f_body, f_small = font(SANS_BOLD, 24), font(SANS, 22), font(SANS, 20)
    f_tag = font(SANS_BOLD, 16)
    M, GREY = 60, (100, 116, 139)

    def wrap(text, f, limit):
        out, line = [], ""
        for word in text.split():
            trial = (line + " " + word).strip()
            if d.textbbox((0, 0), trial, font=f)[2] > limit and line:
                out.append(line); line = word
            else:
                line = trial
        return out + ([line] if line else [])

    def box(x, y, w, h, title, body, colour, fill=PANEL, dashed=False):
        d.rounded_rectangle([(x, y), (x + w, y + h)], radius=12, fill=fill + (255,),
                            outline=colour + (255,), width=0 if dashed else 3)
        if dashed:
            for i in range(0, w, 22):
                d.line([(x + i, y), (x + min(i + 11, w), y)], fill=colour, width=3)
                d.line([(x + i, y + h), (x + min(i + 11, w), y + h)], fill=colour, width=3)
            d.line([(x, y), (x, y + h)], fill=colour, width=3)
            d.line([(x + w, y), (x + w, y + h)], fill=colour, width=3)
        d.text((x + 20, y + 16), title, font=f_box, fill=colour)
        yy = y + 52
        for ln in body:
            for piece in wrap(ln, f_small, w - 40):
                d.text((x + 20, yy), piece, font=f_small, fill=MUTED)
                yy += 26

    def h_arrow(x1, x2, y, colour, label="", dashed=False):
        if dashed:
            x = x1
            while x < x2 - 10:
                d.line([(x, y), (x + 9, y)], fill=colour, width=3); x += 18
        else:
            d.line([(x1, y), (x2, y)], fill=colour, width=3)
        d.polygon([(x2, y), (x2 - 11, y - 8), (x2 - 11, y + 8)], fill=colour)
        if label:
            w = d.textbbox((0, 0), label, font=f_small)[2]
            d.text(((x1 + x2 - w) // 2, y - 32), label, font=f_small, fill=colour)

    d.text((M, 28), "What a repo full of .md files guarantees", font=f_title, fill=FG)
    d.text((M, 82), "A file in the context window is a file in the context window. Whether it became a rule the session followed is a separate question.",
           font=f_body, fill=MUTED)

    # --- band 1: the belief ----------------------------------------------------
    d.text((M, 146), "THE ASSUMPTION", font=f_band, fill=GREY)
    bw, by, bh = 400, 182, 108
    gap = (W - 2 * M - 3 * bw) // 2
    box(M, by, bw, bh, "The rules are written", ["CLAUDE.md, the ADRs,", "the project notes."], GREY)
    box(M + bw + gap, by, bw, bh, "The model reads them", ["They are in the repo,", "so they are in play."], GREY)
    box(M + 2 * (bw + gap), by, bw, bh, "The code follows them", ["The decision holds", "across sessions."], GREY)
    h_arrow(M + bw + 12, M + bw + gap - 12, by + bh // 2, GREY)
    h_arrow(M + 2 * bw + gap + 12, M + 2 * (bw + gap) - 12, by + bh // 2, GREY)
    d.text((M, by + bh + 22), "Written down once, and from then on assumed. This is where most setups stop.", font=f_small, fill=GREY)

    # --- band 2: what the loop confirms ---------------------------------------
    d.text((M, 392), "WHAT THE LOOP ACTUALLY CONFIRMS", font=f_band, fill=ORANGE)
    # narrower than band 1: the arrow labels here need room between the boxes
    cy, ch, cw = 428, 104, 350
    cgap = (W - 2 * M - 3 * cw) // 2
    box(M, cy, cw, ch, "The rules are written", ["On disk. Certain."], CYAN)
    h_arrow(M + cw + 12, M + cw + cgap - 12, cy + ch // 2, CYAN, "in context, always")
    box(M + cw + cgap, cy, cw, ch, "The model", ["What happens here", "leaves no log."], ORANGE, fill=(26, 20, 12), dashed=True)

    qx, qw = M + 2 * (cw + cgap), cw
    d.rounded_rectangle([(qx, cy - 46), (qx + qw, cy + ch + 96)], radius=12, fill=(26, 20, 12, 255), outline=ORANGE + (255,), width=3)
    d.text((qx + 20, cy - 34), "Two open questions", font=f_box, fill=ORANGE)
    for i, (q, a) in enumerate([
        ("Did it read the decision that governs this file?", "The transcript records the call. Nothing reads the transcript."),
        ("Did reading it change what it wrote?", "No record of this exists anywhere."),
    ]):
        yy = cy + 8 + i * 106
        for piece in wrap(q, f_small, qw - 40):
            d.text((qx + 20, yy), piece, font=f_small, fill=FG); yy += 26
        for piece in wrap(a, f_small, qw - 40):
            d.text((qx + 20, yy), piece, font=f_small, fill=ORANGE); yy += 25
    d.line([(M + 2 * cw + cgap + 12, cy + ch // 2), (qx - 12, cy + ch // 2)], fill=ORANGE, width=3)
    d.polygon([(qx - 12, cy + ch // 2), (qx - 23, cy + ch // 2 - 8), (qx - 23, cy + ch // 2 + 8)], fill=ORANGE)

    d.text((M, 678), "Two steps sit between a written rule and a followed one. One is recorded and unchecked. The other is not recorded at all.",
           font=font(SANS_BOLD, 23), fill=ORANGE)

    # --- band 3: where the field works, on the same three links ----------------
    PURPLE = (167, 139, 250)
    d.text((M, 748), "WHERE THE REST OF THE FIELD WORKS", font=f_band, fill=PURPLE)
    ey, eh = 784, 186
    for i, (head, body, colour) in enumerate([
        ("Getting the rules in", "Most of the effort. Better stores, better retrieval, automatic capture. 81 of 148 reviewed systems inject on their own.", PURPLE),
        ("Confirming it read them", "5 of 97 pushing systems test afterwards whether the memory changed behaviour. None of those five block anything.", ORANGE),
        ("Confirming it applied them", "Nothing in that index does this, and its own synthesis says so.", ORANGE),
    ]):
        x = M + i * (cw + cgap)
        d.rounded_rectangle([(x, ey), (x + cw, ey + eh)], radius=12, fill=PANEL + (255,), outline=colour + (255,), width=3)
        d.text((x + 20, ey + 14), head, font=f_box, fill=colour)
        yy = ey + 50
        for piece in wrap(body, f_small, cw - 40):
            d.text((x + 20, yy), piece, font=f_small, fill=MUTED)
            yy += 25
    d.text((M, 1000), "The link that already works is the one most of the field keeps improving.",
           font=font(SANS_BOLD, 23), fill=PURPLE)

    # --- band 4: what changes --------------------------------------------------
    d.text((M, 1062), "WHAT K-MEM CHANGES", font=f_band, fill=CYAN)
    ry, rh = 1098, 116
    half = (W - 2 * M - 30) // 2
    d.rounded_rectangle([(M, ry), (M + half, ry + rh)], radius=12, fill=PANEL + (255,), outline=CYAN + (255,), width=3)
    d.text((M + 20, ry + 16), "Closed", font=f_box, fill=GREEN)
    tw = d.textbbox((0, 0), "k-mem", font=f_tag)[2] + 20
    d.rounded_rectangle([(M + 20 + d.textbbox((0, 0), "Closed", font=f_box)[2] + 14, ry + 19),
                         (M + 20 + d.textbbox((0, 0), "Closed", font=f_box)[2] + 14 + tw, ry + 45)], radius=6, fill=CYAN + (255,))
    d.text((M + 30 + d.textbbox((0, 0), "Closed", font=f_box)[2] + 14, ry + 23), "k-mem", font=f_tag, fill=NAVY)
    yy = ry + 54
    for piece in wrap("The gate reads the transcript before the write lands, and refuses until the read is there.", f_small, half - 40):
        d.text((M + 20, yy), piece, font=f_small, fill=MUTED); yy += 26

    d.rounded_rectangle([(M + half + 30, ry), (W - M, ry + rh)], radius=12, fill=(26, 20, 12, 255), outline=ORANGE + (255,), width=3)
    d.text((M + half + 50, ry + 16), "Still open", font=f_box, fill=ORANGE)
    yy = ry + 54
    for piece in wrap("Whether the decision was understood. The gate proves a read happened, and claims nothing more.", f_small, half - 40):
        d.text((M + half + 50, yy), piece, font=f_small, fill=MUTED); yy += 26

    d.text((M, H - 44), "Closing the first question is what makes the second one worth arguing about.", font=f_small, fill=MUTED)
    im.convert("RGB").save(ASSETS / "the-fallacy.png", optimize=True)
    return ASSETS / "the-fallacy.png"


def make_diagram() -> Path:
    """The zone diagram. Implements docs/diagram-brief.md; argue with the brief, not here."""
    W, H = 1500, 1150
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    f_title, f_zone = font(SANS_BOLD, 40), font(SANS_BOLD, 24)
    f_box, f_body, f_small = font(SANS_BOLD, 25), font(SANS, 23), font(SANS, 20)
    f_tag = font(SANS_BOLD, 16)
    M = 60

    def wrap(text: str, f, limit: int) -> list[str]:
        out, line = [], ""
        for word in text.split():
            trial = (line + " " + word).strip()
            if d.textbbox((0, 0), trial, font=f)[2] > limit and line:
                out.append(line)
                line = word
            else:
                line = trial
        return out + ([line] if line else [])

    def tag(x, y):
        """The mark that says: this ships with k-mem. Everything untagged is already in a session."""
        w = d.textbbox((0, 0), "k-mem", font=f_tag)[2] + 20
        d.rounded_rectangle([(x, y), (x + w, y + 26)], radius=6, fill=CYAN + (255,))
        d.text((x + 10, y + 4), "k-mem", font=f_tag, fill=NAVY)
        return w

    def block(x, y, w, h, title, lines, colour, tagged=()):
        """lines: (text, is_kmem). A tagged line gets the mark and the brand colour."""
        d.rounded_rectangle([(x, y), (x + w, y + h)], radius=12, fill=PANEL + (255,), outline=colour + (255,), width=3)
        d.text((x + 22, y + 18), title, font=f_box, fill=colour)
        yy = y + 56
        for ln in lines:
            mine = ln in tagged
            for piece in wrap(ln, f_small, w - 44 - (78 if mine else 0)):
                d.text((x + 22, yy), piece, font=f_small, fill=CYAN if mine else MUTED)
                if mine:
                    tag(x + 26 + d.textbbox((0, 0), piece, font=f_small)[2], yy - 2)
                    mine = False
                yy += 27

    def v_arrow(x, y1, y2, colour, dashed=False):
        step = 16 if y2 > y1 else -16
        if dashed:
            y = y1
            while (y < y2 - 8) if y2 > y1 else (y > y2 + 8):
                d.line([(x, y), (x, y + step * 0.55)], fill=colour, width=3)
                y += step
        else:
            d.line([(x, y1), (x, y2)], fill=colour, width=3)
        s = 10 if y2 > y1 else -10
        d.polygon([(x, y2), (x - 8, y2 - s), (x + 8, y2 - s)], fill=colour)

    # --- header ---------------------------------------------------------------
    d.text((M, 30), "Where the unpredictable part sits", font=f_title, fill=FG)
    d.text((M, 84), "A session's use of a decision is sampled. The record of a tool call is a fact. The gate checks the fact.",
           font=f_body, fill=MUTED)

    # --- zone 1: deterministic -------------------------------------------------
    z1y, z1h = 178, 178
    d.text((M, 140), "DETERMINISTIC   ·   runs the same way every time, and leaves a record", font=f_zone, fill=CYAN)
    d.rounded_rectangle([(M - 14, z1y - 12), (W - M + 14, z1y + z1h + 12)], radius=16, outline=CYAN + (80,), width=2)
    bw = (W - 2 * M - 2 * 26) // 3
    block(M, z1y, bw, z1h, "Files on disk",
          ["Decision records and STATE.md,", "which you write anyway.", ".claude/adr_map.json"],
          CYAN, tagged={".claude/adr_map.json"})
    block(M + bw + 26, z1y, bw, z1h, "Hooks",
          ["The harness fires them.", "The read gate, the sweep and", "the session brief ship here."],
          CYAN, tagged={"the session brief ship here."})
    block(M + 2 * (bw + 26), z1y, bw, z1h, "The transcript",
          ["Every tool call the session", "made, with its input.", "Written by the harness."], CYAN)

    # --- the two arrows between zone 1 and zone 2 ------------------------------
    z2y, z2h = 530, 226
    down_x = M + bw // 2
    up_x = M + 2 * (bw + 26) + bw // 2
    v_arrow(down_x, z1y + z1h + 22, z2y - 14, CYAN)
    d.text((down_x + 20, 412), "injected at session start, always", font=f_small, fill=CYAN)
    v_arrow(up_x, z2y - 14, z1y + z1h + 22, MUTED, dashed=True)
    lbl = "a Read call, if it makes one"
    d.text((up_x - 24 - d.textbbox((0, 0), lbl, font=f_small)[2], 412), lbl, font=f_small, fill=MUTED)

    # --- zone 2: sampled --------------------------------------------------------
    # right-aligned: the "injected" arrow runs down the left and would cross a left-aligned label
    zl = "SAMPLED   ·   no log of attention   ·   not observable from outside"
    d.text((W - M - d.textbbox((0, 0), zl, font=f_zone)[2], 492), zl, font=f_zone, fill=ORANGE)
    d.rounded_rectangle([(M, z2y), (W - M, z2y + z2h)], radius=12, fill=(26, 20, 12, 255))
    for i in range(0, W - 2 * M, 24):  # dashed edge: a boundary, not a container
        d.line([(M + i, z2y), (M + min(i + 12, W - 2 * M), z2y)], fill=ORANGE, width=3)
        d.line([(M + i, z2y + z2h), (M + min(i + 12, W - 2 * M), z2y + z2h)], fill=ORANGE, width=3)
    d.line([(M, z2y), (M, z2y + z2h)], fill=ORANGE, width=3)
    d.line([(W - M, z2y), (W - M, z2y + z2h)], fill=ORANGE, width=3)
    d.text((M + 26, z2y + 20), "The model", font=f_box, fill=ORANGE)
    for i, q in enumerate([
        "1.  Does it call Read on the governing decision at all?",
        "2.  Once the text is in context, does attention land on it?",
        "3.  Do those tokens change the ones it emits?",
    ]):
        d.text((M + 26, z2y + 62 + i * 34), q, font=f_body, fill=FG)
    d.text((M + 26, z2y + 178), "A transcript shows that a file was opened. It never shows that the file was used.",
           font=font(SANS_BOLD, 23), fill=ORANGE)

    # --- zone 3: the gate -------------------------------------------------------
    z3y, z3h = 872, 132
    v_arrow(down_x, z2y + z2h + 22, z3y - 14, ORANGE)
    d.text((down_x + 20, 796), "proposes a write", font=f_small, fill=ORANGE)
    gw = int((W - 2 * M) * 0.60)
    d.rounded_rectangle([(M, z3y), (M + gw, z3y + z3h)], radius=12, fill=PANEL + (255,), outline=CYAN + (255,), width=4)
    d.text((M + 24, z3y + 18), "The gate", font=f_box, fill=CYAN)
    tag(M + 24 + d.textbbox((0, 0), "The gate", font=f_box)[2] + 16, z3y + 22)
    d.text((M + 24, z3y + 58), "Does the transcript hold a read of every decision that", font=f_body, fill=FG)
    d.text((M + 24, z3y + 88), "governs this path, earlier in this session?", font=f_body, fill=FG)

    # the record reaches the gate; the model never does
    rail = W - M + 14
    entry = z3y + 40
    d.line([(W - M, z1y + z1h // 2), (rail, z1y + z1h // 2)], fill=CYAN, width=3)
    d.line([(rail, z1y + z1h // 2), (rail, entry)], fill=CYAN, width=3)
    d.line([(rail, entry), (M + gw + 10, entry)], fill=CYAN, width=3)
    d.polygon([(M + gw, entry), (M + gw + 11, entry - 8), (M + gw + 11, entry + 8)], fill=CYAN)
    d.text((M + gw + 30, entry - 54), "reads the record,", font=f_small, fill=CYAN)
    d.text((M + gw + 30, entry - 28), "never the model", font=f_small, fill=CYAN)

    # outcomes, below the entry line so nothing competes with it
    oy = z3y + 78
    d.rounded_rectangle([(M + gw + 30, oy), (M + gw + 152, oy + 38)], radius=8, outline=GREEN + (255,), width=2)
    d.text((M + gw + 56, oy + 7), "allow", font=f_box, fill=GREEN)
    d.rounded_rectangle([(M + gw + 168, oy), (M + gw + 302, oy + 38)], radius=8, outline=RED + (255,), width=2)
    d.text((M + gw + 192, oy + 7), "refuse", font=f_box, fill=RED)

    lx = M
    d.text((lx, H - 96), "Tagged", font=f_small, fill=MUTED)
    lx += d.textbbox((0, 0), "Tagged ", font=f_small)[2]
    lx += tag(lx, H - 98) + 10
    d.text((lx, H - 96), "ships with k-mem. Everything else is already in your session: the model, the transcript, the hook mechanism, your own notes.",
           font=f_small, fill=MUTED)
    d.text((M, H - 48), "The gate makes no judgement about understanding. It checks whether the decision was opened before the edit was attempted.",
           font=f_small, fill=MUTED)
    im.convert("RGB").save(ASSETS / "where-retrieval-sits.png", optimize=True)
    return ASSETS / "where-retrieval-sits.png"


def make_system() -> Path:
    """The whole loop, including the task half.

    Hand-placed because mermaid's auto-layout produced either a 0.72 or a 5.85
    aspect ratio, both unusable in a README; docs/assets/system.mmd keeps an
    editable version. Every return path runs in a reserved channel: y=490
    between the top row and the model, y=700 between the model and the gate,
    x=790 between the gate and the transcript, and x=1200 down the right.
    Nothing crosses a box.
    """
    W, H = 1560, 1060
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    f_title = font(SANS_BOLD, 38)
    f_box, f_small, f_tag, f_band = font(SANS_BOLD, 23), font(SANS, 19), font(SANS_BOLD, 15), font(SANS_BOLD, 20)
    M, GREY = 52, (100, 116, 139)

    def wrap(text, f, limit):
        out, line = [], ""
        for w in text.split():
            trial = (line + " " + w).strip()
            if d.textbbox((0, 0), trial, font=f)[2] > limit and line:
                out.append(line); line = w
            else:
                line = trial
        return out + ([line] if line else [])

    def tag(x, y):
        w = d.textbbox((0, 0), "k-mem", font=f_tag)[2] + 18
        d.rounded_rectangle([(x, y), (x + w, y + 24)], radius=6, fill=CYAN + (255,))
        d.text((x + 9, y + 3), "k-mem", font=f_tag, fill=NAVY)

    def card(x, y, w, h, title, body, colour, fill=PANEL, dashed=False, mine=False):
        d.rounded_rectangle([(x, y), (x + w, y + h)], radius=11, fill=fill + (255,),
                            outline=colour + (255,), width=0 if dashed else 3)
        if dashed:
            for i in range(0, w, 20):
                d.line([(x + i, y), (x + min(i + 10, w), y)], fill=colour, width=3)
                d.line([(x + i, y + h), (x + min(i + 10, w), y + h)], fill=colour, width=3)
            d.line([(x, y), (x, y + h)], fill=colour, width=3)
            d.line([(x + w, y), (x + w, y + h)], fill=colour, width=3)
        d.text((x + 17, y + 12), title, font=f_box, fill=colour)
        if mine:
            tag(x + 17 + d.textbbox((0, 0), title, font=f_box)[2] + 12, y + 15)
        yy = y + 46
        for ln in body:
            for piece in wrap(ln, f_small, w - 34):
                d.text((x + 17, yy), piece, font=f_small, fill=MUTED); yy += 24

    def path(pts, colour, dashed=False):
        for i in range(len(pts) - 1):
            (x1, y1), (x2, y2) = pts[i], pts[i + 1]
            if dashed:
                n = max(1, int((abs(x2 - x1) + abs(y2 - y1)) // 18))
                for k in range(n):
                    a, b = k / n, (k + 0.55) / n
                    d.line([(x1 + (x2 - x1) * a, y1 + (y2 - y1) * a), (x1 + (x2 - x1) * b, y1 + (y2 - y1) * b)], fill=colour, width=3)
            else:
                d.line([(x1, y1), (x2, y2)], fill=colour, width=3)
        (px, py), (qx, qy) = pts[-2], pts[-1]
        if abs(qx - px) > abs(qy - py):
            s = 10 if qx > px else -10
            d.polygon([(qx, qy), (qx - s, qy - 8), (qx - s, qy + 8)], fill=colour)
        else:
            s = 10 if qy > py else -10
            d.polygon([(qx, qy), (qx - 8, qy - s), (qx + 8, qy - s)], fill=colour)

    def note(x, y, text, colour):
        for i, piece in enumerate(text.split("|")):
            d.text((x, y + i * 22), piece, font=f_small, fill=colour)

    d.text((M, 24), "The whole loop", font=f_title, fill=FG)
    d.text((M, 72), "Two kinds of memory: what was decided, and what is still owed. Both reach the session, and one check stands between them and the code.",
           font=font(SANS, 20), fill=MUTED)

    # --- top row --------------------------------------------------------------
    d.text((M, 128), "WHAT YOU WRITE", font=f_band, fill=GREY)
    d.text((402, 128), "THE RECORD", font=f_band, fill=CYAN)
    d.text((752, 128), "EVERY SESSION BEGINS WITH", font=f_band, fill=CYAN)
    card(M, 158, 300, 136, "Decisions, notes", ["One file per decision.", "STATE.md and plans.md.", "Yours, written anyway."], GREY)
    card(402, 158, 300, 136, "The map", [".claude/adr_map.json:", "which decisions govern", "which paths."], CYAN, mine=True)
    card(402, 322, 300, 128, "Tickets", ["DevFlow. backlog, active,", "blocked, done. One per", "piece of outstanding work."], CYAN, mine=True)
    card(752, 158, 320, 292, "Session start", ["The brief and the plan index.",
                                               "The inventory of every decision",
                                               "that exists.", "",
                                               "What is active, blocked, or",
                                               "ready to unblock.", "",
                                               "Delivered before the first",
                                               "answer, every time."], CYAN, mine=True)

    path([(M + 308, 226), (394, 226)], GREY)
    path([(M + 308, 262), (350, 262), (350, 386), (394, 386)], GREY)
    note(M + 316, 296, "outstanding work|becomes a ticket", GREY)
    path([(710, 226), (744, 226)], CYAN)
    path([(710, 386), (727, 386), (727, 300), (744, 300)], CYAN)

    # --- the model ------------------------------------------------------------
    d.text((M, 520), "SAMPLED  ·  no log of attention  ·  not observable from outside", font=f_band, fill=ORANGE)
    card(M, 552, 700, 138, "The model", ["Does it read the decision that governs this file?",
                                         "Does reading it change what it writes?",
                                         "A transcript shows a file was opened. It never shows it was used."],
         ORANGE, fill=(26, 20, 12), dashed=True)
    # channel y=490, clear of everything
    path([(912, 458), (912, 490), (300, 490), (300, 544)], CYAN)
    note(322, 496, "injected every session", CYAN)

    card(812, 552, 300, 104, "The transcript", ["Every tool call,", "written by the harness."], GREY)
    path([(760, 596), (804, 596)], GREY, dashed=True)
    note(766, 500, "a Read call,|if it makes one", GREY)

    # --- the gate -------------------------------------------------------------
    card(M, 744, 700, 112, "The gate", ["Is there a read of every decision governing this path,",
                                        "earlier in this transcript?"], CYAN, mine=True)
    path([(160, 698), (160, 736)], ORANGE)
    note(178, 700, "proposes a write", ORANGE)
    # transcript down the x=962 channel, into the gate's right edge
    path([(962, 664), (962, 800), (760, 800)], CYAN)
    note(800, 700, "the recorded fact", CYAN)

    # --- outcomes --------------------------------------------------------------
    oy = 890
    d.rounded_rectangle([(M, oy), (M + 330, oy + 62)], radius=11, fill=PANEL + (255,), outline=GREEN + (255,), width=3)
    d.text((M + 17, oy + 9), "allow", font=f_box, fill=GREEN)
    d.text((M + 17, oy + 37), "the edit lands, the ticket moves", font=f_small, fill=MUTED)
    d.rounded_rectangle([(422, oy), (752, oy + 62)], radius=11, fill=PANEL + (255,), outline=RED + (255,), width=3)
    d.text((439, oy + 9), "refuse", font=f_box, fill=RED)
    d.text((439, oy + 37), "and name the files to read", font=f_small, fill=MUTED)
    path([(150, 860), (150, oy - 6)], GREEN)
    path([(620, 860), (620, oy - 6)], RED)

    # allow closes a ticket: down, out to the right gutter, back along y=490 to the ticket
    path([(217, oy + 62), (217, 992), (1200, 992), (1200, 490), (552, 490), (552, 458)], GREEN)
    note(1216, 620, "the work lands,|the ticket closes", GREEN)
    # a refusal sends the session back to read: around the gate's right, along y=712
    path([(760, oy + 31), (790, oy + 31), (790, 706), (430, 706), (430, 698)], RED, dashed=True)
    note(448, 712, "read them, re-issue the identical edit", RED)

    d.text((M, H - 40), "Tagged boxes ship with k-mem. The decisions, the notes and the transcript exist either way.", font=f_small, fill=MUTED)
    im.convert("RGB").save(ASSETS / "the-system.png", optimize=True)
    return ASSETS / "the-system.png"


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for path in (make_banner(), make_social(), make_gate_demo(), make_fallacy(), make_system(), make_diagram()):
        size = Image.open(path).size
        print(f"{path.relative_to(ROOT)}  {size[0]}x{size[1]}  {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
