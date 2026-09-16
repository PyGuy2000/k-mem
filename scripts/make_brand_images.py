#!/usr/bin/env python3
"""Generate the repo's brand images from the logo and the gate's real output.

    python3 scripts/make_brand_images.py

Writes, all under docs/assets/:

    banner.png          the README header card (1600x460, shown at 800)
    social-preview.png  GitHub's Open Graph card (1280x640, the size GitHub wants)
    gate-demo.png       a terminal card showing the refusal, text captured from the hook
    the-fallacy.png     the belief, where it breaks inside one turn, and where the check goes
    the-system.png      the whole loop, decisions and tickets both

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
    """Four sections with equal white headers, three columns that hold the same x
    down the page so a reader can track one column downward.

    Colour carries meaning rather than section: cyan for what is certain, orange
    for what is sampled. Band 4 places the transcript and the gate outside the
    model and shows where the transcript's line comes from, because a check that
    appears with no origin reads as an assertion.
    """
    W, H = 1560, 1424
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    f_h, f_over = font(SANS_BOLD, 27), font(SANS_BOLD, 16)
    f_box, f_small, f_stmt = font(SANS_BOLD, 21), font(SANS, 18), font(SANS_BOLD, 21)
    f_tag, f_lead = font(SANS_BOLD, 15), font(SANS_BOLD, 18)
    M, GREY, PURPLE = 52, (100, 116, 139), (167, 139, 250)
    COLS, CW, DW = [52, 432, 812, 1192], 330, 316

    def wrap(text, f, limit):
        out, line = [], ""
        for w in text.split():
            trial = (line + " " + w).strip()
            if d.textbbox((0, 0), trial, font=f)[2] > limit and line:
                out.append(line); line = w
            else:
                line = trial
        return out + ([line] if line else [])

    def box(x, y, w, h, title, body, colour, tint=None, mine=False):
        d.rounded_rectangle([(x, y), (x + w, y + h)], radius=11, fill=(tint or PANEL) + (255,), outline=colour + (255,), width=3)
        d.text((x + 16, y + 11), title, font=f_box, fill=colour)
        if mine:
            tx = x + 16 + d.textbbox((0, 0), title, font=f_box)[2] + 12
            tw = d.textbbox((0, 0), "k-mem", font=f_tag)[2] + 18
            d.rounded_rectangle([(tx, y + 14), (tx + tw, y + 38)], radius=6, fill=CYAN + (255,))
            d.text((tx + 9, y + 17), "k-mem", font=f_tag, fill=NAVY)
        yy = y + 42
        for ln in body:
            for piece in wrap(ln, f_small, w - 32):
                d.text((x + 16, yy), piece, font=f_small, fill=MUTED); yy += 23

    def h_arrow(x1, x2, y, colour):
        d.line([(x1, y), (x2, y)], fill=colour, width=3)
        d.polygon([(x2, y), (x2 - 11, y - 8), (x2 - 11, y + 8)], fill=colour)

    def dashed_rect(x1, y1, x2, y2, colour, step=20):
        for i in range(0, x2 - x1, step):
            d.line([(x1 + i, y1), (x1 + min(i + 10, x2 - x1), y1)], fill=colour, width=3)
            d.line([(x1 + i, y2), (x1 + min(i + 10, x2 - x1), y2)], fill=colour, width=3)
        for i in range(0, y2 - y1, step):
            d.line([(x1, y1 + i), (x1, y1 + min(i + 10, y2 - y1))], fill=colour, width=3)
            d.line([(x2, y1 + i), (x2, y1 + min(i + 10, y2 - y1))], fill=colour, width=3)

    d.text((M, 22), "K-MEM  ·  THE PROBLEM", font=f_over, fill=CYAN)

    # --- 1 · the assumption ----------------------------------------------------
    d.text((M, 54), "What a repo full of .md files suggests will happen inside the LLM", font=f_h, fill=FG)
    by, bh, w1 = 102, 92, 420
    g1 = (W - 2 * M - 3 * w1) // 2
    for i, (title, body) in enumerate([
        ("The rules are written", "CLAUDE.md, the ADRs, the notes."),
        ("The model reads them", "They are in the repo, so in play."),
        ("The code follows them", "The decision holds across sessions."),
    ]):
        box(M + i * (w1 + g1), by, w1, bh, title, [body], GREY)
    h_arrow(M + w1 + 10, M + w1 + g1 - 10, by + bh // 2, GREY)
    h_arrow(M + 2 * w1 + g1 + 10, M + 2 * (w1 + g1) - 10, by + bh // 2, GREY)
    d.text((M, 206), "Written once, and assumed from then on. This is where most setups stop.", font=f_small, fill=GREY)

    # --- 2 · where it breaks ---------------------------------------------------
    d.text((M, 256), "The existence of instructions does not guarantee the LLM reads them", font=f_h, fill=FG)
    sy, sh = 376, 96
    d.text((COLS[1] - 22, 318), "INSIDE THE MODEL  ·  nothing outside it can confirm either step", font=f_small, fill=ORANGE)
    dashed_rect(COLS[1] - 22, 346, COLS[2] + CW + 22, 566, ORANGE)
    box(COLS[0], sy, CW, sh, "Context window", ["The decision is in here.", "A hook put it there. Certain."], CYAN)
    box(COLS[1], sy, CW, sh, "1 · Does it call Read?", ["The tool-call decision."], ORANGE, tint=(26, 20, 12))
    box(COLS[2], sy, CW, sh, "2 · Attention, then tokens", ["What it writes next."], ORANGE, tint=(26, 20, 12))
    box(COLS[3], sy, DW, sh, "The edit it proposes", ["Arrives either way."], GREY)
    for a, b in [(0, 1), (1, 2), (2, 3)]:
        h_arrow(COLS[a] + CW + 10, COLS[b] - 10, sy + sh // 2, CYAN if a == 0 else ORANGE)
    for col, lines in [(COLS[1], ["A tool_use line lands in", "the transcript. Nothing", "reads it. RECORDED, UNCHECKED."]),
                       (COLS[2], ["Attention leaves no log.", "Nothing to check, even", "in principle. NOT RECORDED."])]:
        for i, ln in enumerate(lines):
            d.text((col, 490 + i * 23), ln, font=f_lead if i == 2 else f_small, fill=ORANGE)
    d.text((M, 604), "Two steps sit between a written rule and a followed one. One is recorded and unchecked. The other is not recorded at all.",
           font=f_stmt, fill=ORANGE)

    # --- 3 · the market --------------------------------------------------------
    d.text((M, 654), "How the market is trying to fix what the LLM never discloses", font=f_h, fill=FG)
    ey, eh = 702, 142
    box(COLS[0], ey, CW, eh, "On the context window", ["Most of the effort. Better stores,", "better retrieval, automatic capture.",
                                                       "81 of 148 reviewed systems inject", "on their own."], CYAN)
    box(COLS[1], ey, CW, eh, "On step 1", ["5 of 97 pushing systems check", "afterwards whether the memory",
                                           "changed behaviour. None of those", "five block anything."], ORANGE)
    box(COLS[2], ey, CW, eh, "On step 2", ["Nothing in that index does this,", "and its own synthesis says so."], ORANGE)
    d.text((M, 866), "The column that already works is the one most of the field keeps improving.", font=f_stmt, fill=PURPLE)

    # --- 4 · the check ---------------------------------------------------------
    d.text((M, 916), "Where k-mem puts the check", font=f_h, fill=FG)
    ky, kh = 1022, 112
    d.text((COLS[1] - 22, 978), "INSIDE THE MODEL  ·  k-mem changes nothing in here", font=f_small, fill=ORANGE)
    dashed_rect(COLS[1] - 22, 1006, COLS[2] + CW + 22, 1150, ORANGE)
    box(COLS[0], ky, CW, kh, "Context window", ["k-mem delivers here too, like", "everyone else. That alone",
                                                "guarantees nothing."], CYAN, mine=True)
    box(COLS[1], ky, CW, kh, "1 · Does it call Read?", ["Untouched. The record it", "leaves is what gets checked."], ORANGE, tint=(26, 20, 12))
    box(COLS[2], ky, CW, kh, "2 · Attention, then tokens", ["Untouched, and uncheckable.", "No record to check."], ORANGE, tint=(26, 20, 12))

    ty, th = 1206, 112
    box(COLS[1], ty, CW, th, "The transcript", ["A file the harness writes.", "Outside the model."], GREY)
    box(COLS[2], ty, CW, th, "The gate", ["A hook the harness runs. Outside", "the model. Refuses the write until", "that line is there."], CYAN, mine=True)
    # step 1 is where the transcript's line comes from
    d.line([(COLS[1] + CW // 2, 1150), (COLS[1] + CW // 2, ty - 10)], fill=ORANGE, width=3)
    d.polygon([(COLS[1] + CW // 2, ty - 10), (COLS[1] + CW // 2 - 8, ty - 20), (COLS[1] + CW // 2 + 8, ty - 20)], fill=ORANGE)
    d.text((COLS[1] + CW // 2 + 16, 1160), "step 1 leaves a tool_use line here", font=f_small, fill=ORANGE)
    h_arrow(COLS[1] + CW + 10, COLS[2] - 10, ty + th // 2, CYAN)
    d.text((668, ty + th + 12), "the gate reads this", font=f_small, fill=CYAN)
    # and never the other way
    rx = 1250
    d.line([(COLS[2] + CW, ty + 60), (rx, ty + 60)], fill=RED, width=3)
    d.line([(rx, ty + 60), (rx, 1166)], fill=RED, width=3)
    d.polygon([(rx, 1166), (rx - 8, 1176), (rx + 8, 1176)], fill=RED)
    for a, b in [((rx - 15, 1206), (rx + 15, 1236)), ((rx + 15, 1206), (rx - 15, 1236))]:
        d.line([a, b], fill=RED, width=4)
    d.text((rx + 28, 1196), "the gate cannot", font=f_small, fill=RED)
    d.text((rx + 28, 1218), "look in here", font=f_small, fill=RED)

    d.text((M, H - 36), "The boundary is not a defect. It is the part that cannot be verified from outside, drawn so the check can be placed on the other side of it.",
           font=f_small, fill=MUTED)
    im.convert("RGB").save(ASSETS / "the-fallacy.png", optimize=True)
    return ASSETS / "the-fallacy.png"


def make_system() -> Path:
    """The whole loop, including the task half.

    Hand-placed because mermaid's auto-layout produced either a 0.72 or a 5.85
    aspect ratio, both unusable in a README; docs/assets/system.mmd keeps an
    editable version. Every return path runs in a reserved channel: y=490
    between the top row and the model, y=700 between the model and the gate,
    x=790 between the gate and the transcript, and x=1200 down the right.
    Nothing crosses a box.
    """
    W, H = 1560, 1080
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
    card(402, 158, 300, 126, "The map", [".claude/adr_map.json:", "which decisions govern", "which paths."], CYAN, mine=True)
    card(402, 352, 300, 128, "Tickets", ["DevFlow. backlog, active,", "blocked, done. One per", "piece of outstanding work."], CYAN, mine=True)
    card(752, 158, 320, 322, "Session start", ["The brief and the plan index.",
                                               "The inventory of every decision",
                                               "that exists.", "",
                                               "What is active, blocked, or",
                                               "ready to unblock.", "",
                                               "Delivered before the first",
                                               "answer, every time."], CYAN, mine=True)

    path([(M + 308, 221), (394, 221)], GREY)
    path([(M + 308, 258), (350, 258), (350, 416), (394, 416)], GREY)
    note(368, 296, "outstanding work|becomes a ticket", GREY)
    path([(710, 221), (744, 221)], CYAN)
    path([(710, 416), (727, 416), (727, 320), (744, 320)], CYAN)

    # --- the model ------------------------------------------------------------
    d.text((M, 540), "SAMPLED  ·  no log of attention  ·  not observable from outside", font=f_band, fill=ORANGE)
    card(M, 572, 700, 138, "The model", ["Does it read the decision that governs this file?",
                                         "Does reading it change what it writes?",
                                         "A transcript shows a file was opened. It never shows it was used."],
         ORANGE, fill=(26, 20, 12), dashed=True)
    # channel y=490, clear of everything
    path([(912, 488), (912, 510), (300, 510), (300, 564)], CYAN)
    note(322, 516, "injected every session", CYAN)

    card(812, 572, 300, 104, "The transcript", ["Every tool call,", "written by the harness."], GREY)
    path([(760, 616), (804, 616)], GREY, dashed=True)
    note(766, 520, "a Read call,|if it makes one", GREY)

    # --- the gate -------------------------------------------------------------
    card(M, 764, 700, 112, "The gate", ["Is there a read of every decision governing this path,",
                                        "earlier in this transcript?"], CYAN, mine=True)
    path([(160, 718), (160, 756)], ORANGE)
    note(178, 720, "proposes a write", ORANGE)
    # transcript down the x=962 channel, into the gate's right edge
    path([(962, 684), (962, 820), (760, 820)], CYAN)
    note(800, 720, "the recorded fact", CYAN)

    # --- outcomes --------------------------------------------------------------
    oy = 910
    d.rounded_rectangle([(M, oy), (M + 330, oy + 62)], radius=11, fill=PANEL + (255,), outline=GREEN + (255,), width=3)
    d.text((M + 17, oy + 9), "allow", font=f_box, fill=GREEN)
    d.text((M + 17, oy + 37), "the edit lands, the ticket moves", font=f_small, fill=MUTED)
    d.rounded_rectangle([(422, oy), (752, oy + 62)], radius=11, fill=PANEL + (255,), outline=RED + (255,), width=3)
    d.text((439, oy + 9), "refuse", font=f_box, fill=RED)
    d.text((439, oy + 37), "and name the files to read", font=f_small, fill=MUTED)
    path([(150, 880), (150, oy - 6)], GREEN)
    path([(620, 880), (620, oy - 6)], RED)

    # allow closes a ticket: down, out to the right gutter, back along y=490 to the ticket
    path([(217, oy + 62), (217, 1012), (1200, 1012), (1200, 510), (552, 510), (552, 488)], GREEN)
    note(1216, 640, "the work lands,|the ticket closes", GREEN)
    # a refusal sends the session back to read: around the gate's right, along y=712
    path([(760, oy + 31), (790, oy + 31), (790, 726), (430, 726), (430, 718)], RED, dashed=True)
    note(448, 732, "read them, re-issue the identical edit", RED)

    d.text((M, H - 40), "Tagged boxes ship with k-mem. The decisions, the notes and the transcript exist either way.", font=f_small, fill=MUTED)
    im.convert("RGB").save(ASSETS / "the-system.png", optimize=True)
    return ASSETS / "the-system.png"


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for path in (make_banner(), make_social(), make_gate_demo(), make_fallacy(), make_system()):
        size = Image.open(path).size
        print(f"{path.relative_to(ROOT)}  {size[0]}x{size[1]}  {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
