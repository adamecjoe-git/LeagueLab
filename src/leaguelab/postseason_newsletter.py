"""Newsletter-facing postseason data for LeagueLab. Python 3.8 compatible."""
import csv
from pathlib import Path

from leaguelab.postseason import (
    build_regular_season_standings,
    build_virtual_team_scores,
    load_postseason_config,
    resolve_matchup,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_ROOT = PROJECT_ROOT / "data" / "normalized"


def _read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _seed_row(row):
    return {
        "seed": int(row["seed"]),
        "team_key": row["team_key"],
        "team_name": row["team_name"],
        "record": row.get("record", ""),
        "points_for": row.get("points_for", 0),
    }


def _pairings_from_seeds(by_seed, pairs):
    output = []
    for a, b in pairs:
        if a in by_seed and b in by_seed:
            output.append({"team_a": _seed_row(by_seed[a]), "team_b": _seed_row(by_seed[b])})
    return output


def _official_playoff_results(team_rows, week, playoff_keys, seed_by_key):
    rows = [r for r in team_rows if int(r.get("week", 0) or 0) == int(week)]
    by_key = {str(r.get("team_key")): r for r in rows}
    seen = set()
    output = []
    for row in rows:
        key = str(row.get("team_key") or "")
        opp = str(row.get("opponent_team_key") or "")
        if key not in playoff_keys or opp not in playoff_keys or not opp:
            continue
        pair = tuple(sorted([key, opp]))
        if pair in seen:
            continue
        seen.add(pair)
        other = by_key.get(opp, {})
        output.append({
            "team_a": {"seed": seed_by_key.get(key), "team_name": row.get("team_name", ""), "score": row.get("points", "")},
            "team_b": {"seed": seed_by_key.get(opp), "team_name": row.get("opponent_team_name") or other.get("team_name", ""), "score": row.get("opponent_points", other.get("points", ""))},
        })
    return output


def _progressive_toilet_bowl(standings, team_rows, player_rows, config, week):
    toilet = config.get("toilet_bowl", {})
    if not toilet.get("enabled", True):
        return None

    by_seed = {int(row["seed"]): row for row in standings}
    pairs = toilet.get("semifinals", [[9, 12], [10, 11]])
    semifinal_week = int(toilet.get("semifinal_week", 15))
    championship_week = int(toilet.get("championship_week", 16))
    tie_breaker = toilet.get("tie_breaker", "higher_seed")
    participant_keys = [by_seed[int(s)]["team_key"] for s in toilet.get("seeds", [9, 10, 11, 12]) if int(s) in by_seed]

    projections = _projection_map(team_rows)

    def add_projection_fields(matchup, target_week):
        if not matchup:
            return matchup
        matchup["team_a_projected_points"] = projections.get(
            (int(target_week), str(matchup.get("team_a_key") or ""))
        )
        matchup["team_b_projected_points"] = projections.get(
            (int(target_week), str(matchup.get("team_b_key") or ""))
        )
        return matchup

    preview = _pairings_from_seeds(
        by_seed, [(int(x[0]), int(x[1])) for x in pairs]
    )
    for pair in preview:
        for side in ("team_a", "team_b"):
            team = pair.get(side) or {}
            team["projected_points"] = projections.get(
                (semifinal_week, str(team.get("team_key") or ""))
            )

    data = {
        "name": toilet.get("name", "Toilet Bowl"),
        "semifinal_week": semifinal_week,
        "championship_week": championship_week,
        "preview": preview,
        "semifinals": [],
        "championship": None,
        "champion": None,
    }

    if int(week) < semifinal_week:
        return data

    virtual = build_virtual_team_scores(player_rows, [semifinal_week, championship_week], participant_keys)
    semis = []
    for pair in pairs:
        a, b = int(pair[0]), int(pair[1])
        if (semifinal_week, by_seed[a]["team_key"]) not in virtual or (semifinal_week, by_seed[b]["team_key"]) not in virtual:
            continue
        semis.append(add_projection_fields(
            resolve_matchup(semifinal_week, by_seed[a], by_seed[b], virtual, tie_breaker),
            semifinal_week,
        ))
    data["semifinals"] = semis

    # As soon as the semifinal winners are known (Week 15), populate the
    # Week 16 final.  Before Week 16 is complete it is a pending matchup with
    # Yahoo projections; once Week 16 is complete, replace projections with
    # actual results and determine the Toilet Bowl champion.
    if int(week) >= semifinal_week and len(semis) == 2:
        finalists = [
            by_seed[int(semis[0]["winner_seed"])],
            by_seed[int(semis[1]["winner_seed"])],
        ]

        if int(week) >= championship_week and all(
            (championship_week, team["team_key"]) in virtual
            for team in finalists
        ):
            championship = add_projection_fields(
                resolve_matchup(
                    championship_week,
                    finalists[0],
                    finalists[1],
                    virtual,
                    tie_breaker,
                ),
                championship_week,
            )
            data["championship"] = championship
            data["champion"] = {
                "seed": championship["winner_seed"],
                "team_name": championship["winner_name"],
                "payout": float(toilet.get("payout", 40)),
            }
        else:
            data["championship"] = {
                "week": championship_week,
                "team_a_seed": int(finalists[0]["seed"]),
                "team_a_key": finalists[0]["team_key"],
                "team_a_name": finalists[0]["team_name"],
                "team_a_score": None,
                "team_b_seed": int(finalists[1]["seed"]),
                "team_b_key": finalists[1]["team_key"],
                "team_b_name": finalists[1]["team_name"],
                "team_b_score": None,
                "winner_seed": None,
                "winner_key": None,
                "winner_name": None,
            }
            add_projection_fields(data["championship"], championship_week)
    return data



def _score_map(team_rows):
    output = {}
    for row in team_rows:
        try:
            week = int(row.get("week", 0) or 0)
            score = float(row.get("points"))
        except (TypeError, ValueError):
            continue
        key = str(row.get("team_key") or "")
        if key:
            output[(week, key)] = score
    return output


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


def _winner(matchup, by_key):
    return by_key.get(matchup.get("winner_key")) if matchup and matchup.get("winner_key") else None


def _loser(matchup, by_key):
    return by_key.get(matchup.get("loser_key")) if matchup and matchup.get("loser_key") else None


def _build_playoff_bracket(standings, team_rows, newsletter_week, regular_end):
    by_seed = {int(row["seed"]): row for row in standings}
    by_key = {row["team_key"]: row for row in standings}
    scores = {
        key: value
        for key, value in _score_map(team_rows).items()
        if key[0] <= int(newsletter_week)
    }
    projections = _projection_map(team_rows)

    qf_week = int(regular_end) + 1
    sf_week = qf_week + 1
    final_week = qf_week + 2

    # Yahoo's 2025 eight-team bracket branches:
    # 1/8 with 4/5, and 3/6 with 2/7.
    qf_pairs = [(1, 8), (4, 5), (3, 6), (2, 7)]
    qfs = [
        _bracket_matchup(qf_week, by_seed.get(a), by_seed.get(b), scores, projections)
        for a, b in qf_pairs
    ]

    championship_semis = []
    consolation_semis = []
    if int(newsletter_week) >= qf_week:
        championship_semis = [
            _bracket_matchup(sf_week, _winner(qfs[0], by_key), _winner(qfs[1], by_key), scores, projections),
            _bracket_matchup(sf_week, _winner(qfs[2], by_key), _winner(qfs[3], by_key), scores, projections),
        ]
        consolation_semis = [
            _bracket_matchup(sf_week, _loser(qfs[0], by_key), _loser(qfs[1], by_key), scores, projections),
            _bracket_matchup(sf_week, _loser(qfs[2], by_key), _loser(qfs[3], by_key), scores, projections),
        ]

    finals = {}
    if int(newsletter_week) >= sf_week and all(championship_semis) and all(consolation_semis):
        finals = {
            "championship": _bracket_matchup(
                final_week,
                _winner(championship_semis[0], by_key),
                _winner(championship_semis[1], by_key),
                scores,
                projections,
            ),
            "third_place": _bracket_matchup(
                final_week,
                _loser(championship_semis[0], by_key),
                _loser(championship_semis[1], by_key),
                scores,
                projections,
            ),
            "fifth_place": _bracket_matchup(
                final_week,
                _winner(consolation_semis[0], by_key),
                _winner(consolation_semis[1], by_key),
                scores,
                projections,
            ),
            "seventh_place": _bracket_matchup(
                final_week,
                _loser(consolation_semis[0], by_key),
                _loser(consolation_semis[1], by_key),
                scores,
                projections,
            ),
        }

    championship = finals.get("championship")
    champion = None
    if championship and championship.get("complete"):
        champion = {
            "seed": championship["winner_seed"],
            "team_name": championship["winner_name"],
        }

    return {
        "quarterfinal_week": qf_week,
        "semifinal_week": sf_week,
        "final_week": final_week,
        "quarterfinals": qfs,
        "championship_semifinals": [x for x in championship_semis if x],
        "consolation_semifinals": [x for x in consolation_semis if x],
        "finals": finals,
        "champion": champion,
    }


def _build_league_payouts(playoff, toilet, config):
    # Defaults match XTreme Football. They can be overridden in
    # postseason.json with:
    # "league_payouts": {"first":210,"second":100,"third":40,"toilet_bowl":40}
    amounts = {
        "first": 210.0,
        "second": 100.0,
        "third": 40.0,
        "toilet_bowl": 40.0,
    }
    configured = config.get("league_payouts", {}) or {}
    for key in amounts:
        if key in configured:
            try:
                amounts[key] = float(configured[key])
            except (TypeError, ValueError):
                pass

    rows = []
    finals = playoff.get("finals") or {}
    championship = finals.get("championship") or {}
    third_place = finals.get("third_place") or {}

    if championship.get("complete"):
        rows.extend([
            {
                "place": "1st",
                "team_name": championship.get("winner_name"),
                "amount": amounts["first"],
            },
            {
                "place": "2nd",
                "team_name": championship.get("loser_name"),
                "amount": amounts["second"],
            },
        ])

    if third_place.get("complete"):
        rows.append({
            "place": "3rd",
            "team_name": third_place.get("winner_name"),
            "amount": amounts["third"],
        })

    toilet_champion = (toilet or {}).get("champion") or {}
    if toilet_champion:
        rows.append({
            "place": "Toilet Bowl",
            "team_name": toilet_champion.get("team_name"),
            "amount": amounts["toilet_bowl"],
        })

    return [row for row in rows if row.get("team_name")]

def build_postseason_newsletter_data(season, week, analytics_result):
    root = NORMALIZED_ROOT / str(season)
    team_rows = _read_csv(root / "weekly_team_results.csv")
    player_rows = _read_csv(root / "weekly_players.csv")
    if not team_rows:
        return None

    config = load_postseason_config(season)
    regular_end = int(
        config.get("toilet_bowl", {}).get("regular_season_end_week", 14)
    )
    standings = build_regular_season_standings(team_rows, regular_end)

    playoff = _build_playoff_bracket(
        standings, team_rows, int(week), regular_end
    )
    toilet = _progressive_toilet_bowl(
        standings, team_rows, player_rows, config, int(week)
    )

    return {
        "playoff": playoff,
        "champion": playoff.get("champion"),
        "toilet_bowl": toilet,
        "league_payouts": _build_league_payouts(
            playoff, toilet, config
        ),
        "final_standings": [_seed_row(row) for row in standings],
    }
