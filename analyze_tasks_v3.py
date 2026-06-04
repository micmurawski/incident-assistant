"""
analyze_tasks_v3.py - Extends v2 with learning-cycle probability tracking.

Adds Figure 7:
  - Learning progress every N incidents (default: 5)
  - Probabilities for RCA, successful fix, visible recovery
  - Probability of perfect score (score = 3)
  - Baseline comparison against the no-learning cohort
"""

import os

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

import analyze_tasks_v2 as v2


def _compute_rate(metrics, key):
    if not metrics:
        return 0.0
    return float(np.mean([m.get(key, 0) for m in metrics])) * 100.0


def _compute_score3_rate(metrics):
    if not metrics:
        return 0.0
    return float(np.mean([1 if m.get("score", 0) == 3 else 0 for m in metrics])) * 100.0


def _checkpoint_sizes(n_items, interval):
    checkpoints = list(range(interval, n_items + 1, interval))
    if n_items > 0 and (not checkpoints or checkpoints[-1] != n_items):
        checkpoints.append(n_items)
    return checkpoints


def plot_fig7_learning_probabilities(root_nl, root_l, outfile, interval=5):
    """Plot cumulative learning-cycle success probabilities with baseline lines."""
    root_l_sorted = sorted(root_l, key=lambda x: x["created_at_dt"] or v2.datetime.min)
    checkpoints = _checkpoint_sizes(len(root_l_sorted), interval)
    if not checkpoints:
        print("  No learning root tasks for fig7.")
        return

    metric_specs = [
        ("root_cause_analysis", "RCA", v2.PALETTE["rca"]),
        ("successful_fix", "Fix", v2.PALETTE["fix"]),
        ("system_recovery_visible", "Recovery", v2.PALETTE["recovery"]),
    ]

    # Baseline across all no-learning incidents.
    baseline = {key: _compute_rate(root_nl, key) for key, _, _ in metric_specs}
    baseline_score3 = _compute_score3_rate(root_nl)

    # Learning cumulative trajectory at each checkpoint.
    series = {key: [] for key, _, _ in metric_specs}
    series_score3 = []
    for n in checkpoints:
        subset = root_l_sorted[:n]
        for key, _, _ in metric_specs:
            series[key].append(_compute_rate(subset, key))
        series_score3.append(_compute_score3_rate(subset))

    fig, (ax_top, ax_bot) = plt.subplots(
        2,
        1,
        figsize=(12, 8),
        facecolor="white",
        gridspec_kw={"height_ratios": [2, 1], "hspace": 0.24},
    )

    # Top panel: RCA/Fix/Recovery.
    for key, label, color in metric_specs:
        ax_top.plot(
            checkpoints,
            series[key],
            marker="o",
            linewidth=2.2,
            markersize=5,
            color=color,
            label=f"Learning {label}",
        )
        ax_top.axhline(
            baseline[key],
            linestyle="--",
            linewidth=1.5,
            color=color,
            alpha=0.45,
            label=f"Baseline {label} ({baseline[key]:.1f}%)",
        )

    ax_top.set_title(
        f"Learning Progress by Incident Checkpoint (every {interval})",
        fontsize=13,
        fontweight="bold",
    )
    ax_top.set_ylabel("Probability (%)")
    ax_top.set_ylim(0, 105)
    ax_top.yaxis.set_major_locator(mticker.MultipleLocator(20))
    ax_top.legend(loc="lower right", fontsize=8, frameon=True, ncol=2)
    ax_top.grid(axis="y", alpha=0.25)

    # Bottom panel: perfect score probability.
    ax_bot.plot(
        checkpoints,
        series_score3,
        marker="D",
        linewidth=2.4,
        markersize=5,
        color=v2.PALETTE["score3"],
        label="Learning Perfect Score (3/3)",
    )
    ax_bot.axhline(
        baseline_score3,
        linestyle="--",
        linewidth=1.6,
        color=v2.PALETTE["score3"],
        alpha=0.45,
        label=f"Baseline Perfect Score ({baseline_score3:.1f}%)",
    )
    ax_bot.set_ylabel("Probability (%)")
    ax_bot.set_ylabel("Probability (%)")
    ax_bot.set_xlabel("Learning Incidents Seen (cumulative)")
    max_score3 = max(series_score3 + [baseline_score3]) if series_score3 else baseline_score3
    ax_bot.set_ylim(0, min(100, max_score3 + 10))
    ax_bot.yaxis.set_major_locator(mticker.MultipleLocator(20))
    ax_bot.grid(axis="y", alpha=0.25)
    ax_bot.legend(loc="lower right", fontsize=8, frameon=True)

    # Keep x ticks readable and anchored to checkpoints.
    ax_bot.set_xticks(checkpoints)
    ax_bot.set_xticklabels([str(x) for x in checkpoints], fontsize=9)

    summary = (
        f"{v2.LABEL_NO_LEARNING}: n={len(root_nl)}  |  "
        f"{v2.LABEL_LEARNING}: n={len(root_l)}"
    )
    ax_top.text(
        0.01,
        0.97,
        summary,
        transform=ax_top.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=v2.PALETTE["grid"]),
    )

    v2.sns.despine(ax=ax_top)
    v2.sns.despine(ax=ax_bot)
    fig.savefig(outfile)
    plt.close(fig)
    print(f"  Saved {outfile}")


def analyze():
    db_no_learning = "./agent_no_learning.db"
    db_agent = "./agent.db"

    print("Loading databases ...")
    metrics_nl = v2.get_metrics(db_no_learning)
    metrics_l = v2.get_metrics(db_agent)

    if not metrics_nl or not metrics_l:
        print("Both databases are required for comparison.")
        return

    root_nl, child_nl, tools_nl = metrics_nl
    root_l, child_l, tools_l = metrics_l

    print(f"  {v2.LABEL_NO_LEARNING}: {len(root_nl)} root, {len(child_nl)} child tasks")
    print(f"  {v2.LABEL_LEARNING}:    {len(root_l)} root, {len(child_l)} child tasks\n")

    out_dir = "./figures"
    os.makedirs(out_dir, exist_ok=True)

    print("Generating figures ...")
    v2.plot_fig1_success(root_nl, root_l, f"{out_dir}/fig1_success_comparison.png")
    v2.plot_fig2_operational(
        root_nl,
        child_nl,
        tools_nl,
        root_l,
        child_l,
        tools_l,
        f"{out_dir}/fig2_operational_comparison.png",
    )
    v2.plot_fig3_timeline(root_nl, root_l, f"{out_dir}/fig3_chronological_timeline.png")
    v2.plot_fig4_tools(tools_nl, tools_l, f"{out_dir}/fig4_failing_tools.png")
    v2.plot_fig5_playbook_evolution(
        "./playbook_history_minimax_25_45",
        f"{out_dir}/fig5_playbook_evolution.png",
    )
    v2.plot_fig6_tree_structure(root_nl, root_l, f"{out_dir}/fig6_tree_structure.png")
    plot_fig7_learning_probabilities(
        root_nl,
        root_l,
        f"{out_dir}/fig7_learning_cycle_probabilities.png",
        interval=5,
    )

    v2.print_terminal_tables(root_nl, child_nl, tools_nl, root_l, child_l, tools_l)
    print("\nDone. All figures saved to ./figures/")


if __name__ == "__main__":
    analyze()
