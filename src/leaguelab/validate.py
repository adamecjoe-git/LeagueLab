import argparse
import csv
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

NORMALIZED_DATA_ROOT = (
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


def to_bool(value):
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    return str(value).strip().lower() in (
        "true",
        "1",
        "yes",
        "y",
    )


def validate(season):
    print()
    print("=" * 78)
    print(
        f"LeagueLab Player Score Validation - {season}"
    )
    print("=" * 78)

    season_dir = (
        NORMALIZED_DATA_ROOT
        / str(season)
    )

    team_path = (
        season_dir
        / "weekly_team_results.csv"
    )

    player_path = (
        season_dir
        / "weekly_players.csv"
    )

    if not team_path.exists():
        raise RuntimeError(
            f"Missing file:\n{team_path}"
        )

    if not player_path.exists():
        raise RuntimeError(
            f"Missing file:\n{player_path}"
        )

    print()
    print(
        f"Team results: {team_path}"
    )

    print(
        f"Players:      {player_path}"
    )

    team_rows = read_csv(
        team_path
    )

    player_rows = read_csv(
        player_path
    )

    # ---------------------------------------------------------
    # Sum starter points by week/team
    # ---------------------------------------------------------

    starter_points = defaultdict(
        float
    )

    starter_counts = defaultdict(
        int
    )

    selected_position_counts = defaultdict(
        int
    )

    for row in player_rows:
        week = int(
            row["week"]
        )

        team_key = row[
            "team_key"
        ]

        if not to_bool(
            row["is_starter"]
        ):
            continue

        points = to_float(
            row["points"]
        )

        if points is None:
            points = 0.0

        key = (
            week,
            team_key,
        )

        starter_points[
            key
        ] += points

        starter_counts[
            key
        ] += 1

        selected_position = (
            row[
                "selected_position"
            ]
        )

        selected_position_counts[
            (
                week,
                team_key,
                selected_position,
            )
        ] += 1

    # ---------------------------------------------------------
    # Compare against Yahoo team scores
    # ---------------------------------------------------------

    comparisons = []

    for row in team_rows:
        week = int(
            row["week"]
        )

        # Challenges / regular-season validation only.
        if week > 14:
            continue

        team_key = row[
            "team_key"
        ]

        yahoo_score = to_float(
            row["points"]
        )

        calculated_score = (
            starter_points[
                (
                    week,
                    team_key,
                )
            ]
        )

        difference = None

        if yahoo_score is not None:
            difference = round(
                calculated_score
                - yahoo_score,
                4,
            )

        comparisons.append(
            {
                "week": week,
                "team_id": row[
                    "team_id"
                ],
                "team_name": row[
                    "team_name"
                ],
                "starter_count": (
                    starter_counts[
                        (
                            week,
                            team_key,
                        )
                    ]
                ),
                "yahoo_score": yahoo_score,
                "calculated_score": round(
                    calculated_score,
                    2,
                ),
                "difference": difference,
            }
        )

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------

    exact = [
        row
        for row in comparisons
        if (
            row["difference"]
            is not None
            and abs(
                row["difference"]
            ) < 0.01
        )
    ]

    within_tenth = [
        row
        for row in comparisons
        if (
            row["difference"]
            is not None
            and abs(
                row["difference"]
            ) < 0.10
        )
    ]

    mismatches = [
        row
        for row in comparisons
        if (
            row["difference"]
            is None
            or abs(
                row["difference"]
            ) >= 0.01
        )
    ]

    large_mismatches = [
        row
        for row in comparisons
        if (
            row["difference"]
            is None
            or abs(
                row["difference"]
            ) >= 0.10
        )
    ]

    print()
    print("-" * 78)
    print("Summary")
    print("-" * 78)

    print(
        f"Team-week comparisons:     "
        f"{len(comparisons)}"
    )

    print(
        f"Exact within 0.01 pts:      "
        f"{len(exact)}"
    )

    print(
        f"Within 0.10 pts:            "
        f"{len(within_tenth)}"
    )

    print(
        f"Mismatches >= 0.01 pts:     "
        f"{len(mismatches)}"
    )

    print(
        f"Mismatches >= 0.10 pts:     "
        f"{len(large_mismatches)}"
    )

    starter_count_values = [
        row[
            "starter_count"
        ]
        for row in comparisons
    ]

    if starter_count_values:
        print(
            f"Starter count range:        "
            f"{min(starter_count_values)}"
            f" - "
            f"{max(starter_count_values)}"
        )

    # ---------------------------------------------------------
    # Largest mismatches
    # ---------------------------------------------------------

    print()
    print("-" * 78)
    print("Largest score differences")
    print("-" * 78)

    ordered = sorted(
        comparisons,
        key=lambda row: (
            -1
            if row[
                "difference"
            ] is None
            else abs(
                row[
                    "difference"
                ]
            )
        ),
        reverse=True,
    )

    print(
        f"{'Week':<6}"
        f"{'Team':<5}"
        f"{'Team Name':<28}"
        f"{'Start':>7}"
        f"{'Yahoo':>10}"
        f"{'Players':>10}"
        f"{'Delta':>10}"
    )

    print(
        "-" * 78
    )

    for row in ordered[:20]:
        yahoo_score = (
            ""
            if row[
                "yahoo_score"
            ] is None
            else f"{row['yahoo_score']:.2f}"
        )

        calculated_score = (
            f"{row['calculated_score']:.2f}"
        )

        difference = (
            ""
            if row[
                "difference"
            ] is None
            else f"{row['difference']:+.2f}"
        )

        print(
            f"{row['week']:<6}"
            f"{row['team_id']:<5}"
            f"{row['team_name'][:27]:<28}"
            f"{row['starter_count']:>7}"
            f"{yahoo_score:>10}"
            f"{calculated_score:>10}"
            f"{difference:>10}"
        )

    # ---------------------------------------------------------
    # Starter-position distribution
    # ---------------------------------------------------------

    print()
    print("-" * 78)
    print("Starter position counts")
    print("-" * 78)

    position_totals = defaultdict(
        int
    )

    for (
        week,
        team_key,
        position,
    ), count in (
        selected_position_counts.items()
    ):
        if week <= 14:
            position_totals[
                position
            ] += count

    for position, count in sorted(
        position_totals.items(),
        key=lambda item: (
            str(item[0])
        ),
    ):
        print(
            f"{str(position):<15} "
            f"{count}"
        )

    # ---------------------------------------------------------
    # Save detailed comparison CSV
    # ---------------------------------------------------------

    output_path = (
        season_dir
        / "validation_team_scores.csv"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "week",
                "team_id",
                "team_name",
                "starter_count",
                "yahoo_score",
                "calculated_score",
                "difference",
            ],
        )

        writer.writeheader()
        writer.writerows(
            comparisons
        )

    print()
    print(
        f"Detailed comparison saved to:"
    )

    print(
        f"  {output_path}"
    )

    # ---------------------------------------------------------
    # Final result
    # ---------------------------------------------------------

    print()
    print("=" * 78)

    if not large_mismatches:
        print(
            "VALIDATION RESULT: PASS"
        )

    elif (
        len(large_mismatches)
        <= 5
    ):
        print(
            "VALIDATION RESULT: REVIEW SMALL NUMBER OF MISMATCHES"
        )

    else:
        print(
            "VALIDATION RESULT: CHECK"
        )

    print("=" * 78)
    print()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Validate LeagueLab normalized "
            "player scoring against Yahoo "
            "team scores."
        )
    )

    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Fantasy football season.",
    )

    args = parser.parse_args()

    validate(
        season=args.season
    )


if __name__ == "__main__":
    main()
