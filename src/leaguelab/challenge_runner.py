import argparse
import csv
import json
from pathlib import Path

from leaguelab.challenges import run_challenges


PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_ROOT = (
    PROJECT_ROOT
    / "data"
    / "output"
)


def print_result(result):
    print()
    print("=" * 78)
    print(
        "{} (Weeks {}-{})".format(
            result["name"],
            result["start_week"],
            result["end_week"],
        )
    )
    print(
        "Type: {} | Payout: ${:.0f} | Status: {}".format(
            result["challenge_type"],
            result["payout"],
            result["status"],
        )
    )
    print("=" * 78)

    if result.get("message"):
        print(result["message"])

    standings = result.get(
        "standings",
        []
    )

    if not standings:
        return

    print()
    print(
        "{:<6}{:<30}{:>12}".format(
            "Rank",
            "Team",
            "Value",
        )
    )
    print("-" * 48)

    for row in standings:
        print(
            "{:<6}{:<30}{:>12.2f}".format(
                row["rank"],
                row["team_name"][:29],
                row["value"],
            )
        )


def save_outputs(
    season,
    results,
):
    output_dir = (
        OUTPUT_ROOT
        / str(season)
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        output_dir
        / "challenge_results.json"
    )

    with json_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            results,
            file,
            indent=2,
        )

    csv_path = (
        output_dir
        / "challenge_standings.csv"
    )

    rows = []

    for result in results:
        for standing in result.get(
            "standings",
            []
        ):
            rows.append(
                {
                    "season": season,
                    "challenge_id": result[
                        "challenge_id"
                    ],
                    "challenge_type": result[
                        "challenge_type"
                    ],
                    "challenge_name": result[
                        "name"
                    ],
                    "start_week": result[
                        "start_week"
                    ],
                    "end_week": result[
                        "end_week"
                    ],
                    "payout": result[
                        "payout"
                    ],
                    "status": result[
                        "status"
                    ],
                    "rank": standing[
                        "rank"
                    ],
                    "team_key": standing[
                        "team_key"
                    ],
                    "team_id": standing[
                        "team_id"
                    ],
                    "team_name": standing[
                        "team_name"
                    ],
                    "value": standing[
                        "value"
                    ],
                    "detail": standing.get(
                        "detail"
                    ),
                }
            )

    fieldnames = [
        "season",
        "challenge_id",
        "challenge_type",
        "challenge_name",
        "start_week",
        "end_week",
        "payout",
        "status",
        "rank",
        "team_key",
        "team_id",
        "team_name",
        "value",
        "detail",
    ]

    with csv_path.open(
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

    return json_path, csv_path


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run LeagueLab modular fantasy "
            "football challenges."
        )
    )

    parser.add_argument(
        "--season",
        type=int,
        required=True,
    )

    args = parser.parse_args()

    results = run_challenges(
        args.season
    )

    for result in results:
        print_result(
            result
        )

    json_path, csv_path = (
        save_outputs(
            args.season,
            results,
        )
    )

    print()
    print("=" * 78)
    print("Challenge outputs")
    print("=" * 78)
    print(json_path)
    print(csv_path)
    print()


if __name__ == "__main__":
    main()
