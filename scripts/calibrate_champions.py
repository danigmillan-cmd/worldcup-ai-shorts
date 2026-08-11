#!/usr/bin/env python3
"""
scripts/calibrate_champions.py
Calibration for the club-football constants in champions_predictions.py.

NOT part of the render pipeline — run by hand, and run it repeatedly:
    python scripts/calibrate_champions.py

Why this is different from scripts/calibrate_model.py
-----------------------------------------------------
The national-team script backtests against a public results dataset and scores
by Brier. There is no equivalent free dataset of club results with a matching
Elo history, but clubelo.com publishes, for every scheduled fixture, the full
scoreline probability distribution from its own model — the same model whose
ratings we consume. Fitting our Poisson to reproduce those probabilities is a
sound target: ClubElo's model is itself fitted to real results.

Be clear about what this proves: it calibrates us to AGREE WITH CLUBELO, not
to be accurate against reality. Any bias in their model is inherited.

The accumulation problem
------------------------
/Fixtures only returns the next few days, so a single run sees ~55 matches,
mostly from minor leagues in the European summer. That is nowhere near enough,
and it is skewed low. So each run appends what it sees to
data/clubelo_fixtures_history.json, keyed by fixture, and fits on the whole
accumulated history. Run it weekly through the autumn and the sample builds up
on its own — including the actual league-phase nights, which are the ones that
matter.

The script never edits champions_predictions.py. It prints a recommendation.
"""
import csv
import io
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import prediction_engine as pe

HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "clubelo_fixtures_history.json"

# Below this many fixtures the fit is noise. Chosen so that a run in August
# (~55 fixtures, minor leagues) refuses to recommend anything.
MIN_SAMPLE = 400

# Only fit on fixtures where both clubs are at least this strong. League-phase
# clubs sit well above it; without the filter the fit is dominated by leagues
# that score nothing like the Champions League.
MIN_ELO = 1550.0

GRID = {
    "base_total_goals": [round(2.4 + 0.1 * i, 1) for i in range(13)],   # 2.4 .. 3.6
    "elo_to_goals": [100 + 10 * i for i in range(21)],                  # 100 .. 300
    "host_elo_bonus": [20 + 10 * i for i in range(10)],                 # 20 .. 110
}

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; champions-shorts-calibration)"}


def _fetch_elo_by_name() -> dict[str, float]:
    """Every club ClubElo rates today, keyed by ITS spelling (not our slugs)."""
    url = f"http://api.clubelo.com/{date.today().isoformat()}"
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return {
        row["Club"]: float(row["Elo"])
        for row in csv.DictReader(io.StringIO(resp.text))
        if row.get("Club") and row.get("Elo")
    }


def _fetch_fixtures() -> list[dict]:
    resp = requests.get("http://api.clubelo.com/Fixtures", headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return list(csv.DictReader(io.StringIO(resp.text)))


def _clubelo_outcome_probs(row: dict) -> tuple[float, float, float] | None:
    """
    Collapse the R:i-j scoreline columns into (home, draw, away), normalized.

    The CSV only carries scorelines up to six goals, so the columns sum to
    between 0.92 and 0.99 rather than to 1 — the missing mass is the
    high-scoring tail. Rejecting rows that don't sum to 1 would silently throw
    away precisely the goal-heavy fixtures, which is the worst possible bias
    for fitting an expected-goals constant. They get renormalized instead.

    Returns None only if the row is genuinely unusable.
    """
    home = draw = away = 0.0
    for key, value in row.items():
        if not key or not key.startswith("R:"):
            continue
        try:
            goles_h, goles_a = (int(x) for x in key[2:].split("-"))
            p = float(value)
        except (ValueError, TypeError):
            continue
        if goles_h > goles_a:
            home += p
        elif goles_h == goles_a:
            draw += p
        else:
            away += p

    total = home + draw + away
    # Por debajo de esto la fila esta rota, no truncada.
    if total < 0.85:
        return None
    return home / total, draw / total, away / total


def _load_history() -> dict[str, dict]:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))["fixtures"]
    except (OSError, KeyError, ValueError):
        return {}


