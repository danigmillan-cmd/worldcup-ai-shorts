#!/usr/bin/env python3
"""
scripts/calibrate_model.py
One-off backtest/calibration for prediction_engine's Poisson model.

NOT part of the hourly pipeline — run by hand:
    python scripts/calibrate_model.py

What it does
------------
1. Downloads (and caches in data/international_results.csv) the free,
   public match-results dataset from martj42/international_results.
2. Recomputes a from-scratch Elo rating for every team in rankings.ELO_MAP
   using a standard K=20 update, starting from 1500 on 2000-01-01 — this
   gives each backtest match an "as of the time" Elo without leaking future
   information.
3. Backtests prediction_engine over matches from 2010-01-01 onward, sweeping
   a small grid of ELO_TO_GOALS / BASE_TOTAL_GOALS / HOST_ELO_BONUS values,
   scored by multiclass (1X2) Brier score and accuracy, with a reconstructed
   "old model" (pre-Poisson win%-only heuristic) as the baseline.
4. Prints the best combinations and writes reports/calibration_<date>.md.

This script does NOT modify config.py — the recommended values are applied
by hand (or by a follow-up edit) after reviewing the report.
"""
import csv
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import rankings

# ─── Dataset ──────────────────────────────────────────────────────────────────
CSV_URL    = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
CACHE_FILE = config.DATA_DIR / "international_results.csv"

# ─── Elo recompute ────────────────────────────────────────────────────────────
ELO_START_DATE      = date(2000, 1, 1)   # Elo recompute starts here (1500 for everyone)
BACKTEST_START_DATE = date(2010, 1, 1)   # backtest uses matches on/after this date
K_FACTOR            = 20.0
INITIAL_ELO         = 1500.0

# ─── Calibration grid ─────────────────────────────────────────────────────────
ELO_TO_GOALS_GRID     = [120, 150, 180, 210, 240]
BASE_TOTAL_GOALS_GRID = [2.4, 2.6, 2.8]
HOST_ELO_BONUS_GRID   = [0, 50, 75, 100, 125, 150]

REPORT_FILE = config.REPORTS_DIR / f"calibration_{date.today().isoformat()}.md"


# ═══════════════════════════════════════════════════════════════════════════════
# DATASET
# ═══════════════════════════════════════════════════════════════════════════════
def _ensure_dataset() -> bool:
    if CACHE_FILE.exists():
        print(f"[INFO] Using cached dataset: {CACHE_FILE}")
        return True
    try:
        print(f"[INFO] Downloading {CSV_URL} ...")
        resp = requests.get(CSV_URL, timeout=30)
        resp.raise_for_status()
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_bytes(resp.content)
        print(f"[INFO] Cached {len(resp.content)} bytes -> {CACHE_FILE}")
        return True
    except Exception as exc:
        print(f"[WARN] Download failed ({type(exc).__name__}): {exc}")
        print(f"[WARN] Download it manually from:\n         {CSV_URL}")
        print(f"[WARN] and save it as:\n         {CACHE_FILE}")
        return False


def _map_team(name: str) -> str | None:
    """Maps a historical team name to its rankings.ELO_MAP display name, or
    None if untracked (dissolved nations like "West Germany", non-FIFA
    sides, etc. — those rows are simply dropped)."""
    mapping = rankings.ELO_MAP.get(name) or next(
        (v for k, v in rankings.ELO_MAP.items() if k.lower() == name.lower()), None
    )
    return mapping[0] if mapping else None


