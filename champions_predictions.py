"""
champions_predictions.py
Club-football layer on top of the shared Poisson engine.

Reuses prediction_engine (same scoreline matrix, same coherence between the
probability bars and the predicted score) with constants calibrated for club
football instead of international, and with a scoreline picker tuned for a
predictions channel: plausible results, never a 7-0.

Why not the engine's own scoreline helpers
------------------------------------------
`spectacle_score()` builds a deliberately attacking matrix and adds a goleada
boost — that is what produced the 7-0s. `matrix_modal_score()` goes too far the
other way: over a realistic spread of Elo gaps it only ever returns two
scorelines (2-1 and 2-0), so 32 predictions a season would show the same two
results. Measured over 640 simulated matches:

    spectacle          -> 7-0, 5-1, 4-3 appear
    modal only         -> 2 distinct scorelines
    sample the matrix  -> 21 distinct, but 24% of matches end with 5+ goals
    top-4 (this file)  -> 6 distinct, 2.36 goals/match, 0% with 5+ goals

Public API:
    predict(elo_local, elo_visitante, seed) -> dict
    CHAMPIONS_CONSTANTS
"""
import random

import prediction_engine as pe

# Calibrated for club football. BASE_TOTAL_GOALS is the big one: config.py uses
# 2.4 (international average), while the Champions league phase runs above 3.
#
# ELO_TO_GOALS and HOME_ELO_BONUS are placeholders on the ClubElo scale and
# still need calibrating against real results, the same way
# scripts/calibrate_model.py did it for the national-team model.
CHAMPIONS_CONSTANTS = {
    "base_total_goals": 3.1,
    "elo_to_goals": 180.0,
    "host_elo_bonus": 65.0,
}

# Two win probabilities closer than this and the match is called a draw.
#
# In a Poisson model the draw is NEVER the most likely of the three outcomes —
# even with identical teams it splits 38/24/38 — so without this rule the draw
# bar would never be highlighted and no 1-1 would ever be predicted all season.
#
# Calibrated over 3000 simulated league-phase pairings: 0.04 gives 7% draws,
# 0.10 gives 13% and 0.12 gives 18%. At 0.10 a draw comes up roughly once every
# eight matches — about one per two Shorts — which keeps the draw bar alive
# without turning the channel into a tipster who never picks a winner.
DRAW_MARGIN = 0.10

# How many of the most likely scorelines to draw from. Three is too repetitive,
# five starts letting 4-0 and 3-2 through too often. See the table above.
TOP_SCORELINES = 4


def _outcome_cells(matrix: list[list[float]], outcome: str):
    """Matrix cells consistent with a given outcome, as ((ga, gb), p)."""
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if outcome == "local" and i <= j:
                continue
            if outcome == "visitante" and i >= j:
                continue
            if outcome == "empate" and i != j:
                continue
            yield (i, j), p


def _pick_scoreline(matrix, outcome: str, rng: random.Random) -> tuple[int, int]:
    """
    Draw one of the `TOP_SCORELINES` most likely scorelines for this outcome,
    weighted by probability.

    Taking the single most likely cell would be defensible but deadly dull; the
    full distribution has a tail that puts 5-1 on screen. The top few give a
    realistic spread with a hard ceiling.
    """
    cells = sorted(_outcome_cells(matrix, outcome), key=lambda kv: kv[1], reverse=True)
    top = cells[:TOP_SCORELINES]
    if not top:
        return {"local": (1, 0), "visitante": (0, 1)}.get(outcome, (1, 1))
    return rng.choices([c for c, _ in top], weights=[p for _, p in top], k=1)[0]


def _decide_outcome(p_local: float, p_empate: float, p_visitante: float) -> str:
    """Most likely outcome, except that a near coin-flip is called a draw."""
    if abs(p_local - p_visitante) < DRAW_MARGIN:
        return "empate"
    return "local" if p_local > p_visitante else "visitante"


def predict(elo_local: float, elo_visitante: float, seed: str) -> dict:
    """
    Predict one match.

    `seed` keys the scoreline draw — pass something stable for the fixture
    (e.g. "2026-10-21|real-madrid|bayern") so re-rendering the same matchday
    never changes the predicted score.

    Returns the keys the Remotion schema expects, plus `resultadoPredicho` so
    the video highlights the same outcome the model chose instead of
    re-deriving it from the rounded probabilities.
    """
    matrix = pe.match_matrix(
        elo_local, elo_visitante, host_a=True, **CHAMPIONS_CONSTANTS
    )
    p_local, p_empate, p_visitante = pe.matrix_outcome_probs(matrix)

    outcome = _decide_outcome(p_local, p_empate, p_visitante)
    goles_local, goles_visitante = _pick_scoreline(
        matrix, outcome, random.Random(seed)
    )

    return {
        "probLocal": round(p_local, 4),
        "probEmpate": round(p_empate, 4),
        "probVisitante": round(p_visitante, 4),
        "prediccion": f"{goles_local}-{goles_visitante}",
        "resultadoPredicho": outcome,
    }
