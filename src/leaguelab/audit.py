import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_ROOT = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "yahoo"
)

SEASON = 2025
LEAGUE_KEY = "461.l.85972"

LEAGUE_DIR = (
    DATA_ROOT
    / str(SEASON)
    / LEAGUE_KEY
)


def load_json(path):
    """
    Load JSON and return None if the file
    does not exist or cannot be parsed.
    """

    if not path.exists():
        return None

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception as exc:
        print(
            f"ERROR reading {path}: {exc}"
        )
        return None


def numeric_children(obj):
    """
    Return dictionary values whose keys
    are numeric Yahoo collection indexes.
    """

    if not isinstance(obj, dict):
        return []

    result = []

    for key, value in obj.items():
        if str(key).isdigit():
            result.append(value)

    return result


def recursive_find(obj, key):
    """
    Recursively collect all values for
    a given dictionary key.
    """

    results = []

    if isinstance(obj, dict):
        for current_key, value in obj.items():
            if current_key == key:
                results.append(value)

            results.extend(
                recursive_find(
                    value,
                    key,
                )
            )

    elif isinstance(obj, list):
        for item in obj:
            results.extend(
                recursive_find(
                    item,
                    key,
                )
            )

    return results


def count_transactions(data):
    """
    Return Yahoo's reported transaction count
    and actual transaction object count.
    """

    if data is None:
        return 0, 0

    try:
        transactions = (
            data["fantasy_content"]
            ["league"][1]
            ["transactions"]
        )

        reported = int(
            transactions.get(
                "count",
                0,
            )
        )

        actual = len(
            numeric_children(
                transactions
            )
        )

        return reported, actual

    except Exception:
        return 0, 0


