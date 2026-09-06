import argparse
import csv
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DATA_ROOT = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "yahoo"
)

NORMALIZED_DATA_ROOT = (
    PROJECT_ROOT
    / "data"
    / "normalized"
)


def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def numeric_items(obj):
    """
    Return values from Yahoo collections whose keys are numeric.
    """

    if not isinstance(obj, dict):
        return []

    items = []

    for key, value in obj.items():
        if str(key).isdigit():
            items.append(value)

    return items


def recursive_find_first(obj, key):
    """
    Recursively find the first value for a key.
    """

    if isinstance(obj, dict):
        if key in obj:
            return obj[key]

        for value in obj.values():
            found = recursive_find_first(
                value,
                key,
            )

            if found is not None:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = recursive_find_first(
                item,
                key,
            )

            if found is not None:
                return found

    return None


def recursive_find_all(obj, key):
    """
    Recursively collect all values for a key.
    """

    results = []

    if isinstance(obj, dict):
        for current_key, value in obj.items():
            if current_key == key:
                results.append(value)

            results.extend(
                recursive_find_all(
                    value,
                    key,
                )
            )

    elif isinstance(obj, list):
        for item in obj:
            results.extend(
                recursive_find_all(
                    item,
                    key,
                )
            )

    return results


def find_league_directory(season):
    """
    Find the single captured league directory for a season.

    For now we expect one league per season.
    """

    season_dir = (
        RAW_DATA_ROOT
        / str(season)
    )

    if not season_dir.exists():
        raise RuntimeError(
            f"No raw data directory found for season {season}:\n"
            f"{season_dir}"
        )

    league_dirs = [
        path
        for path in season_dir.iterdir()
        if path.is_dir()
    ]

    if not league_dirs:
        raise RuntimeError(
            f"No league directory found under:\n"
            f"{season_dir}"
        )

    if len(league_dirs) > 1:
        raise RuntimeError(
            f"Multiple league directories found for {season}.\n"
            f"Specify league support will be added later.\n"
            f"Found: {[p.name for p in league_dirs]}"
        )

    return league_dirs[0]


def parse_team_metadata(teams_data):
    """
    Build team metadata keyed by Yahoo team_key.

    Yahoo represents a team as a collection of small
    dictionaries inside nested lists rather than one flat dict.
    """

    team_map = {}

    def parse_team(team_value):
        """
        Flatten one Yahoo team object enough to retrieve
        team_key, team_id, and team name.
        """

        team_key = recursive_find_first(
            team_value,
            "team_key",
        )

        team_id = recursive_find_first(
            team_value,
            "team_id",
        )

        team_name = recursive_find_first(
            team_value,
            "name",
        )

        if isinstance(team_name, dict):
            team_name = (
                team_name.get("full")
                or team_name.get("name")
            )

        if not team_key:
            return

        if not team_id:
            team_id = (
                str(team_key)
                .split(".")[-1]
            )

        if not team_name:
            team_name = (
                f"Team {team_id}"
            )

        team_map[
            str(team_key)
        ] = {
            "team_key": str(team_key),
            "team_id": str(team_id),
            "team_name": str(team_name),
        }

    def walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "team":
                    parse_team(
                        value
                    )
                else:
                    walk(
                        value
                    )

        elif isinstance(obj, list):
            for item in obj:
                walk(
                    item
                )

    walk(
        teams_data
    )

    if not team_map:
        raise RuntimeError(
            "Could not extract team metadata "
            "from teams.json"
        )

    return team_map


def extract_team_points(stats_data):
    """
    Extract team weekly points and projected points.
    """

    points = None
    projected = None

    team_points_blocks = recursive_find_all(
        stats_data,
        "team_points",
    )

    if team_points_blocks:
        block = team_points_blocks[0]

        if isinstance(block, dict):
            points = block.get("total")

    projected_blocks = recursive_find_all(
        stats_data,
        "team_projected_points",
    )

    if projected_blocks:
        block = projected_blocks[0]

        if isinstance(block, dict):
            projected = block.get("total")

    return points, projected


