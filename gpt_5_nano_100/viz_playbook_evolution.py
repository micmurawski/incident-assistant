"""Render playbook snapshots with each bullet colored by the phase in which it was first added.

Each snapshot file is named ``<agent>-<timestamp>.json`` (see
``agent/ace/playbook_history_minimax_25_45/``).  Snapshots sorted by timestamp
define "phases" (phase 0 = oldest snapshot, phase N-1 = newest).  For every
bullet ``id`` we record the phase in which it first appeared and render the
*final* playbook with each bullet colored by that birth phase.

Usage
-----
    python viz_playbook_evolution.py \
        --history-dir agent/ace/playbook_history_minimax_25_45 \
        --out-html playbook_evolution.html

    # Terminal output (ANSI 256-color) for a single agent
    python viz_playbook_evolution.py \
        --history-dir agent/ace/playbook_history_minimax_25_45 \
        --agent incident_commander \
        --ansi
"""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path


FILENAME_RE = re.compile(r"^(?P<agent>[a-z_]+)-(?P<ts>\d+)\.json$")


@dataclass
class Snapshot:
    agent: str
    timestamp: int
    path: Path
    data: dict


def load_snapshots(history_dir: Path) -> dict[str, list[Snapshot]]:
    """Group snapshots by agent, sorted by timestamp ascending."""
    by_agent: dict[str, list[Snapshot]] = defaultdict(list)
    for p in sorted(history_dir.iterdir()):
        m = FILENAME_RE.match(p.name)
        if not m:
            continue
        with p.open() as f:
            data = json.load(f)
        by_agent[m.group("agent")].append(
            Snapshot(agent=m.group("agent"), timestamp=int(m.group("ts")), path=p, data=data)
        )
    for agent in by_agent:
        by_agent[agent].sort(key=lambda s: s.timestamp)
    return dict(by_agent)


def compute_birth_phase(snapshots: list[Snapshot]) -> dict[str, int]:
    """Return {bullet_id: phase_index_of_first_appearance}."""
    birth: dict[str, int] = {}
    for phase, snap in enumerate(snapshots):
        for _, bullets in snap.data.get("sections", {}).items():
            for b in bullets:
                bid = b.get("id")
                if bid and bid not in birth:
                    birth[bid] = phase
    return birth


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

# 10-step viridis-ish palette (perceptually uniform-ish, dark->bright).
# Generated from matplotlib.cm.viridis at 10 linearly spaced points.
VIRIDIS_10 = [
    "#440154",
    "#482475",
    "#414487",
    "#355f8d",
    "#2a788e",
    "#21918c",
    "#22a884",
    "#44bf70",
    "#7ad151",
    "#bddf26",
]


def phase_color(phase: int, n_phases: int) -> str:
    """Pick a color for a phase index, adapting to number of phases."""
    if n_phases <= 1:
        return VIRIDIS_10[0]
    # map phase in [0, n_phases-1] into [0, len(palette)-1]
    idx = round(phase * (len(VIRIDIS_10) - 1) / (n_phases - 1))
    return VIRIDIS_10[idx]


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_ansi256(r: int, g: int, b: int) -> int:
    """Map 24-bit RGB to the nearest ANSI 256-color index (6x6x6 cube)."""

    def q(c: int) -> int:
        if c < 48:
            return 0
        if c < 115:
            return 1
        return (c - 35) // 40

    return 16 + 36 * q(r) + 6 * q(g) + q(b)


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------


