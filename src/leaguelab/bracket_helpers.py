"""Shared bracket presentation primitives without data-source dependencies."""

def _seed_row(row):
    return {
        "seed": int(row["seed"]),
        "team_key": row["team_key"],
        "team_name": row["team_name"],
        "record": row.get("record", ""),
        "points_for": row.get("points_for", 0),
    }


def _projection_map(team_rows):
    output = {}
    for row in team_rows:
        try:
            week = int(row.get("week", 0) or 0)
            projected = float(row.get("projected_points"))
        except (TypeError, ValueError):
            continue
        key = str(row.get("team_key") or "")
        if key and projected > 0:
            output[(week, key)] = projected
    return output


def _bracket_team(row, score=None, projected_points=None):
    if not row:
        return None
    team = _seed_row(row)
    team["score"] = score
    team["projected_points"] = projected_points
    return team


def _bracket_matchup(week, team_a, team_b, scores, projections):
    if not team_a or not team_b:
        return None

    score_a = scores.get((int(week), team_a["team_key"]))
    score_b = scores.get((int(week), team_b["team_key"]))
    complete = score_a is not None and score_b is not None
    winner = None
    loser = None

    if complete:
        if score_a > score_b:
            winner, loser = team_a, team_b
        elif score_b > score_a:
            winner, loser = team_b, team_a
        else:
            winner, loser = (
                (team_a, team_b)
                if int(team_a["seed"]) < int(team_b["seed"])
                else (team_b, team_a)
            )

    return {
        "week": int(week),
        "team_a": _bracket_team(
            team_a, score_a, projections.get((int(week), team_a["team_key"]))
        ),
        "team_b": _bracket_team(
            team_b, score_b, projections.get((int(week), team_b["team_key"]))
        ),
        "complete": complete,
        "winner_key": winner["team_key"] if winner else None,
        "winner_seed": int(winner["seed"]) if winner else None,
        "winner_name": winner["team_name"] if winner else None,
        "loser_key": loser["team_key"] if loser else None,
        "loser_seed": int(loser["seed"]) if loser else None,
        "loser_name": loser["team_name"] if loser else None,
    }


