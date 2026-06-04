"""
ngram_emergence_v3.py - Analiza emergencji wzorców n-gramowych

Trzy warstwy analizy:
  1. L vs NL       — które wzorce pojawiły się / wzmocniły dzięki ACE
  2. L1 vs L2      — czy wzorce rosną w drugiej połowie datasetu (epizody chronologiczne)
  3. Trójkąt       — wzorce emergentne: słabe w NL, obecne w L1, silne w L2

Metryki:
  lift  = success_rate(wzorzec) / baseline
  Δlift = lift_L - lift_NL
  trend = lift_L2 - lift_L1

Jednostka: epizod (binarnie), test Fishera (dwustronny), próg n≥3 dla połówek.
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


def load_episodes(db_path: str, success_threshold: int = 2) -> list:
    """Załaduj epizody posortowane chronologicznie."""
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
            "created_at": r.get("created_at") or "",
        })

    episodes.sort(key=lambda e: e["created_at"])
    return episodes


# ── n-gram logic ──────────────────────────────────────────────────────────────

def episode_ngrams(seq: list, n: int) -> set:
    if len(seq) < n:
        return set()
    return {tuple(seq[i:i+n]) for i in range(len(seq) - n + 1)}


def compute_pattern_stats(episodes: list, seq_key: str, n: int, min_ep: int = 3) -> dict:
    """
    Zwraca słownik: pattern → {n_with, n_success, success_rate, lift, p_value, stars}
    """
    baseline_s = sum(1 for e in episodes if e["success"])
    baseline_n = len(episodes)
    baseline_r = baseline_s / baseline_n if baseline_n else 0

    pat_s = defaultdict(int)
    pat_f = defaultdict(int)
    for ep in episodes:
        for gram in episode_ngrams(ep[seq_key], n):
            if ep["success"]:
                pat_s[gram] += 1
            else:
                pat_f[gram] += 1

    result = {}
    for pat in set(pat_s) | set(pat_f):
        ns, nf = pat_s[pat], pat_f[pat]
        total = ns + nf
        if total < min_ep:
            continue
        sr = ns / total
        lift = sr / baseline_r if baseline_r else 0
        nws = max(baseline_s - ns, 0)
        nwf = max((baseline_n - baseline_s) - nf, 0)
        _, p = fisher_exact([[ns, nf], [nws, nwf]])
        stars = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
        result[pat] = {
            "n_with": total, "n_success": ns,
            "success_rate": sr, "baseline": baseline_r,
            "lift": lift, "p_value": p, "stars": stars,
        }
    return result, baseline_r, baseline_s, baseline_n


# ── comparison helpers ────────────────────────────────────────────────────────

def fmt_pat(pat):
    return " → ".join(pat)


def compare_groups(stats_a: dict, stats_b: dict, label_a: str, label_b: str,
                   seq_label: str, n: int,
                   min_delta: float = 0.3, top: int = 12):
    """Wyświetl porównanie dwóch grup dla danego n-gramu."""
    all_pats = set(stats_a) | set(stats_b)
    rows = []
    for pat in all_pats:
        lift_a = stats_a[pat]["lift"] if pat in stats_a else None
        lift_b = stats_b[pat]["lift"] if pat in stats_b else None
        n_a = stats_a[pat]["n_with"] if pat in stats_a else 0
        n_b = stats_b[pat]["n_with"] if pat in stats_b else 0
        sr_a = stats_a[pat]["success_rate"] if pat in stats_a else None
        sr_b = stats_b[pat]["success_rate"] if pat in stats_b else None
        p_b = stats_b[pat]["p_value"] if pat in stats_b else 1.0
        stars_b = stats_b[pat]["stars"] if pat in stats_b else ""
        if lift_a is None and lift_b is None:
            continue
        delta = (lift_b or 0) - (lift_a or 0)
        rows.append((pat, lift_a, lift_b, n_a, n_b, sr_a, sr_b, delta, p_b, stars_b))

    rows.sort(key=lambda x: -x[7])  # sort by delta desc

    print(f"\n  {seq_label} {n}-gramy │ {label_a} → {label_b}  (Δlift ≥ {min_delta} pokazane)")
    print(f"  {'Wzorzec':<48} {label_a:>8}  {label_b:>8}  {'Δlift':>7}  {'n_'+label_b:>6}  p{label_b}")
    print(f"  {'-'*48} {'--------':>8}  {'--------':>8}  {'-------':>7}  {'------':>6}  ------")

    shown = 0
    for pat, la, lb, na, nb, sra, srb, delta, pb, sb in rows:
        if abs(delta) < min_delta and shown >= 3:
            continue
        la_s = f"{la:.2f}x" if la is not None else "  —   "
        lb_s = f"{lb:.2f}x" if lb is not None else "  —   "
        sr_s = f"({srb:.0%})" if srb is not None else ""
        print(f"  {fmt_pat(pat):<48} {la_s:>8}  {lb_s:>8}  {delta:>+7.2f}  {nb:>6}  {pb:.4f}{sb} {sr_s}")
        shown += 1
        if shown >= top:
            break


def emergence_triangle(stats_nl: dict, stats_l1: dict, stats_l2: dict,
                        seq_label: str, n: int,
                        delta_nl: float = 0.2, min_l2_lift: float = 1.2):
    """Wzorce emergentne: słabe w NL, rosnące L1→L2."""
    all_pats = set(stats_l1) | set(stats_l2)
    candidates = []
    for pat in all_pats:
        lift_nl = stats_nl.get(pat, {}).get("lift", 0)
        lift_l1 = stats_l1.get(pat, {}).get("lift")
        lift_l2 = stats_l2.get(pat, {}).get("lift")
        n_l2 = stats_l2.get(pat, {}).get("n_with", 0)
        p_l2 = stats_l2.get(pat, {}).get("p_value", 1.0)
        stars_l2 = stats_l2.get(pat, {}).get("stars", "")

        if lift_l1 is None or lift_l2 is None:
            continue
        trend = lift_l2 - lift_l1
        delta_from_nl = (lift_l2 or 0) - lift_nl

        # Kryteria trójkąta emergencji:
        # 1. słaby lub nieobecny w NL
        # 2. lift_l2 powyżej progu
        # 3. trend rosnący
        if lift_nl < 1.2 and lift_l2 >= min_l2_lift and trend > 0:
            candidates.append((pat, lift_nl, lift_l1, lift_l2, trend, delta_from_nl, n_l2, p_l2, stars_l2))

    candidates.sort(key=lambda x: -x[4])  # sort by trend

    if not candidates:
        print(f"\n  {seq_label} {n}-gramy │ BRAK kandydatów emergentnych")
        return

    print(f"\n  {seq_label} {n}-gramy │ Trójkąt emergencji (NL<1.2, L2≥{min_l2_lift}, trend>0)")
    print(f"  {'Wzorzec':<48} {'NL':>6}  {'L1':>6}  {'L2':>6}  {'trend':>7}  {'n_L2':>5}  p_L2")
    print(f"  {'-'*48} {'------':>6}  {'------':>6}  {'------':>6}  {'-------':>7}  {'-----':>5}  ----")
    for pat, nl, l1, l2, trend, delta, nl2, pl2, sl2 in candidates:
        print(f"  {fmt_pat(pat):<48} {nl:>6.2f}x  {l1:>6.2f}x  {l2:>6.2f}x  {trend:>+7.2f}  {nl2:>5}  {pl2:.4f}{sl2}")


# ── main ──────────────────────────────────────────────────────────────────────

def run(learning_db: str, no_learning_db: str, label: str, min_ep_full: int = 5, min_ep_half: int = 3):
    ep_L = load_episodes(learning_db)
    ep_NL = load_episodes(no_learning_db)

    mid = len(ep_L) // 2
    ep_L1 = ep_L[:mid]
    ep_L2 = ep_L[mid:]

    print(f"\n{'═'*72}")
    print(f"  {label}")
    print(f"{'═'*72}")
    print(f"  Epizody NL : {len(ep_NL)}  │  baseline: "
          f"{sum(1 for e in ep_NL if e['success'])/len(ep_NL):.1%}")
    print(f"  Epizody L  : {len(ep_L)}  │  baseline: "
          f"{sum(1 for e in ep_L if e['success'])/len(ep_L):.1%}")
    print(f"  L1 (pierwsze {mid}): baseline "
          f"{sum(1 for e in ep_L1 if e['success'])/len(ep_L1):.1%}  "
          f"│  L2 (ostatnie {len(ep_L2)}): baseline "
          f"{sum(1 for e in ep_L2 if e['success'])/len(ep_L2):.1%}")
    print(f"  Sortowanie L: chronologicznie po created_at")

    for n in [2, 3]:
        for seq_key, seq_label in [("assigns", "Delegacja"), ("tools", "Narzędzia")]:

            stats_NL, *_ = compute_pattern_stats(ep_NL, seq_key, n, min_ep_full)
            stats_L,  *_ = compute_pattern_stats(ep_L,  seq_key, n, min_ep_full)
            stats_L1, *_ = compute_pattern_stats(ep_L1, seq_key, n, min_ep_half)
            stats_L2, *_ = compute_pattern_stats(ep_L2, seq_key, n, min_ep_half)

            print(f"\n{'─'*72}")
            print(f"  ▶ {seq_label} {n}-gramy")
            print(f"{'─'*72}")

            # Warstwa 1: L vs NL
            compare_groups(stats_NL, stats_L, "NL", "L",
                           seq_label, n, min_delta=0.25)

            # Warstwa 2: L1 vs L2
            compare_groups(stats_L1, stats_L2, "L1", "L2",
                           seq_label, n, min_delta=0.20)

            # Warstwa 3: trójkąt emergencji
            print()
            emergence_triangle(stats_NL, stats_L1, stats_L2, seq_label, n)

    # Podsumowanie: top emergentne wzorce delegacji
    print(f"\n{'═'*72}")
    print(f"  PODSUMOWANIE EMERGENCJI — najsilniejsze trójkąty (delegacja + narzędzia)")
    print(f"{'═'*72}")
    for n in [2, 3]:
        for seq_key, seq_label in [("assigns", "Delegacja"), ("tools", "Narzędzia")]:
            stats_NL, *_ = compute_pattern_stats(ep_NL, seq_key, n, min_ep_full)
            stats_L1, *_ = compute_pattern_stats(ep_L1, seq_key, n, min_ep_half)
            stats_L2, *_ = compute_pattern_stats(ep_L2, seq_key, n, min_ep_half)
            stats_L,  *_ = compute_pattern_stats(ep_L,  seq_key, n, min_ep_full)

            all_pats = set(stats_L1) | set(stats_L2)
            rows = []
            for pat in all_pats:
                lift_nl  = stats_NL.get(pat, {}).get("lift", 0)
                lift_l   = stats_L.get(pat, {}).get("lift", 0)
                lift_l1  = stats_L1.get(pat, {}).get("lift", 0)
                lift_l2  = stats_L2.get(pat, {}).get("lift", 0)
                n_l      = stats_L.get(pat, {}).get("n_with", 0)
                p_l      = stats_L.get(pat, {}).get("p_value", 1.0)
                stars_l  = stats_L.get(pat, {}).get("stars", "")
                trend    = lift_l2 - lift_l1
                delta_nl = lift_l - lift_nl
                if lift_nl < 1.2 and lift_l2 >= 1.2 and trend > 0:
                    rows.append((pat, lift_nl, lift_l1, lift_l2, trend, delta_nl, lift_l, n_l, p_l, stars_l))

            if not rows:
                continue
            rows.sort(key=lambda x: -(x[4] * x[6]))  # trend * lift_L

            print(f"\n  {seq_label} {n}-gramy (NL→L1→L2, sortowane wg trend×lift_L):")
            print(f"  {'Wzorzec':<48} {'NL':>6}  {'L1':>6}  {'L2':>6}  {'trend':>7}  {'lift_L':>7}  n_L  p_L")
            print(f"  {'-'*48} {'------':>6}  {'------':>6}  {'------':>6}  {'-------':>7}  {'-------':>7}  ---  ---")
            for pat, nl, l1, l2, trend, dlt, ll, nl_n, pl, sl in rows[:8]:
                print(f"  {fmt_pat(pat):<48} {nl:>6.2f}x  {l1:>6.2f}x  {l2:>6.2f}x  {trend:>+7.2f}  {ll:>7.2f}x  {nl_n:>3}  {pl:.4f}{sl}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--learning-db",    default="./agent.db")
    parser.add_argument("--no-learning-db", default="./agent_no_learning.db")
    parser.add_argument("--label",          default="Agent")
    parser.add_argument("--min-ep-full",    type=int, default=5)
    parser.add_argument("--min-ep-half",    type=int, default=3)
    args = parser.parse_args()
    run(args.learning_db, args.no_learning_db, args.label,
        args.min_ep_full, args.min_ep_half)