def render_agent_html(agent: str, snapshots: list[Snapshot]) -> str:
    birth = compute_birth_phase(snapshots)
    n_phases = len(snapshots)
    final = snapshots[-1].data

    parts: list[str] = []
    parts.append(f'<section class="agent"><h2>{escape(agent)}</h2>')

    # Legend: one swatch per phase with its timestamp
    parts.append('<div class="legend"><span class="legend-label">phases:</span>')
    for phase, snap in enumerate(snapshots):
        c = phase_color(phase, n_phases)
        parts.append(
            f'<span class="swatch" style="background:{c}" '
            f'title="{snap.timestamp}">{phase}</span>'
        )
    parts.append("</div>")

    for section, bullets in final.get("sections", {}).items():
        parts.append(f'<h3>{escape(section)}</h3><ul class="bullets">')
        for b in bullets:
            bid = b.get("id", "")
            phase = birth.get(bid, n_phases - 1)
            c = phase_color(phase, n_phases)
            helpful = b.get("helpful", 0)
            harmful = b.get("harmful", 0)
            content = escape(b.get("content", ""))
            parts.append(
                f'<li style="border-left:6px solid {c};">'
                f'<div class="meta"><code>{escape(bid)}</code>'
                f' <span class="phase-tag" style="background:{c}">phase {phase}</span>'
                f' <span class="caption">helpful {helpful} &middot; harmful {harmful}</span>'
                f'</div>'
                f'<div class="content">{content}</div></li>'
            )
        parts.append("</ul>")
    parts.append("</section>")
    return "\n".join(parts)


