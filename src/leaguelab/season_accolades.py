"""Week 17 season accolades for LeagueLab. Python 3.8 compatible."""
import csv
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_ROOT = PROJECT_ROOT / "data" / "normalized"
RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "yahoo"


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _player_totals(rows, start_week, end_week, starters_only=False):
    totals = {}
    for row in rows:
        week = int(_num(row.get("week")))
        if week < int(start_week) or week > int(end_week):
            continue
        if starters_only and str(row.get("is_starter", "")).lower() not in (
            "1", "true", "yes"
        ):
            continue
        key = str(row.get("player_key") or row.get("player_id") or "")
        if not key:
            continue
        item = totals.setdefault(key, {
            "player_key": key,
            "player_name": row.get("player_name") or "-",
            "team_name": row.get("team_name") or "-",
            "points": 0.0,
            "starts": 0,
        })
        item["points"] += _num(row.get("points"))
        if str(row.get("is_starter", "")).lower() in ("1", "true", "yes"):
            item["starts"] += 1
        # The final roster/team association is useful for display.
        if row.get("team_name"):
            item["team_name"] = row.get("team_name")
    return totals


def _draft_records(value, output):
    """Recursively extract Yahoo draft-result records."""
    if isinstance(value, dict):
        pick = value.get("pick")
        player_key = value.get("player_key")
        team_key = value.get("team_key")
        if pick is not None and player_key:
            try:
                pick_num = int(float(pick))
            except (TypeError, ValueError):
                pick_num = None
            if pick_num is not None:
                output.append({
                    "pick": pick_num,
                    "player_key": str(player_key),
                    "team_key": str(team_key or ""),
                })
        for child in value.values():
            _draft_records(child, output)
    elif isinstance(value, list):
        for child in value:
            _draft_records(child, output)


def _load_draft_results(season):
    season_root = RAW_ROOT / str(season)
    if not season_root.exists():
        return []

    candidates = []
    for pattern in ("**/draft_results.json", "**/draftresults.json", "**/*draft*.json"):
        candidates.extend(season_root.glob(pattern))

    seen_paths = set()
    records = []
    for path in candidates:
        key = str(path).lower()
        if key in seen_paths:
            continue
        seen_paths.add(key)
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            continue
        _draft_records(payload, records)
        if records:
            break

    unique = {}
    for row in records:
        unique[row["player_key"]] = row
    return list(unique.values())


def build_season_accolades(season):
    root = NORMALIZED_ROOT / str(season)
    players = _read_csv(root / "weekly_players.csv")
    teams = _read_csv(root / "weekly_team_results.csv")
    if not players:
        return []

    output = []

    # Regular-season MVP: total player fantasy points, Weeks 1-14.
    regular = _player_totals(players, 1, 14, starters_only=False)
    if regular:
        winner = max(regular.values(), key=lambda row: row["points"])
        output.append({
            "icon": "🏆",
            "title": "Regular-Season MVP",
            "winner": winner["player_name"],
            "detail": "{:.2f} pts • Weeks 1-14".format(winner["points"]),
        })

    # Playoff MVP: points actually contributed to starting lineups, Weeks 15-17.
    playoff = _player_totals(players, 15, 17, starters_only=True)
    if playoff:
        winner = max(playoff.values(), key=lambda row: row["points"])
        output.append({
            "icon": "🔥",
            "title": "Playoff MVP",
            "winner": winner["player_name"],
            "detail": "{:.2f} starter pts • Weeks 15-17".format(
                winner["points"]
            ),
        })

    draft = _load_draft_results(season)
    drafted_keys = {row["player_key"] for row in draft}

    # Best Draft Pick: among meaningful fantasy contributors (top 24 drafted
    # players in regular-season points), reward the largest improvement from
    # draft slot to production rank.  This prevents a modest last-round player
    # from winning merely because he was drafted late.
    drafted_production = []
    draft_by_key = {row["player_key"]: row for row in draft}
    for key, stats in regular.items():
        if key in draft_by_key:
            row = dict(stats)
            row["pick"] = draft_by_key[key]["pick"]
            drafted_production.append(row)
    drafted_production.sort(key=lambda row: row["points"], reverse=True)
    for rank, row in enumerate(drafted_production, start=1):
        row["production_rank"] = rank
        row["value"] = row["pick"] - rank
    meaningful = drafted_production[:24]
    if meaningful:
        winner = max(
            meaningful,
            key=lambda row: (row["value"], row["points"]),
        )
        output.append({
            "icon": "💎",
            "title": "Best Draft Pick",
            "winner": winner["player_name"],
            "detail": "Pick #{} • {:.2f} regular-season pts".format(
                winner["pick"], winner["points"]
            ),
        })

    # Waiver Pickup of the Year: best starter production from a player who
    # was not drafted.  Weekly roster ownership means the player had to be on
    # a fantasy roster; using starter points measures actual lineup impact.
    season_starters = _player_totals(players, 1, 17, starters_only=True)
    waiver_candidates = [
        row for key, row in season_starters.items()
        if key not in drafted_keys and row["starts"] > 0
    ]
    if draft and waiver_candidates:
        winner = max(
            waiver_candidates,
            key=lambda row: (row["points"], row["starts"]),
        )
        output.append({
            "icon": "🛒",
            "title": "Waiver Pickup of the Year",
            "winner": winner["player_name"],
            "detail": "{:.2f} starter pts • {} starts".format(
                winner["points"], winner["starts"]
            ),
        })

    # Most Improved Team: compare average scoring in Weeks 1-7 with Weeks 8-14.
    by_team = {}
    for row in teams:
        week = int(_num(row.get("week")))
        if week < 1 or week > 14:
            continue
        key = str(row.get("team_key") or row.get("team_name") or "")
        item = by_team.setdefault(key, {
            "team_name": row.get("team_name") or "-",
            "first": [],
            "second": [],
        })
        bucket = "first" if week <= 7 else "second"
        item[bucket].append(_num(row.get("points")))
    improved = []
    for item in by_team.values():
        if not item["first"] or not item["second"]:
            continue
        first = sum(item["first"]) / len(item["first"])
        second = sum(item["second"]) / len(item["second"])
        improved.append((second - first, first, second, item))
    if improved:
        delta, first, second, winner = max(improved, key=lambda item: item[0])
        output.append({
            "icon": "📈",
            "title": "Most Improved Team",
            "winner": winner["team_name"],
            "detail": "{:+.2f} pts/week • {:.2f} → {:.2f}".format(
                delta, first, second
            ),
        })

    return output
