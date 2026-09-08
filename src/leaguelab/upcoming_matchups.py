"""Build compact upcoming matchup data from normalized Yahoo rows. Python 3.8 compatible."""
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_ROOT = PROJECT_ROOT / "data" / "normalized"


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _record(row):
    w = int(_num(row.get("actual_wins")))
    l = int(_num(row.get("actual_losses")))
    t = int(_num(row.get("actual_ties")))
    return "{}-{}-{}".format(w, l, t) if t else "{}-{}".format(w, l)


def build_upcoming_matchups(season, week, analytics_result):
    """Return next-week pairings enriched with current record and LeagueLab power rank.

    Returns None when next-week schedule rows are not present locally. This is intentional:
    the newsletter should omit the block rather than invent a matchup.
    """
    next_week = int(week) + 1
    path = NORMALIZED_ROOT / str(season) / "weekly_team_results.csv"
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if int(_num(r.get("week"))) == next_week]
    if not rows:
        return None

    current_rows = [
        r for r in analytics_result.get("weekly_analytics", [])
        if int(_num(r.get("week"))) == int(week)
    ]
    current_by_key = {str(r.get("team_key", "")): r for r in current_rows}
    current_by_name = {str(r.get("team_name", "")): r for r in current_rows}
    power_by_key = {str(r.get("team_key", "")): r for r in analytics_result.get("power_rankings", [])}
    power_by_name = {str(r.get("team_name", "")): r for r in analytics_result.get("power_rankings", [])}

    def team_info(key, name, projected_points=None):
        cur = current_by_key.get(str(key)) or current_by_name.get(str(name)) or {}
        pwr = power_by_key.get(str(key)) or power_by_name.get(str(name)) or {}
        return {
            "team_key": key,
            "team_name": name or cur.get("team_name") or pwr.get("team_name") or "-",
            "record": _record(cur),
            "power_rank": int(_num(pwr.get("power_rank"), 999)) if pwr else None,
            "projected_points": (
                round(_num(projected_points), 2)
                if _num(projected_points) > 0
                else None
            ),
        }

    seen = set()
    matchups = []
    for row in rows:
        a_key = str(row.get("team_key", "") or "")
        b_key = str(row.get("opponent_team_key", "") or "")
        a_name = str(row.get("team_name", "") or "")
        b_name = str(row.get("opponent_team_name", "") or "")
        if not a_name or not b_name:
            continue
        identity = tuple(sorted([a_key or a_name, b_key or b_name]))
        if identity in seen:
            continue
        seen.add(identity)
        opponent_row = next(
            (r for r in rows if str(r.get("team_key", "") or "") == b_key),
            {},
        )
        a = team_info(a_key, a_name, row.get("projected_points"))
        b = team_info(b_key, b_name, opponent_row.get("projected_points"))
        matchups.append({"team_a": a, "team_b": b})

    def interest(item):
        ar = item["team_a"].get("power_rank") or 999
        br = item["team_b"].get("power_rank") or 999
        return ar + br

    matchups.sort(key=interest)
    if not matchups:
        return None
    return {"week": next_week, "matchups": matchups, "matchup_to_watch": 0}
