"""
rankings.py
World Football Elo Rankings data pipeline.

Fetches live data from eloratings.net or Wikipedia, converts to
World Cup win probabilities, and returns a structured top-10 list.

Public API:
    get_top10() -> list[dict]

Each dict: {rank, name, code, elo, pct}
"""
import json
import re
from datetime import datetime, timezone

import requests
import numpy as np

import config


# ═══════════════════════════════════════════════════════════════════════════════
# COUNTRY MAPPING
# English name (as used on ELO rating sites) → (display name, ISO flag code)
# ═══════════════════════════════════════════════════════════════════════════════
ELO_MAP: dict[str, tuple[str, str]] = {
    "Spain":                    ("SPAIN",          "es"),
    "France":                   ("FRANCE",         "fr"),
    "England":                  ("ENGLAND",        "gb-eng"),
    "Brazil":                   ("BRAZIL",         "br"),
    "Argentina":                ("ARGENTINA",      "ar"),
    "Netherlands":              ("NETHERLANDS",    "nl"),
    "Germany":                  ("GERMANY",        "de"),
    "Portugal":                 ("PORTUGAL",       "pt"),
    "Belgium":                  ("BELGIUM",        "be"),
    "Italy":                    ("ITALY",          "it"),
    "Uruguay":                  ("URUGUAY",        "uy"),
    "Croatia":                  ("CROATIA",        "hr"),
    "Denmark":                  ("DENMARK",        "dk"),
    "Switzerland":              ("SWITZERLAND",    "ch"),
    "Morocco":                  ("MOROCCO",        "ma"),
    "Mexico":                   ("MEXICO",         "mx"),
    "Colombia":                 ("COLOMBIA",       "co"),
    "United States":            ("USA",            "us"),
    "USA":                      ("USA",            "us"),
    "Japan":                    ("JAPAN",          "jp"),
    "Senegal":                  ("SENEGAL",        "sn"),
    "Ecuador":                  ("ECUADOR",        "ec"),
    "Chile":                    ("CHILE",          "cl"),
    "Peru":                     ("PERU",           "pe"),
    "Ukraine":                  ("UKRAINE",        "ua"),
    "Poland":                   ("POLAND",         "pl"),
    "Czech Republic":           ("CZECH REPUBLIC", "cz"),
    "Czechia":                  ("CZECH REPUBLIC", "cz"),
    "Sweden":                   ("SWEDEN",         "se"),
    "Turkey":                   ("TURKEY",         "tr"),
    "Norway":                   ("NORWAY",         "no"),
    "Australia":                ("AUSTRALIA",      "au"),
    "South Korea":              ("SOUTH KOREA",    "kr"),
    "Austria":                  ("AUSTRIA",        "at"),
    "Serbia":                   ("SERBIA",         "rs"),
    "Hungary":                  ("HUNGARY",        "hu"),
    "Romania":                  ("ROMANIA",        "ro"),
    "Wales":                    ("WALES",          "gb-wls"),
    "Scotland":                 ("SCOTLAND",       "gb-sct"),
    "Ivory Coast":              ("IVORY COAST",    "ci"),
    "Cote d'Ivoire":            ("IVORY COAST",    "ci"),
    "Ghana":                    ("GHANA",          "gh"),
    "Cameroon":                 ("CAMEROON",       "cm"),
    "Egypt":                    ("EGYPT",          "eg"),
    "Algeria":                  ("ALGERIA",        "dz"),
    "Nigeria":                  ("NIGERIA",        "ng"),
    "Tunisia":                  ("TUNISIA",        "tn"),
    "Iran":                     ("IRAN",           "ir"),
    "Saudi Arabia":             ("SAUDI ARABIA",   "sa"),
    "Qatar":                    ("QATAR",          "qa"),
    "Canada":                   ("CANADA",         "ca"),
    "South Africa":             ("SOUTH AFRICA",   "za"),
    "Russia":                   ("RUSSIA",         "ru"),
    "Slovakia":                 ("SLOVAKIA",       "sk"),
    "Slovenia":                 ("SLOVENIA",       "si"),
    "Albania":                  ("ALBANIA",        "al"),
    "Israel":                   ("ISRAEL",         "il"),
    "Georgia":                  ("GEORGIA",        "ge"),
    "North Macedonia":          ("N. MACEDONIA",   "mk"),
    "Finland":                  ("FINLAND",        "fi"),
    "Costa Rica":               ("COSTA RICA",     "cr"),
    "Panama":                   ("PANAMA",         "pa"),
    "Paraguay":                 ("PARAGUAY",       "py"),
    "Bolivia":                  ("BOLIVIA",        "bo"),
    "Venezuela":                ("VENEZUELA",      "ve"),
    "Honduras":                 ("HONDURAS",       "hn"),
    "New Zealand":              ("NEW ZEALAND",    "nz"),
    "Uzbekistan":               ("UZBEKISTAN",     "uz"),
    "Cape Verde":               ("CAPE VERDE",     "cv"),
    "Burkina Faso":             ("BURKINA FASO",   "bf"),
    "Mali":                     ("MALI",           "ml"),
    "Curacao":                  ("CURACAO",        "cw"),
    "Curaçao":                  ("CURACAO",        "cw"),
    "Bosnia Herzegovina":       ("BOSNIA",         "ba"),
    "Bosnia and Herzegovina":   ("BOSNIA",         "ba"),
    "Jordan":                   ("JORDAN",         "jo"),
    "Iraq":                     ("IRAQ",           "iq"),
    "Greece":                   ("GREECE",         "gr"),
    "Haiti":                    ("HAITI",          "ht"),
    "DR Congo":                 ("DR CONGO",       "cd"),
}

