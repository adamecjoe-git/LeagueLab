"""Authoritative postseason seeds and completed games from captured Yahoo JSON."""
import json
from pathlib import Path

RAW_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "yahoo"


def find(value, key):
    if isinstance(value, dict):
        if key in value:
            yield value[key]
        for child in value.values():
            yield from find(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from find(child, key)


def field(value, key, default=None):
    return next(find(value, key), default)


def league_root(season, team_rows):
    leagues = {str(r.get("team_key", "")).split(".t.")[0] for r in team_rows
               if ".t." in str(r.get("team_key", ""))}
    if len(leagues) != 1:
        raise RuntimeError("Cannot select one Yahoo league from normalized team keys.")
    return RAW_ROOT / str(season) / leagues.pop()


def read(path):
    if not path.exists():
        raise RuntimeError("Missing Yahoo postseason source {}; refresh Yahoo data first.".format(path))
    with path.open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_standings(season, team_rows):
    """playoff_seed is qualification order; Yahoo rank is a postseason finish."""
    payload = read(league_root(season, team_rows) / "standings.json")
    rows = []
    for team in find(payload, "team"):
        standing = field(team, "team_standings", {})
        if not standing:
            continue
        totals = standing.get("outcome_totals") or {}
        wins, losses, ties = [int(totals.get(k, 0)) for k in ("wins", "losses", "ties")]
        games = wins + losses + ties
        seed = standing.get("playoff_seed")
        rows.append(dict(team_key=field(team, "team_key"), team_name=field(team, "name"),
                         seed=int(seed) if seed not in (None, "", "0", 0) else None,
                         wins=wins, losses=losses, ties=ties,
                         win_pct=(wins + ties * .5) / games if games else 0,
                         points_for=float(standing.get("points_for", 0)),
                         record="{}-{}-{}".format(wins, losses, ties)))
    qualifiers = [r for r in rows if r["seed"] is not None]
    if len(rows) != 12 or len({r["team_key"] for r in rows}) != 12 or sorted(r["seed"] for r in qualifiers) != list(range(1, 9)):
        raise RuntimeError("Yahoo standings must contain 12 teams and eight distinct playoff seeds (1-8). Refresh standings after qualification is final.")
    if {r["team_key"] for r in rows} != {r["team_key"] for r in team_rows}:
        raise RuntimeError("Yahoo standings and normalized team identities do not match.")
    # Yahoo does not seed nonqualifiers. Apply regular-season W/L and PF
    # tiebreaking only to those four teams, never to the official playoff field.
    others = sorted((r for r in rows if r["seed"] is None),
                    key=lambda r: (-r["win_pct"], -r["points_for"], r["team_name"].lower()))
    for seed, row in enumerate(others, 9):
        row["seed"] = seed
    return sorted(rows, key=lambda r: r["seed"])


def build_bracket(season, team_rows, standings, week, regular_end):
    from leaguelab.bracket_helpers import _bracket_matchup, _projection_map
    by_seed = {r["seed"]: r for r in standings}
    by_key = {r["team_key"]: r for r in standings if r["seed"] <= 8}
    projections = _projection_map(team_rows)
    root = league_root(season, team_rows)
    rounds = {}
    for target in range(regular_end + 1, min(week, regular_end + 3) + 1):
        matches = {}
        payload = read(root / "weeks" / "week_{:02d}".format(target) / "scoreboard.json")
        for raw in find(payload, "matchup"):
            teams = list(find(raw, "team"))
            keys = [field(t, "team_key") for t in teams]
            if len(keys) != 2 or not all(k in by_key for k in keys):
                continue
            pair = frozenset(keys)
            if pair in matches:
                raise RuntimeError("Duplicate Yahoo playoff matchup in week {}.".format(target))
            scores = {}
            complete = raw.get("status") == "postevent"
            if complete:
                for key, team in zip(keys, teams):
                    points = field(team, "team_points", {})
                    if str(points.get("week")) != str(target):
                        raise RuntimeError("Yahoo playoff score has incorrect week coverage.")
                    scores[(target, key)] = float(points["total"])
            item = _bracket_matchup(target, by_key[keys[0]], by_key[keys[1]], scores, projections)
            if complete:
                winner = raw.get("winner_team_key")
                if winner not in keys:
                    raise RuntimeError("Completed Yahoo playoff matchup has no valid winner.")
                loser = next(k for k in keys if k != winner)
                for prefix, key in (("winner", winner), ("loser", loser)):
                    item[prefix + "_key"] = key
                    item[prefix + "_seed"] = by_key[key]["seed"]
                    item[prefix + "_name"] = by_key[key]["team_name"]
            matches[pair] = item
        rounds[target] = matches

    def game(target, a, b):
        if not a or not b:
            return None
        if target <= week:
            item = rounds[target].get(frozenset((a["team_key"], b["team_key"])))
            if item is None:
                raise RuntimeError("Yahoo Week {} is missing expected matchup: {} / {}. Check scoreboard and reseeding settings.".format(target, a["team_name"], b["team_name"]))
            # Keep bracket display order stable even if Yahoo reverses sides.
            item = dict(item)
            if item["team_a"]["team_key"] != a["team_key"]:
                item["team_a"], item["team_b"] = item["team_b"], item["team_a"]
            return item
        return _bracket_matchup(target, a, b, {}, projections)

    def participant(item, outcome):
        return by_key.get((item or {}).get(outcome + "_key"))

    q, s, f = regular_end + 1, regular_end + 2, regular_end + 3
    quarterfinals = [game(q, by_seed[a], by_seed[b]) for a, b in ((1, 8), (4, 5), (3, 6), (2, 7))]
    semis = [game(s, participant(quarterfinals[a], "winner"), participant(quarterfinals[b], "winner")) for a, b in ((0, 1), (2, 3))]
    consolation = [game(s, participant(quarterfinals[a], "loser"), participant(quarterfinals[b], "loser")) for a, b in ((0, 1), (2, 3))]
    finals = {label: game(f, participant(source[0], outcome), participant(source[1], outcome))
              for label, source, outcome in (("championship", semis, "winner"), ("third_place", semis, "loser"),
                                             ("fifth_place", consolation, "winner"), ("seventh_place", consolation, "loser"))}
    final = finals.get("championship") or {}
    champion = dict(seed=final["winner_seed"], team_name=final["winner_name"]) if final.get("complete") else None
    return dict(quarterfinal_week=q, semifinal_week=s, final_week=f, quarterfinals=quarterfinals,
                championship_semifinals=[m for m in semis if m], consolation_semifinals=[m for m in consolation if m],
                finals=finals, champion=champion)