def to_float(value):
    if value in (
        None,
        "",
    ):
        return None

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def flatten_yahoo_player(player_wrapper):
    """
    Yahoo player objects are commonly structured as:

    {
        "player": [
            [metadata fields...],
            {
                "selected_position": ...
            },
            {
                "player_stats": ...
            },
            {
                "player_points": ...
            }
        ]
    }

    Flatten all dictionary content into a more usable structure.
    """

    if not isinstance(
        player_wrapper,
        dict,
    ):
        return None

    player = player_wrapper.get(
        "player"
    )

    if not isinstance(
        player,
        list,
    ):
        return None

    flattened = {}

    for part in player:
        if isinstance(part, dict):
            flattened.update(part)

        elif isinstance(part, list):
            for item in part:
                if isinstance(
                    item,
                    dict,
                ):
                    flattened.update(item)

    return flattened


def extract_selected_position(value):
    """
    Normalize Yahoo selected_position into:
    position, is_flex
    """

    if value is None:
        return None, False

    if isinstance(value, dict):
        position = value.get(
            "position"
        )

        is_flex = value.get(
            "is_flex",
            False,
        )

        return (
            position,
            bool(is_flex),
        )

    if isinstance(value, list):
        position = None
        is_flex = False

        for item in value:
            if not isinstance(
                item,
                dict,
            ):
                continue

            if "position" in item:
                position = item[
                    "position"
                ]

            if "is_flex" in item:
                is_flex = bool(
                    item["is_flex"]
                )

        return position, is_flex

    return None, False


def extract_eligible_positions(value):
    """
    Return eligible positions as a pipe-delimited string.
    """

    positions = []

    if isinstance(value, dict):
        possible = value.get(
            "position"
        )

        if isinstance(possible, list):
            positions.extend(
                str(item)
                for item in possible
            )

        elif possible:
            positions.append(
                str(possible)
            )

    elif isinstance(value, list):
        for item in value:
            if isinstance(
                item,
                str,
            ):
                positions.append(
                    item
                )

            elif isinstance(
                item,
                dict,
            ):
                position = item.get(
                    "position"
                )

                if position:
                    positions.append(
                        str(position)
                    )

    unique = list(
        dict.fromkeys(
            positions
        )
    )

    return "|".join(unique)


def extract_player_points(value):
    if isinstance(value, dict):
        return to_float(
            value.get("total")
        )

    if isinstance(value, list):
        for item in value:
            if (
                isinstance(item, dict)
                and "total" in item
            ):
                return to_float(
                    item.get("total")
                )

    return None


def assign_lineup_slots(rows):
    """
    Assign an ordered LeagueLab lineup slot within a team/week.

    Yahoo selected_position tells us the slot type (RB, WR, W/R/T, BN, etc.)
    but repeated slots need an ordinal so challenges can distinguish RB1/RB2,
    WR1/WR2, FLEX1/FLEX2, and bench order.

    The ordinal follows Yahoo's roster order in the captured player response.
    """

    counts = {}

    slot_prefix = {
        "QB": "QB",
        "RB": "RB",
        "WR": "WR",
        "TE": "TE",
        "W/R/T": "FLEX",
        "DEF": "DEF",
        "K": "K",
        "BN": "BN",
        "IR": "IR",
        "IL": "IL",
        "NA": "NA",
    }

    for row in rows:
        selected_position = row.get(
            "selected_position"
        )

        prefix = slot_prefix.get(
            selected_position,
            selected_position,
        )

        if not prefix:
            row["lineup_slot"] = None
            continue

        counts[prefix] = (
            counts.get(prefix, 0)
            + 1
        )

        row["lineup_slot"] = (
            "{}{}".format(
                prefix,
                counts[prefix],
            )
        )

    return rows


