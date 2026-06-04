"""
analyze_tasks_v2.py – Publication-quality comparison of learning vs. no-learning SRE agents.

Produces five figures:
  1. fig1_success_comparison   – Overall & per-incident-type success rates
  2. fig2_operational_comparison – TTR, trajectory, tool usage, error rates
  3. fig3_chronological_timeline – Per-episode score timeline (aligned)
  4. fig4_failing_tools          – Top failing tools side-by-side
  5. fig5_playbook_evolution     – Token count of playbooks across revisions
"""

import sqlite3
import json
import os
import re
import glob as globmod
import argparse
from collections import defaultdict
from datetime import datetime
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np
import seaborn as sns

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------
sns.set_theme(style="whitegrid", font_scale=1.1)
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.dpi": 200,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.15,
})

PALETTE = {
    "learning": "#2563EB",
    "no_learning": "#F59E0B",
    "learning_light": "#93C5FD",
    "no_learning_light": "#FDE68A",
    "rca": "#6366F1",
    "fix": "#10B981",
    "recovery": "#F97316",
    "score3": "#16A34A",
    "score2": "#A3E635",
    "score1": "#FB923C",
    "score0": "#DC2626",
    "grid": "#E5E7EB",
    "text": "#1F2937",
    "bg": "#FAFAFA",
}

LABEL_LEARNING = "With Learning"
LABEL_NO_LEARNING = "Without Learning"

INCIDENT_LABELS = {
    "1": "Type 1",
    "2": "Type 2",
    "3": "Type 3",
    "4": "Type 4",
}

# ---------------------------------------------------------------------------
# Data helpers (reused from V1)
# ---------------------------------------------------------------------------
DEFAULT_SUCCESS_METRICS = {
    "root_cause_analysis": 0,
    "successful_fix": 0,
    "system_recovery_visible": 0,
}


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
    return None


