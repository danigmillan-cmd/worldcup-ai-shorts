"""
tournament_simulator.py
Monte Carlo simulator for the full 2026 World Cup -> real "probability of
winning the tournament" per team. Feeds the Power Ranking (renderer.py).

Reuses the shared Poisson model (prediction_engine.py) for EVERY match —
group stage AND knockout — so this stays mutually coherent with Match
Prediction and Group Qualification Shorts. No probability/score logic is
reimplemented here.

Format approximations (all documented, none are the official 2026 draw):
  - Group stage: the 12 GROUPS (group_data.GROUPS) are played out via
    group_simulator.simulate_group_once() — same round-robin + tiebreak
    rules as the Group Qualification Short.
  - Qualification: top-2 per group (24) + the best 8 third-placed teams
    across all groups (ranked by points -> GD -> GF -> random tiebreak,
    same convention as group_simulator) = 32 teams for the Round of 32.
  - Bracket: since the real 2026 draw doesn't exist, the 32 qualifiers are
    seeded by footballing strength alone (dampened Elo, NO host bonus) and
    placed into a STANDARD single-elimination seeding order (seed 1 and 2
    can only meet in the final, 1-4 only from the semis on, etc.) — a
    plausible "pre-draw" bracket, not the official one. The host-Elo bonus
    is NOT used for seeding (it would double-count: an easier bracket path
    AND a per-match advantage) but IS still applied in every match a host
    plays, per the point below.
  - Knockout: each tie is resolved via prediction_engine.sample_score(). A
    drawn scoreline goes to penalties — modeled by renormalizing the
    matrix's win probabilities WITHOUT the draw (p_a/(p_a+p_b)), which gives
    the stronger side a slight edge while staying honest that penalties are
    close to a coin flip.
  - Host advantage: USA/Mexico/Canada get host=True in every match they
    play (group AND knockout), same approximation prediction_engine already
    applies for group fixtures.

Public API:
    simulate_tournament(n_sims=config.N_SIMS_TOURNAMENT, elo_table=None) -> dict
    get_tournament_odds(elo_table=None, n_sims=None) -> dict

Both return {display_name: {"title_pct", "final_pct", "reached_r16_pct",
"reached_qf_pct", "reached_sf_pct"}} — percentages (0-100) over all sims,
for every team across the 12 GROUPS. sum(title_pct) ~= 100.
"""
import hashlib
import json
import random
import time
from datetime import datetime, timezone

import config
import rankings
import group_data
import group_simulator
import prediction_engine


