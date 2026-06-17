"""
prediction_engine.py
Shared Poisson-based match prediction engine.

Used by both match_data.py (single Match Prediction Shorts) and
group_simulator.py (group-stage Monte Carlo) so both content types derive
win/draw/loss probabilities AND a predicted scoreline from the SAME model —
no more divergence between "the bars" and "the score".

Model
-----
1. Effective Elo: a 2026 host nation (config.HOSTS, checked against the
   ELO_MAP *display* name — "USA"/"MEXICO"/"CANADA") gets
   `+ config.HOST_ELO_BONUS` added to its raw Elo before anything else.
   (Honest simplification: in 2026 the hosts don't play every match at
   home, but a flat bonus is a cheap first-pass approximation.)

2. Elo -> expected goals (lambda_a, lambda_b): the *difference* between the
   two effective Elos is converted into an expected goal difference via
       goal_diff = (elo_eff_a - elo_eff_b) / config.ELO_TO_GOALS
   which is then split around the league-average combined goals per match
   (config.BASE_TOTAL_GOALS):
       lambda_a = (BASE_TOTAL_GOALS + goal_diff) / 2
       lambda_b = (BASE_TOTAL_GOALS - goal_diff) / 2
   both floored at config.MIN_LAMBDA to stay positive for extreme gaps.
   This is a simple, monotonic, linear mapping, calibrated against real
   results by scripts/calibrate_model.py (see config.py for the dated
   comment with the chosen constants).

3. Scoreline matrix: P(a scores i, b scores j) = Poisson(i; lambda_a) *
   Poisson(j; lambda_b), for i, j in 0..config.MAX_GOALS (tail mass beyond
   that is negligible). p_win_a / p_draw / p_win_b and the modal scoreline
   are all derived from this SAME matrix, so the 3-outcome split and the
   predicted score are always coherent with each other:
     - p_win_a  = sum of cells where i > j
     - p_draw   = sum of cells where i == j
     - p_win_b  = sum of cells where i < j
     - score    = the (i, j) cell with the highest probability (the mode)
     - winner   = "draw" if the modal score is a tie, else whichever of
       p_win_a / p_draw / p_win_b is largest.

Public API:
    match_matrix(elo_a, elo_b, host_a=False, host_b=False) -> matrix
    matrix_outcome_probs(matrix) -> (p_a, p_draw, p_b)
    matrix_modal_score(matrix) -> (ga, gb)
    sample_from_matrix(matrix, rng=None) -> (ga, gb)
    predict_match(elo_a, elo_b, host_a=False, host_b=False) -> dict
    sample_score(elo_a, elo_b, host_a=False, host_b=False, rng=None) -> (ga, gb)
"""
import math
import random

import config

# Poisson(k; lam) = exp(-lam) * lam**k / k! — precompute k! for the cells
# we'll ever need (0..MAX_GOALS) to avoid recomputing it per call.
_FACTORIALS = [math.factorial(k) for k in range(config.MAX_GOALS + 1)]


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL
# ═══════════════════════════════════════════════════════════════════════════════
def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / _FACTORIALS[k]


def _expected_goals(elo_a: float, elo_b: float,
                    host_a: bool, host_b: bool) -> tuple[float, float]:
    """Elo -> (lambda_a, lambda_b) — see module docstring for the formula."""
    eff_a = elo_a + (config.HOST_ELO_BONUS if host_a else 0)
    eff_b = elo_b + (config.HOST_ELO_BONUS if host_b else 0)
    goal_diff = (eff_a - eff_b) / config.ELO_TO_GOALS
    lambda_a = max(config.MIN_LAMBDA, (config.BASE_TOTAL_GOALS + goal_diff) / 2)
    lambda_b = max(config.MIN_LAMBDA, (config.BASE_TOTAL_GOALS - goal_diff) / 2)
    return lambda_a, lambda_b


def match_matrix(elo_a: float, elo_b: float,
                 host_a: bool = False, host_b: bool = False) -> list[list[float]]:
    """Returns the (MAX_GOALS+1) x (MAX_GOALS+1) scoreline probability matrix
    P[i][j] = P(team_a scores i, team_b scores j)."""
    lambda_a, lambda_b = _expected_goals(elo_a, elo_b, host_a, host_b)
    n = config.MAX_GOALS + 1
    pa = [_poisson_pmf(i, lambda_a) for i in range(n)]
    pb = [_poisson_pmf(j, lambda_b) for j in range(n)]
    return [[pa[i] * pb[j] for j in range(n)] for i in range(n)]


def matrix_outcome_probs(matrix: list[list[float]]) -> tuple[float, float, float]:
    """Returns (p_win_a, p_draw, p_win_b) by summing the matrix's lower
    triangle / diagonal / upper triangle."""
    p_a = p_draw = p_b = 0.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if i > j:
                p_a += p
            elif i == j:
                p_draw += p
            else:
                p_b += p
    return p_a, p_draw, p_b


def matrix_modal_score(matrix: list[list[float]]) -> tuple[int, int]:
    """Returns the (ga, gb) cell with the highest probability — the
    "predicted score". Ties keep the first (lowest i, then lowest j) cell
    found, which favours the lower-scoring/cleaner result."""
    best_i, best_j, best_p = 0, 0, -1.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if p > best_p:
                best_p, best_i, best_j = p, i, j
    return best_i, best_j


def sample_from_matrix(matrix: list[list[float]], rng=None) -> tuple[int, int]:
    """Draws a single (ga, gb) scoreline from the matrix's distribution.

    `rng` is anything with a `.random()` method (a `random.Random`
    instance, or the `random` module itself — the default).
    """
    rng = rng or random
    total = sum(sum(row) for row in matrix)
    r = rng.random() * total
    acc = 0.0
    last = (0, 0)
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            acc += p
            last = (i, j)
            if r <= acc:
                return i, j
    return last


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════
def predict_match(elo_a: float, elo_b: float,
                  host_a: bool = False, host_b: bool = False) -> dict:
    """
    Returns:
        {
            "p_a":    P(team_a wins),
            "p_draw": P(draw),
            "p_b":    P(team_b wins),
            "score":  (ga, gb) — the modal (most likely) scoreline,
            "winner": "a" | "draw" | "b",
        }

    `winner` is "draw" whenever the modal score is itself a tie (ga == gb),
    even if p_a or p_b individually edge out p_draw — a near-50/50 matchup's
    most likely outcome is a 1-1/0-0 draw, and that's what gets shown.
    Otherwise `winner` is whichever of p_a/p_draw/p_b is largest.
    """
    matrix = match_matrix(elo_a, elo_b, host_a, host_b)
    p_a, p_draw, p_b = matrix_outcome_probs(matrix)
    score = matrix_modal_score(matrix)

    outcomes = {"a": p_a, "draw": p_draw, "b": p_b}
    winner = max(outcomes, key=outcomes.get)
    if score[0] == score[1]:
        winner = "draw"

    return {"p_a": p_a, "p_draw": p_draw, "p_b": p_b, "score": score, "winner": winner}


def sample_score(elo_a: float, elo_b: float,
                 host_a: bool = False, host_b: bool = False, rng=None) -> tuple[int, int]:
    """Draws a single (ga, gb) scoreline for one Monte Carlo iteration."""
    matrix = match_matrix(elo_a, elo_b, host_a, host_b)
    return sample_from_matrix(matrix, rng)