def _normalize_success_metrics(raw: dict) -> dict:
    return {
        "root_cause_analysis": int(raw.get("root_cause_analysis", 0)),
        "successful_fix": int(raw.get("successful_fix", 0)),
        "system_recovery_visible": int(raw.get("system_recovery_visible", 0)),
    }


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    candidates = []
    if "```json" in text:
        part = text.split("```json")[-1]
        candidates.append(part.split("```")[0].strip())
    candidates.append(text.strip())
    decoder = json.JSONDecoder()
    for candidate in candidates:
        if not candidate:
            continue
        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        for idx, ch in enumerate(candidate):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(candidate[idx:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def extract_success_metrics(task: dict, db_label: str) -> dict:
    try:
        conversation = json.loads(task["conversation"])
        if not conversation:
            return dict(DEFAULT_SUCCESS_METRICS)
        last = conversation[-1]
        content = last.get("content", "") if isinstance(last, dict) else ""
        if isinstance(content, list):
            content = "\n".join(
                x.get("text", "") for x in content if isinstance(x, dict)
            )
        elif not isinstance(content, str):
            content = str(content)
        parsed = _extract_json_object(content)
        if parsed is None:
            return dict(DEFAULT_SUCCESS_METRICS)
        return _normalize_success_metrics(parsed)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
        return dict(DEFAULT_SUCCESS_METRICS)


def count_tool_stats(messages_history):
    if not messages_history:
        return 0, 0, {}
    try:
        messages = json.loads(messages_history)
    except Exception:
        return 0, 0, {}
    uses, errors = 0, 0
    failing_tools = {}
    tool_map = {}
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "tool_use":
                    uses += 1
                    tool_map[item.get("id")] = item.get("name")
                elif item.get("type") == "tool_result":
                    if item.get("is_error") is True:
                        errors += 1
                        tool_name = tool_map.get(item.get("tool_use_id"), "unknown")
                        failing_tools[tool_name] = failing_tools.get(tool_name, 0) + 1
    return uses, errors, failing_tools


# ---------------------------------------------------------------------------
# Database -> metrics
# ---------------------------------------------------------------------------
def get_metrics(db_path):
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks")
    rows = cursor.fetchall()

    tasks = {}
    for row in rows:
        tasks[row["id"]] = dict(row)
        tasks[row["id"]]["children_ids"] = (
            json.loads(row["children"]) if row["children"] else []
        )
        tasks[row["id"]]["todo_list_data"] = (
            json.loads(row["todo_list"]) if row["todo_list"] else []
        )
        tasks[row["id"]]["created_at_dt"] = parse_date(row["created_at"])
        tasks[row["id"]]["resolved_at_dt"] = parse_date(row["resolved_at"])

    root_metrics = []
    child_metrics = []
    global_failing_tools = {}
    root_id_cache = {}

    def get_subtree_stats(task_id, current_depth):
        task = tasks[task_id]
        all_descendants = []
        level_counts = defaultdict(int)
        max_d = current_depth
        for child_id in task["children_ids"]:
            if child_id in tasks:
                level_counts[current_depth + 1] += 1
                descendants, child_max_d, child_levels = get_subtree_stats(
                    child_id, current_depth + 1
                )
                all_descendants.append(child_id)
                all_descendants.extend(descendants)
                max_d = max(max_d, child_max_d)
                for lvl, cnt in child_levels.items():
                    level_counts[lvl] += cnt
        return all_descendants, max_d, level_counts

    def get_root_id(task_id):
        if task_id in root_id_cache:
            return root_id_cache[task_id]
        current_id = task_id
        visited = set()
        while current_id in tasks and current_id not in visited:
            visited.add(current_id)
            parent = tasks[current_id].get("parent")
            if not parent:
                root_id_cache[task_id] = current_id
                return current_id
            current_id = parent
        root_id_cache[task_id] = task_id
        return task_id

    for tid, t in tasks.items():
        is_root = not t["parent"] or t["parent"] == ""
        created = t["created_at_dt"]
        resolved = t["resolved_at_dt"]
        ttr = (resolved - created).total_seconds() if created and resolved else None

        messages_history = t["messages_history"]
        try:
            trajectory_len = len(json.loads(messages_history))
        except Exception:
            trajectory_len = 0

        descendants, max_d, level_counts = get_subtree_stats(tid, 0)
        tool_uses, tool_errors, failing_tools = count_tool_stats(messages_history)
        for tool_name, count in failing_tools.items():
            global_failing_tools[tool_name] = global_failing_tools.get(tool_name, 0) + count

        error_rate = (tool_errors / tool_uses * 100) if tool_uses > 0 else 0

        metric = {
            "id": tid,
            "root_id": tid if is_root else get_root_id(tid),
            "ttr": ttr,
            "trajectory_length": trajectory_len,
            "iterations_count": t.get("iterations_count", 0),
            "child_count": len(descendants),
            "max_depth": max_d,
            "tool_uses": tool_uses,
            "tool_errors": tool_errors,
            "tool_error_rate": error_rate,
            "failing_tools": dict(failing_tools),
            "created_at_dt": created,
        }

        if is_root:
            parts = tid.split("-")
            metric["incident_type"] = parts[1] if len(parts) > 1 else "unknown"
            metric["service_name"] = parts[2] if len(parts) > 2 else "unknown"
            metric["level_counts"] = dict(level_counts)
            success = extract_success_metrics(t, db_path)
            metric.update(success)
            metric["score"] = (
                metric.get("root_cause_analysis", 0)
                + metric.get("successful_fix", 0)
                + metric.get("system_recovery_visible", 0)
            )
            root_metrics.append(metric)
        else:
            metric["todo_count"] = len(t["todo_list_data"])
            child_metrics.append(metric)

    conn.close()
    return root_metrics, child_metrics, global_failing_tools


def _aggregate_failing_tools(metrics):
    aggregated = {}
    for m in metrics:
        for tool_name, count in m.get("failing_tools", {}).items():
            aggregated[tool_name] = aggregated.get(tool_name, 0) + count
    return aggregated


def _select_incidents(root_nl, child_nl, root_l, child_l, incident_limit):
    if incident_limit is None:
        return root_nl, child_nl, root_l, child_l

    root_nl_sorted = sorted(root_nl, key=lambda x: x["created_at_dt"] or datetime.min)
    selected_nl = root_nl_sorted[:incident_limit]
    selected_ids = {m["id"] for m in selected_nl}

    selected_l = [m for m in root_l if m["id"] in selected_ids]
    selected_l_sorted = sorted(selected_l, key=lambda x: x["created_at_dt"] or datetime.min)

    selected_root_ids_nl = {m["id"] for m in selected_nl}
    selected_root_ids_l = {m["id"] for m in selected_l_sorted}

    selected_child_nl = [m for m in child_nl if m.get("root_id") in selected_root_ids_nl]
    selected_child_l = [m for m in child_l if m.get("root_id") in selected_root_ids_l]

    return selected_nl, selected_child_nl, selected_l_sorted, selected_child_l


# ---------------------------------------------------------------------------
# Helper: annotate bar
# ---------------------------------------------------------------------------
def _annotate_bars(ax, bars, fmt="{:.0f}%", fontsize=9, offset=1.5):
    for bar in bars:
        h = bar.get_height()
        if h > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h + offset,
                fmt.format(h),
                ha="center",
                va="bottom",
                fontsize=fontsize,
                color=PALETTE["text"],
                fontweight="semibold",
            )


def _stat_text(values, unit=""):
    if not values:
        return "n=0"
    med = np.median(values)
    mean = np.mean(values)
    return f"med={med:.0f}{unit}  μ={mean:.0f}{unit}  n={len(values)}"


# ---------------------------------------------------------------------------
# Figure 1 – Success Metrics Comparison
# ---------------------------------------------------------------------------
def plot_fig1_success(root_nl, root_l, outfile):
    fig = plt.figure(figsize=(14, 10.5), facecolor="white")
    gs = gridspec.GridSpec(3, 2, hspace=0.45, wspace=0.30,
                           height_ratios=[1, 0.8, 1.2])

    # ---- 1a: Overall success rates (grouped bar) ----
    ax1 = fig.add_subplot(gs[0, :])
    metric_names = ["Root Cause\nAnalysis", "Successful\nFix", "System\nRecovery"]
    metric_keys = ["root_cause_analysis", "successful_fix", "system_recovery_visible"]

    n_nl = len(root_nl)
    n_l = len(root_l)

    rates_nl = [
        sum(m.get(k, 0) for m in root_nl) / n_nl * 100 if n_nl else 0
        for k in metric_keys
    ]
    rates_l = [
        sum(m.get(k, 0) for m in root_l) / n_l * 100 if n_l else 0
        for k in metric_keys
    ]

    x = np.arange(len(metric_names))
    w = 0.32
    bars_nl = ax1.bar(x - w / 2, rates_nl, w, label=LABEL_NO_LEARNING,
                       color=PALETTE["no_learning"], edgecolor="white", linewidth=0.8)
    bars_l = ax1.bar(x + w / 2, rates_l, w, label=LABEL_LEARNING,
                      color=PALETTE["learning"], edgecolor="white", linewidth=0.8)
    _annotate_bars(ax1, bars_nl, offset=1.2)
    _annotate_bars(ax1, bars_l, offset=1.2)
    ax1.set_ylim(0, 115)
    ax1.set_xticks(x)
    ax1.set_xticklabels(metric_names)
    ax1.set_ylabel("Success Rate (%)")
    ax1.set_title("Overall Success Rates")
    ax1.legend(frameon=True, loc="upper center")
    ax1.yaxis.set_major_locator(mticker.MultipleLocator(20))
    sns.despine(ax=ax1)

    # Composite score summary
    scores_nl = [m["score"] for m in root_nl]
    scores_l = [m["score"] for m in root_l]
    avg_nl = np.mean(scores_nl) if scores_nl else 0
    avg_l = np.mean(scores_l) if scores_l else 0
    summary = (
        f"Composite Score (0–3)\n"
        f"  {LABEL_NO_LEARNING}: {avg_nl:.2f}  (n={n_nl})\n"
        f"  {LABEL_LEARNING}:       {avg_l:.2f}  (n={n_l})"
    )
    ax1.text(
        0.99, 0.97, summary, transform=ax1.transAxes, ha="right", va="top",
        fontsize=9, family="monospace",
        bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=PALETTE["grid"], alpha=0.9),
    )

    # ---- 1b: Composite score threshold attainment ----
    ax_mid = fig.add_subplot(gs[1, :])
    thresholds = [1, 2, 3]
    threshold_labels = ["Score >= 1", "Score >= 2", "Score >= 3"]

    rates_thr_nl = [
        (sum(1 for m in root_nl if m.get("score", 0) >= thr) / n_nl * 100) if n_nl else 0
        for thr in thresholds
    ]
    rates_thr_l = [
        (sum(1 for m in root_l if m.get("score", 0) >= thr) / n_l * 100) if n_l else 0
        for thr in thresholds
    ]

    x_thr = np.arange(len(threshold_labels))
    bars_thr_nl = ax_mid.bar(
        x_thr - w / 2, rates_thr_nl, w, label=LABEL_NO_LEARNING,
        color=PALETTE["no_learning"], edgecolor="white", linewidth=0.8
    )
    bars_thr_l = ax_mid.bar(
        x_thr + w / 2, rates_thr_l, w, label=LABEL_LEARNING,
        color=PALETTE["learning"], edgecolor="white", linewidth=0.8
    )
    _annotate_bars(ax_mid, bars_thr_nl, offset=1.2)
    _annotate_bars(ax_mid, bars_thr_l, offset=1.2)
    ax_mid.set_ylim(0, 115)
    ax_mid.set_xticks(x_thr)
    ax_mid.set_xticklabels(threshold_labels)
    ax_mid.set_ylabel("Episodes Reaching Threshold (%)")
    ax_mid.set_title("Composite Score Threshold Attainment")
    ax_mid.legend(frameon=True, loc="upper center")
    ax_mid.yaxis.set_major_locator(mticker.MultipleLocator(20))
    sns.despine(ax=ax_mid)

    # ---- 1c: Success by incident type – No Learning ----
    ax2 = fig.add_subplot(gs[2, 0])
    _plot_incident_breakdown(ax2, root_nl, f"{LABEL_NO_LEARNING}  (n={n_nl})")

    # ---- 1d: Success by incident type – Learning ----
    ax3 = fig.add_subplot(gs[2, 1])
    _plot_incident_breakdown(ax3, root_l, f"{LABEL_LEARNING}  (n={n_l})")

    fig.savefig(outfile)
    plt.close(fig)
    print(f"  Saved {outfile}")


