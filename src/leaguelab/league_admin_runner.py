import argparse

from leaguelab.league_admin import (
    run_league_admin,
)


def money_text(value):
    value = float(value)

    if value.is_integer():
        return "${}".format(
            int(value)
        )

    return "${:.2f}".format(
        value
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run LeagueLab league-admin outputs."
        )
    )

    parser.add_argument(
        "--season",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--regular-season-end-week",
        type=int,
        default=14,
    )

    args = parser.parse_args()

    result = run_league_admin(
        args.season,
        regular_season_end_week=(
            args.regular_season_end_week
        ),
    )

    loser = result[
        "losers_trophy"
    ]

    print()
    print("=" * 118)
    print(
        "League Admin - {}".format(
            args.season
        )
    )
    print("=" * 118)

    print()
    print("Loser's Trophy")
    print("-" * 90)
    print(
        "#{} {} - {} - {:.2f} PF".format(
            loser["rank"],
            loser["team_name"],
            loser["record"],
            loser["points_for"],
        )
    )

    summary = result[
        "dues_summary"
    ]

    print()
    print("League Dues")
    print("-" * 90)
    print(
        "Paid: {}/{} | Unpaid: {} | Collected: {} | Balance: {}".format(
            summary["paid_count"],
            summary["team_count"],
            summary["unpaid_count"],
            money_text(
                summary["total_paid"]
            ),
            money_text(
                summary["balance_due"]
            ),
        )
    )

    print()
    print(
        "{:<18}{:<28}{:<38}{:>10}{:>12}".format(
            "Manager",
            "Team",
            "Email",
            "Status",
            "Balance",
        )
    )
    print("-" * 106)

    for row in result["dues"]:
        status = (
            "PAID"
            if row["paid"]
            else "UNPAID"
        )

        print(
            "{:<18}{:<28}{:<38}{:>10}{:>12}".format(
                (
                    row[
                        "manager_name"
                    ][:17]
                    if row[
                        "manager_name"
                    ]
                    else "-"
                ),
                row[
                    "team_name"
                ][:27],
                (
                    row[
                        "manager_email"
                    ][:37]
                    if row[
                        "manager_email"
                    ]
                    else "-"
                ),
                status,
                money_text(
                    row["balance_due"]
                ),
            )
        )

    missing_email = [
        row
        for row in result[
            "manager_directory"
        ]
        if not row["email"]
    ]

    print()
    print("Newsletter Contacts")
    print("-" * 90)

    if missing_email:
        print(
            "{} manager(s) are missing email addresses.".format(
                len(missing_email)
            )
        )
        print(
            "Add them to:"
        )
        print(
            "  {}".format(
                result[
                    "manager_contacts_path"
                ]
            )
        )
    else:
        print(
            "All managers have email addresses."
        )

    print()
    print("Sources / Config:")
    print(
        "  Yahoo teams: {}".format(
            result[
                "yahoo_teams_path"
            ]
            or "NOT FOUND"
        )
    )
    print(
        "  Manager contacts: {}".format(
            result[
                "manager_contacts_path"
            ]
        )
    )
    print(
        "  Dues config: {}".format(
            result[
                "dues_config_path"
            ]
        )
    )

    print()
    print("Saved:")
    print(
        "  {}".format(
            result[
                "losers_trophy_path"
            ]
        )
    )
    print(
        "  {}".format(
            result[
                "dues_json_path"
            ]
        )
    )
    print(
        "  {}".format(
            result[
                "dues_csv_path"
            ]
        )
    )
    print(
        "  {}".format(
            result[
                "manager_json_path"
            ]
        )
    )
    print(
        "  {}".format(
            result[
                "manager_csv_path"
            ]
        )
    )
    print()


if __name__ == "__main__":
    main()
