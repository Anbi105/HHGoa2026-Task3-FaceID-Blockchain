"""Generate the README's SVG artwork, in light and dark variants.

    python scripts/gen_readme_assets.py

Writes assets/{hero,pipeline,demo}-{light,dark}.svg.

The README pairs each variant with <picture> + prefers-color-scheme, which
is the only reliable way to get a theme-aware image on GitHub: media
queries inside an SVG loaded via <img> are not honoured consistently, so
two files beat one clever one.

Everything is drawn with presentation attributes and system font stacks —
no <style> blocks, no web fonts, no scripts — because GitHub serves these
through its image proxy and strips anything else.

The terminal transcript is real output from `make demo`, transcribed here
so the graphic cannot drift from what the tool actually prints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"

MONO = "ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,Liberation Mono,monospace"
SANS = "-apple-system,BlinkMacSystemFont,Segoe UI,Noto Sans,Helvetica,Arial,sans-serif"

# GitHub's own palette, so the artwork sits naturally in either theme.
THEMES: Dict[str, Dict[str, str]] = {
    "light": dict(
        bg="#ffffff", panel="#f6f8fa", panel2="#eaeef2", border="#d1d9e0",
        text="#1f2328", muted="#59636e", faint="#818b98",
        purple="#8250df", green="#1a7f37", red="#cf222e",
        amber="#9a6700", blue="#0969da", shadow="#1f232812",
    ),
    "dark": dict(
        bg="#0d1117", panel="#161b22", panel2="#1c2128", border="#3d444d",
        text="#e6edf3", muted="#9198a1", faint="#6e7681",
        purple="#a371f7", green="#3fb950", red="#f85149",
        amber="#d29922", blue="#4493f7", shadow="#00000040",
    ),
}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, *, fill, size=13, family=MONO, weight="400", anchor="start",
         opacity=None, spacing=None) -> str:
    extra = ""
    if opacity is not None:
        extra += f' opacity="{opacity}"'
    if spacing is not None:
        extra += f' letter-spacing="{spacing}"'
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"'
        f'{extra} xml:space="preserve">{esc(s)}</text>'
    )


def rect(x, y, w, h, *, fill, stroke=None, rx=6, sw=1, dash=None, opacity=None) -> str:
    extra = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    if dash:
        extra += f' stroke-dasharray="{dash}"'
    if opacity is not None:
        extra += f' opacity="{opacity}"'
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{extra}/>'


def svg(w: int, h: int, body: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">'
        f"<title>{esc(title)}</title>{body}</svg>"
    )


# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------


def hero(t: Dict[str, str]) -> str:
    W, H = 1200, 300
    b: List[str] = [rect(0, 0, W, H, fill=t["bg"], rx=0)]
    b.append(rect(0.5, 0.5, W - 1, H - 1, fill=t["panel"], stroke=t["border"], rx=14))

    # Scan-grid motif on the right: a face bracket over a faint dot lattice.
    for i in range(11):
        for j in range(7):
            cx, cy = 905 + i * 26, 62 + j * 26
            b.append(f'<circle cx="{cx}" cy="{cy}" r="1.6" fill="{t["faint"]}" opacity="0.5"/>')
    bx, by, bw, bh, arm = 918, 74, 232, 152, 34
    for x1, y1, x2, y2 in [
        (bx, by + arm, bx, by), (bx, by, bx + arm, by),
        (bx + bw - arm, by, bx + bw, by), (bx + bw, by, bx + bw, by + arm),
        (bx + bw, by + bh - arm, bx + bw, by + bh), (bx + bw, by + bh, bx + bw - arm, by + bh),
        (bx + arm, by + bh, bx, by + bh), (bx, by + bh, bx, by + bh - arm),
    ]:
        b.append(
            f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{t["purple"]}" '
            f'stroke-width="2.5" stroke-linecap="round" fill="none"/>'
        )
    b.append(
        f'<path d="M{bx} {by + bh / 2} L{bx + bw} {by + bh / 2}" stroke="{t["purple"]}" '
        f'stroke-width="1.5" opacity="0.45" stroke-dasharray="5 5" fill="none"/>'
    )

    b.append(text(64, 118, "FaceProof", fill=t["text"], size=62, family=SANS,
                  weight="700", spacing="-1.5"))
    b.append(text(64, 156, "Consent-gated face identification for on-chain attestation",
                  fill=t["muted"], size=19, family=SANS))

    pills: List[Tuple[str, str]] = [
        ("InsightFace buffalo_l", t["blue"]), ("keccak256 commitments", t["purple"]),
        ("erasure path", t["red"]), ("167 tests", t["green"]),
    ]
    x = 64
    for label, colour in pills:
        w = 15 + int(len(label) * 6.9) + 15
        b.append(rect(x, 196, w, 30, fill=t["bg"], stroke=colour, rx=15, opacity=0.95))
        b.append(text(x + w / 2, 216, label, fill=colour, size=12, family=SANS,
                      weight="600", anchor="middle"))
        x += w + 10

    b.append(text(64, 262, "Hacker House Goa 2026  ·  Task 3  ·  Stage 1 — the probe",
                  fill=t["faint"], size=13, family=MONO, spacing="0.4"))
    return svg(W, H, "".join(b), "FaceProof — consent-gated face identification")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def pipeline(t: Dict[str, str]) -> str:
    W, H = 1200, 400
    b: List[str] = [rect(0, 0, W, H, fill=t["bg"], rx=0)]
    b.append(
        f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{t["muted"]}"/></marker>'
        f'<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{t["red"]}"/></marker>'
        f'<marker id="aa" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{t["amber"]}"/></marker></defs>'
    )

    def node(x, y, w, h, lines, *, accent, fill=None, dash=None, bold_first=True):
        out = [rect(x, y, w, h, fill=fill or t["panel"], stroke=accent, sw=1.6,
                    rx=8, dash=dash)]
        n = len(lines)
        y0 = y + h / 2 - (n - 1) * 8 + 4
        for i, ln in enumerate(lines):
            out.append(text(x + w / 2, y0 + i * 16, ln,
                            fill=accent if (i == 0 and bold_first) else t["muted"],
                            size=12 if i == 0 else 11, family=MONO,
                            weight="700" if (i == 0 and bold_first) else "400",
                            anchor="middle"))
        return "".join(out)

    def arrow(x1, y1, x2, y2, *, colour=None, marker="a", dash=None):
        c = colour or t["muted"]
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return (f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{c}" stroke-width="1.8" '
                f'fill="none" marker-end="url(#{marker})"{d}/>')

    ROW = 120
    b.append(node(40, ROW, 132, 66, ["probe image", "jpg / png"], accent=t["muted"]))
    b.append(arrow(172, ROW + 33, 214, ROW + 33))

    # The consent gate — the distinguishing element, so it gets the emphasis.
    b.append(rect(214, ROW - 12, 190, 90, fill=t["panel2"], stroke=t["purple"], sw=2.4, rx=8))
    b.append(text(309, ROW + 16, "CONSENT GATE", fill=t["purple"], size=13,
                  family=MONO, weight="700", anchor="middle"))
    b.append(text(309, ROW + 36, "granted · in scope", fill=t["muted"], size=11,
                  family=MONO, anchor="middle"))
    b.append(text(309, ROW + 52, "unexpired · not revoked", fill=t["muted"], size=11,
                  family=MONO, anchor="middle"))
    b.append(text(309, ROW - 24, "before cv2.imread", fill=t["purple"], size=11,
                  family=MONO, weight="600", anchor="middle"))

    b.append(arrow(404, ROW + 33, 452, ROW + 33))
    b.append(node(452, ROW, 128, 66, ["SCRFD", "detect"], accent=t["blue"]))
    b.append(arrow(580, ROW + 33, 622, ROW + 33))
    b.append(node(622, ROW, 150, 66, ["quality gate", "4 checks"], accent=t["blue"]))
    b.append(arrow(772, ROW + 33, 814, ROW + 33))
    b.append(node(814, ROW, 150, 66, ["ArcFace 512-d", "L2-normalised"], accent=t["green"]))
    b.append(arrow(964, ROW + 33, 1006, ROW + 33))
    b.append(node(1006, ROW, 154, 66, ["keccak256", "commitments"], accent=t["green"]))

    # Refusal branch
    b.append(arrow(309, ROW + 78, 309, ROW + 130, colour=t["red"], marker="ar"))
    b.append(text(319, ROW + 108, "no valid consent", fill=t["red"], size=11, family=MONO))
    b.append(node(214, ROW + 130, 190, 58, ["REFUSED   exit 2", "nothing was read"],
                  accent=t["red"]))

    # Abstain branch
    b.append(arrow(697, ROW + 66, 697, ROW + 130, colour=t["amber"], marker="aa"))
    b.append(text(707, ROW + 104, "fails a check", fill=t["amber"], size=11, family=MONO))
    b.append(node(622, ROW + 130, 150, 58, ["ABSTAIN   exit 1", "a valid outcome"],
                  accent=t["amber"]))

    # Both outcomes converge on the run directory: an abstain is recorded,
    # not discarded.
    BOX_X, BOX_W, BOX_Y = 320, 500, ROW + 202
    b.append(f'<path d="M1083 {ROW + 66} L1083 {BOX_Y + 30} L{BOX_X + BOX_W + 6} {BOX_Y + 30}" '
             f'stroke="{t["green"]}" stroke-width="1.8" fill="none" marker-end="url(#a)"/>')
    b.append(f'<path d="M697 {ROW + 188} L697 {BOX_Y}" stroke="{t["amber"]}" '
             f'stroke-width="1.8" fill="none" stroke-dasharray="4 4"/>')

    b.append(rect(BOX_X, BOX_Y, BOX_W, 60, fill=t["panel"], stroke=t["green"], sw=1.6, rx=8))
    b.append(text(BOX_X + 22, BOX_Y + 24, "out/run-<id>/", fill=t["green"], size=12,
                  family=MONO, weight="700"))
    b.append(text(BOX_X + 22, BOX_Y + 44, "probe.json   embedding.f32   manifest.jsonl",
                  fill=t["muted"], size=11.5, family=MONO))
    b.append(text(BOX_X + BOX_W - 20, BOX_Y + 24, "Stage 1 output", fill=t["faint"],
                  size=11, family=MONO, anchor="end"))

    b.append(arrow(BOX_X - 6, BOX_Y + 30, 258, BOX_Y + 30))
    b.append(node(40, BOX_Y, 210, 60, ["Stage 2 · discovery", "Stage 3 · attestation"],
                  accent=t["faint"], dash="5 4", bold_first=False))

    b.append(text(40, 42, "The pipeline", fill=t["text"], size=20, family=SANS, weight="700"))
    b.append(text(40, 66, "Consent is the first branch, not a printed disclaimer.",
                  fill=t["muted"], size=13, family=SANS))
    return svg(W, H, "".join(b), "FaceProof Stage 1 pipeline")


# ---------------------------------------------------------------------------
# Terminal cast — real `make demo` output
# ---------------------------------------------------------------------------

# (text, colour-key). "" is a blank line.
CAST: List[Tuple[str, str]] = [
    ("$ make probe SUBJECT=alice", "cmd"),
    ("probe run_start       run_id=20260905T193502Z-0f0b21", "log"),
    ("probe consent_denied  subject=alice  reason=no_consent_on_record", "red"),
    ("  CONSENT=DENIED   No face was detected, encoded, or stored.", "red"),
    ("exit 2", "faint"),
    ("", ""),
    ("$ make consent-grant SUBJECT=alice", "cmd"),
    ("  subject_commitment = 0x17392aa0207b2bd29b227e1201b438e373732bd7…", "log"),
    ("  token + 256-bit salt -> data/consent/store.json (mode 600)", "faint"),
    ("", ""),
    ("$ make probe SUBJECT=alice", "cmd"),
    ("probe consent_ok      scope=face_probe_demo  expires=2026-10-05", "green"),
    ("probe quality_gate    result=PASS  det_score=0.7729  face_px=199", "green"),
    ("                      blur_var=827.38  n_faces=1", "log"),
    ("probe encoded         dim=512  dtype=float32  l2_norm=1.0", "log"),
    ("probe commitment      embedding=0x2545e41b2ec3533cd0da374b6cbd02…", "log"),
    ("probe artifact        out/run-demo/probe.json  bytes=1906", "log"),
    ("                      sha256=50a7a72591c8c9bf…", "faint"),
    ("probe run_end         status=accepted", "green"),
    ("exit 0", "faint"),
    ("", ""),
    ("$ make consent-revoke SUBJECT=alice", "cmd"),
    ("  revoked_at = 2026-09-05T19:35:05Z", "log"),
    ("  salt       = DESTROYED", "red"),
    ("  every commitment ever made for this subject is now", "faint"),
    ("  permanently unverifiable — including one already on chain", "faint"),
    ("", ""),
    ("$ make probe SUBJECT=alice", "cmd"),
    ("probe consent_denied  subject=alice", "red"),
    ("                      reason=consent_revoked:2026-09-05T19:35:05Z", "red"),
    ("exit 2", "faint"),
]


def demo(t: Dict[str, str]) -> str:
    pad, top, lh, fs = 24, 46, 19, 13
    W = 760
    H = top + len(CAST) * lh + pad + 6
    colours = {"cmd": t["text"], "log": t["muted"], "green": t["green"],
               "red": t["red"], "faint": t["faint"], "": t["muted"]}

    b: List[str] = [rect(0, 0, W, H, fill=t["bg"], rx=0)]
    b.append(rect(0.5, 0.5, W - 1, H - 1, fill=t["panel"], stroke=t["border"], rx=10))
    b.append(f'<path d="M1 32 H{W - 1}" stroke="{t["border"]}" stroke-width="1"/>')
    for i, c in enumerate((t["red"], t["amber"], t["green"])):
        b.append(f'<circle cx="{20 + i * 18}" cy="16.5" r="5.5" fill="{c}" opacity="0.85"/>')
    b.append(text(W / 2, 21, "make demo", fill=t["faint"], size=11.5,
                  family=MONO, anchor="middle"))

    y = top + 14
    for line, key in CAST:
        if line:
            colour = colours[key]
            weight = "600" if key == "cmd" else "400"
            b.append(text(pad, y, line, fill=colour, size=fs, family=MONO, weight=weight))
        y += lh
    return svg(W, H, "".join(b), "make demo — real terminal output")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("hero", hero), ("pipeline", pipeline), ("demo", demo)):
        for theme, palette in THEMES.items():
            path = OUT / f"{name}-{theme}.svg"
            path.write_text(fn(palette) + "\n")
            print(f"  wrote {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