def _plot_incident_breakdown(ax, root_metrics, title):
    categories = sorted(INCIDENT_LABELS.keys())
    metric_keys = ["root_cause_analysis", "successful_fix", "system_recovery_visible"]
    short_labels = ["RCA", "Fix", "Recovery"]
    colors = [PALETTE["rca"], PALETTE["fix"], PALETTE["recovery"]]

    x = np.arange(len(categories))
    w = 0.22

    for i, (key, lbl, col) in enumerate(zip(metric_keys, short_labels, colors)):
        vals = []
        for cat in categories:
            cat_tasks = [m for m in root_metrics if m["incident_type"] == cat]
            rate = np.mean([m.get(key, 0) for m in cat_tasks]) * 100 if cat_tasks else 0
            vals.append(rate)
        bars = ax.bar(x + (i - 1) * w, vals, w, label=lbl, color=col,
                       edgecolor="white", linewidth=0.6)
        _annotate_bars(ax, bars, fontsize=8, offset=1.0)

    # Episode counts per category
    counts = []
    for cat in categories:
        counts.append(sum(1 for m in root_metrics if m["incident_type"] == cat))
    xlabels = [f"{INCIDENT_LABELS.get(c, c)}\n(n={counts[i]})" for i, c in enumerate(categories)]

    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, fontsize=9)
    ax.set_ylim(0, 120)
    ax.set_ylabel("Success Rate (%)")
    ax.set_title(title)
    ax.legend(fontsize=8, frameon=True, loc="upper right")
    ax.yaxis.set_major_locator(mticker.MultipleLocator(20))
    sns.despine(ax=ax)


# ---------------------------------------------------------------------------
# Figure 2 – Operational Metrics Comparison
# ---------------------------------------------------------------------------
def plot_fig2_operational(root_nl, child_nl, tools_nl,
                          root_l, child_l, tools_l, outfile):
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), facecolor="white")

    all_nl = root_nl + child_nl
    all_l = root_l + child_l

    # ---- 2a: TTR (root tasks only) ----
    ax = axes[0, 0]
    ttr_nl = [m["ttr"] / 60 for m in root_nl if m["ttr"] is not None]
    ttr_l = [m["ttr"] / 60 for m in root_l if m["ttr"] is not None]
    _side_by_side_distribution(ax, ttr_nl, ttr_l, "Time to Resolution (min)",
                         "Time to Resolution – Root Tasks")

    # ---- 2b: Trajectory length (all tasks) ----
    ax = axes[0, 1]
    traj_nl = [m["trajectory_length"] for m in all_nl if m["trajectory_length"] > 0]
    traj_l = [m["trajectory_length"] for m in all_l if m["trajectory_length"] > 0]
    _side_by_side_distribution(ax, traj_nl, traj_l, "Message Count",
                         "Trajectory Length – All Tasks")

    # ---- 2c: Iterations (root) ----
    ax = axes[0, 2]
    iter_nl = [m["iterations_count"] for m in root_nl]
    iter_l = [m["iterations_count"] for m in root_l]
    _side_by_side_distribution(ax, iter_nl, iter_l, "Iterations",
                         "Iteration Count – Root Tasks")

    # ---- 2d: Tool uses (all) ----
    ax = axes[1, 0]
    tu_nl = [m["tool_uses"] for m in all_nl if m["tool_uses"] > 0]
    tu_l = [m["tool_uses"] for m in all_l if m["tool_uses"] > 0]
    _side_by_side_distribution(ax, tu_nl, tu_l, "Tool Invocations",
                         "Tool Uses per Task")

    # ---- 2e: Tool error rate (all) ----
    ax = axes[1, 1]
    er_nl = [m["tool_error_rate"] for m in all_nl if m["tool_uses"] > 0]
    er_l = [m["tool_error_rate"] for m in all_l if m["tool_uses"] > 0]
    _side_by_side_distribution(ax, er_nl, er_l, "Error Rate (%)",
                         "Tool Error Rate per Task")

    # ---- 2f: Subtree depth (root) ----
    ax = axes[1, 2]
    dep_nl = [m["max_depth"] for m in root_nl]
    dep_l = [m["max_depth"] for m in root_l]
    _side_by_side_distribution(ax, dep_nl, dep_l, "Max Depth",
                         "Task-Tree Depth – Root Tasks")

    fig.tight_layout(h_pad=3.0, w_pad=2.5)
    fig.savefig(outfile)
    plt.close(fig)
    print(f"  Saved {outfile}")


def _side_by_side_distribution(ax, data_nl, data_l, ylabel, title):
    """Draw overlapping violin + box for two groups."""
    if not data_nl and not data_l:
        ax.set_title(title)
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center")
        return

    plot_data = []
    labels = []
    for v in data_nl:
        plot_data.append(v)
        labels.append(LABEL_NO_LEARNING)
    for v in data_l:
        plot_data.append(v)
        labels.append(LABEL_LEARNING)

    import pandas as pd
    df = pd.DataFrame({"value": plot_data, "group": labels})

    order = [LABEL_NO_LEARNING, LABEL_LEARNING]
    pal = {LABEL_NO_LEARNING: PALETTE["no_learning"], LABEL_LEARNING: PALETTE["learning"]}
    sns.violinplot(
        data=df,
        x="group",
        y="value",
        hue="group",
        order=order,
        palette=pal,
        inner=None,
        ax=ax,
        cut=0,
        linewidth=0.8,
        alpha=0.35,
        density_norm="width",
        legend=False,
    )
    sns.boxplot(
        data=df,
        x="group",
        y="value",
        hue="group",
        order=order,
        ax=ax,
        width=0.15,
        showcaps=True,
        boxprops=dict(facecolor="white", edgecolor=PALETTE["text"], linewidth=1),
        whiskerprops=dict(color=PALETTE["text"]),
        medianprops=dict(color=PALETTE["score0"], linewidth=1.5),
        capprops=dict(color=PALETTE["text"]),
        fliersize=0,
        zorder=3,
        legend=False,
    )

    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)

    stat_nl = _stat_text(data_nl)
    stat_l = _stat_text(data_l)
    ax.text(0.02, 0.97, stat_nl, transform=ax.transAxes, fontsize=7.5,
            va="top", color=PALETTE["no_learning"], fontweight="semibold")
    ax.text(0.02, 0.91, stat_l, transform=ax.transAxes, fontsize=7.5,
            va="top", color=PALETTE["learning"], fontweight="semibold")
    sns.despine(ax=ax)


