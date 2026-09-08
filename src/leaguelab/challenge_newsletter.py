"""
LeagueLab challenge newsletter adapter.

Reads normalized LeagueLab CSVs and produces newsletter-ready challenge data.
The formulas mirror LeagueLab's existing challenge definitions.

Python 3.8 compatible.
"""

import csv
from collections import defaultdict
from pathlib import Path

from leaguelab.lineup import solve_optimal_lineup


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_ROOT = PROJECT_ROOT / "data" / "normalized"

CHALLENGES = (
    {"name": "Hot Start", "type": "hot_start", "start": 1, "end": 2, "prize": 10,
     "description": "Most total starting-lineup points across the two challenge weeks."},
    {"name": "Dynamic Duo", "type": "dynamic_duo", "start": 3, "end": 4, "prize": 10,
     "description": "Most combined points from each team's two highest-scoring starters each week."},
    {"name": "Flex Appeal", "type": "flex_appeal", "start": 5, "end": 6, "prize": 10,
     "description": "Most points scored from the W/R/T flex positions across the two weeks."},
    {"name": "Depth Charge", "type": "depth_charge", "start": 7, "end": 8, "prize": 10,
     "description": "Most combined points from RB2, WR2, FLEX1 and FLEX2 across the two weeks."},
    {"name": "Perfect Lineup", "type": "perfect_lineup", "start": 9, "end": 10, "prize": 10,
     "description": "Highest lineup efficiency: actual starter points divided by the optimal legal lineup."},
    {"name": "No Weak Links", "type": "no_weak_links", "start": 11, "end": 12, "prize": 10,
     "description": "Highest combined score from each team's lowest-scoring starter each week."},
    {"name": "Finish Strong", "type": "finish_strong", "start": 13, "end": 14, "prize": 10,
     "description": "Largest improvement over the team's expected two-week score based on its Weeks 1-12 average."},
)

SEASON_SCORING = {
    "name": "Season Points",
    "type": "season_scoring",
    "start": 1,
    "end": 14,
    "prize": 20,
    "description": "Most total fantasy points scored during the 14-week regular season.",
}


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _load_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_rows(season):
    folder = NORMALIZED_ROOT / str(season)
    team_path = folder / "weekly_team_results.csv"
    player_path = folder / "weekly_players.csv"

    if not team_path.exists():
        raise FileNotFoundError("Missing normalized team results: {}".format(team_path))
    if not player_path.exists():
        raise FileNotFoundError("Missing normalized player data: {}".format(player_path))

    return _load_csv(team_path), _load_csv(player_path)


def _rank(values, teams):
    ordered = sorted(
        values.items(),
        key=lambda item: (-item[1], teams.get(item[0], "").lower()),
    )
    return [
        {
            "rank": index,
            "team_key": key,
            "team_name": teams.get(key, key),
            "value": round(value, 2),
        }
        for index, (key, value) in enumerate(ordered, 1)
    ]


def _team_names(team_rows, player_rows):
    names = {}
    for row in team_rows + player_rows:
        key = str(row.get("team_key") or "")
        name = str(row.get("team_name") or "")
        if key and name:
            names[key] = name
    return names


def _starter_rows(player_rows, start_week, through_week):
    return [
        row for row in player_rows
        if start_week <= int(row.get("week", 0) or 0) <= through_week
        and _to_bool(row.get("is_starter"))
    ]


def _score_challenge(definition, team_rows, player_rows, through_week):
    start_week = definition["start"]
    end_week = min(definition["end"], through_week)
    challenge_type = definition["type"]
    teams = _team_names(team_rows, player_rows)

    if through_week < start_week:
        return []

    if challenge_type == "hot_start":
        totals = defaultdict(float)
        for row in _starter_rows(player_rows, start_week, end_week):
            totals[str(row["team_key"])] += _to_float(row.get("points"))
        return _rank(totals, teams)

    if challenge_type == "dynamic_duo":
        weekly = defaultdict(list)
        for row in _starter_rows(player_rows, start_week, end_week):
            weekly[(str(row["team_key"]), int(row["week"]))].append(
                _to_float(row.get("points"))
            )
        totals = defaultdict(float)
        for (team_key, _week), scores in weekly.items():
            totals[team_key] += sum(sorted(scores, reverse=True)[:2])
        return _rank(totals, teams)

    if challenge_type == "flex_appeal":
        totals = defaultdict(float)
        for row in _starter_rows(player_rows, start_week, end_week):
            if str(row.get("selected_position") or "") != "W/R/T":
                continue
            totals[str(row["team_key"])] += _to_float(row.get("points"))
        return _rank(totals, teams)

    if challenge_type == "depth_charge":
        target_slots = {"RB2", "WR2", "FLEX1", "FLEX2"}
        totals = defaultdict(float)
        for row in _starter_rows(player_rows, start_week, end_week):
            if str(row.get("lineup_slot") or "") not in target_slots:
                continue
            totals[str(row["team_key"])] += _to_float(row.get("points"))
        return _rank(totals, teams)

    if challenge_type == "perfect_lineup":
        grouped = defaultdict(list)
        for row in player_rows:
            week = int(row.get("week", 0) or 0)
            if start_week <= week <= end_week:
                grouped[(str(row["team_key"]), week)].append(row)

        actual = defaultdict(float)
        optimal = defaultdict(float)
        for (team_key, _week), players in grouped.items():
            actual[team_key] += sum(
                _to_float(player.get("points"))
                for player in players
                if _to_bool(player.get("is_starter"))
            )
            optimal[team_key] += _to_float(
                solve_optimal_lineup(players).get("total_points")
            )

        values = {}
        for team_key, actual_points in actual.items():
            optimal_points = optimal.get(team_key, 0.0)
            if optimal_points > 0:
                values[team_key] = actual_points / optimal_points * 100.0
        return _rank(values, teams)

    if challenge_type == "no_weak_links":
        weekly = defaultdict(list)
        for row in _starter_rows(player_rows, start_week, end_week):
            weekly[(str(row["team_key"]), int(row["week"]))].append(
                _to_float(row.get("points"))
            )
        totals = defaultdict(float)
        for (team_key, _week), scores in weekly.items():
            if scores:
                totals[team_key] += min(scores)
        return _rank(totals, teams)

    if challenge_type == "finish_strong":
        team_week_scores = {}
        for row in team_rows:
            week = int(row.get("week", 0) or 0)
            if week <= end_week:
                team_week_scores[(str(row["team_key"]), week)] = _to_float(
                    row.get("points")
                )

        values = {}
        for team_key in teams:
            baseline = [
                team_week_scores[(team_key, week)]
                for week in range(1, start_week)
                if (team_key, week) in team_week_scores
            ]
            challenge = [
                team_week_scores[(team_key, week)]
                for week in range(start_week, end_week + 1)
                if (team_key, week) in team_week_scores
            ]
            if not baseline or not challenge:
                continue
            expected = (sum(baseline) / len(baseline)) * len(challenge)
            values[team_key] = sum(challenge) - expected
        return _rank(values, teams)

    if challenge_type == "season_scoring":
        totals = defaultdict(float)
        for row in team_rows:
            week = int(row.get("week", 0) or 0)
            if start_week <= week <= end_week:
                totals[str(row["team_key"])] += _to_float(row.get("points"))
        return _rank(totals, teams)

    return []