# Offline fallback — top 10 snapshot (June 2025)
FALLBACK_TOP10: list[tuple[str, int]] = [
    ("Spain",       2166),
    ("France",      2122),
    ("England",     2092),
    ("Brazil",      2069),
    ("Argentina",   2061),
    ("Netherlands", 2024),
    ("Germany",     2018),
    ("Portugal",    2001),
    ("Belgium",     1965),
    ("Italy",       1955),
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ═══════════════════════════════════════════════════════════════════════════════
# SCRAPING — private helpers
# ═══════════════════════════════════════════════════════════════════════════════
def _record_elo_source(source: str, teams_resolved: int) -> None:
    """Persists which source fed the last Elo refresh to
    data/elo_source.json, so a silent fall-back to offline data can be
    audited after the fact. Non-fatal — a write failure is just a [WARN]."""
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": source,
            "teams_resolved": teams_resolved,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        config.ELO_SOURCE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"[WARN] Could not write Elo source audit file: {exc}")


def _deduplicated(rows: list[tuple[str, int]]) -> list[tuple[str, int]]:
    seen: set[str] = set()
    return [
        (n, e) for n, e in sorted(rows, key=lambda x: x[1], reverse=True)
        if not (n in seen or seen.add(n))  # type: ignore[func-returns-value]
    ]


def _fetch_eloratings(timeout: int = 12) -> list[tuple[str, int]]:
    """
    eloratings.net renders its table client-side via AJAX, so the static
    `/World` page is empty. The actual data lives in two TSV feeds:
      - World.tsv    : rank, rank, 2-letter team code, current Elo, ...
      - en.teams.tsv : 2-letter team code -> English team name
    """
    base = "https://www.eloratings.net/"

    ratings_resp = requests.get(base + "World.tsv", headers=_HEADERS, timeout=timeout)
    ratings_resp.raise_for_status()
    ratings_resp.encoding = "utf-8"

    names_resp = requests.get(base + "en.teams.tsv", headers=_HEADERS, timeout=timeout)
    names_resp.raise_for_status()
    names_resp.encoding = "utf-8"

    code_to_name: dict[str, str] = {}
    for line in names_resp.text.splitlines():
        cols = line.split("\t")
        if len(cols) >= 2 and not cols[0].endswith("_loc"):
            code_to_name.setdefault(cols[0], cols[1])

    rows: list[tuple[str, int]] = []
    for line in ratings_resp.text.splitlines():
        cols = line.split("\t")
        if len(cols) < 4:
            continue
        name = code_to_name.get(cols[2])
        try:
            elo = int(cols[3])
        except ValueError:
            continue
        if name and 1400 < elo < 2500:
            rows.append((name, elo))

    if len(rows) < 5:
        raise ValueError(f"Only {len(rows)} rows from eloratings.net")
    return _deduplicated(rows)