def parse_week_players(
    data,
    season,
    week,
    team_key,
    team_meta,
):
    """
    Convert one weekly Yahoo player file into
    clean LeagueLab player rows.
    """

    rows = []

    player_wrappers = recursive_find_all(
        data,
        "player",
    )

    for raw_player in player_wrappers:
        wrapper = {
            "player": raw_player
        }

        player = flatten_yahoo_player(
            wrapper
        )

        if not player:
            continue

        player_key = player.get(
            "player_key"
        )

        player_id = player.get(
            "player_id"
        )

        name = player.get(
            "name"
        )

        if isinstance(name, dict):
            player_name = name.get(
                "full"
            )
        else:
            player_name = None

        nfl_team = player.get(
            "editorial_team_abbr"
        )

        display_position = player.get(
            "display_position"
        )

        selected_position, is_flex = (
            extract_selected_position(
                player.get(
                    "selected_position"
                )
            )
        )

        eligible_positions = (
            extract_eligible_positions(
                player.get(
                    "eligible_positions"
                )
            )
        )

        points = extract_player_points(
            player.get(
                "player_points"
            )
        )

        is_starter = (
            selected_position
            not in (
                None,
                "",
                "BN",
                "IR",
                "IL",
                "NA",
            )
        )

        rows.append(
            {
                "season": season,
                "week": week,
                "team_key": team_key,
                "team_id": team_meta[
                    "team_id"
                ],
                "team_name": team_meta[
                    "team_name"
                ],
                "player_key": player_key,
                "player_id": player_id,
                "player_name": player_name,
                "nfl_team": nfl_team,
                "display_position": (
                    display_position
                ),
                "selected_position": (
                    selected_position
                ),
                "lineup_slot": None,
                "is_starter": is_starter,
                "is_flex": is_flex,
                "eligible_positions": (
                    eligible_positions
                ),
                "points": points,
            }
        )

    return assign_lineup_slots(
        rows
    )


def extract_scoreboard_team_records(
    scoreboard_data,
):
    """
    Extract all team score entries from a Yahoo
    weekly scoreboard.

    Returns:
        {
            team_key: {
                "team_key": ...,
                "team_name": ...,
                "points": ...
            }
        }
    """

    records = {}

    def walk(obj):
        if isinstance(obj, dict):
            team_key = obj.get(
                "team_key"
            )

            if team_key:
                team_name = obj.get(
                    "name"
                )

                team_points = obj.get(
                    "team_points"
                )

                points = None

                if isinstance(
                    team_points,
                    dict,
                ):
                    points = to_float(
                        team_points.get(
                            "total"
                        )
                    )

                if team_key not in records:
                    records[
                        team_key
                    ] = {
                        "team_key": (
                            team_key
                        ),
                        "team_name": (
                            team_name
                            if isinstance(
                                team_name,
                                str,
                            )
                            else None
                        ),
                        "points": (
                            points
                        ),
                    }

            for value in obj.values():
                walk(value)

        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(scoreboard_data)

    return records


def extract_matchups(scoreboard_data):
    """
    Extract matchup pairings from a Yahoo scoreboard.

    Returns list of:
        (team_key_1, team_key_2)
    """

    matchups = []

    def walk(obj):
        if isinstance(obj, dict):
            if "matchup" in obj:
                matchup = obj[
                    "matchup"
                ]

                team_keys = (
                    recursive_find_all(
                        matchup,
                        "team_key",
                    )
                )

                unique = list(
                    dict.fromkeys(
                        team_keys
                    )
                )

                if len(unique) >= 2:
                    pair = (
                        unique[0],
                        unique[1],
                    )

                    if pair not in matchups:
                        matchups.append(
                            pair
                        )

            for value in obj.values():
                walk(value)

        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(scoreboard_data)

    cleaned = []
    seen = set()

    for team_a, team_b in matchups:
        key = tuple(
            sorted(
                (
                    team_a,
                    team_b,
                )
            )
        )

        if key in seen:
            continue

        seen.add(key)
        cleaned.append(
            (
                team_a,
                team_b,
            )
        )

    return cleaned