def _format_value(challenge_type, value):
    if challenge_type == "perfect_lineup":
        return "{:.1f}%".format(_to_float(value))
    if challenge_type == "finish_strong":
        return "{:+.2f}".format(_to_float(value))
    return "{:.2f}".format(_to_float(value))


def _challenge_summary(definition):
    if not definition:
        return None
    return {
        "name": definition["name"],
        "type": definition["type"],
        "start": definition["start"],
        "end": definition["end"],
        "weeks": "Weeks {}-{}".format(definition["start"], definition["end"]),
        "prize": definition["prize"],
        "description": definition.get("description", ""),
    }


def build_challenge_newsletter_data(season, week):
    team_rows, player_rows = _load_rows(season)

    current = None
    for definition in CHALLENGES:
        if definition["start"] <= week <= definition["end"]:
            current = definition
            break

    if current is None:
        return None

    standings = _score_challenge(current, team_rows, player_rows, week)
    formatted = [
        {
            "rank": row["rank"],
            "team_name": row["team_name"],
            "value": _format_value(current["type"], row["value"]),
        }
        for row in standings
    ]

    complete = week >= current["end"]
    winner = standings[0] if complete and standings else None

    payouts = defaultdict(float)
    winners = []
    for definition in CHALLENGES:
        if week < definition["end"]:
            continue
        result = _score_challenge(definition, team_rows, player_rows, definition["end"])
        if result:
            payouts[result[0]["team_name"]] += definition["prize"]
            winners.append({
                "name": definition["name"],
                "weeks": "Weeks {}-{}".format(definition["start"], definition["end"]),
                "team_name": result[0]["team_name"],
                "prize": definition["prize"],
            })

    season_result = _score_challenge(
        SEASON_SCORING, team_rows, player_rows, min(week, SEASON_SCORING["end"])
    )
    season_complete = week >= SEASON_SCORING["end"]
    if season_complete and season_result:
        payouts[season_result[0]["team_name"]] += SEASON_SCORING["prize"]
        winners.append({
            "name": SEASON_SCORING["name"],
            "weeks": "Weeks 1-14",
            "team_name": season_result[0]["team_name"],
            "prize": SEASON_SCORING["prize"],
        })

    payout_rows = [
        {"team_name": team, "amount": amount}
        for team, amount in sorted(
            payouts.items(), key=lambda item: (-item[1], item[0].lower())
        )
    ]

    next_definition = None
    for definition in CHALLENGES:
        if definition["start"] > current["end"]:
            next_definition = definition
            break

    next_challenge = _challenge_summary(next_definition)

    return {
        "name": current["name"],
        "type": current["type"],
        "weeks": "Weeks {}-{}".format(current["start"], current["end"]),
        "prize": current["prize"],
        "description": current.get("description", ""),
        "complete": complete,
        "status": (
            "Winner: {} — ${}".format(winner["team_name"], current["prize"])
            if winner else "In Progress"
        ),
        "leader": formatted[0] if formatted else None,
        "standings": formatted,
        "next_challenge": next_challenge,
        "payout_leaderboard": payout_rows,
        "challenge_winners": winners,
        "season_points": [
            {
                "rank": row["rank"],
                "team_name": row["team_name"],
                "value": "{:.2f}".format(_to_float(row["value"])),
            }
            for row in season_result
        ],
        "season_points_complete": season_complete,
        "season_points_description": SEASON_SCORING["description"],
    }
