"""
knockout_ranking.py
Power Ranking of the teams STILL ALIVE in the World Cup knockout stage.

Unlike the weekly Power Ranking (tournament_simulator, a full simulation from
the group stage over a provisional/pre-draw bracket), this builds the ranking
from the REAL remaining bracket:

  1. The surviving teams and their real next-round pairings are read from the
     live ESPN fixtures (fixtures_fetcher). The only upcoming fixtures whose
     BOTH sides resolve to real ELO_MAP teams are the current frontier round —
     later rounds are still "Quarterfinal 1 Winner"/"Semifinal 1 Loser"
     placeholders that don't resolve — so the frontier (and thus the exact set
     of survivors) falls out naturally. Expected 8 teams after the Round of 16,
     4 after the Quarter-finals.
  2. Those real pairings are played out Monte-Carlo (prediction_engine — the
     same Poisson model every other Short uses, reusing
     tournament_simulator._play_knockout) through to the final, so each
     surviving team gets an honest "chance to win the cup from here". These
     percentages DO sum to ~100% across the survivors.

Because it's the real bracket (not a seeded approximation), there's no
"provisional bracket / draw pending" disclaimer.

Public API:
    build_ranking(expected_teams, elo_table=None, n_sims=None) -> list[dict]
    run_pipeline(expected_teams, ...) -> dict
"""
from pathlib import Path

import config
import rankings
import group_data
import fixtures_fetcher
import tournament_simulator
import renderer
import uploader


# ═══════════════════════════════════════════════════════════════════════════════
# FRONTIER (surviving teams + real pairings) FROM LIVE FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════
def get_frontier_pairings(expected_teams: int,
                          days_ahead: float = 20.0) -> list[tuple[str, str]]:
    """Reads the current knockout frontier from live ESPN fixtures.

    Returns the next round's matchups as (home, away) pairs, ordered by
    kickoff (fixtures_fetcher already sorts + normalizes to ELO_MAP names and
    drops any fixture with an unrecognized side, so placeholder ties like
    "Quarterfinal 1 Winner" vanish and only the resolved frontier remains).

    Raises ValueError if the number of surviving teams doesn't match
    `expected_teams` — a hard guard so a mistimed run (round not finished, or
    already into the next round) fails loudly instead of publishing a wrong
    ranking.
    """
    fixtures = fixtures_fetcher.fetch_fixtures(days_ahead=days_ahead)
    pairings = [(fx["home"], fx["away"]) for fx in fixtures]

    teams: list[str] = []
    for home, away in pairings:
        for name in (home, away):
            if name not in teams:
                teams.append(name)

    expected_pairs = expected_teams // 2
    if len(teams) != expected_teams or len(pairings) != expected_pairs:
        raise ValueError(
            f"Expected {expected_teams} surviving teams in {expected_pairs} "
            f"fixtures, but live fixtures resolved to {len(teams)} team(s) in "
            f"{len(pairings)} fixture(s): {pairings}. Aborting — the round may "
            f"not be finished yet, or the tournament has moved on."
        )

    print(f"[INFO] Frontier: {len(teams)} surviving teams / {len(pairings)} ties")
    for home, away in pairings:
        print(f"       {home}  vs  {away}")
    return pairings


# ═══════════════════════════════════════════════════════════════════════════════
# REMAINING-BRACKET MONTE CARLO
# ═══════════════════════════════════════════════════════════════════════════════
def _bracket_order(pairings: list[tuple[str, str]], elo_table: dict) -> list[dict]:
    """Flattens the frontier pairings into single-elimination bracket order —
    [tie0.home, tie0.away, tie1.home, tie1.away, ...] — so playing adjacent
    pairs each round (winners of tie0/tie1 meet, tie2/tie3 meet, ...) walks the
    standard bracket to a single champion.

    Each team's Elo is compressed toward the surviving field's mean by
    config.TOURNAMENT_ELO_DAMPENING (same rationale as tournament_simulator:
    a clean Poisson model is over-confident when a favorite must win several
    ties in a row), and hosts keep their per-match Elo bonus.
    """
    names = [name for tie in pairings for name in tie]
    infos = [group_data._team_info(n, elo_table) for n in names]

    mean_elo = sum(t["elo"] for t in infos) / len(infos)
    damp     = config.TOURNAMENT_ELO_DAMPENING

    order: list[dict] = []
    for t in infos:
        team = dict(t)
        team["elo"]  = mean_elo + (t["elo"] - mean_elo) * damp
        team["host"] = t["display"] in config.HOSTS
        order.append(team)
    return order