HTML_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       max-width: 1100px; margin: 2rem auto; padding: 0 1rem; color: #222; }
h1 { margin-bottom: 0.3rem; }
h2 { margin-top: 2.5rem; border-bottom: 2px solid #ddd; padding-bottom: 0.2rem; }
h3 { margin-top: 1.4rem; color: #444; font-size: 1.05rem; }
.legend { margin: 0.6rem 0 1rem; display: flex; gap: 0.25rem; align-items: center;
          flex-wrap: wrap; }
.legend-label { color: #666; margin-right: 0.3rem; font-size: 0.85rem; }
.swatch { display: inline-block; width: 1.6rem; height: 1.2rem; line-height: 1.2rem;
          text-align: center; color: white; font-size: 0.75rem; border-radius: 3px; }
ul.bullets { list-style: none; padding: 0; margin: 0; }
ul.bullets li { background: #fafafa; margin: 0.4rem 0; padding: 0.6rem 0.8rem;
                border-radius: 4px; }
.meta { font-size: 0.8rem; color: #555; margin-bottom: 0.3rem; }
.meta code { background: #eee; padding: 0 0.3rem; border-radius: 3px; }
.phase-tag { color: white; padding: 0.05rem 0.4rem; border-radius: 3px;
             font-size: 0.72rem; margin-left: 0.4rem; }
.caption { color: #888; font-size: 0.75rem; margin-left: 0.5rem;
           font-style: italic; }
.content { font-size: 0.95rem; line-height: 1.45; white-space: pre-wrap; }
"""


def render_html(by_agent: dict[str, list[Snapshot]], title: str) -> str:
    body = "\n".join(render_agent_html(a, snaps) for a, snaps in by_agent.items())
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>{HTML_CSS}</style></head>
<body><h1>{escape(title)}</h1>
<p>Each bullet is tinted by the <strong>phase</strong> (snapshot index) in which
it first appeared. Phase 0 = oldest, phase N-1 = newest.</p>
{body}
</body></html>"""


# ---------------------------------------------------------------------------
# ANSI rendering
# ---------------------------------------------------------------------------


def render_agent_ansi(agent: str, snapshots: list[Snapshot]) -> str:
    birth = compute_birth_phase(snapshots)
    n_phases = len(snapshots)
    final = snapshots[-1].data

    RESET = "\x1b[0m"
    BOLD = "\x1b[1m"
    DIM = "\x1b[2m"

    lines: list[str] = []
    lines.append(f"\n{BOLD}=== {agent} ==={RESET}")

    # Legend
    legend_parts = []
    for phase in range(n_phases):
        r, g, b = hex_to_rgb(phase_color(phase, n_phases))
        code = rgb_to_ansi256(r, g, b)
        legend_parts.append(f"\x1b[48;5;{code}m\x1b[38;5;15m {phase:>2} {RESET}")
    lines.append("phases: " + "".join(legend_parts))

    for section, bullets in final.get("sections", {}).items():
        lines.append(f"\n{BOLD}{section}{RESET}")
        for b in bullets:
            bid = b.get("id", "")
            phase = birth.get(bid, n_phases - 1)
            r, g, bl = hex_to_rgb(phase_color(phase, n_phases))
            code = rgb_to_ansi256(r, g, bl)
            tag = f"\x1b[48;5;{code}m\x1b[38;5;15m p{phase:02d} {RESET}"
            helpful = int(b.get("helpful", 0))
            harmful = int(b.get("harmful", 0))
            content = b.get("content", "")
            caption = f"{DIM}(helpful {helpful} \u00b7 harmful {harmful}){RESET}"
            lines.append(f"  {tag} {DIM}{bid}{RESET}  {caption}")
            # indent wrapped content, color-left-border via 38;5 vertical bar
            for cl in content.splitlines() or [""]:
                lines.append(
                    f"      \x1b[38;5;{code}m\u2502{RESET} {cl}"
                )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PNG rendering (matplotlib)
# ---------------------------------------------------------------------------


def render_agent_png(
    agent: str,
    snapshots: list[Snapshot],
    out_path: Path,
    wrap_chars: int = 110,
    fig_width_in: float = 13.0,
    dpi: int = 150,
) -> None:
    """Render one agent's final playbook to a PNG.

    Each bullet gets a colored left border and a small "phase N" tag
    indicating when it was first added.  matplotlib is imported lazily so the
    HTML/ANSI paths don't require it.
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    birth = compute_birth_phase(snapshots)
    n_phases = len(snapshots)
    final = snapshots[-1].data

    # Build a flat list of "rows" to draw.  A row is a (kind, ...) tuple and
    # has a known height in "line units"; we compute total height from this.
    # Kinds:
    #   ("title", text)                    -> 1.6 lu
    #   ("legend", n_phases)               -> 1.6 lu
    #   ("section", text)                  -> 1.4 lu
    #   ("bullet", bid, phase, meta, lines)-> 0.4 (gap) + 1.0 (meta) + len(lines)*1.0
    rows: list[tuple] = []
    rows.append(("title", agent))
    rows.append(("legend", n_phases))
    for section, bullets in final.get("sections", {}).items():
        rows.append(("section", section))
        for b in bullets:
            bid = b.get("id", "")
            phase = birth.get(bid, n_phases - 1)
            helpful = int(b.get("helpful", 0))
            harmful = int(b.get("harmful", 0))
            content = b.get("content", "")
            lines = []
            for paragraph in content.splitlines() or [""]:
                wrapped = textwrap.wrap(paragraph, width=wrap_chars) or [""]
                lines.extend(wrapped)
            rows.append(("bullet", bid, phase, helpful, harmful, lines))

    # Pre-compute total height in line units.
    def row_height(r: tuple) -> float:
        kind = r[0]
        if kind == "title":
            return 1.8
        if kind == "legend":
            return 1.6
        if kind == "section":
            return 1.6
        if kind == "bullet":
            lines = r[5]
            return 0.5 + 1.0 + 1.0 * len(lines) + 0.4
        return 1.0

    total_lu = sum(row_height(r) for r in rows) + 1.0  # top/bottom padding

    # Pick line height so that font sizes render reasonably.
    line_height_in = 0.19
    fig_height_in = total_lu * line_height_in + 0.6

    fig, ax = plt.subplots(figsize=(fig_width_in, fig_height_in), dpi=dpi)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, total_lu)
    ax.invert_yaxis()
    ax.set_axis_off()

    y = 0.5  # top padding
    for r in rows:
        kind = r[0]
        if kind == "title":
            ax.text(
                0.5,
                y + 0.2,
                r[1],
                fontsize=18,
                fontweight="bold",
                va="top",
                ha="left",
            )
            y += 1.8
        elif kind == "legend":
            n = r[1]
            ax.text(0.5, y + 0.15, "phases:", fontsize=9, color="#555", va="top")
            # Draw n swatches from x=8 onwards, up to x=50
            swatch_w = min(3.5, 42.0 / max(n, 1))
            for phase in range(n):
                c = phase_color(phase, n)
                x0 = 8 + phase * swatch_w
                ax.add_patch(
                    Rectangle(
                        (x0, y + 0.15),
                        swatch_w * 0.9,
                        1.0,
                        facecolor=c,
                        edgecolor="none",
                    )
                )
                ax.text(
                    x0 + swatch_w * 0.45,
                    y + 0.65,
                    str(phase),
                    fontsize=8,
                    color="white",
                    va="center",
                    ha="center",
                    fontweight="bold",
                )
            y += 1.6
        elif kind == "section":
            ax.text(
                0.5,
                y + 0.2,
                r[1],
                fontsize=12,
                fontweight="bold",
                color="#333",
                va="top",
            )
            # horizontal rule
            ax.plot([0.5, 99.5], [y + 1.2, y + 1.2], color="#dddddd", linewidth=0.6)
            y += 1.6
        elif kind == "bullet":
            _, bid, phase, helpful, harmful, lines = r
            c = phase_color(phase, n_phases)
            block_top = y + 0.3
            block_bot = block_top + 1.0 + 1.0 * len(lines) + 0.1
            # left color border
            ax.add_patch(
                Rectangle(
                    (0.5, block_top),
                    0.7,
                    block_bot - block_top,
                    facecolor=c,
                    edgecolor="none",
                )
            )
            # faint background
            ax.add_patch(
                Rectangle(
                    (1.3, block_top),
                    98.2,
                    block_bot - block_top,
                    facecolor="#fafafa",
                    edgecolor="none",
                )
            )

            # Phase pill
            pill_y = block_top + 0.1
            pill_h = 0.8
            ax.add_patch(
                Rectangle(
                    (2.0, pill_y),
                    4.0,
                    pill_h,
                    facecolor=c,
                    edgecolor="none",
                )
            )
            ax.text(
                4.0,
                pill_y + pill_h / 2,
                f"p{phase:02d}",
                fontsize=8,
                color="white",
                fontweight="bold",
                va="center",
                ha="center",
            )
            # id + small caption
            ax.text(
                6.8,
                block_top + 0.5,
                bid,
                fontsize=8,
                color="#666",
                family="monospace",
                va="center",
                ha="left",
            )
            ax.text(
                99.0,
                block_top + 0.5,
                f"helpful {helpful} \u00b7 harmful {harmful}",
                fontsize=7.5,
                color="#888",
                style="italic",
                va="center",
                ha="right",
            )
            # content lines
            for i, ln in enumerate(lines):
                ax.text(
                    2.0,
                    block_top + 1.2 + i * 1.0,
                    ln,
                    fontsize=9,
                    color="#1d1d1d",
                    va="top",
                    ha="left",
                )
            y = block_bot + 0.4

    fig.tight_layout(pad=0.3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--history-dir",
        type=Path,
        default=Path("playbook_history_minimax_25_45"),
        help="Directory containing <agent>-<timestamp>.json snapshots.",
    )
    ap.add_argument(
        "--agent",
        default=None,
        help="Render only this agent (default: all).",
    )
    ap.add_argument(
        "--out-html",
        type=Path,
        default=Path("playbook_evolution.html"),
        help="Output HTML file path.",
    )
    ap.add_argument(
        "--ansi",
        action="store_true",
        help="Print ANSI-colored playbook to stdout instead of writing HTML.",
    )
    ap.add_argument(
        "--out-png-dir",
        type=Path,
        default=None,
        help="If set, write one PNG per agent into this directory "
        "(filename: <agent>.png).",
    )
    ap.add_argument(
        "--title",
        default="Playbook evolution by phase",
    )
    args = ap.parse_args()

    by_agent = load_snapshots(args.history_dir)
    if not by_agent:
        raise SystemExit(f"No snapshots found in {args.history_dir}")

    if args.agent:
        if args.agent not in by_agent:
            raise SystemExit(
                f"Unknown agent '{args.agent}'. Available: {sorted(by_agent)}"
            )
        by_agent = {args.agent: by_agent[args.agent]}

    if args.ansi:
        for agent, snaps in by_agent.items():
            print(render_agent_ansi(agent, snaps))
        return

    if args.out_png_dir is not None:
        for agent, snaps in by_agent.items():
            out_path = args.out_png_dir / f"{agent}.png"
            render_agent_png(agent, snaps, out_path)
            print(f"Wrote {out_path}")
        return

    html = render_html(by_agent, args.title)
    args.out_html.write_text(html)
    total_phases = {a: len(s) for a, s in by_agent.items()}
    print(f"Wrote {args.out_html} (agents: {total_phases})")


if __name__ == "__main__":
    main()
