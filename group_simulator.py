"""
group_simulator.py
Lightweight Monte Carlo simulator for World Cup group-stage qualification.

Simulates the remaining round-robin fixtures of a 4-team group hundreds of
times, sampling each match's scoreline from the shared prediction_engine
Poisson model (the same model used by Match Prediction Shorts), then
estimates each team's projected points/GF/GA and probability of finishing
in the top 2 (qualifying for the knockout stage). Tuned for engaging
sports-analytics content, not scientific accuracy.

Public API:
    simulate_group(teams, fixtures, n_sims=800) -> list[dict]
    build_match_matrices(teams, fixtures) -> dict
    simulate_group_once(names, fixtures, matrices, rng=random) -> list[dict]
"""
import random

import config
import prediction_engine


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS (also used by tournament_simulator.py)
# ═══════════════════════════════════════════════════════════════════════════════
def build_match_matrices(teams: list[dict],
                          fixtures: list[tuple[str, str]]) -> dict:
    """Builds a `prediction_engine.match_matrix()` for each fixture, applying
    the host-Elo bonus (config.HOSTS) per team. Depends only on Elo/host
    status, so callers can build this once and reuse it across many
    simulations of the same fixtures."""
    elos  = {t["name"]: t["elo"] for t in teams}
    hosts = {t["name"]: t.get("display") in config.HOSTS for t in teams}
    return {
        (h, a): prediction_engine.match_matrix(elos[h], elos[a], hosts[h], hosts[a])
        for h, a in fixtures
    }


def simulate_group_once(names: list[str], fixtures: list[tuple[str, str]],
                         matrices: dict, rng=random) -> list[dict]:
    """
    Plays one realization of `fixtures` (one round-robin) and returns the
    final table, sorted by points -> goal difference -> goals for -> a
    random tiebreak (descending) — mirrors a head-to-head/coin-flip
    tiebreaker.

    Returns a list of dicts, one per team in final-table order:
        {"name", "points", "gf", "ga", "gd"}
    """
    points = {n: 0 for n in names}
    gf     = {n: 0 for n in names}
    ga     = {n: 0 for n in names}

    for home, away in fixtures:
        gh, gw = prediction_engine.sample_from_matrix(matrices[(home, away)], rng)
        gf[home] += gh; ga[home] += gw
        gf[away] += gw; ga[away] += gh
        if gh > gw:
            points[home] += 3
        elif gh < gw:
            points[away] += 3
        else:
            points[home] += 1
            points[away] += 1

    order = sorted(
        names,
        key=lambda n: (points[n], gf[n] - ga[n], gf[n], rng.random()),
        reverse=True,
    )
    return [
        {"name": n, "points": points[n], "gf": gf[n], "ga": ga[n], "gd": gf[n] - ga[n]}
        for n in order
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════
def simulate_group(teams: list[dict], fixtures: list[tuple[str, str]],
                   n_sims: int = 800) -> list[dict]:
    """
    Runs `n_sims` Monte Carlo simulations of `fixtures` (a 4-team group's
    full round-robin, 6 matches) and returns each team's projected stats.

    Args:
        teams:    list of {"name": <canonical key>, "display": <ELO_MAP
                  display name>, "elo": int, ...}. "display" is used to
                  check config.HOSTS for the home-advantage Elo bonus.
        fixtures: list of (home_name, away_name) — both canonical keys
                  matching teams[i]["name"]
        n_sims:   number of simulations (500-1000 recommended)

    Returns a list of dicts (one per team), sorted by descending
    qualification probability:
        {"team", "points", "gf", "ga", "qualification_probability"}
    """
    names    = [t["name"] for t in teams]
    matrices = build_match_matrices(teams, fixtures)

    qualify_count = {n: 0 for n in names}
    points_sum    = {n: 0 for n in names}
    gf_sum        = {n: 0 for n in names}
    ga_sum        = {n: 0 for n in names}

    for _ in range(n_sims):
        standings = simulate_group_once(names, fixtures, matrices)
        for s in standings[:2]:
            qualify_count[s["name"]] += 1
        for s in standings:
            points_sum[s["name"]] += s["points"]
            gf_sum[s["name"]]     += s["gf"]
            ga_sum[s["name"]]     += s["ga"]

    results = [
        {
            "team":   n,
            "points": round(points_sum[n] / n_sims),
            "gf":     round(gf_sum[n] / n_sims),
            "ga":     round(ga_sum[n] / n_sims),
            "qualification_probability": round(100 * qualify_count[n] / n_sims),
        }
        for n in names
    ]
    results.sort(key=lambda r: -r["qualification_probability"])
    return results
