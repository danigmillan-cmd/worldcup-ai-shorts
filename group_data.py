"""
group_data.py
World Cup 2026 group-stage data and qualification predictions.

Defines the 12 groups (A-L) of 4 teams each via a pot-based Elo seeding
(no official 2026 draw data exists in this codebase), generates each
group's round-robin fixture list, and combines live Elo ratings with
group_simulator's Monte Carlo output into a render-ready prediction.

Public API:
    get_group_prediction(group_letter, elo_table=None) -> dict
    youtube_metadata(group_result) -> dict
"""
import itertools
import random

import rankings
import group_simulator
from match_data import DEFAULT_ELO

N_SIMULATIONS = 800

# Pot-seeded group assignment — Pot 1 = strongest 12 of the 48 teams in
# data/fixtures.json by current Elo, down to Pot 4 = weakest 12. One team
# per pot per group, like a real World Cup draw. Fixed/deterministic since
# the official 2026 draw isn't modeled here.
GROUPS: dict[str, list[str]] = {
    "A": ["Spain",       "Turkey",      "Australia",    "DR Congo"],
    "B": ["Argentina",   "Japan",       "Algeria",      "Tunisia"],
    "C": ["France",      "Belgium",     "Iran",         "Iraq"],
    "D": ["England",     "Uruguay",     "South Korea",  "Bosnia and Herzegovina"],
    "E": ["Brazil",      "Switzerland", "Czech Republic", "Cape Verde"],
    "F": ["Portugal",    "Mexico",      "Panama",       "Saudi Arabia"],
    "G": ["Colombia",    "Senegal",     "United States", "New Zealand"],
    "H": ["Netherlands", "Paraguay",    "Uzbekistan",   "Haiti"],
    "I": ["Ecuador",     "Austria",     "Sweden",       "South Africa"],
    "J": ["Germany",     "Morocco",     "Egypt",        "Ghana"],
    "K": ["Norway",      "Canada",      "Ivory Coast",  "Curaçao"],
    "L": ["Croatia",     "Scotland",    "Jordan",       "Qatar"],
}

# AI insight templates. {team} is filled with the title-cased team name.
INSIGHT_TIGHT = [
    "AI predicts a tight finish \U0001f440",
    "Too close to call — anyone could go through \U0001f525",
    "This group is wide open \U0001f3af",
]
INSIGHT_CLEAR = [
    "{team} looks set to top the group ✅",
    "AI sees {team} cruising through \U0001f680",
    "{team} is the team to beat here \U0001f3c6",
]
CLEAR_THRESHOLD = 88   # qualification_probability above which the leader is "clear"


# ═══════════════════════════════════════════════════════════════════════════════
# TEAM RESOLUTION + FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════
def _team_info(name: str, elo_table: dict) -> dict:
    """Resolves a GROUPS team name to {"name","display","code","elo"}."""
    display, code = rankings.ELO_MAP[name]
    info = elo_table.get(display)
    if info is None:
        print(f"  [warn] No live Elo for {display}, using default ({DEFAULT_ELO})")
        elo = DEFAULT_ELO
    else:
        elo = info["elo"]
    return {"name": name, "display": display, "code": code, "elo": elo}


def group_round_robin(teams: list[str]) -> list[tuple[str, str]]:
    """All unique pairings for a 4-team group (6 matches)."""
    return list(itertools.combinations(teams, 2))


# ═══════════════════════════════════════════════════════════════════════════════
# AI INSIGHT
# ═══════════════════════════════════════════════════════════════════════════════
def _ai_insight(standings: list[dict]) -> str:
    leader = standings[0]
    if leader["qualification_probability"] >= CLEAR_THRESHOLD:
        return random.choice(INSIGHT_CLEAR).format(team=leader["display"].title())
    return random.choice(INSIGHT_TIGHT)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════
def get_group_prediction(group_letter: str, elo_table: dict | None = None) -> dict:
    """
    Returns:
        {
            "group": "A",
            "standings": [
                {"team", "display", "code", "elo", "points", "gf", "ga",
                 "qualification_probability"},
                ...  # sorted by descending qualification_probability
            ],
            "insight": "AI predicts a tight finish \U0001f440",
        }

    Args:
        elo_table: pre-fetched table from rankings.get_elo_table().
                   If omitted, the table is fetched here.
    """
    letter = group_letter.strip().upper()
    if letter not in GROUPS:
        raise ValueError(f"Unknown group '{group_letter}'. Valid groups: {', '.join(sorted(GROUPS))}")

    if elo_table is None:
        print("  Fetching Elo ratings...")
        elo_table = rankings.get_elo_table()

    team_names = GROUPS[letter]
    teams      = [_team_info(name, elo_table) for name in team_names]
    by_name    = {t["name"]: t for t in teams}

    fixtures = group_round_robin(team_names)

    print(f"\n  Simulating Group {letter} ({N_SIMULATIONS} runs)...")
    sim_results = group_simulator.simulate_group(teams, fixtures, N_SIMULATIONS)

    standings = []
    for r in sim_results:
        info = by_name[r["team"]]
        standings.append({
            "team":    info["name"],
            "display": info["display"],
            "code":    info["code"],
            "elo":     info["elo"],
            "points":  r["points"],
            "gf":      r["gf"],
            "ga":      r["ga"],
            "qualification_probability": r["qualification_probability"],
        })

    insight = _ai_insight(standings)

    print(f"\n  {'Team':<16} {'Pts':>4}  {'GF':>5}  {'GA':>5}  {'Qual%':>6}")
    print("  " + "-" * 42)
    for s in standings:
        print(f"  {s['display']:<16} {s['points']:>4}  {s['gf']:>5}  {s['ga']:>5}  {s['qualification_probability']:>5}%")
    print(f"\n  AI insight : {insight}\n")

    return {"group": letter, "standings": standings, "insight": insight}


def youtube_metadata(group_result: dict) -> dict:
    """Builds a title/description/tags set for the YouTube upload."""
    letter    = group_result["group"]
    standings = group_result["standings"]

    title = f"Group {letter} World Cup 2026: Who Qualifies? \U0001f30d⚽"

    lines = "\n".join(
        f"{s['display'].title()}: {s['points']} pts, "
        f"{s['qualification_probability']}% qualification chance"
        for s in standings
    )
    description = (
        f"AI-powered World Cup 2026 group-stage simulation: Group {letter}.\n\n"
        f"{lines}\n\n"
        f"{group_result['insight']}\n\n"
        "Who do you think makes it through? Drop your prediction in the comments!\n\n"
        "#WorldCup #WorldCup2026 #Football #Soccer #AI #Prediction #Shorts #FIFA #Sports"
    )
    tags = [
        "World Cup", "World Cup 2026", "FIFA", "Football", "Soccer",
        "AI", "Prediction", "Group Stage", "Qualification", "Shorts", "Sports",
        f"Group {letter}",
    ] + [s["display"].title() for s in standings]

    return {"title": title, "description": description, "tags": tags}
