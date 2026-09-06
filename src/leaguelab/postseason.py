import csv
import json
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_ROOT = PROJECT_ROOT / "data" / "normalized"
OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"
CONFIG_ROOT = PROJECT_ROOT / "data" / "config"

DEFAULT_POSTSEASON_CONFIG = {
    "toilet_bowl": {
        "enabled": True,
        "name": "Toilet Bowl",
        "regular_season_end_week": 14,
        "semifinal_week": 15,
        "championship_week": 16,
        "seeds": [9, 10, 11, 12],
        "semifinals": [
            [9, 12],
            [10, 11]
        ],
        "payout": 40,
        "tie_breaker": "higher_seed"
    }
}


def read_csv(path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def is_true(value):
    return str(value).strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
    )


def record_text(wins, losses, ties):
    if ties:
        return "{}-{}-{}".format(
            wins,
            losses,
            ties,
        )

    return "{}-{}".format(
        wins,
        losses,
    )


def load_postseason_config(season):
    path = (
        CONFIG_ROOT
        / str(season)
        / "postseason.json"
    )

    if not path.exists():
        return DEFAULT_POSTSEASON_CONFIG

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def build_regular_season_standings(
    team_rows,
    end_week,
):
    """
    Rebuild final regular-season standings using the same convention
    LeagueLab currently uses elsewhere:

      1. Actual win percentage
      2. Points for
      3. Team name

    This keeps the postseason engine independent of previously
    generated analytics output.
    """

    teams = {}

    for row in team_rows:
        week = to_int(
            row.get("week")
        )

        if week < 1 or week > end_week:
            continue

        team_key = row["team_key"]

        if team_key not in teams:
            teams[team_key] = {
                "team_key": team_key,
                "team_id": row.get(
                    "team_id",
                    "",
                ),
                "team_name": row["team_name"],
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "points_for": 0.0,
            }

        team = teams[team_key]

        team["points_for"] += to_float(
            row.get("points")
        )

        result = str(
            row.get("result")
            or ""
        ).strip().upper()

        if result == "W":
            team["wins"] += 1
        elif result == "L":
            team["losses"] += 1
        elif result == "T":
            team["ties"] += 1

    rows = []

    for team in teams.values():
        games = (
            team["wins"]
            + team["losses"]
            + team["ties"]
        )

        win_pct = (
            (
                team["wins"]
                + 0.5 * team["ties"]
            )
            / games
            if games
            else 0.0
        )

        row = dict(team)
        row["win_pct"] = win_pct
        row["points_for"] = round(
            row["points_for"],
            2,
        )
        rows.append(row)

    rows = sorted(
        rows,
        key=lambda row: (
            -row["win_pct"],
            -row["points_for"],
            row["team_name"].lower(),
        ),
    )

    for rank, row in enumerate(
        rows,
        start=1,
    ):
        row["seed"] = rank
        row["record"] = record_text(
            row["wins"],
            row["losses"],
            row["ties"],
        )

    return rows


def build_virtual_team_scores(
    player_rows,
    weeks,
    eligible_team_keys=None,
):
    """
    Reconstruct team scores from Yahoo's historical player rows.

    Yahoo can omit official team matchup scores for teams outside the
    championship bracket, while still preserving each player's
    historical selected lineup position and weekly points.

    LeagueLab therefore sums normalized starter rows for those teams.
    """

    requested_weeks = set(
        int(week)
        for week in weeks
    )

    eligible = (
        set(eligible_team_keys)
        if eligible_team_keys
        else None
    )

    totals = defaultdict(float)
    starter_counts = defaultdict(int)
    team_names = {}

    for row in player_rows:
        week = to_int(
            row.get("week")
        )

        if week not in requested_weeks:
            continue

        team_key = row["team_key"]

        if (
            eligible is not None
            and team_key not in eligible
        ):
            continue

        if not is_true(
            row.get("is_starter")
        ):
            continue

        key = (
            week,
            team_key,
        )

        totals[key] += to_float(
            row.get("points")
        )

        starter_counts[key] += 1
        team_names[team_key] = (
            row["team_name"]
        )

    output = {}

    for key, score in totals.items():
        week, team_key = key

        output[key] = {
            "week": week,
            "team_key": team_key,
            "team_name": team_names.get(
                team_key,
                "",
            ),
            "score": round(
                score,
                2,
            ),
            "starter_count": (
                starter_counts[key]
            ),
            "score_source": (
                "reconstructed_starters"
            ),
        }

    return output