# ---------------------------------------------------------------------------
# Figure 6 – Task-Tree Structure (width & depth)
# ---------------------------------------------------------------------------
def plot_fig6_tree_structure(root_nl, root_l, outfile):
    max_level = max(
        max((max(m.get("level_counts", {}).keys(), default=0) for m in root_nl), default=0),
        max((max(m.get("level_counts", {}).keys(), default=0) for m in root_l), default=0),
    )
    max_level = max(max_level, 1)
    levels = list(range(1, max_level + 1))

    def _collect_widths(root_metrics):
        """Return {level: [width_values_per_root_task]}."""
        result = {}
        for lvl in levels:
            result[lvl] = [m.get("level_counts", {}).get(lvl, 0) for m in root_metrics]
        return result

    widths_nl = _collect_widths(root_nl)
    widths_l = _collect_widths(root_l)

    fig = plt.figure(figsize=(14, 8), facecolor="white")
    gs = gridspec.GridSpec(2, 2, hspace=0.35, wspace=0.30,
                           height_ratios=[1, 1.1])

    # ---- 6a: Butterfly / pyramid chart (average tree silhouette) ----
    ax_fly = fig.add_subplot(gs[0, 0])

    y_pos = np.arange(len(levels))
    avg_nl = [np.mean(widths_nl[l]) for l in levels]
    avg_l = [np.mean(widths_l[l]) for l in levels]

    ax_fly.barh(y_pos, [-v for v in avg_nl], height=0.55,
                color=PALETTE["no_learning"], edgecolor="white", linewidth=0.8,
                label=LABEL_NO_LEARNING)
    ax_fly.barh(y_pos, avg_l, height=0.55,
                color=PALETTE["learning"], edgecolor="white", linewidth=0.8,
                label=LABEL_LEARNING)

    x_max = max(max(avg_nl, default=1), max(avg_l, default=1)) * 1.3
    for i, (vnl, vl) in enumerate(zip(avg_nl, avg_l)):
        ax_fly.text(-vnl - x_max * 0.03, i, f"{vnl:.1f}", ha="right", va="center",
                    fontsize=9, fontweight="semibold", color=PALETTE["no_learning"])
        ax_fly.text(vl + x_max * 0.03, i, f"{vl:.1f}", ha="left", va="center",
                    fontsize=9, fontweight="semibold", color=PALETTE["learning"])

    ax_fly.set_yticks(y_pos)
    ax_fly.set_yticklabels([f"Depth {l}" for l in levels])
    ax_fly.invert_yaxis()
    ax_fly.axvline(0, color=PALETTE["text"], linewidth=0.8)
    ax_fly.set_xlim(-x_max, x_max)
    ax_fly.set_xlabel("← " + LABEL_NO_LEARNING + "          " + LABEL_LEARNING + " →")
    ax_fly.set_title("Average Tree Shape (children per level)")
    ax_fly.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{abs(x):.0f}"))
    ax_fly.legend(fontsize=8, frameon=True, loc="lower left")
    sns.despine(ax=ax_fly)

    # ---- 6b: Total descendants + depth summary ----
    ax_sum = fig.add_subplot(gs[0, 1])
    desc_nl = [m["child_count"] for m in root_nl]
    desc_l = [m["child_count"] for m in root_l]
    dep_nl = [m["max_depth"] for m in root_nl]
    dep_l = [m["max_depth"] for m in root_l]

    summary_labels = ["Total\nDescendants", "Max\nDepth"]
    x_sum = np.arange(len(summary_labels))
    w = 0.30

    means_nl = [np.mean(desc_nl), np.mean(dep_nl)]
    means_l = [np.mean(desc_l), np.mean(dep_l)]
    stds_nl = [np.std(desc_nl), np.std(dep_nl)]
    stds_l = [np.std(desc_l), np.std(dep_l)]

    bars1 = ax_sum.bar(x_sum - w / 2, means_nl, w, yerr=stds_nl,
                        color=PALETTE["no_learning"], edgecolor="white",
                        linewidth=0.8, capsize=4, error_kw=dict(linewidth=1),
                        label=LABEL_NO_LEARNING)
    bars2 = ax_sum.bar(x_sum + w / 2, means_l, w, yerr=stds_l,
                        color=PALETTE["learning"], edgecolor="white",
                        linewidth=0.8, capsize=4, error_kw=dict(linewidth=1),
                        label=LABEL_LEARNING)
    for bars in (bars1, bars2):
        for bar in bars:
            h = bar.get_height()
            ax_sum.text(bar.get_x() + bar.get_width() / 2, h + 0.15,
                        f"{h:.1f}", ha="center", va="bottom", fontsize=9,
                        fontweight="semibold")
    ax_sum.set_xticks(x_sum)
    ax_sum.set_xticklabels(summary_labels)
    ax_sum.set_ylabel("Mean ± Std")
    ax_sum.set_title("Tree Size Summary")
    ax_sum.legend(fontsize=8, frameon=True, loc="upper right")
    sns.despine(ax=ax_sum)

    # ---- 6c–d: Per-level distribution (same as fig2: box + strip) ----
    for col_idx, lvl in enumerate(levels[:3]):
        if col_idx >= 2:
            break
        ax = fig.add_subplot(gs[1, col_idx])

        vals_nl = widths_nl[lvl]
        vals_l = widths_l[lvl]

        _side_by_side_distribution(
            ax,
            vals_nl,
            vals_l,
            "Number of Children",
            f"Depth {lvl}  –  Children Distribution",
        )

        pct_nl = sum(1 for v in vals_nl if v > 0) / len(vals_nl) * 100 if vals_nl else 0
        pct_l = sum(1 for v in vals_l if v > 0) / len(vals_l) * 100 if vals_l else 0
        pct_txt = (
            f"% with children →  {LABEL_NO_LEARNING}: {pct_nl:.0f}%  |  "
            f"{LABEL_LEARNING}: {pct_l:.0f}%"
        )
        ax.text(
            0.02,
            0.02,
            pct_txt,
            transform=ax.transAxes,
            fontsize=7,
            va="bottom",
            ha="left",
            family="monospace",
            bbox=dict(
                boxstyle="round,pad=0.25",
                fc="white",
                ec=PALETTE["grid"],
                alpha=0.92,
            ),
        )
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        sns.despine(ax=ax)

    # If only 2 levels in bottom row, handle extra subplot
    if len(levels) < 3:
        for extra in range(len(levels), 2):
            fig.delaxes(fig.add_subplot(gs[1, extra]))

    fig.savefig(outfile)
    plt.close(fig)
    print(f"  Saved {outfile}")