def _simulate(order: list[dict], n_sims: int) -> dict[str, int]:
    """Plays the remaining bracket `n_sims` times; returns {display: wins}."""
    counts = {t["display"]: 0 for t in order}
    for _ in range(n_sims):
        round_teams = order
        while len(round_teams) > 1:
            round_teams = [
                tournament_simulator._play_knockout(round_teams[i], round_teams[i + 1])
                for i in range(0, len(round_teams), 2)
            ]
        counts[round_teams[0]["display"]] += 1
    return counts


def build_ranking(expected_teams: int,
                  elo_table: dict | None = None,
                  n_sims: int | None = None) -> list[dict]:
    """Builds the surviving-teams ranking sorted by descending title odds.

    Each entry: {rank, name (display), code, pct (0-100, sums to ~100)}.
    """
    n_sims = n_sims or config.N_SIMS_KNOCKOUT
    if elo_table is None:
        elo_table = rankings.get_elo_table()

    pairings = get_frontier_pairings(expected_teams)
    order    = _bracket_order(pairings, elo_table)

    print(f"[INFO] Simulating remaining bracket ({n_sims} sims)...")
    counts = _simulate(order, n_sims)

    ranking = sorted(
        (
            {
                "name": t["display"],
                "code": t["code"],
                "pct":  round(100 * counts[t["display"]] / n_sims, 1),
            }
            for t in order
        ),
        key=lambda r: -r["pct"],
    )
    for i, r in enumerate(ranking):
        r["rank"] = i + 1

    print(f"\n  {'#':>3}  {'Team':<16}  {'Title':>6}")
    print("  " + "-" * 30)
    for r in ranking:
        print(f"  {r['rank']:>3}  {r['name']:<16}  {r['pct']:>5}%")
    print()

    return ranking


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════
def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def run_pipeline(expected_teams: int,
                 output_path: Path | None = None,
                 privacy:     str  = "public",
                 upload:      bool = True,
                 skip_render: bool = False) -> dict:
    """End-to-end knockout Power Ranking: live frontier → simulate remaining
    bracket → render → upload."""
    out = output_path or config.KNOCKOUT_RANKING_OUTPUT
    result = {"ranking": None, "video_path": out, "video_id": None, "youtube_url": None}

    subtitle = config.KNOCKOUT_RANKING_SUBTITLES.get(
        expected_teams, config.POWER_RANKING_TITLE_LABEL)

    if not skip_render:
        _section(f"STEP 1 / 3  —  SURVIVING TEAMS  (FINAL {expected_teams})")
        ranking = build_ranking(expected_teams)
        result["ranking"] = ranking

        _section("STEP 2 / 3  —  RENDER")
        result["video_path"] = renderer.render_power_ranking(
            ranking, out,
            use_title_odds  = False,
            label           = subtitle,
            show_disclaimer = False,
            background      = config.KNOCKOUT_RANKING_BG,
            sub_y           = config.KNOCKOUT_RANKING_SUB_Y,
            band            = config.KNOCKOUT_RANKING_BAND,
            hband           = config.KNOCKOUT_RANKING_HBAND,
        )
        print(f"\n  Video ready : {result['video_path']}")
    else:
        _section("STEP 2 / 3  —  RENDER  (skipped)")
        if not out.exists():
            raise SystemExit(f"  ERROR: {out} does not exist. Render first.")
        print(f"  Using existing file: {out}")

    if upload:
        _section("STEP 3 / 3  —  UPLOAD TO YOUTUBE")
        print("  Authenticating with YouTube...")
        yt = uploader.get_upload_client()
        print()
        video_id = uploader.upload_video(
            yt,
            video_path  = result["video_path"],
            title       = config.KNOCKOUT_RANKING_YT_TITLES.get(
                              expected_teams, config.YT_TITLE),
            description = config.YT_DESCRIPTION,
            privacy     = privacy,
        )
        result["video_id"]    = video_id
        result["youtube_url"] = f"https://www.youtube.com/shorts/{video_id}"

        _section("DONE")
        print(f"  Video ID    : {video_id}")
        print(f"  Short URL   : {result['youtube_url']}")
    else:
        _section("DONE  (no upload)")
        print(f"  Video saved : {result['video_path']}")

    print()
    return result