def _load_matches() -> list[dict]:
    rows = []
    with open(CACHE_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                d = date.fromisoformat(row["date"][:10])
            except ValueError:
                continue
            if d < ELO_START_DATE:
                continue
            home = _map_team(row["home_team"])
            away = _map_team(row["away_team"])
            if not home or not away or home == away:
                continue
            try:
                hs, gs = int(row["home_score"]), int(row["away_score"])
            except ValueError:
                continue
            neutral = row.get("neutral", "FALSE").strip().upper() == "TRUE"
            rows.append({
                "date": d, "home": home, "away": away,
                "home_score": hs, "away_score": gs, "neutral": neutral,
            })
    rows.sort(key=lambda r: r["date"])
    return rows


def _recompute_elo_and_backtest(rows: list[dict]) -> list[dict]:
    """Recomputes a from-scratch Elo rating for every ELO_MAP team (K=20,
    starting from 1500 on ELO_START_DATE), then returns the subset of
    matches on/after BACKTEST_START_DATE, each annotated with both teams'
    Elo *immediately before* that match was played."""
    elo: dict[str, float] = {}
    backtest = []
    for r in rows:
        h, a = r["home"], r["away"]
        elo_h = elo.get(h, INITIAL_ELO)
        elo_a = elo.get(a, INITIAL_ELO)
        if r["date"] >= BACKTEST_START_DATE:
            backtest.append({**r, "elo_home": elo_h, "elo_away": elo_a})

        expected_h = 1.0 / (1.0 + 10 ** ((elo_a - elo_h) / 400.0))
        if r["home_score"] > r["away_score"]:
            actual_h = 1.0
        elif r["home_score"] < r["away_score"]:
            actual_h = 0.0
        else:
            actual_h = 0.5
        delta = K_FACTOR * (actual_h - expected_h)
        elo[h] = elo_h + delta
        elo[a] = elo_a - delta
    return backtest


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL (vectorized re-implementation of prediction_engine, for grid-search speed)
# ═══════════════════════════════════════════════════════════════════════════════
def _poisson_pmf(k: int, lam: np.ndarray) -> np.ndarray:
    return np.exp(-lam) * lam ** k / math.factorial(k)


def _outcome_probs(elo_home: np.ndarray, elo_away: np.ndarray, neutral: np.ndarray,
                   elo_to_goals: float, base_total_goals: float, host_bonus: float
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Same formula as prediction_engine.match_matrix / matrix_outcome_probs,
    vectorized over all backtest matches at once. host_a = not neutral,
    host_b is never bonused (mirrors how HOSTS will apply in 2026)."""
    eff_home  = elo_home + np.where(neutral, 0.0, host_bonus)
    goal_diff = (eff_home - elo_away) / elo_to_goals
    lambda_home = np.maximum(config.MIN_LAMBDA, (base_total_goals + goal_diff) / 2)
    lambda_away = np.maximum(config.MIN_LAMBDA, (base_total_goals - goal_diff) / 2)

    p_home = np.zeros_like(elo_home)
    p_draw = np.zeros_like(elo_home)
    p_away = np.zeros_like(elo_home)
    for i in range(config.MAX_GOALS + 1):
        pmf_i = _poisson_pmf(i, lambda_home)
        for j in range(config.MAX_GOALS + 1):
            cell = pmf_i * _poisson_pmf(j, lambda_away)
            if i > j:
                p_home += cell
            elif i == j:
                p_draw += cell
            else:
                p_away += cell
    return p_home, p_draw, p_away


def _brier_and_accuracy(p_home: np.ndarray, p_draw: np.ndarray, p_away: np.ndarray,
                        y: np.ndarray) -> tuple[float, float]:
    """y: 0=home win, 1=draw, 2=away win. Brier = multiclass (1X2) Brier
    score (lower is better, 0=perfect). Accuracy = argmax(p_home,p_draw,p_away)
    matching the actual result."""
    y_home = (y == 0).astype(float)
    y_draw = (y == 1).astype(float)
    y_away = (y == 2).astype(float)
    brier = np.mean((p_home - y_home) ** 2 + (p_draw - y_draw) ** 2 + (p_away - y_away) ** 2)
    pred = np.argmax(np.stack([p_home, p_draw, p_away]), axis=0)
    accuracy = np.mean(pred == y)
    return float(brier), float(accuracy)


def _old_model(elo_home: np.ndarray, elo_away: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Reconstruction of the pre-Poisson heuristic:
    match_data.head_to_head_probabilities (logistic win%, no draw
    probability) + match_data.predict_score's deterministic winner choice
    (draw iff the win% gap < 5, else the higher-% side)."""
    p_home = 1.0 / (1.0 + 10 ** ((elo_away - elo_home) / 400.0))
    p_away = 1.0 - p_home
    p_draw = np.zeros_like(p_home)
    brier, _ = _brier_and_accuracy(p_home, p_draw, p_away, y)

    pct_home = np.clip(np.round(p_home * 100), 1, 99)
    pct_away = 100 - pct_home
    diff = np.abs(pct_home - pct_away)
    pred = np.where(diff < 5, 1, np.where(pct_home >= pct_away, 0, 2))
    accuracy = float(np.mean(pred == y))
    return brier, accuracy


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════════════════
def _write_report(backtest: list[dict], old_brier: float, old_acc: float,
                  results: list[tuple]) -> None:
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    top = results[:10]
    best = results[0]

    lines = [
        f"# Prediction Model Calibration — {date.today().isoformat()}",
        "",
        "One-off backtest of `prediction_engine`'s Poisson model against real "
        "historical results, run via `scripts/calibrate_model.py`. This script "
        "does not modify `config.py` — the recommended values below were "
        "reviewed and applied by hand.",
        "",
        "## Methodology",
        "",
        "- **Dataset**: [martj42/international_results]"
        "(https://github.com/martj42/international_results) `results.csv`, "
        f"cached at `data/international_results.csv`.",
        f"- **Elo recompute**: every team in `rankings.ELO_MAP` starts at "
        f"{INITIAL_ELO:.0f} on {ELO_START_DATE}, and a standard Elo update "
        f"(K={K_FACTOR:.0f}) is applied match-by-match using only matches "
        f"between two ELO_MAP teams. This gives each backtest match an "
        f"\"as of the time\" rating — current live Elo is never used, so "
        f"no future information leaks into past matches.",
        f"- **Backtest window**: {len(backtest)} matches from "
        f"{BACKTEST_START_DATE} onward (after a 10-year Elo burn-in).",
        "- **Home advantage proxy**: `host_a = not neutral` (the listed home "
        "team gets `HOST_ELO_BONUS` unless the match was played at a neutral "
        "venue); `host_b` is never bonused. This mirrors how `config.HOSTS` "
        "applies the bonus to USA/Mexico/Canada in 2026.",
        "- **Metrics**: multiclass (1X2) Brier score (lower is better, "
        "0 = perfect) and accuracy of `argmax(p_a, p_draw, p_b)` against the "
        "actual full-time result.",
        "- **Old-model baseline**: reconstruction of the pre-Poisson "
        "heuristic — `p_home = 1/(1+10^((elo_away-elo_home)/400))`, "
        "`p_away = 1-p_home`, `p_draw = 0` (the old model never modeled "
        "draws); predicted winner is `draw` when the win% gap is `<5`, else "
        "the higher-% side, matching `match_data.predict_score`'s "
        "deterministic winner choice. No home-advantage term (the old model "
        "never had one).",
        "",
        "## Old model baseline",
        "",
        f"Brier = **{old_brier:.4f}**, Accuracy = **{old_acc:.3%}**",
        "",
        "## Top 10 grid combinations (by Brier score)",
        "",
        "| ELO_TO_GOALS | BASE_TOTAL_GOALS | HOST_ELO_BONUS | Brier | Accuracy |",
        "|---:|---:|---:|---:|---:|",
    ]
    for etg, btg, hb, brier, acc in top:
        lines.append(f"| {etg} | {btg:.1f} | {hb} | {brier:.4f} | {acc:.3%} |")

    lines += [
        "",
        "## Recommended config.py values",
        "",
        "```python",
        f"ELO_TO_GOALS = {best[0]}",
        f"BASE_TOTAL_GOALS = {best[1]}",
        f"HOST_ELO_BONUS = {best[2]}",
        "```",
        "",
        f"vs. old model: Brier {best[3]:.4f} vs {old_brier:.4f} "
        f"({'better' if best[3] < old_brier else 'worse'}), "
        f"Accuracy {best[4]:.3%} vs {old_acc:.3%}.",
        "",
    ]

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[INFO] Report written: {REPORT_FILE}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    if not _ensure_dataset():
        print("[WARN] Calibration aborted — no dataset available.")
        return

    rows = _load_matches()
    backtest = _recompute_elo_and_backtest(rows)
    print(f"[INFO] {len(rows)} ELO_MAP-vs-ELO_MAP matches since {ELO_START_DATE} "
          f"used for the Elo recompute")
    print(f"[INFO] {len(backtest)} matches since {BACKTEST_START_DATE} used for the backtest")

    if not backtest:
        print("[WARN] No backtest matches found — aborting.")
        return

    elo_home = np.array([m["elo_home"] for m in backtest], dtype=float)
    elo_away = np.array([m["elo_away"] for m in backtest], dtype=float)
    neutral  = np.array([m["neutral"] for m in backtest], dtype=bool)
    y = np.array([
        0 if m["home_score"] > m["away_score"]
        else (2 if m["home_score"] < m["away_score"] else 1)
        for m in backtest
    ])

    old_brier, old_acc = _old_model(elo_home, elo_away, y)
    print(f"\n[INFO] Old model (win%% only, no draw modeling): "
          f"Brier={old_brier:.4f}  Accuracy={old_acc:.3%}")

    results = []
    for etg in ELO_TO_GOALS_GRID:
        for btg in BASE_TOTAL_GOALS_GRID:
            for hb in HOST_ELO_BONUS_GRID:
                p_home, p_draw, p_away = _outcome_probs(elo_home, elo_away, neutral, etg, btg, hb)
                brier, acc = _brier_and_accuracy(p_home, p_draw, p_away, y)
                results.append((etg, btg, hb, brier, acc))

    results.sort(key=lambda r: r[3])  # lower Brier = better

    print(f"\n  {'ELO_TO_GOALS':>13} {'BASE_TOTAL_GOALS':>17} {'HOST_ELO_BONUS':>15} {'Brier':>8} {'Accuracy':>9}")
    print("  " + "-" * 68)
    for etg, btg, hb, brier, acc in results[:10]:
        print(f"  {etg:>13} {btg:>17.1f} {hb:>15} {brier:>8.4f} {acc:>9.3%}")

    best = results[0]
    print(f"\n[INFO] Recommended: ELO_TO_GOALS={best[0]}, BASE_TOTAL_GOALS={best[1]}, HOST_ELO_BONUS={best[2]}")
    print(f"[INFO] Brier {best[3]:.4f} vs old-model baseline {old_brier:.4f} "
          f"({'better' if best[3] < old_brier else 'worse'})")
    print(f"[INFO] Accuracy {best[4]:.3%} vs old-model baseline {old_acc:.3%}")

    _write_report(backtest, old_brier, old_acc, results)


if __name__ == "__main__":
    main()
