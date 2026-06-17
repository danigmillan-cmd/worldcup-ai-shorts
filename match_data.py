"""
match_data.py
Head-to-head data for AI Match Prediction Shorts.

Resolves two team names to live Elo ratings, then asks the shared
prediction_engine (Poisson model) for win/draw/loss probabilities and a
predicted scoreline.

Public API:
    get_match_prediction(team_a, team_b) -> dict
    youtube_metadata(match) -> dict
"""
import random

import config
import rankings
import prediction_engine

# Used when a requested team has no live Elo data (network failure and the
# team isn't in the small offline fallback table).
DEFAULT_ELO = 1700

# Title templates for YouTube Shorts — concise, mobile-readable, and
# varied so repeated uploads don't all look identical in feeds/search.
# {a} / {b} are filled with the title-cased team names.
TITLE_TEMPLATES = [
    "{a} vs {b} AI Prediction ⚽\U0001f525",
    "AI Predicts {a} vs {b} \U0001f440",
    "{a} vs {b} World Cup Prediction \U0001f30d",
    "Who Wins? {a} vs {b} \U0001f916⚽",
]


# ═══════════════════════════════════════════════════════════════════════════════
# TEAM RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════════
def _resolve_team(name: str, table: dict[str, dict]) -> dict:
    """
    Resolves a user-supplied team name (e.g. "spain", "Brazil") against
    rankings.ELO_MAP and looks up its current Elo in `table`.

    Returns {"input", "name", "code", "elo"}.
    Raises ValueError if the name isn't recognized.
    """
    key = name.strip()
    mapping = rankings.ELO_MAP.get(key) or next(
        (v for k, v in rankings.ELO_MAP.items() if k.lower() == key.lower()), None
    )
    if mapping is None:
        raise ValueError(
            f"Unknown team '{name}'. Use an English team name, e.g. 'Spain', 'Brazil'."
        )
    display, code = mapping
    info = table.get(display)
    if info is None:
        print(f"  [warn] No live Elo for {display}, using default ({DEFAULT_ELO})")
        elo = DEFAULT_ELO
    else:
        elo = info["elo"]
    return {"input": name, "name": display, "code": code, "elo": elo}


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════
def get_match_prediction(team_a_name: str, team_b_name: str,
                         elo_table: dict | None = None) -> dict:
    """
    Returns:
        {
            "team_a": {"input","name","code","elo","pct","score"},
            "team_b": {"input","name","code","elo","pct","score"},
            "winner": "a" | "draw" | "b",
        }

    Args:
        elo_table: pre-fetched table from rankings.get_elo_table().
                   Pass this when generating multiple matches in a batch
                   to avoid re-fetching live Elo data for every matchup.
                   If omitted, the table is fetched here.
    """
    if elo_table is None:
        print("  Fetching Elo ratings...")
        elo_table = rankings.get_elo_table()
    table = elo_table

    a = _resolve_team(team_a_name, table)
    b = _resolve_team(team_b_name, table)

    host_a = a["name"] in config.HOSTS
    host_b = b["name"] in config.HOSTS
    prediction = prediction_engine.predict_match(a["elo"], b["elo"], host_a, host_b)

    # The two vertical bars in the Short must sum to 100. Each team's share
    # is its "expected points share" (win probability + half the draw
    # probability), then pulled toward 50/50 by config.PCT_DISPLAY_SOFTEN so
    # big Elo gaps don't render as near-0/near-100 splits. The draw itself is
    # communicated separately via the DRAW case in match_renderer (two flags
    # + "DRAW" label), not via these bars.
    points_share_a = prediction["p_a"] + prediction["p_draw"] / 2
    pct_a_raw = 50 + (points_share_a * 100 - 50) * config.PCT_DISPLAY_SOFTEN
    pct_a = max(1, min(99, round(pct_a_raw)))
    a["pct"], b["pct"]     = pct_a, 100 - pct_a
    winner = prediction["winner"]

    # Displayed scoreline: a deliberately more entertaining "spectacle" score
    # (see config.SPECTACLE_*), NOT the calibrated modal score. It's sampled
    # from a more attacking Poisson matrix but constrained to agree with the
    # `winner` decided above, so the outcome shown never changes — only the
    # goals get livelier. Seeded on the matchup so re-renders stay identical.
    score_rng = random.Random(f"{a['name']}|{b['name']}")
    a["score"], b["score"] = prediction_engine.spectacle_score(
        a["elo"], b["elo"], host_a, host_b, winner, rng=score_rng
    )

    print(f"\n  {'Team':<16} {'Elo':>5}  {'Win%':>5}  {'Score'}")
    print("  " + "-" * 36)
    print(f"  {a['name']:<16} {a['elo']:>5}  {a['pct']:>4}%  {a['score']}")
    print(f"  {b['name']:<16} {b['elo']:>5}  {b['pct']:>4}%  {b['score']}")
    if winner == "draw":
        print("\n  Predicted winner : DRAW")
    else:
        print(f"\n  Predicted winner : {(a if winner == 'a' else b)['name']}")
    print(f"  Predicted score  : {a['score']}-{b['score']}\n")

    return {"team_a": a, "team_b": b, "winner": winner}


def youtube_metadata(match: dict) -> dict:
    """Builds a title/description/tags set for the YouTube upload.

    The title is generated dynamically from TITLE_TEMPLATES, optimized
    for Shorts discovery (clickable, mobile-readable, both team names).
    The chosen template's index is returned as "title_template_index" so
    callers can log which variant was used (e.g. video_attributes.json).
    """
    a, b = match["team_a"], match["team_b"]
    title_template_index = random.randrange(len(TITLE_TEMPLATES))
    title = TITLE_TEMPLATES[title_template_index].format(a=a["name"].title(), b=b["name"].title())
    description = (
        f"AI-powered World Cup 2026 prediction: {a['name'].title()} vs {b['name'].title()}.\n\n"
        f"{a['name'].title()}: {a['pct']}% win probability\n"
        f"{b['name'].title()}: {b['pct']}% win probability\n"
        f"Predicted score: {a['score']}-{b['score']}\n\n"
        "Who do you think wins? Drop your prediction in the comments!\n\n"
        "#WorldCup #WorldCup2026 #Football #Soccer #AI #Prediction #Shorts #FIFA #Sports"
    )
    tags = [
        "World Cup", "World Cup 2026", "FIFA", "Football", "Soccer",
        "AI", "Prediction", "Match Preview", "Shorts", "Sports",
        a["name"].title(), b["name"].title(),
    ]
    return {
        "title": title,
        "description": description,
        "tags": tags,
        "title_template_index": title_template_index,
    }