def build_weekly_team_results(
    season,
    league_dir,
    team_map,
):
    rows = []

    weeks_dir = (
        league_dir
        / "weeks"
    )

    for week in range(
        1,
        18,
    ):
        week_dir = (
            weeks_dir
            / f"week_{week:02d}"
        )

        scoreboard_data = load_json(
            week_dir
            / "scoreboard.json"
        )

        scoreboard_teams = (
            extract_scoreboard_team_records(
                scoreboard_data
            )
        )

        matchups = extract_matchups(
            scoreboard_data
        )

        opponent_map = {}

        for team_a, team_b in matchups:
            opponent_map[
                team_a
            ] = team_b

            opponent_map[
                team_b
            ] = team_a

        for (
            team_key,
            team_meta,
        ) in team_map.items():

            team_id = team_meta[
                "team_id"
            ]

            stats_path = (
                week_dir
                / (
                    f"team_{team_id}"
                    f"_stats.json"
                )
            )

            stats_data = load_json(
                stats_path
            )

            points, projected = (
                extract_team_points(
                    stats_data
                )
            )

            points = to_float(
                points
            )

            projected = to_float(
                projected
            )

            if points is None:
                scoreboard_record = (
                    scoreboard_teams.get(
                        team_key,
                        {},
                    )
                )

                points = (
                    scoreboard_record.get(
                        "points"
                    )
                )

            opponent_key = (
                opponent_map.get(
                    team_key
                )
            )

            opponent_name = None
            opponent_points = None

            if opponent_key:
                opponent_meta = (
                    team_map.get(
                        opponent_key
                    )
                )

                if opponent_meta:
                    opponent_name = (
                        opponent_meta[
                            "team_name"
                        ]
                    )

                opponent_record = (
                    scoreboard_teams.get(
                        opponent_key,
                        {},
                    )
                )

                opponent_points = (
                    opponent_record.get(
                        "points"
                    )
                )

            result = None

            if (
                points is not None
                and opponent_points
                is not None
            ):
                if points > opponent_points:
                    result = "W"

                elif points < opponent_points:
                    result = "L"

                else:
                    result = "T"

            rows.append(
                {
                    "season": season,
                    "week": week,
                    "team_key": team_key,
                    "team_id": team_id,
                    "team_name": (
                        team_meta[
                            "team_name"
                        ]
                    ),
                    "points": points,
                    "projected_points": (
                        projected
                    ),
                    "opponent_team_key": (
                        opponent_key
                    ),
                    "opponent_team_name": (
                        opponent_name
                    ),
                    "opponent_points": (
                        opponent_points
                    ),
                    "result": result,
                }
            )


    # Complete matchup fields from reciprocal normalized team rows.
    # This is intentionally done during normalization so downstream analytics
    # can trust opponent_points and result.
    rows_by_week = {}

    for normalized_row in rows:
        week = int(normalized_row["week"])

        if week not in rows_by_week:
            rows_by_week[week] = []

        rows_by_week[week].append(
            normalized_row
        )

    for week_rows in rows_by_week.values():
        by_team_key = {
            str(item["team_key"]): item
            for item in week_rows
        }

        by_team_name = {
            str(item["team_name"]): item
            for item in week_rows
        }

        for normalized_row in week_rows:
            opponent = None

            opponent_key = str(
                normalized_row.get(
                    "opponent_team_key"
                )
                or ""
            ).strip()

            opponent_name = str(
                normalized_row.get(
                    "opponent_team_name"
                )
                or ""
            ).strip()

            if opponent_key:
                opponent = by_team_key.get(
                    opponent_key
                )

            if (
                opponent is None
                and opponent_name
            ):
                opponent = by_team_name.get(
                    opponent_name
                )

            if opponent is None:
                # Expected for teams without an active postseason matchup.
                normalized_row[
                    "opponent_points"
                ] = None
                normalized_row[
                    "result"
                ] = None
                continue

            opponent_points = to_float(
                opponent.get("points")
            )

            team_points = to_float(
                normalized_row.get(
                    "points"
                )
            )

            normalized_row[
                "opponent_points"
            ] = opponent_points

            if team_points > opponent_points:
                normalized_row["result"] = "W"
            elif team_points < opponent_points:
                normalized_row["result"] = "L"
            else:
                normalized_row["result"] = "T"
    return rows


def build_weekly_players(
    season,
    league_dir,
    team_map,
):
    rows = []

    weeks_dir = (
        league_dir
        / "weeks"
    )

    for week in range(
        1,
        18,
    ):
        week_dir = (
            weeks_dir
            / f"week_{week:02d}"
        )

        for (
            team_key,
            team_meta,
        ) in team_map.items():

            team_id = (
                team_meta[
                    "team_id"
                ]
            )

            path = (
                week_dir
                / (
                    f"team_{team_id}"
                    f"_players.json"
                )
            )

            data = load_json(
                path
            )

            player_rows = (
                parse_week_players(
                    data=data,
                    season=season,
                    week=week,
                    team_key=team_key,
                    team_meta=team_meta,
                )
            )

            rows.extend(
                player_rows
            )

    return rows


