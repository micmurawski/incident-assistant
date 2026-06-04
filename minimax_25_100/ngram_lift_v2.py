"""
ngram_lift_v2.py - N-gram analysis with lift above baseline

Methodology
-----------
Unit of analysis: epizod (root task). Każdy epizod liczy się co najwyżej raz
dla danego n-gramu (present/absent), co pozwala na poprawną tabelę 2×2 do
testu Fishera. Wzorce rankinowane są według liftu, nie surowego success rate.

Lift = success_rate(wzorzec) / success_rate(baseline)
  lift > 1: wzorzec koreluje z sukcesem
  lift < 1: wzorzec koreluje z porażką
  lift = 1: wzorzec neutralny (brak informacji)

Testy: Fisher's exact (dwustronny) dla każdego wzorca.
Próg częstości: domyślnie min_episodes=5 (epizodów z danym wzorcem, nie wystąpień).
"""

import sqlite3, json, re, sys
from collections import defaultdict
from scipy.stats import fisher_exact
import argparse

INVALID_TOOLS = {"assign_issue", "read_1file", "read_issue", "assign__task"}

# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_score(task: dict) -> int:
    try:
        conv = json.loads(task["conversation"] or "[]")
        if not conv:
            return 0
        last = conv[-1]
        content = last.get("content", "") if isinstance(last, dict) else ""
        if isinstance(content, list):
            content = "\n".join(x.get("text", "") for x in content if isinstance(x, dict))
        m = re.search(r"\{.*?\}", content, re.DOTALL)
        parsed = json.loads(m.group()) if m else {}
        return sum(int(parsed.get(k, 0)) for k in
                   ["root_cause_analysis", "successful_fix", "system_recovery_visible"])
    except Exception:
        return 0


def _extract_sequences(task: dict):
    assigns, tools = [], []
    try:
        msgs = json.loads(task["messages_history"] or "[]")
    except Exception:
        msgs = []
    for msg in msgs:
        for item in (msg.get("content", []) if isinstance(msg.get("content"), list) else []):
            if item.get("type") != "tool_use":
                continue
            name = item.get("name", "")
            if name == "assign_task":
                assigns.append(item.get("input", {}).get("assignee", "unknown"))
            if name not in INVALID_TOOLS:
                tools.append(name)
    return assigns, tools


def load_episodes(db_path: str, success_threshold: int = 2):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    root_ids = {r["id"] for r in rows if not r.get("parent")}
    episodes = []
    for r in rows:
        if r["id"] not in root_ids:
            continue
        score = _extract_score(r)
        assigns, tools = _extract_sequences(r)
        episodes.append({
            "id": r["id"],
            "score": score,
            "success": score >= success_threshold,
            "assigns": assigns,
            "tools": tools,
        })
    return episodes


# ── n-gram logic ──────────────────────────────────────────────────────────────

def episode_ngrams(seq: list, n: int) -> set:
    """Unique n-grams present in a sequence (binary per episode)."""
    if len(seq) < n:
        return set()
    return {tuple(seq[i:i+n]) for i in range(len(seq) - n + 1)}