def resolve_matchup(
    week,
    team_a,
    team_b,
    virtual_scores,
    tie_breaker="higher_seed",
):
    """
    Resolve one custom postseason matchup.

    If scores tie and tie_breaker is higher_seed, the better regular-
    season seed advances.
    """

    score_a_row = virtual_scores.get(
        (
            week,
            team_a["team_key"],
        )
    )

    score_b_row = virtual_scores.get(
        (
            week,
            team_b["team_key"],
        )
    )

    if score_a_row is None:
        raise RuntimeError(
            "Missing reconstructed Week {} score for {}.".format(
                week,
                team_a["team_name"],
            )
        )

    if score_b_row is None:
        raise RuntimeError(
            "Missing reconstructed Week {} score for {}.".format(
                week,
                team_b["team_name"],
            )
        )

    score_a = score_a_row["score"]
    score_b = score_b_row["score"]

    if score_a > score_b:
        winner = team_a
        loser = team_b
    elif score_b > score_a:
        winner = team_b
        loser = team_a
    else:
        if tie_breaker != "higher_seed":
            raise RuntimeError(
                "Unsupported Toilet Bowl tie breaker: {}".format(
                    tie_breaker
                )
            )

        if team_a["seed"] < team_b["seed"]:
            winner = team_a
            loser = team_b
        else:
            winner = team_b
            loser = team_a

    return {
        "week": week,
        "team_a_seed": team_a["seed"],
        "team_a_key": team_a["team_key"],
        "team_a_name": team_a["team_name"],
        "team_a_score": score_a,
        "team_b_seed": team_b["seed"],
        "team_b_key": team_b["team_key"],
        "team_b_name": team_b["team_name"],
        "team_b_score": score_b,
        "winner_seed": winner["seed"],
        "winner_key": winner["team_key"],
        "winner_name": winner["team_name"],
        "loser_seed": loser["seed"],
        "loser_key": loser["team_key"],
        "loser_name": loser["team_name"],
        "margin": round(
            abs(score_a - score_b),
            2,
        ),
        "tie_breaker_used": (
            score_a == score_b
        ),
        "score_source": (
            "reconstructed_starters"
        ),
    }


def run_toilet_bowl(
    season,
    team_rows,
    player_rows,
    config,
):
    toilet = config.get(
        "toilet_bowl",
        {}
    )

    if not toilet.get(
        "enabled",
        True,
    ):
        return None

    regular_season_end_week = to_int(
        toilet.get(
            "regular_season_end_week",
            14,
        )
    )

    semifinal_week = to_int(
        toilet.get(
            "semifinal_week",
            regular_season_end_week + 1,
        )
    )

    championship_week = to_int(
        toilet.get(
            "championship_week",
            semifinal_week + 1,
        )
    )

    requested_seeds = [
        to_int(seed)
        for seed in toilet.get(
            "seeds",
            [9, 10, 11, 12],
        )
    ]

    standings = (
        build_regular_season_standings(
            team_rows,
            regular_season_end_week,
        )
    )

    by_seed = {
        row["seed"]: row
        for row in standings
    }

    missing_seeds = [
        seed
        for seed in requested_seeds
        if seed not in by_seed
    ]

    if missing_seeds:
        raise RuntimeError(
            "Missing postseason seed(s): {}".format(
                ", ".join(
                    str(seed)
                    for seed in missing_seeds
                )
            )
        )

    participants = [
        by_seed[seed]
        for seed in requested_seeds
    ]

    participant_keys = [
        row["team_key"]
        for row in participants
    ]

    virtual_scores = (
        build_virtual_team_scores(
            player_rows,
            [
                semifinal_week,
                championship_week,
            ],
            eligible_team_keys=participant_keys,
        )
    )

    semifinal_pairs = toilet.get(
        "semifinals",
        [
            [9, 12],
            [10, 11],
        ],
    )

    if len(semifinal_pairs) != 2:
        raise RuntimeError(
            "Toilet Bowl currently requires exactly two semifinal matchups."
        )

    tie_breaker = toilet.get(
        "tie_breaker",
        "higher_seed",
    )

    semifinal_results = []

    for pair in semifinal_pairs:
        seed_a = to_int(pair[0])
        seed_b = to_int(pair[1])

        if (
            seed_a not in by_seed
            or seed_b not in by_seed
        ):
            raise RuntimeError(
                "Invalid Toilet Bowl semifinal seeds: {} vs {}".format(
                    seed_a,
                    seed_b,
                )
            )

        semifinal_results.append(
            resolve_matchup(
                semifinal_week,
                by_seed[seed_a],
                by_seed[seed_b],
                virtual_scores,
                tie_breaker=tie_breaker,
            )
        )

    finalists = [
        by_seed[
            semifinal_results[0][
                "winner_seed"
            ]
        ],
        by_seed[
            semifinal_results[1][
                "winner_seed"
            ]
        ],
    ]

    championship = resolve_matchup(
        championship_week,
        finalists[0],
        finalists[1],
        virtual_scores,
        tie_breaker=tie_breaker,
    )

    champion = by_seed[
        championship["winner_seed"]
    ]

    return {
        "season": int(season),
        "name": toilet.get(
            "name",
            "Toilet Bowl",
        ),
        "regular_season_end_week": (
            regular_season_end_week
        ),
        "semifinal_week": semifinal_week,
        "championship_week": championship_week,
        "payout": to_float(
            toilet.get(
                "payout",
                40,
            )
        ),
        "tie_breaker": tie_breaker,
        "participants": participants,
        "semifinals": semifinal_results,
        "championship": championship,
        "champion": {
            "seed": champion["seed"],
            "team_key": champion["team_key"],
            "team_id": champion[
                "team_id"
            ],
            "team_name": champion[
                "team_name"
            ],
            "payout": to_float(
                toilet.get(
                    "payout",
                    40,
                )
            ),
        },
        "regular_season_standings": standings,
    }