def write_csv(
    rows,
    path,
    fieldnames,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(
            rows
        )


def normalize(season):
    print()
    print("=" * 70)
    print(
        f"LeagueLab Normalizer - {season}"
    )
    print("=" * 70)

    league_dir = (
        find_league_directory(
            season
        )
    )

    league_key = (
        league_dir.name
    )

    print()
    print(
        f"League: {league_key}"
    )

    print(
        f"Source: {league_dir}"
    )

    output_dir = (
        NORMALIZED_DATA_ROOT
        / str(season)
    )

    print()
    print("Loading teams...")

    teams_data = load_json(
        league_dir
        / "teams.json"
    )

    team_map = (
        parse_team_metadata(
            teams_data
        )
    )

    print(
        f"Found {len(team_map)} teams."
    )

    for team in sorted(
        team_map.values(),
        key=lambda item: int(
            item["team_id"]
        ),
    ):
        print(
            f"  Team {team['team_id']}: "
            f"{team['team_name']}"
        )

    print()
    print(
        "Normalizing weekly team results..."
    )

    team_rows = (
        build_weekly_team_results(
            season=season,
            league_dir=league_dir,
            team_map=team_map,
        )
    )

    team_output = (
        output_dir
        / "weekly_team_results.csv"
    )

    write_csv(
        rows=team_rows,
        path=team_output,
        fieldnames=[
            "season",
            "week",
            "team_key",
            "team_id",
            "team_name",
            "points",
            "projected_points",
            "opponent_team_key",
            "opponent_team_name",
            "opponent_points",
            "result",
        ],
    )

    print(
        f"  Rows: {len(team_rows)}"
    )

    print(
        f"  Saved: {team_output}"
    )

    print()
    print(
        "Normalizing weekly players..."
    )

    player_rows = (
        build_weekly_players(
            season=season,
            league_dir=league_dir,
            team_map=team_map,
        )
    )

    player_output = (
        output_dir
        / "weekly_players.csv"
    )

    write_csv(
        rows=player_rows,
        path=player_output,
        fieldnames=[
            "season",
            "week",
            "team_key",
            "team_id",
            "team_name",
            "player_key",
            "player_id",
            "player_name",
            "nfl_team",
            "display_position",
            "selected_position",
            "lineup_slot",
            "is_starter",
            "is_flex",
            "eligible_positions",
            "points",
        ],
    )

    print(
        f"  Rows: {len(player_rows)}"
    )

    print(
        f"  Saved: {player_output}"
    )

    print()
    print("-" * 70)
    print("Quick checks")
    print("-" * 70)

    expected_team_rows = (
        17
        * len(team_map)
    )

    print(
        f"Expected team-week rows: "
        f"{expected_team_rows}"
    )

    print(
        f"Actual team-week rows:   "
        f"{len(team_rows)}"
    )

    players_with_points = sum(
        1
        for row in player_rows
        if row["points"] is not None
    )

    starters = sum(
        1
        for row in player_rows
        if row["is_starter"]
    )

    bench = sum(
        1
        for row in player_rows
        if row[
            "selected_position"
        ] == "BN"
    )

    print(
        f"Player-week rows:        "
        f"{len(player_rows)}"
    )

    print(
        f"Players with points:     "
        f"{players_with_points}"
    )

    print(
        f"Starter rows:            "
        f"{starters}"
    )

    print(
        f"Bench rows:              "
        f"{bench}"
    )

    missing_team_scores = [
        row
        for row in team_rows
        if row["points"] is None
    ]

    missing_opponents = [
        row
        for row in team_rows
        if row[
            "opponent_team_key"
        ] is None
    ]

    missing_player_names = [
        row
        for row in player_rows
        if not row[
            "player_name"
        ]
    ]

    print(
        f"Missing team scores:     "
        f"{len(missing_team_scores)}"
    )

    print(
        f"Rows without matchup:       "
        f"{len(missing_opponents)}"
    )

    print(
        f"Missing player names:    "
        f"{len(missing_player_names)}"
    )

    print()
    print("=" * 70)

    if (
        len(team_rows)
        == expected_team_rows
        and not missing_team_scores
        and not missing_player_names
    ):
        print(
            "NORMALIZATION RESULT: PASS"
        )
    else:
        print(
            "NORMALIZATION RESULT: CHECK"
        )

    print("=" * 70)
    print()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Normalize LeagueLab Yahoo "
            "fantasy data."
        )
    )

    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Fantasy football season.",
    )

    args = parser.parse_args()

    normalize(
        season=args.season
    )


if __name__ == "__main__":
    main()