# ---------------------------------------------------------------------------
# Figure 3 – Chronological Timeline
# ---------------------------------------------------------------------------
def plot_fig3_timeline(root_nl, root_l, outfile):
    root_nl_sorted = sorted(root_nl, key=lambda x: x["created_at_dt"] or datetime.min)
    agent_map = {m["id"]: m for m in root_l}

    master_ids = [m["id"] for m in root_nl_sorted]
    n = len(master_ids)
    if n == 0:
        print("  No root tasks for timeline.")
        return

    score_colors = {
        3: PALETTE["score3"],
        2: PALETTE["score2"],
        1: PALETTE["score1"],
        0: PALETTE["score0"],
    }

    # More compact figure size
    fig_w = max(8, n * 0.25)
    fig = plt.figure(figsize=(fig_w, 6), facecolor="white")
    gs = gridspec.GridSpec(3, 1, height_ratios=[1, 1, 0.8], hspace=0.05)
    
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    indices = np.arange(n)
    bar_w = 0.9

    # --- Top: No Learning ---
    colors_nl = [score_colors[m["score"]] for m in root_nl_sorted]
    bars_nl = ax1.bar(indices, [1] * n, color=colors_nl, edgecolor="none",
                       linewidth=0, width=bar_w)

    ax1.set_ylabel(LABEL_NO_LEARNING, fontsize=12, fontweight="bold", labelpad=5)
    ax1.set_ylim(0, 1)
    ax1.set_yticks([])
    ax1.set_xlim(-0.5, n-0.5)  # Tight fit around data

    # --- Middle: Learning ---
    agent_data = [agent_map.get(tid) for tid in master_ids]
    colors_l = [score_colors[m["score"]] if m else "#F3F4F6" for m in agent_data]
    heights = [1 if m else 0.3 for m in agent_data]
    bars_l = ax2.bar(indices, heights, color=colors_l, edgecolor="none",
                      linewidth=0, width=bar_w)

    ax2.set_ylabel(LABEL_LEARNING, fontsize=12, fontweight="bold", labelpad=5)
    ax2.set_ylim(0, 1)
    ax2.set_yticks([])
    ax2.set_xlim(-0.5, n-0.5)  # Tight fit around data

    # --- Bottom: Cumulative Score Difference ---
    cumulative_diff = []
    cumulative_nl = 0
    cumulative_l = 0
    
    for i, (m_nl, m_l) in enumerate(zip(root_nl_sorted, agent_data)):
        cumulative_nl += m_nl["score"]
        if m_l:
            cumulative_l += m_l["score"]
        diff = cumulative_l - cumulative_nl
        cumulative_diff.append(diff)

    # Plot the cumulative difference
    ax3.plot(indices, cumulative_diff, color=PALETTE["learning"], linewidth=2, marker='o', markersize=3)
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5, alpha=0.7)
    ax3.fill_between(indices, cumulative_diff, 0, 
                     where=[d >= 0 for d in cumulative_diff], 
                     color=PALETTE["learning"], alpha=0.3, interpolate=True)
    ax3.fill_between(indices, cumulative_diff, 0, 
                     where=[d < 0 for d in cumulative_diff], 
                     color=PALETTE["no_learning"], alpha=0.3, interpolate=True)
    
    ax3.set_ylabel("Cumulative Score Difference\n(Learning - No Learning)", fontsize=10, fontweight="bold", labelpad=15)
    ax3.set_xlabel("Episode", fontsize=11)
    ax3.set_xlim(-0.5, n-0.5)  # Tight fit around data

    # Remove all x-axis labels except from bottom plot
    ax1.set_xticks([])
    ax2.set_xticks([])
    ax3.set_xticks(indices[::max(1, n//10)])  # Show every 10th or fewer labels
    ax3.set_xticklabels([f"{i+1}" for i in ax3.get_xticks()], fontsize=9)

    # Legend - larger and more prominent, positioned at top right with white background
    legend_patches = [
        mpatches.Patch(color=score_colors[3], label="Score 3"),
        mpatches.Patch(color=score_colors[2], label="Score 2"),
        mpatches.Patch(color=score_colors[1], label="Score 1"),
        mpatches.Patch(color=score_colors[0], label="Score 0"),
    ]
    ax1.legend(handles=legend_patches, loc="upper right", ncol=4, fontsize=10,
               frameon=True, facecolor='white', edgecolor='none', 
               handlelength=1.5, handletextpad=0.5, columnspacing=1.2)

    # Remove all spines and grids
    for ax in [ax1, ax2, ax3]:
        sns.despine(ax=ax, left=True, bottom=True, right=True, top=True)
        ax.grid(False)
        ax.set_facecolor('white')

    # Only show bottom spine for the bottom plot
    sns.despine(ax=ax3, left=True, right=True, top=True)

    # Adjust subplot spacing for better margins
    plt.subplots_adjust(left=0.15, right=0.95, top=0.95, bottom=0.1, hspace=0.05)
    fig.savefig(outfile, dpi=300, bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)
    print(f"  Saved {outfile}")


# ---------------------------------------------------------------------------
# Figure 4 – Top Failing Tools (side by side)
# ---------------------------------------------------------------------------
def plot_fig4_tools(tools_nl, tools_l, outfile):
    top_n = 10

    all_tools = set(tools_nl.keys()) | set(tools_l.keys())
    combined = {t: tools_nl.get(t, 0) + tools_l.get(t, 0) for t in all_tools}
    top_tools = sorted(combined, key=combined.get, reverse=True)[:top_n]

    if not top_tools:
        print("  No failing tools to plot.")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), facecolor="white",
                                     sharey=True)

    y = np.arange(len(top_tools))

    vals_nl = [tools_nl.get(t, 0) for t in top_tools]
    vals_l = [tools_l.get(t, 0) for t in top_tools]

    ax1.barh(y, vals_nl, color=PALETTE["no_learning"], edgecolor="white", height=0.6)
    ax1.set_yticks(y)
    ax1.set_yticklabels(top_tools, fontsize=9)
    ax1.invert_yaxis()
    ax1.set_xlabel("Error Count")
    ax1.set_title(LABEL_NO_LEARNING)
    for i, v in enumerate(vals_nl):
        if v > 0:
            ax1.text(v + 0.5, i, str(v), va="center", fontsize=8)
    sns.despine(ax=ax1)

    ax2.barh(y, vals_l, color=PALETTE["learning"], edgecolor="white", height=0.6)
    ax2.invert_yaxis()
    ax2.set_xlabel("Error Count")
    ax2.set_title(LABEL_LEARNING)
    for i, v in enumerate(vals_l):
        if v > 0:
            ax2.text(v + 0.5, i, str(v), va="center", fontsize=8)
    sns.despine(ax=ax2)

    fig.suptitle("Top Failing Tools (by total errors)", fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(outfile)
    plt.close(fig)
    print(f"  Saved {outfile}")


# ---------------------------------------------------------------------------
# Figure 5 – Playbook Token Evolution
# ---------------------------------------------------------------------------
AGENT_DISPLAY = {
    "incident_commander": "Incident Commander",
    "monitoring_agent": "Monitoring Agent",
    "devops_agent": "DevOps Agent",
    "coder_agent": "Coder Agent",
}

AGENT_COLORS = {
    "incident_commander": "#6366F1",
    "monitoring_agent": "#10B981",
    "devops_agent": "#F59E0B",
    "coder_agent": "#EF4444",
}


def _playbook_to_text(data: dict) -> str:
    """Render a playbook JSON into the prompt text that would be sent to the LLM."""
    lines = []
    for section_name, entries in data.get("sections", {}).items():
        lines.append(f"## {section_name}")
        for entry in entries:
            lines.append(f"- {entry['content']}")
        lines.append("")
    return "\n".join(lines)


def _count_tokens(text: str, encoder) -> int:
    return len(encoder.encode(text))


def _count_section_entries(data: dict) -> int:
    return sum(len(entries) for entries in data.get("sections", {}).values())


def plot_fig5_playbook_evolution(history_dir: str, outfile: str):
    import tiktoken
    encoder = tiktoken.encoding_for_model("gpt-4o")

    files = globmod.glob(os.path.join(history_dir, "*.json"))
    if not files:
        print("  No playbook history files found.")
        return

    agent_snapshots = defaultdict(list)
    for fpath in files:
        fname = os.path.basename(fpath).replace(".json", "")
        # agent name may itself contain hyphens, timestamp is the last segment
        idx = fname.rfind("-")
        agent_name = fname[:idx]
        timestamp = int(fname[idx + 1:])
        with open(fpath) as f:
            data = json.load(f)
        text = _playbook_to_text(data)
        tokens = _count_tokens(text, encoder)
        entries = _count_section_entries(data)
        agent_snapshots[agent_name].append({
            "timestamp": timestamp,
            "tokens": tokens,
            "entries": entries,
            "data": data,
        })

    for snaps in agent_snapshots.values():
        snaps.sort(key=lambda s: s["timestamp"])

    agents = sorted(agent_snapshots.keys(),
                    key=lambda a: list(AGENT_DISPLAY.keys()).index(a)
                    if a in AGENT_DISPLAY else 999)
    n_revisions = max(len(agent_snapshots[a]) for a in agents)

    # --- Figure ---
    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(10, 7.5), facecolor="white",
        gridspec_kw={"height_ratios": [2, 1], "hspace": 0.28},
    )

    # Top: stacked area + lines for token count
    rev_indices = np.arange(n_revisions)
    token_stacks = []
    for agent in agents:
        snaps = agent_snapshots[agent]
        vals = [s["tokens"] for s in snaps]
        # pad with last value if fewer revisions
        while len(vals) < n_revisions:
            vals.append(vals[-1])
        token_stacks.append(vals)

    token_stacks_arr = np.array(token_stacks)
    ax_top.stackplot(
        rev_indices, *token_stacks_arr,
        labels=[AGENT_DISPLAY.get(a, a) for a in agents],
        colors=[AGENT_COLORS.get(a, "#888888") + "55" for a in agents],
        edgecolor="white", linewidth=0.5,
    )
    for i, agent in enumerate(agents):
        cumulative = token_stacks_arr[:i + 1].sum(axis=0)
        ax_top.plot(rev_indices, cumulative,
                    color=AGENT_COLORS.get(agent, "#888888"),
                    linewidth=1.5, alpha=0.7)

    totals = token_stacks_arr.sum(axis=0)
    for r in rev_indices:
        ax_top.text(r, totals[r] + totals.max() * 0.02,
                    f"{int(totals[r]):,}",
                    ha="center", va="bottom", fontsize=8, fontweight="semibold",
                    color=PALETTE["text"])

    ax_top.set_ylabel("Token Count")
    ax_top.set_title("Playbook Size Evolution (tokens)")
    ax_top.set_xticks(rev_indices)
    ax_top.set_xticklabels([f"Rev {i}" for i in rev_indices], fontsize=9)
    ax_top.set_xlim(-0.3, n_revisions - 0.7)
    ax_top.legend(loc="upper left", fontsize=9, frameon=True, ncol=2)
    ax_top.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    sns.despine(ax=ax_top)

    # Bottom: per-agent line chart of rule/entry count
    for agent in agents:
        snaps = agent_snapshots[agent]
        entries_vals = [s["entries"] for s in snaps]
        while len(entries_vals) < n_revisions:
            entries_vals.append(entries_vals[-1])
        ax_bot.plot(rev_indices, entries_vals,
                    marker="o", markersize=6, linewidth=2,
                    color=AGENT_COLORS.get(agent, "#888888"),
                    label=AGENT_DISPLAY.get(agent, agent))
        for r, v in enumerate(entries_vals):
            ax_bot.text(r, v + 0.3, str(v), ha="center", va="bottom",
                        fontsize=8, color=AGENT_COLORS.get(agent, "#888888"),
                        fontweight="semibold")

    ax_bot.set_ylabel("Playbook Entries (rules)")
    ax_bot.set_xlabel("Revision")
    ax_bot.set_title("Number of Playbook Rules per Agent")
    ax_bot.set_xticks(rev_indices)
    ax_bot.set_xticklabels([f"Rev {i}" for i in rev_indices], fontsize=9)
    ax_bot.set_xlim(-0.3, n_revisions - 0.7)
    ax_bot.legend(loc="upper left", fontsize=9, frameon=True, ncol=2)
    ax_bot.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    sns.despine(ax=ax_bot)

    fig.savefig(outfile)
    plt.close(fig)
    print(f"  Saved {outfile}")


# ---------------------------------------------------------------------------
# Terminal tables
# ---------------------------------------------------------------------------
def _fmt_num(v, unit="", decimals=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, int):
        return f"{v}{unit}"
    return f"{v:.{decimals}f}{unit}"


def _fmt_delta(a, b, unit="", decimals=1, higher_is_better=True):
    """Return formatted delta string comparing b vs a (learning vs no-learning)."""
    if a is None or b is None:
        return "—"
    diff = b - a
    pct = (diff / a * 100) if a not in (0, 0.0) else None
    sign = "+" if diff >= 0 else ""
    # arrow based on direction and whether higher is better
    if diff == 0:
        arrow = "="
    elif (diff > 0) == higher_is_better:
        arrow = "▲"
    else:
        arrow = "▼"
    base = f"{sign}{diff:.{decimals}f}{unit}"
    if pct is not None:
        base += f" ({sign}{pct:.1f}%)"
    return f"{arrow} {base}"


def _print_table(title, headers, rows):
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    def render_row(cells):
        parts = []
        for i, cell in enumerate(cells):
            if i == 0:
                parts.append(str(cell).ljust(col_widths[i]))
            else:
                parts.append(str(cell).rjust(col_widths[i]))
        return "  ".join(parts)

    sep = "─" * (sum(col_widths) + 2 * (len(headers) - 1))
    print()
    print(f"━━ {title} ━━")
    print(sep)
    print(render_row(headers))
    print(sep)
    for row in rows:
        print(render_row(row))
    print(sep)


def _safe_mean(xs):
    return float(np.mean(xs)) if xs else None


def _safe_median(xs):
    return float(np.median(xs)) if xs else None


def print_terminal_tables(root_nl, child_nl, tools_nl,
                          root_l, child_l, tools_l):
    print("\n" + "=" * 72)
    print(" COMPARISON TABLES  —  Without Learning  vs.  With Learning")
    print("=" * 72)

    n_nl = len(root_nl)
    n_l = len(root_l)

    # --- Overall success rates ---
    metric_keys = ["root_cause_analysis", "successful_fix", "system_recovery_visible"]
    metric_names = ["Root Cause Analysis", "Successful Fix", "System Recovery"]
    rows = []
    for key, name in zip(metric_keys, metric_names):
        rate_nl = (sum(m.get(key, 0) for m in root_nl) / n_nl * 100) if n_nl else 0
        rate_l = (sum(m.get(key, 0) for m in root_l) / n_l * 100) if n_l else 0
        rows.append([
            name,
            _fmt_num(rate_nl, unit="%"),
            _fmt_num(rate_l, unit="%"),
            _fmt_delta(rate_nl, rate_l, unit=" pp", higher_is_better=True),
        ])

    scores_nl = [m["score"] for m in root_nl]
    scores_l = [m["score"] for m in root_l]
    avg_nl = _safe_mean(scores_nl) or 0
    avg_l = _safe_mean(scores_l) or 0
    total_nl = sum(scores_nl)
    total_l = sum(scores_l)
    max_nl = n_nl * 3
    max_l = n_l * 3
    pct_nl = (total_nl / max_nl * 100) if max_nl else 0
    pct_l = (total_l / max_l * 100) if max_l else 0

    rows.append([
        "Composite Score (mean, /3)",
        _fmt_num(avg_nl, decimals=2),
        _fmt_num(avg_l, decimals=2),
        _fmt_delta(avg_nl, avg_l, decimals=2, higher_is_better=True),
    ])
    rows.append([
        "Composite Score (total)",
        f"{total_nl}/{max_nl} ({pct_nl:.1f}%)",
        f"{total_l}/{max_l} ({pct_l:.1f}%)",
        _fmt_delta(pct_nl, pct_l, unit=" pp", higher_is_better=True),
    ])
    # Calculate threshold percentages
    score_1_nl = sum(1 for s in scores_nl if s >= 1)
    score_1_l = sum(1 for s in scores_l if s >= 1)
    score_2_nl = sum(1 for s in scores_nl if s >= 2)
    score_2_l = sum(1 for s in scores_l if s >= 2)
    score_3_nl = sum(1 for s in scores_nl if s == 3)
    score_3_l = sum(1 for s in scores_l if s == 3)
    score_0_nl = sum(1 for s in scores_nl if s == 0)
    score_0_l = sum(1 for s in scores_l if s == 0)
    
    pct_1_nl = (score_1_nl / n_nl * 100) if n_nl else 0
    pct_1_l = (score_1_l / n_l * 100) if n_l else 0
    pct_2_nl = (score_2_nl / n_nl * 100) if n_nl else 0
    pct_2_l = (score_2_l / n_l * 100) if n_l else 0
    pct_3_nl = (score_3_nl / n_nl * 100) if n_nl else 0
    pct_3_l = (score_3_l / n_l * 100) if n_l else 0
    
    # Calculate progressions and regressions
    progressions = 0
    regressions = 0
    matched_tasks = []
    
    # Match tasks by ID to compare scores
    nl_scores_by_id = {m["id"]: m["score"] for m in root_nl}
    for l_task in root_l:
        task_id = l_task["id"]
        if task_id in nl_scores_by_id:
            score_nl = nl_scores_by_id[task_id]
            score_l = l_task["score"]
            matched_tasks.append((score_nl, score_l))
            if score_l > score_nl:
                progressions += 1
            elif score_l < score_nl:
                regressions += 1
    
    n_matched = len(matched_tasks)
    
    rows.append([
        "Episodes >= 1/3 score",
        f"{score_1_nl}/{n_nl} ({pct_1_nl:.1f}%)",
        f"{score_1_l}/{n_l} ({pct_1_l:.1f}%)",
        _fmt_delta(pct_1_nl, pct_1_l, unit=" pp", higher_is_better=True),
    ])
    rows.append([
        "Episodes >= 2/3 score",
        f"{score_2_nl}/{n_nl} ({pct_2_nl:.1f}%)",
        f"{score_2_l}/{n_l} ({pct_2_l:.1f}%)",
        _fmt_delta(pct_2_nl, pct_2_l, unit=" pp", higher_is_better=True),
    ])
    rows.append([
        "Full-Success Episodes (score=3)",
        f"{score_3_nl}/{n_nl} ({pct_3_nl:.1f}%)",
        f"{score_3_l}/{n_l} ({pct_3_l:.1f}%)",
        _fmt_delta(pct_3_nl, pct_3_l, unit=" pp", higher_is_better=True),
    ])
    rows.append([
        "Complete-Failure Episodes (score=0)",
        f"{score_0_nl}/{n_nl}",
        f"{score_0_l}/{n_l}",
        "",
    ])
    rows.append([
        "Progressions (L > NL)",
        f"—",
        f"{progressions}/{n_matched} ({(progressions/n_matched*100):.1f}%)" if n_matched else "—",
        "",
    ])
    rows.append([
        "Regressions (L < NL)",
        f"—",
        f"{regressions}/{n_matched} ({(regressions/n_matched*100):.1f}%)" if n_matched else "—",
        "",
    ])

    _print_table(
        "Overall Success Rates",
        ["Metric", LABEL_NO_LEARNING, LABEL_LEARNING, "Δ (L − NL)"],
        rows,
    )

    # --- Per-incident-type success breakdown ---
    incident_rows = []
    categories = sorted(INCIDENT_LABELS.keys())
    for cat in categories:
        cat_nl = [m for m in root_nl if m["incident_type"] == cat]
        cat_l = [m for m in root_l if m["incident_type"] == cat]
        score_nl = _safe_mean([m["score"] for m in cat_nl]) or 0
        score_l = _safe_mean([m["score"] for m in cat_l]) or 0
        rca_nl = _safe_mean([m["root_cause_analysis"] for m in cat_nl]) or 0
        rca_l = _safe_mean([m["root_cause_analysis"] for m in cat_l]) or 0
        fix_nl = _safe_mean([m["successful_fix"] for m in cat_nl]) or 0
        fix_l = _safe_mean([m["successful_fix"] for m in cat_l]) or 0
        rec_nl = _safe_mean([m["system_recovery_visible"] for m in cat_nl]) or 0
        rec_l = _safe_mean([m["system_recovery_visible"] for m in cat_l]) or 0
        incident_rows.append([
            f"{INCIDENT_LABELS.get(cat, cat)}",
            f"{len(cat_nl)}/{len(cat_l)}",
            f"{rca_nl * 100:.0f}% / {rca_l * 100:.0f}%",
            f"{fix_nl * 100:.0f}% / {fix_l * 100:.0f}%",
            f"{rec_nl * 100:.0f}% / {rec_l * 100:.0f}%",
            f"{score_nl:.2f} / {score_l:.2f}",
            _fmt_delta(score_nl, score_l, decimals=2, higher_is_better=True),
        ])

    _print_table(
        "Success by Incident Type  (values: NL / L)",
        ["Incident", "n (NL/L)", "RCA", "Fix", "Recovery", "Score /3", "Δ Score"],
        incident_rows,
    )

    # --- Operational metrics (root tasks & all tasks) ---
    all_nl = root_nl + child_nl
    all_l = root_l + child_l

    ttr_nl = [m["ttr"] / 60 for m in root_nl if m["ttr"] is not None]
    ttr_l = [m["ttr"] / 60 for m in root_l if m["ttr"] is not None]
    traj_nl = [m["trajectory_length"] for m in all_nl if m["trajectory_length"] > 0]
    traj_l = [m["trajectory_length"] for m in all_l if m["trajectory_length"] > 0]
    iter_nl = [m["iterations_count"] for m in root_nl]
    iter_l = [m["iterations_count"] for m in root_l]
    tu_nl = [m["tool_uses"] for m in all_nl if m["tool_uses"] > 0]
    tu_l = [m["tool_uses"] for m in all_l if m["tool_uses"] > 0]
    er_nl = [m["tool_error_rate"] for m in all_nl if m["tool_uses"] > 0]
    er_l = [m["tool_error_rate"] for m in all_l if m["tool_uses"] > 0]
    dep_nl = [m["max_depth"] for m in root_nl]
    dep_l = [m["max_depth"] for m in root_l]
    desc_nl = [m["child_count"] for m in root_nl]
    desc_l = [m["child_count"] for m in root_l]

    op_specs = [
        ("TTR (min, root)", ttr_nl, ttr_l, "min", 1, False),
        ("Trajectory length (all)", traj_nl, traj_l, "", 1, False),
        ("Iterations (root)", iter_nl, iter_l, "", 1, False),
        ("Tool uses (all)", tu_nl, tu_l, "", 1, False),
        ("Tool error rate (all)", er_nl, er_l, "%", 1, False),
        ("Max tree depth (root)", dep_nl, dep_l, "", 2, False),
        ("Total descendants (root)", desc_nl, desc_l, "", 1, False),
    ]

    op_rows = []
    for name, xs_nl, xs_l, unit, decimals, higher_better in op_specs:
        med_nl = _safe_median(xs_nl)
        med_l = _safe_median(xs_l)
        mean_nl = _safe_mean(xs_nl)
        mean_l = _safe_mean(xs_l)
        op_rows.append([
            name,
            f"{_fmt_num(med_nl, unit, decimals)} / {_fmt_num(mean_nl, unit, decimals)}",
            f"{_fmt_num(med_l, unit, decimals)} / {_fmt_num(mean_l, unit, decimals)}",
            _fmt_delta(mean_nl, mean_l, unit=unit, decimals=decimals,
                       higher_is_better=higher_better),
        ])

    _print_table(
        "Operational Metrics  (median / mean)",
        ["Metric", LABEL_NO_LEARNING, LABEL_LEARNING, "Δ mean (L − NL)"],
        op_rows,
    )

    # --- Top failing tools ---
    all_tools = set(tools_nl.keys()) | set(tools_l.keys())
    combined = {t: tools_nl.get(t, 0) + tools_l.get(t, 0) for t in all_tools}
    top_tools = sorted(combined, key=combined.get, reverse=True)[:10]
    if top_tools:
        tool_rows = []
        for t in top_tools:
            v_nl = tools_nl.get(t, 0)
            v_l = tools_l.get(t, 0)
            tool_rows.append([
                t,
                str(v_nl),
                str(v_l),
                _fmt_delta(v_nl, v_l, decimals=0, higher_is_better=False),
            ])
        total_nl_err = sum(tools_nl.values())
        total_l_err = sum(tools_l.values())
        tool_rows.append([
            "TOTAL (all tools)",
            str(total_nl_err),
            str(total_l_err),
            _fmt_delta(total_nl_err, total_l_err, decimals=0, higher_is_better=False),
        ])
        _print_table(
            "Top Failing Tools (error count)",
            ["Tool", LABEL_NO_LEARNING, LABEL_LEARNING, "Δ"],
            tool_rows,
        )

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def analyze():
    parser = argparse.ArgumentParser(
        description="Compare learning vs. no-learning agent performance."
    )
    parser.add_argument(
        "--incident-limit",
        type=int,
        default=None,
        help="Use only the first N incidents (chronological, based on no-learning run). "
             "Omit for all incidents.",
    )
    args = parser.parse_args()
    if args.incident_limit is not None and args.incident_limit <= 0:
        raise ValueError("--incident-limit must be a positive integer.")

    db_no_learning = "./agent_no_learning.db"
    db_agent = "./agent.db"

    print("Loading databases …")
    metrics_nl = get_metrics(db_no_learning)
    metrics_l = get_metrics(db_agent)

    if not metrics_nl or not metrics_l:
        print("Both databases are required for comparison.")
        return

    root_nl, child_nl, _ = metrics_nl
    root_l, child_l, _ = metrics_l

    root_nl, child_nl, root_l, child_l = _select_incidents(
        root_nl, child_nl, root_l, child_l, args.incident_limit
    )
    tools_nl = _aggregate_failing_tools(root_nl + child_nl)
    tools_l = _aggregate_failing_tools(root_l + child_l)

    print(f"  {LABEL_NO_LEARNING}: {len(root_nl)} root, {len(child_nl)} child tasks")
    print(f"  {LABEL_LEARNING}:    {len(root_l)} root, {len(child_l)} child tasks\n")
    if args.incident_limit is None:
        print("  Incident scope: all incidents\n")
    else:
        print(f"  Incident scope: first {args.incident_limit} incidents (chronological)\n")

    out_dir = "./figures"
    os.makedirs(out_dir, exist_ok=True)

    print("Generating figures …")
    plot_fig1_success(root_nl, root_l, f"{out_dir}/fig1_success_comparison.png")
    plot_fig2_operational(root_nl, child_nl, tools_nl,
                          root_l, child_l, tools_l,
                          f"{out_dir}/fig2_operational_comparison.png")
    plot_fig3_timeline(root_nl, root_l, f"{out_dir}/fig3_chronological_timeline.png")
    plot_fig4_tools(tools_nl, tools_l, f"{out_dir}/fig4_failing_tools.png")
    plot_fig5_playbook_evolution("./agent/ace/playbook_history",
                                 f"{out_dir}/fig5_playbook_evolution.png")
    plot_fig6_tree_structure(root_nl, root_l,
                             f"{out_dir}/fig6_tree_structure.png")

    print_terminal_tables(root_nl, child_nl, tools_nl,
                          root_l, child_l, tools_l)

    print("\nDone. All figures saved to ./figures/")


if __name__ == "__main__":
    analyze()