def _save_history(fixtures: dict[str, dict]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(
            {
                "actualizado": datetime.now(timezone.utc).isoformat(),
                "n": len(fixtures),
                "fixtures": fixtures,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def accumulate() -> dict[str, dict]:
    """Add today's fixtures to the history and return the whole thing."""
    history = _load_history()
    antes = len(history)

    elo = _fetch_elo_by_name()
    for row in _fetch_fixtures():
        home, away = row.get("Home"), row.get("Away")
        if home not in elo or away not in elo:
            continue
        probs = _clubelo_outcome_probs(row)
        if probs is None:
            continue
        p_home, p_draw, p_away = probs

        clave = f"{row['Date']}|{home}|{away}"
        history[clave] = {
            "elo_home": round(elo[home], 1),
            "elo_away": round(elo[away], 1),
            "p_home": round(p_home, 4),
            "p_draw": round(p_draw, 4),
            "p_away": round(p_away, 4),
        }

    _save_history(history)
    print(f"[INFO] Historial: {antes} -> {len(history)} partidos "
          f"(+{len(history) - antes} nuevos)")
    return history


def error_medio(muestra: list[dict], **constantes) -> float:
    """Brier multiclase medio contra las probabilidades de ClubElo."""
    total = 0.0
    for f in muestra:
        matrix = pe.match_matrix(f["elo_home"], f["elo_away"], host_a=True, **constantes)
        p_h, p_d, p_a = pe.matrix_outcome_probs(matrix)
        total += ((p_h - f["p_home"]) ** 2
                  + (p_d - f["p_draw"]) ** 2
                  + (p_a - f["p_away"]) ** 2)
    return total / len(muestra)


def main() -> None:
    history = accumulate()

    muestra = [
        f for f in history.values()
        if min(f["elo_home"], f["elo_away"]) >= MIN_ELO
    ]
    print(f"[INFO] Partidos con ambos equipos >= {MIN_ELO:.0f}: {len(muestra)}")

    if not muestra:
        print("[WARN] Muestra vacía. Vuelve a ejecutarlo cuando arranquen las ligas.")
        return

    resultados = []
    for base in GRID["base_total_goals"]:
        for divisor in GRID["elo_to_goals"]:
            for bonus in GRID["host_elo_bonus"]:
                err = error_medio(
                    muestra,
                    base_total_goals=base,
                    elo_to_goals=divisor,
                    host_elo_bonus=bonus,
                )
                resultados.append((err, base, divisor, bonus))
    resultados.sort()

    import champions_predictions as cp
    actual = error_medio(muestra, **cp.CHAMPIONS_CONSTANTS)

    print(f"\nConstantes actuales -> error {actual:.5f}")
    print("\nMejores combinaciones:")
    print(f"{'error':>9}  {'goles':>6} {'elo/gol':>8} {'bonus':>6}")
    for err, base, divisor, bonus in resultados[:8]:
        print(f"{err:>9.5f}  {base:>6.1f} {divisor:>8} {bonus:>6}")

    mejor = resultados[0]
    print()
    if len(muestra) < MIN_SAMPLE:
        print(f"[WARN] Muestra insuficiente ({len(muestra)} < {MIN_SAMPLE}). "
              "NO apliques estos valores todavía.")
        print("       Vuelve a ejecutarlo cada semana: el historial se acumula solo,")
        print("       y lo que importa son las noches de fase liga.")
    else:
        print(f"[INFO] Recomendado: base_total_goals={mejor[1]}, "
              f"elo_to_goals={mejor[2]}, host_elo_bonus={mejor[3]}")
        print(f"       Mejora del error: {actual:.5f} -> {mejor[0]:.5f} "
              f"({(1 - mejor[0] / actual):.1%})")
        print("       Aplícalo a mano en CHAMPIONS_CONSTANTS.")


if __name__ == "__main__":
    main()
