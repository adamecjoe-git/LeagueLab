import argparse
import csv
from collections import defaultdict
from pathlib import Path

from leaguelab.lineup import (
    solve_optimal_lineup,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

NORMALIZED_ROOT = (
    PROJECT_ROOT
    / "data"
    / "normalized"
)


def read_csv(path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        return list(
            csv.DictReader(file)
        )


def to_bool(value):
    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
        "y",
    }


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--season",
        type=int,
        required=True,
    )

    args = parser.parse_args()

    player_path = (
        NORMALIZED_ROOT
        / str(args.season)
        / "weekly_players.csv"
    )

    rows = read_csv(
        player_path
    )

    grouped = defaultdict(list)

    for row in rows:
        week = int(
            row["week"]
        )

        if week > 14:
            continue

        grouped[
            (
                week,
                row["team_key"],
            )
        ].append(row)

    comparisons = []

    for (
        week,
        team_key,
    ), players in grouped.items():

        actual = sum(
            to_float(
                player["points"]
            )
            for player in players
            if to_bool(
                player["is_starter"]
            )
        )

        optimal = solve_optimal_lineup(
            players
        )

        optimal_points = (
            optimal[
                "total_points"
            ]
        )

        comparisons.append(
            {
                "week": week,
                "team_key": team_key,
                "team_name": players[0][
                    "team_name"
                ],
                "actual": round(
                    actual,
                    2,
                ),
                "optimal": optimal_points,
                "gain": round(
                    optimal_points
                    - actual,
                    2,
                ),
            }
        )

    invalid = [
        row
        for row in comparisons
        if row["optimal"]
        + 0.001
        < row["actual"]
    ]

    perfect = [
        row
        for row in comparisons
        if abs(
            row["optimal"]
            - row["actual"]
        ) < 0.01
    ]

    ordered = sorted(
        comparisons,
        key=lambda row: (
            -row["gain"],
            row["week"],
            row["team_name"],
        ),
    )

    print()
    print("=" * 78)
    print(
        "LeagueLab Optimal Lineup Validation - {}".format(
            args.season
        )
    )
    print("=" * 78)

    print()
    print(
        "Team-week comparisons: {}".format(
            len(comparisons)
        )
    )

    print(
        "Optimal < actual:      {}".format(
            len(invalid)
        )
    )

    print(
        "Perfect lineups:       {}".format(
            len(perfect)
        )
    )

    print()
    print(
        "{:<6}{:<30}{:>12}{:>12}{:>12}".format(
            "Week",
            "Team",
            "Actual",
            "Optimal",
            "Gain",
        )
    )

    print("-" * 72)

    for row in ordered[:20]:
        print(
            "{:<6}{:<30}{:>12.2f}{:>12.2f}{:>12.2f}".format(
                row["week"],
                row["team_name"][:29],
                row["actual"],
                row["optimal"],
                row["gain"],
            )
        )

    print()
    print("=" * 78)

    if invalid:
        print(
            "VALIDATION RESULT: CHECK"
        )
    else:
        print(
            "VALIDATION RESULT: PASS"
        )

    print("=" * 78)
    print()


if __name__ == "__main__":
    main()