def audit():
    print()
    print("=" * 70)
    print("LeagueLab 2025 Data Audit")
    print("=" * 70)

    print()
    print(f"Season:     {SEASON}")
    print(f"League:     {LEAGUE_KEY}")
    print(f"Data path:  {LEAGUE_DIR}")

    if not LEAGUE_DIR.exists():
        print()
        print("ERROR: League directory does not exist.")
        return

    # ---------------------------------------------------------
    # League-level files
    # ---------------------------------------------------------

    print()
    print("-" * 70)
    print("League-level files")
    print("-" * 70)

    required_files = [
        "profile.json",
        "leagues.json",
        "settings.json",
        "teams.json",
        "standings.json",
        "rosters.json",
        "draft_results.json",
        "transactions.json",
    ]

    league_errors = []

    for filename in required_files:
        path = LEAGUE_DIR / filename
        data = load_json(path)

        if data is None:
            status = "MISSING / INVALID"
            league_errors.append(
                filename
            )
        else:
            status = "OK"

        print(
            f"{filename:<24} {status}"
        )

    # ---------------------------------------------------------
    # Transactions
    # ---------------------------------------------------------

    print()
    print("-" * 70)
    print("Transactions")
    print("-" * 70)

    transaction_data = load_json(
        LEAGUE_DIR
        / "transactions.json"
    )

    reported_count, actual_count = (
        count_transactions(
            transaction_data
        )
    )

    print(
        f"Yahoo reported count:       "
        f"{reported_count}"
    )

    print(
        f"Transaction objects found:  "
        f"{actual_count}"
    )

    if (
        reported_count
        and reported_count == actual_count
    ):
        print(
            "Transaction collection:     OK"
        )
    else:
        print(
            "Transaction collection:     CHECK"
        )

    # ---------------------------------------------------------
    # Weekly files
    # ---------------------------------------------------------

    print()
    print("-" * 70)
    print("Weekly files")
    print("-" * 70)

    weeks_dir = (
        LEAGUE_DIR
        / "weeks"
    )

    expected_weeks = 17
    expected_teams = 12

    missing_scoreboards = []
    missing_rosters = []
    missing_stats = []
    missing_players = []

    valid_player_files = 0
    valid_roster_files = 0
    valid_stats_files = 0

    weekly_summary = []

    for week in range(
        1,
        expected_weeks + 1,
    ):
        week_dir = (
            weeks_dir
            / f"week_{week:02d}"
        )

        scoreboard_path = (
            week_dir
            / "scoreboard.json"
        )

        scoreboard_ok = (
            load_json(
                scoreboard_path
            )
            is not None
        )

        if not scoreboard_ok:
            missing_scoreboards.append(
                week
            )

        roster_count = 0
        stats_count = 0
        player_count = 0

        for team_id in range(
            1,
            expected_teams + 1,
        ):
            roster_path = (
                week_dir
                / (
                    f"team_{team_id}"
                    f"_roster.json"
                )
            )

            stats_path = (
                week_dir
                / (
                    f"team_{team_id}"
                    f"_stats.json"
                )
            )

            players_path = (
                week_dir
                / (
                    f"team_{team_id}"
                    f"_players.json"
                )
            )

            if load_json(
                roster_path
            ) is not None:
                roster_count += 1
                valid_roster_files += 1

            else:
                missing_rosters.append(
                    (
                        week,
                        team_id,
                    )
                )

            if load_json(
                stats_path
            ) is not None:
                stats_count += 1
                valid_stats_files += 1

            else:
                missing_stats.append(
                    (
                        week,
                        team_id,
                    )
                )

            if load_json(
                players_path
            ) is not None:
                player_count += 1
                valid_player_files += 1

            else:
                missing_players.append(
                    (
                        week,
                        team_id,
                    )
                )

        weekly_summary.append(
            (
                week,
                scoreboard_ok,
                roster_count,
                stats_count,
                player_count,
            )
        )

    print(
        f"{'Week':<8}"
        f"{'Scoreboard':<14}"
        f"{'Rosters':<12}"
        f"{'Stats':<12}"
        f"{'Players':<12}"
    )

    print("-" * 58)

    for (
        week,
        scoreboard_ok,
        roster_count,
        stats_count,
        player_count,
    ) in weekly_summary:

        print(
            f"{week:<8}"
            f"{'OK' if scoreboard_ok else 'MISSING':<14}"
            f"{roster_count:<12}"
            f"{stats_count:<12}"
            f"{player_count:<12}"
        )

    # ---------------------------------------------------------
    # Player data inspection
    # ---------------------------------------------------------

    print()
    print("-" * 70)
    print("Player data inspection")
    print("-" * 70)

    sample_player_file = (
        weeks_dir
        / "week_01"
        / "team_1_players.json"
    )

    sample_data = load_json(
        sample_player_file
    )

    if sample_data is None:
        print(
            "Could not load Week 1 "
            "Team 1 player file."
        )

    else:
        player_keys = recursive_find(
            sample_data,
            "player_key",
        )

        player_names = recursive_find(
            sample_data,
            "full",
        )

        selected_positions = (
            recursive_find(
                sample_data,
                "selected_position",
            )
        )

        eligible_positions = (
            recursive_find(
                sample_data,
                "eligible_positions",
            )
        )

        player_points = recursive_find(
            sample_data,
            "player_points",
        )

        print(
            f"Player keys found:          "
            f"{len(player_keys)}"
        )

        print(
            f"Names found:                "
            f"{len(player_names)}"
        )

        print(
            f"Selected positions found:   "
            f"{len(selected_positions)}"
        )

        print(
            f"Eligible position blocks:   "
            f"{len(eligible_positions)}"
        )

        print(
            f"Player point blocks:        "
            f"{len(player_points)}"
        )

    # ---------------------------------------------------------
    # Totals
    # ---------------------------------------------------------

    print()
    print("-" * 70)
    print("Expected vs actual")
    print("-" * 70)

    expected_team_week_files = (
        expected_weeks
        * expected_teams
    )

    print(
        f"Expected scoreboard files:  "
        f"{expected_weeks}"
    )

    print(
        f"Expected roster files:      "
        f"{expected_team_week_files}"
    )

    print(
        f"Valid roster files:         "
        f"{valid_roster_files}"
    )

    print(
        f"Expected stats files:       "
        f"{expected_team_week_files}"
    )

    print(
        f"Valid stats files:          "
        f"{valid_stats_files}"
    )

    print(
        f"Expected player files:      "
        f"{expected_team_week_files}"
    )

    print(
        f"Valid player files:         "
        f"{valid_player_files}"
    )

    # ---------------------------------------------------------
    # Errors
    # ---------------------------------------------------------

    print()
    print("-" * 70)
    print("Problems found")
    print("-" * 70)

    problem_count = (
        len(league_errors)
        + len(missing_scoreboards)
        + len(missing_rosters)
        + len(missing_stats)
        + len(missing_players)
    )

    if problem_count == 0:
        print(
            "No missing or invalid files found."
        )

    else:
        if league_errors:
            print()
            print(
                "League files:"
            )

            for item in league_errors:
                print(
                    f"  {item}"
                )

        if missing_scoreboards:
            print()
            print(
                "Missing scoreboards:"
            )

            for week in missing_scoreboards:
                print(
                    f"  Week {week}"
                )

        if missing_rosters:
            print()
            print(
                "Missing rosters:"
            )

            for week, team in missing_rosters:
                print(
                    f"  Week {week}, "
                    f"Team {team}"
                )

        if missing_stats:
            print()
            print(
                "Missing stats:"
            )

            for week, team in missing_stats:
                print(
                    f"  Week {week}, "
                    f"Team {team}"
                )

        if missing_players:
            print()
            print(
                "Missing player files:"
            )

            for week, team in missing_players:
                print(
                    f"  Week {week}, "
                    f"Team {team}"
                )

    # ---------------------------------------------------------
    # Final result
    # ---------------------------------------------------------

    print()
    print("=" * 70)

    if problem_count == 0:
        print(
            "AUDIT RESULT: PASS"
        )
    else:
        print(
            f"AUDIT RESULT: CHECK "
            f"({problem_count} problems)"
        )

    print("=" * 70)
    print()


if __name__ == "__main__":
    audit()