def analyze_ngrams(episodes: list, seq_key: str, n: int, min_episodes: int = 5):
    """
    Returns list of dicts with:
      pattern, n_with, n_success, success_rate, baseline, lift, p_value, stars
    Sorted by lift descending.
    """
    baseline_success = sum(1 for e in episodes if e["success"])
    baseline_total = len(episodes)
    baseline_rate = baseline_success / baseline_total if baseline_total else 0

    # per-pattern counts (at episode level)
    pattern_with_success = defaultdict(int)
    pattern_with_failure = defaultdict(int)

    for ep in episodes:
        grams = episode_ngrams(ep[seq_key], n)
        for gram in grams:
            if ep["success"]:
                pattern_with_success[gram] += 1
            else:
                pattern_with_failure[gram] += 1

    all_patterns = set(pattern_with_success) | set(pattern_with_failure)
    results = []
    for pat in all_patterns:
        n_s = pattern_with_success[pat]
        n_f = pattern_with_failure[pat]
        n_with = n_s + n_f
        if n_with < min_episodes:
            continue
        n_without_s = baseline_success - n_s
        n_without_f = (baseline_total - baseline_success) - n_f
        sr = n_s / n_with
        lift = sr / baseline_rate if baseline_rate else 0
        # Fisher's exact: 2×2 table
        # [with&success, with&fail]
        # [without&success, without&fail]
        _, p = fisher_exact([[n_s, n_f], [max(n_without_s, 0), max(n_without_f, 0)]])
        stars = ("***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "")
        results.append({
            "pattern": pat,
            "n_with": n_with,
            "n_success": n_s,
            "success_rate": sr,
            "baseline": baseline_rate,
            "lift": lift,
            "p_value": p,
            "stars": stars,
        })

    results.sort(key=lambda x: -x["lift"])
    return results, baseline_rate, baseline_success, baseline_total


# ── reporting ─────────────────────────────────────────────────────────────────

def fmt_pat(pat):
    return " → ".join(pat)


def print_table(rows, title: str, baseline_rate: float, top: int = 10):
    print(f"\n{'─'*70}")
    print(f"  {title}")
    print(f"  baseline: {baseline_rate:.1%}")
    print(f"{'─'*70}")
    if not rows:
        print("  (brak wzorców spełniających próg częstości)")
        return
    print(f"  {'Wzorzec':<50} {'n':>4}  {'rate':>6}  {'lift':>6}  {'p':>7}  sig")
    print(f"  {'-'*50} {'----':>4}  {'------':>6}  {'------':>6}  {'-------':>7}  ---")
    for r in rows[:top]:
        print(f"  {fmt_pat(r['pattern']):<50} {r['n_with']:>4}  "
              f"{r['success_rate']:>5.1%}  {r['lift']:>6.2f}x  {r['p_value']:>7.4f}  {r['stars']}")


def run(db_path: str, label: str, min_episodes: int = 5):
    episodes = load_episodes(db_path)
    print(f"\n{'═'*70}")
    print(f"  {label}")
    print(f"  Epizody: {len(episodes)}")
    success_n = sum(1 for e in episodes if e["success"])
    print(f"  Sukcesy (score≥2): {success_n}/{len(episodes)} = {success_n/len(episodes):.1%}")
    print(f"  Min próg częstości: {min_episodes} epizodów")

    for n in [2, 3]:
        rows_a, base, bs, bt = analyze_ngrams(episodes, "assigns", n, min_episodes)
        print_table(rows_a, f"Delegacja {n}-gramy (assign_task)", base, top=10)

        rows_t, base, bs, bt = analyze_ngrams(episodes, "tools", n, min_episodes)
        print_table(rows_t, f"Narzędzia {n}-gramy (tool_use)", base, top=10)

    # summary: patterns with lift > 1.2 and p < 0.05
    print(f"\n{'═'*70}")
    print(f"  PODSUMOWANIE: wzorce istotne statystycznie (p<0.05, lift>1.2, n≥{min_episodes})")
    print(f"{'═'*70}")
    for n in [2, 3]:
        for seq_key, label_s in [("assigns", "Delegacja"), ("tools", "Narzędzia")]:
            rows, base, _, _ = analyze_ngrams(episodes, seq_key, n, min_episodes)
            sig = [r for r in rows if r["p_value"] < 0.05 and r["lift"] > 1.2]
            if sig:
                print(f"\n  {label_s} {n}-gramy (lift>1.2, p<0.05):")
                for r in sig:
                    print(f"    {fmt_pat(r['pattern'])}: n={r['n_with']}, "
                          f"rate={r['success_rate']:.1%}, lift={r['lift']:.2f}x, p={r['p_value']:.4f}{r['stars']}")

    # additionally: worst patterns (lift < 0.7, n >= min_episodes)
    print(f"\n{'═'*70}")
    print(f"  WZORCE KORELUJĄCE Z PORAŻKĄ (lift<0.7, n≥{min_episodes})")
    print(f"{'═'*70}")
    for n in [2, 3]:
        for seq_key, label_s in [("assigns", "Delegacja"), ("tools", "Narzędzia")]:
            rows, base, _, _ = analyze_ngrams(episodes, seq_key, n, min_episodes)
            bad = [r for r in rows if r["lift"] < 0.7]
            if bad:
                print(f"\n  {label_s} {n}-gramy (lift<0.7):")
                for r in bad:
                    print(f"    {fmt_pat(r['pattern'])}: n={r['n_with']}, "
                          f"rate={r['success_rate']:.1%}, lift={r['lift']:.2f}x, p={r['p_value']:.4f}{r['stars']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="./agent.db")
    parser.add_argument("--label", default="Agent (learning)")
    parser.add_argument("--min-episodes", type=int, default=5)
    args = parser.parse_args()
    run(args.db, args.label, args.min_episodes)