def save_json(path, payload):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
        )


def save_csv(path, rows, fieldnames):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def build_bracket_csv_rows(result):
    rows = []

    for index, matchup in enumerate(
        result["semifinals"],
        start=1,
    ):
        row = dict(matchup)
        row["round"] = "Semifinal {}".format(
            index
        )
        rows.append(row)

    row = dict(
        result["championship"]
    )
    row["round"] = "Championship"
    rows.append(row)

    return rows


def run_postseason(season):
    normalized_dir = (
        NORMALIZED_ROOT
        / str(season)
    )

    team_path = (
        normalized_dir
        / "weekly_team_results.csv"
    )

    player_path = (
        normalized_dir
        / "weekly_players.csv"
    )

    if not team_path.exists():
        raise RuntimeError(
            "Missing normalized team results:\n{}".format(
                team_path
            )
        )

    if not player_path.exists():
        raise RuntimeError(
            "Missing normalized player results:\n{}".format(
                player_path
            )
        )

    team_rows = read_csv(
        team_path
    )
    player_rows = read_csv(
        player_path
    )

    config = load_postseason_config(
        season
    )

    toilet_bowl = run_toilet_bowl(
        season,
        team_rows,
        player_rows,
        config,
    )

    output_dir = (
        OUTPUT_ROOT
        / str(season)
        / "postseason"
    )

    json_path = (
        output_dir
        / "toilet_bowl.json"
    )

    bracket_path = (
        output_dir
        / "toilet_bowl_bracket.csv"
    )

    if toilet_bowl is not None:
        save_json(
            json_path,
            toilet_bowl,
        )

        bracket_rows = (
            build_bracket_csv_rows(
                toilet_bowl
            )
        )

        save_csv(
            bracket_path,
            bracket_rows,
            [
                "round",
                "week",
                "team_a_seed",
                "team_a_key",
                "team_a_name",
                "team_a_score",
                "team_b_seed",
                "team_b_key",
                "team_b_name",
                "team_b_score",
                "winner_seed",
                "winner_key",
                "winner_name",
                "loser_seed",
                "loser_key",
                "loser_name",
                "margin",
                "tie_breaker_used",
                "score_source",
            ],
        )

    return {
        "toilet_bowl": toilet_bowl,
        "toilet_bowl_json_path": (
            json_path
        ),
        "toilet_bowl_bracket_path": (
            bracket_path
        ),
    }