# ═══════════════════════════════════════════════════════════════════════════════
# BRACKET SEEDING
# ═══════════════════════════════════════════════════════════════════════════════
def _seed_order(n: int) -> list[int]:
    """Standard single-elimination seeding order (1-indexed) for n=2^k
    teams: pairs (order[2i], order[2i+1]) are the round-1 matchups, and this
    recursive construction guarantees seed 1 vs seed 2 can only meet in the
    final, seeds 1-4 only from the semifinals on, etc."""
    if n == 1:
        return [1]
    prev = _seed_order(n // 2)
    order = []
    for s in prev:
        order.append(s)
        order.append(n + 1 - s)
    return order


_SEED_ORDER_32 = _seed_order(32)


# ═══════════════════════════════════════════════════════════════════════════════
# SETUP (built once, reused across all n_sims)
# ═══════════════════════════════════════════════════════════════════════════════
def _build_groups_data(elo_table: dict) -> tuple[dict, dict]:
    """Resolves all 48 GROUPS teams against `elo_table` and pre-builds each
    group's match matrices (Elo/host don't change across sims).

    Before building matrices/seeding, each team's Elo is compressed toward
    the 48-team field average by config.TOURNAMENT_ELO_DAMPENING (see
    config.py for rationale) — this affects ONLY the tournament simulation,
    not prediction_engine or rankings.get_elo_table(). Being an affine
    transform, it preserves the relative ORDER of all teams.

    "eff_elo" (used for bracket seeding) is the dampened Elo WITHOUT the
    host-Elo bonus — seeding reflects footballing strength only. Hosts still
    get the bonus in every match they play (group AND knockout) via the
    "host" flag passed to prediction_engine. Without this split, the bonus
    would double-count for hosts: once as a per-match advantage and again as
    an easier bracket path from a higher seed.

    Returns (groups_data, team_lookup):
        groups_data: {letter: {"names", "fixtures", "matrices"}}
        team_lookup: {name: {"name","display","code","elo","host","eff_elo"}}
        (team_lookup's "elo" is the dampened tournament Elo, not the raw one)
    """
    raw_teams = {
        n: group_data._team_info(n, elo_table)
        for names in group_data.GROUPS.values()
        for n in names
    }
    mean_elo = sum(t["elo"] for t in raw_teams.values()) / len(raw_teams)
    damp     = config.TOURNAMENT_ELO_DAMPENING

    groups_data: dict = {}
    team_lookup: dict = {}

    for letter, names in group_data.GROUPS.items():
        teams = []
        for n in names:
            t = dict(raw_teams[n])
            t["elo"]     = mean_elo + (t["elo"] - mean_elo) * damp
            t["host"]    = t["display"] in config.HOSTS
            t["eff_elo"] = t["elo"]
            team_lookup[t["name"]] = t
            teams.append(t)

        team_names = [t["name"] for t in teams]
        fixtures   = group_data.group_round_robin(team_names)
        matrices   = group_simulator.build_match_matrices(teams, fixtures)
        groups_data[letter] = {
            "names":    team_names,
            "fixtures": fixtures,
            "matrices": matrices,
        }

    return groups_data, team_lookup


# ═══════════════════════════════════════════════════════════════════════════════
# KNOCKOUT
# ═══════════════════════════════════════════════════════════════════════════════
def _play_knockout(team_a: dict, team_b: dict) -> dict:
    """Plays one knockout tie and returns the winning team's info dict.

    A drawn scoreline (penalties) is decided by renormalizing the win
    probabilities without the draw — p_a/(p_a+p_b) — a slight, honest edge
    to the stronger side without pretending the shootout is predictable.
    """
    ga, gb = prediction_engine.sample_score(
        team_a["elo"], team_b["elo"], team_a["host"], team_b["host"]
    )
    if ga != gb:
        return team_a if ga > gb else team_b

    matrix = prediction_engine.match_matrix(
        team_a["elo"], team_b["elo"], team_a["host"], team_b["host"]
    )
    p_a, _, p_b = prediction_engine.matrix_outcome_probs(matrix)
    total = p_a + p_b
    p_a_norm = p_a / total if total > 0 else 0.5
    return team_a if random.random() < p_a_norm else team_b


# ═══════════════════════════════════════════════════════════════════════════════
# ONE FULL TOURNAMENT
# ═══════════════════════════════════════════════════════════════════════════════
def _simulate_once(groups_data: dict, team_lookup: dict) -> dict:
    """Plays out one full tournament (12 groups -> 32 qualifiers -> seeded
    R32-R16-QF-SF-Final bracket). Returns reached-round info by team name:
        {"r16": set, "qf": set, "sf": set, "final": set, "champion": name}
    Each set is the teams that REACHED that round (i.e. won the previous
    round); "final" holds both finalists.
    """
    qualifiers: list[str] = []
    thirds: list[dict] = []

    for letter, gd in groups_data.items():
        standings = group_simulator.simulate_group_once(gd["names"], gd["fixtures"], gd["matrices"])
        qualifiers.append(standings[0]["name"])
        qualifiers.append(standings[1]["name"])
        thirds.append(standings[2])

    # Best 8 third-placed teams across all 12 groups.
    thirds_ranked = sorted(
        thirds,
        key=lambda s: (s["points"], s["gd"], s["gf"], random.random()),
        reverse=True,
    )
    qualifiers += [s["name"] for s in thirds_ranked[:8]]

    # Seed the 32 qualifiers by effective Elo (footballing strength only,
    # no host bonus) and place them into the standard seeding order -> R32
    # matchup order.
    qual_infos  = [team_lookup[n] for n in qualifiers]
    qual_sorted = sorted(qual_infos, key=lambda t: -t["eff_elo"])
    bracket     = [qual_sorted[s - 1] for s in _SEED_ORDER_32]

    reached = {"r16": set(), "qf": set(), "sf": set(), "final": set(), "champion": None}

    round_teams = bracket
    for round_name in ("r32", "r16", "qf", "sf", "final"):
        winners = [
            _play_knockout(round_teams[i], round_teams[i + 1])
            for i in range(0, len(round_teams), 2)
        ]
        if round_name == "r32":
            reached["r16"].update(t["name"] for t in winners)
        elif round_name == "r16":
            reached["qf"].update(t["name"] for t in winners)
        elif round_name == "qf":
            reached["sf"].update(t["name"] for t in winners)
        elif round_name == "sf":
            reached["final"].update(t["name"] for t in winners)
        else:
            reached["champion"] = winners[0]["name"]
        round_teams = winners

    return reached


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════
def simulate_tournament(n_sims: int | None = None, elo_table: dict | None = None) -> dict:
    """Runs `n_sims` full-tournament simulations and returns per-team
    probabilities (percentages, 0-100), keyed by ELO_MAP display name:
        {"SPAIN": {"title_pct", "final_pct", "reached_r16_pct",
                    "reached_qf_pct", "reached_sf_pct"}, ...}
    sum(title_pct) over all teams is ~= 100.
    """
    n_sims = n_sims or config.N_SIMS_TOURNAMENT
    if elo_table is None:
        elo_table = rankings.get_elo_table()

    groups_data, team_lookup = _build_groups_data(elo_table)
    all_names = list(team_lookup)

    title_count = {n: 0 for n in all_names}
    final_count = {n: 0 for n in all_names}
    sf_count    = {n: 0 for n in all_names}
    qf_count    = {n: 0 for n in all_names}
    r16_count   = {n: 0 for n in all_names}

    for _ in range(n_sims):
        reached = _simulate_once(groups_data, team_lookup)
        title_count[reached["champion"]] += 1
        for n in reached["final"]:
            final_count[n] += 1
        for n in reached["sf"]:
            sf_count[n] += 1
        for n in reached["qf"]:
            qf_count[n] += 1
        for n in reached["r16"]:
            r16_count[n] += 1

    odds: dict = {}
    for n in all_names:
        display = team_lookup[n]["display"]
        odds[display] = {
            "title_pct":       round(100 * title_count[n] / n_sims, 1),
            "final_pct":       round(100 * final_count[n] / n_sims, 1),
            "reached_r16_pct": round(100 * r16_count[n] / n_sims, 1),
            "reached_qf_pct":  round(100 * qf_count[n] / n_sims, 1),
            "reached_sf_pct":  round(100 * sf_count[n] / n_sims, 1),
        }
    return odds


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — CACHE
# ═══════════════════════════════════════════════════════════════════════════════
def _state_signature(elo_table: dict, n_sims: int) -> str:
    """Hashes the 48 GROUPS teams' Elo + GROUPS structure + n_sims +
    TOURNAMENT_ELO_DAMPENING, so a cache entry is only reused while none of
    those have changed."""
    rows = []
    for letter in sorted(group_data.GROUPS):
        for name in group_data.GROUPS[letter]:
            display, _ = rankings.ELO_MAP[name]
            elo = elo_table.get(display, {}).get("elo")
            rows.append([letter, name, display, elo])
    payload = json.dumps({
        "rows": rows,
        "n_sims": n_sims,
        "dampening": config.TOURNAMENT_ELO_DAMPENING,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cache() -> dict | None:
    try:
        return json.loads(config.TOURNAMENT_ODDS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] Could not read tournament odds cache ({exc}) — recomputing")
        return None


def _save_cache(payload: dict) -> None:
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.TOURNAMENT_ODDS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"[WARN] Could not write tournament odds cache: {exc}")


def get_tournament_odds(elo_table: dict | None = None, n_sims: int | None = None) -> dict:
    """Returns cached tournament odds if the state signature (48 teams' Elo +
    GROUPS + n_sims) matches; otherwise recomputes via simulate_tournament()
    and saves the new cache. This is what renderer.py should call — never
    call simulate_tournament() directly from a render path."""
    n_sims = n_sims or config.N_SIMS_TOURNAMENT
    if elo_table is None:
        elo_table = rankings.get_elo_table()

    sig    = _state_signature(elo_table, n_sims)
    cached = _load_cache()
    if cached and cached.get("signature") == sig:
        print(f"[INFO] Tournament odds cache hit ({n_sims} sims, "
              f"computed {cached.get('computed_at')})")
        return cached["odds"]

    print(f"[INFO] Recomputing tournament odds ({n_sims} sims)...")
    started = time.monotonic()
    odds = simulate_tournament(n_sims=n_sims, elo_table=elo_table)
    elapsed = time.monotonic() - started
    print(f"[INFO] Tournament simulation finished in {elapsed:.1f}s")

    _save_cache({
        "signature":   sig,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_sims":      n_sims,
        "odds":        odds,
    })
    return odds
