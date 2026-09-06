import argparse

from leaguelab.postseason import (
    run_postseason,
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


def matchup_text(matchup):
    return (
        "#{a_seed} {a_name} {a_score:.2f} "
        "vs #{b_seed} {b_name} {b_score:.2f}"
    ).format(
        a_seed=matchup[
            "team_a_seed"
        ],
        a_name=matchup[
            "team_a_name"
        ],
        a_score=matchup[
            "team_a_score"
        ],
        b_seed=matchup[
            "team_b_seed"
        ],
        b_name=matchup[
            "team_b_name"
        ],
        b_score=matchup[
            "team_b_score"
        ],
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run LeagueLab custom postseason."
        )
    )

    parser.add_argument(
        "--season",
        type=int,
        required=True,
    )

    args = parser.parse_args()

    result = run_postseason(
        args.season
    )

    toilet = result[
        "toilet_bowl"
    ]

    if toilet is None:
        print()
        print(
            "Toilet Bowl is disabled for {}.".format(
                args.season
            )
        )
        return

    print()
    print("=" * 92)
    print(
        "{} - {}".format(
            toilet["name"],
            args.season,
        )
    )
    print("=" * 92)

    print()
    print(
        "Regular season ends Week {}.".format(
            toilet[
                "regular_season_end_week"
            ]
        )
    )
    print(
        "Scores are reconstructed from Yahoo historical starter rows."
    )

    print()
    print("Participants")
    print("-" * 72)

    for team in toilet[
        "participants"
    ]:
        print(
            "#{:<3} {:<30} {:<8} PF {:>8.2f}".format(
                team["seed"],
                team["team_name"][:29],
                team["record"],
                team["points_for"],
            )
        )

    print()
    print(
        "Week {} Semifinals".format(
            toilet["semifinal_week"]
        )
    )
    print("-" * 92)

    for matchup in toilet[
        "semifinals"
    ]:
        print(
            matchup_text(
                matchup
            )
        )
        print(
            "  Winner: #{} {} by {:.2f}".format(
                matchup[
                    "winner_seed"
                ],
                matchup[
                    "winner_name"
                ],
                matchup[
                    "margin"
                ],
            )
        )

    championship = toilet[
        "championship"
    ]

    print()
    print(
        "Week {} Championship".format(
            toilet[
                "championship_week"
            ]
        )
    )
    print("-" * 92)
    print(
        matchup_text(
            championship
        )
    )
    print(
        "  Winner: #{} {} by {:.2f}".format(
            championship[
                "winner_seed"
            ],
            championship[
                "winner_name"
            ],
            championship[
                "margin"
            ],
        )
    )

    champion = toilet[
        "champion"
    ]

    print()
    print("=" * 92)
    print(
        "TOILET BOWL CHAMPION: #{} {} - {}".format(
            champion["seed"],
            champion["team_name"],
            money_text(
                champion["payout"]
            ),
        )
    )
    print("=" * 92)

    print()
    print("Saved:")
    print(
        "  {}".format(
            result[
                "toilet_bowl_json_path"
            ]
        )
    )
    print(
        "  {}".format(
            result[
                "toilet_bowl_bracket_path"
            ]
        )
    )
    print()


if __name__ == "__main__":
    main()
