"""The four default color sets (Bear Brown, Brutalist, Northeastern, Humanitarians AI).

Shared, unchanged, by figma-webdesigner and figma-appdesigner. Standard library only.
Reads palettes/palettes.json, checks it, and works out WCAG contrast ratios so nobody has to
trust a ratio typed into a comment.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROLES = ["ground", "surface", "ink", "ink-soft", "border", "accent", "on-accent"]
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# (label, foreground role, background role, least ratio, what the least ratio is for)
PAIRS = [
    ("text", "ink", "ground", 4.5, "body text (WCAG 1.4.3)"),
    ("text on cards", "ink", "surface", 4.5, "body text (WCAG 1.4.3)"),
    ("secondary text", "ink-soft", "ground", 4.5, "body text (WCAG 1.4.3)"),
    ("secondary text on cards", "ink-soft", "surface", 4.5, "body text (WCAG 1.4.3)"),
    ("button label", "on-accent", "accent", 4.5, "body text (WCAG 1.4.3)"),
    ("button against the page", "accent", "ground", 3.0, "a control's edge (WCAG 1.4.11)"),
]


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def load(repo: Path) -> dict:
    return json.loads((repo / "palettes" / "palettes.json").read_text())


def ids(data: dict) -> list[str]:
    return [p["id"] for p in data["palettes"]]


def find(data: dict, palette_id: str) -> dict | None:
    return next((p for p in data["palettes"] if p["id"] == palette_id), None)


def problems(data: dict) -> list[str]:
    """Structural problems in the file. Empty means it is usable."""
    out: list[str] = []
    seen = set()
    for p in data.get("palettes", []):
        pid = p.get("id", "?")
        if pid in seen:
            out.append(f"{pid}: listed twice")
        seen.add(pid)
        for key in ("name", "source", "modes"):
            if not p.get(key):
                out.append(f"{pid}: missing {key}")
        if "light" not in p.get("modes", {}):
            out.append(f"{pid}: has no light mode")
        for mode, roles in p.get("modes", {}).items():
            for r in ROLES:
                v = roles.get(r)
                if not v or not HEX.match(v):
                    out.append(f"{pid} {mode}: role {r} is not a #RRGGBB color ({v!r})")
        for name, v in p.get("named", {}).items():
            if not HEX.match(v):
                out.append(f"{pid}: named color {name} is not a #RRGGBB color ({v!r})")
    wf = data.get("wireframe")
    if wf is not None:
        for r in ROLES:
            v = wf.get("roles", {}).get(r)
            if not v or not HEX.match(v):
                out.append(f"wireframe: role {r} is not a #RRGGBB color ({v!r})")
    if data.get("default") not in seen:
        out.append(f"default {data.get('default')!r} is not one of the palettes")
    return out


def wireframe(data: dict) -> dict | None:
    """The grey set as a palette-shaped dict (light mode only), or None if the file has none."""
    wf = data.get("wireframe")
    if not wf:
        return None
    return {"id": "wireframe", "name": wf["name"], "source": "this tool", "how_read": "chosen here; greys only",
            "type": wf["type"], "modes": {"light": wf["roles"]}, "named": {}, "notes": [wf["about"]]}


def checks(palette: dict) -> list[dict]:
    """Contrast of every text and control pairing, per mode. Nothing is hidden: fails are listed."""
    out = []
    for mode, roles in palette["modes"].items():
        for label, fg, bg, least, what in PAIRS:
            ratio = contrast(roles[fg], roles[bg])
            out.append({"mode": mode, "pair": label, "fg": roles[fg], "bg": roles[bg],
                        "ratio": round(ratio, 2), "least": least, "passes": ratio >= least, "for": what})
    return out


def print_list(data: dict, say=print) -> None:
    say(f"The default color sets (read from each site on {data['checked']}):\n")
    w = max(len(p["id"]) for p in data["palettes"])
    for p in data["palettes"]:
        star = "*" if p["id"] == data["default"] else " "
        modes = " and ".join(p["modes"])
        light = p["modes"]["light"]
        say(f" {star} {p['id']:<{w}}  {p['name']:<17} ground {light['ground']}  ink {light['ink']}  accent {light['accent']}  ({modes})")
        say(f"   {'':<{w}}  from {p['source']}")
    say(f"\n * = used when you choose nothing. Pick one by its id in your intent or brief (palette: {data['default']}).")
    if data.get("wireframe"):
        say("   Wireframes are drawn in a grey set of their own (see it with: palettes wireframe).")


def print_one(palette: dict, say=print) -> None:
    say(f"{palette['name']}  ({palette['id']})")
    say(f"Read from {palette['source']}: {palette['how_read']}.")
    t = palette.get("type", {})
    if t:
        say(f"Type: {t.get('heading')} headings, {t.get('body')} body.")
    for mode, roles in palette["modes"].items():
        say(f"\n{mode.upper()}")
        for r in ROLES:
            say(f"  {r:<10} {roles[r]}")
    if palette.get("named"):
        say("\nNAMED ON THE SITE")
        for name, v in palette["named"].items():
            say(f"  {v}  {name}")
    say("\nCONTRAST (worked out here, not copied)")
    for c in checks(palette):
        mark = "ok  " if c["passes"] else "LOW "
        say(f"  {mark} {c['mode']:<5} {c['pair']:<24} {c['fg']} on {c['bg']}  {c['ratio']:>5.2f}:1  (needs {c['least']}:1, {c['for']})")
    if palette.get("notes"):
        say("\nNOTES")
        for n in palette["notes"]:
            say(f"  - {n}")


def figma_modes(data: dict, palette_id: str | None = None) -> list[dict]:
    """One entry per Figma variable mode: each color set's light mode, then its dark mode if it has one."""
    out = []
    for p in data["palettes"]:
        if palette_id and p["id"] != palette_id:
            continue
        for mode, roles in p["modes"].items():
            out.append({"name": p["name"] + ("" if mode == "light" else " " + mode), "id": p["id"], "mode": mode,
                        "heading": p["type"]["heading"], "body": p["type"]["body"], "roles": roles})
    wf = data.get("wireframe")
    if wf:  # always last, so the first mode (Figma's default) stays a real color set
        out.append({"name": wf["name"], "id": "wireframe", "mode": "light",
                    "heading": wf["type"]["heading"], "body": wf["type"]["body"], "roles": wf["roles"]})
    return out


def figma_script(repo: Path, data: dict, palette_id: str | None = None) -> str:
    """figma/palette-variables.js with the colors filled in, ready to hand to the Figma MCP's use_figma."""
    template = (repo / "figma" / "palette-variables.js").read_text()
    if template.count("__MODES__") != 1:
        raise ValueError("figma/palette-variables.js must contain __MODES__ exactly once")
    return template.replace("__MODES__", json.dumps(figma_modes(data, palette_id), separators=(",", ":")))