def _fetch_wikipedia(timeout: int = 12) -> list[tuple[str, int]]:
    from bs4 import BeautifulSoup
    resp = requests.get(
        "https://en.wikipedia.org/wiki/World_Football_Elo_Ratings",
        headers=_HEADERS, timeout=timeout,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    rows: list[tuple[str, int]] = []
    for table in soup.find_all("table", class_="wikitable"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            # Layout: Rank | Change | Team | Points. Skip the caption and
            # header rows by requiring a numeric rank in the first cell.
            if len(cells) < 4 or not cells[0].get_text(strip=True).isdigit():
                continue
            name = cells[2].get_text(strip=True)
            raw  = re.sub(r"[^\d]", "", cells[3].get_text(strip=True))
            if raw and len(name) > 1:
                elo = int(raw)
                if 1400 < elo < 2500:
                    rows.append((name, elo))
        if len(rows) >= 10:
            break
    if len(rows) < 5:
        raise ValueError(f"Wikipedia returned only {len(rows)} rows")
    return _deduplicated(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# PROBABILITY CONVERSION
# ═══════════════════════════════════════════════════════════════════════════════
def elo_to_probabilities(elos: list[float],
                         temperature: float = config.ELO_TEMPERATURE) -> list[float]:
    """
    Softmax over Elo ratings → approximate World Cup win probabilities.

    P_i ∝ exp((Elo_i − max_Elo) / T)

    With T=100 the #1 team is ~5-8x more likely to win than #10.
    Increase T for a flatter, more conservative distribution.
    """
    arr  = np.array(elos, dtype=float)
    logw = (arr - arr.max()) / temperature
    w    = np.exp(logw)
    return (w / w.sum() * 100).round(1).tolist()


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════
def get_elo_table() -> dict[str, dict]:
    """
    Returns Elo data for all teams found in live sources, keyed by display
    name (e.g. "SPAIN" -> {"code": "es", "elo": 2166}).

    Tries eloratings.net -> Wikipedia -> offline fallback (top 10 only).
    Used for head-to-head lookups where either team may fall outside the
    top 10 (e.g. AI Match Prediction shorts).
    """
    raw: list[tuple[str, int]] | None = None
    source = "FALLBACK"
    for label, fetch_fn in [
        ("eloratings.net", _fetch_eloratings),
        ("wikipedia",      _fetch_wikipedia),
    ]:
        try:
            raw = fetch_fn()
            source = label
            print(f"[INFO] Elo source: {label} ({len(raw)} teams)")
            break
        except Exception as exc:
            print(f"[INFO] Elo source {label} failed ({type(exc).__name__}) — trying next")
    if raw is None:
        print(f"[WARN] Elo source fell back to FALLBACK (offline, {len(FALLBACK_TOP10)} teams) "
              "— eloratings.net and Wikipedia both unavailable")
        raw = list(FALLBACK_TOP10)

    table: dict[str, dict] = {}
    for name_en, elo in raw:
        mapping = ELO_MAP.get(name_en) or next(
            (v for k, v in ELO_MAP.items() if k.lower() == name_en.lower()), None
        )
        if not mapping:
            continue
        display, code = mapping
        if display not in table:
            table[display] = {"code": code, "elo": int(elo)}

    print(f"[INFO] Elo table: {len(table)} ELO_MAP teams resolved from {source}")
    _record_elo_source(source, len(table))
    return table


def get_top10() -> list[dict]:
    """
    Returns the top-10 teams with Elo-based World Cup win probabilities.

    Tries live sources in order: eloratings.net → Wikipedia → fallback data.

    Each entry in the returned list:
        rank  (int)  : 1–10
        name  (str)  : display name in uppercase (e.g. "SPAIN")
        code  (str)  : ISO flag code (e.g. "es", "gb-eng")
        elo   (int)  : current Elo rating
        pct   (int)  : rounded win probability (%)
    """
    print("  Fetching Elo rankings...")
    raw: list[tuple[str, int]] | None = None
    source = "FALLBACK"

    for label, fetch_fn in [
        ("eloratings.net", _fetch_eloratings),
        ("wikipedia",      _fetch_wikipedia),
    ]:
        try:
            raw = fetch_fn()
            source = label
            print(f"[INFO] Elo source: {label} ({len(raw)} teams parsed)")
            break
        except Exception as exc:
            print(f"[INFO] Elo source {label} failed ({type(exc).__name__}) — trying next")

    if raw is None:
        print(f"[WARN] Elo source fell back to FALLBACK (offline, June 2025, {len(FALLBACK_TOP10)} teams) "
              "— eloratings.net and Wikipedia both unavailable")
        raw = list(FALLBACK_TOP10)

    # Map raw entries to display names and flag codes
    mapped: list[dict] = []
    for name_en, elo in raw:
        mapping = ELO_MAP.get(name_en) or next(
            (v for k, v in ELO_MAP.items() if k.lower() == name_en.lower()), None
        )
        if not mapping:
            continue
        display, code = mapping
        if any(t["code"] == code for t in mapped):
            continue  # deduplicate by flag code
        mapped.append({"name_en": name_en, "name": display, "code": code, "elo": int(elo)})
        if len(mapped) == 10:
            break

    # Pad with fallback if not enough teams were mapped
    for name_en, elo in FALLBACK_TOP10:
        if len(mapped) >= 10:
            break
        display, code = ELO_MAP[name_en]
        if not any(t["code"] == code for t in mapped):
            mapped.append({"name_en": name_en, "name": display,
                           "code": code, "elo": int(elo)})

    _record_elo_source(source, len(mapped))

    # Calculate probabilities
    probs  = elo_to_probabilities([t["elo"] for t in mapped])
    result = [
        {
            "rank": i + 1,
            "name": t["name"],
            "code": t["code"],
            "elo":  t["elo"],
            "pct":  max(1, round(p)),
        }
        for i, (t, p) in enumerate(zip(mapped, probs))
    ]

    # Print summary table
    print(f"\n  {'#':>3}  {'Team':<16}  {'Elo':>5}  {'Prob':>5}")
    print("  " + "-" * 36)
    for t in result:
        print(f"  {t['rank']:>3}  {t['name']:<16}  {t['elo']:>5}  {t['pct']:>4}%")
    print()

    return result
