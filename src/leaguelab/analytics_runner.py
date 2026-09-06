import argparse

from leaguelab.analytics import (
    POWER_RECENT_WEEKS,
    POWER_RECENT_WEEK_WEIGHTS,
    POWER_WEIGHT_ALL_PLAY,
    POWER_WEIGHT_RECENT_FORM,
    POWER_WEIGHT_RECORD,
    POWER_WEIGHT_SEASON_SCORING,
    run_weekly_analytics,
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



def to_float_for_display(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run LeagueLab weekly analytics."
        )
    )

    parser.add_argument(
        "--season",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--through-week",
        type=int,
        default=14,
    )

    args = parser.parse_args()

    result = run_weekly_analytics(
        args.season,
        end_week=args.through_week,
    )

    luck = result["luck"]

    print()
    print("=" * 108)
    print(
        "LeagueLab All-Play + Luck - {} through Week {}".format(
            args.season,
            args.through_week,
        )
    )
    print("=" * 108)

    print()
    print(
        "{:<5}{:<30}{:<12}{:<16}{:>10}{:>12}{:>12}".format(
            "Rank",
            "Team",
            "Actual",
            "All-Play",
            "AP Win%",
            "Exp Wins",
            "Luck Wins",
        )
    )

    print("-" * 104)

    for index, row in enumerate(
        luck,
        start=1,
    ):
        actual = record_text(
            row["actual_wins"],
            row["actual_losses"],
            row["actual_ties"],
        )

        all_play = record_text(
            row["all_play_wins"],
            row["all_play_losses"],
            row["all_play_ties"],
        )

        print(
            "{:<5}{:<30}{:<12}{:<16}{:>9.1%}{:>12.2f}{:>+12.2f}".format(
                index,
                row["team_name"][:29],
                actual,
                all_play,
                row["all_play_win_pct"],
                row["expected_wins"],
                row["luck_wins"],
            )
        )

    print()
    print(
        "Luck Wins = Actual Wins - Expected Wins "
        "(ties count as 0.5 wins)"
    )

    latest_week_rows = [
        row
        for row in result["weekly_analytics"]
        if row["week"] == args.through_week
    ]

    latest_week_rows = sorted(
        latest_week_rows,
        key=lambda row: row["standings_rank"],
    )

    print()
    print("=" * 90)
    print("Standings Movement + Streaks")
    print("=" * 90)
    print()
    print(
        "{:<5}{:<30}{:<12}{:>8}{:>10}{:>10}".format(
            "Rank",
            "Team",
            "Record",
            "Move",
            "Streak",
            "PF",
        )
    )
    print("-" * 80)

    for row in latest_week_rows:
        actual = record_text(
            row["actual_wins"],
            row["actual_losses"],
            row["actual_ties"],
        )

        movement = row["standings_movement"]

        if movement > 0:
            movement_text = "+{}".format(movement)
        elif movement < 0:
            movement_text = str(movement)
        else:
            movement_text = "-"

        print(
            "{:<5}{:<30}{:<12}{:>8}{:>10}{:>10.2f}".format(
                row["standings_rank"],
                row["team_name"][:29],
                actual,
                movement_text,
                row["current_streak"],
                row["points_for"],
            )
        )

    print()
    print("Movement = change from previous week's standings rank.")

    glance = result["week_at_a_glance"]

    if glance is not None:
        print()
        print("=" * 90)
        print(
            "Week {} at a Glance".format(
                glance["week"]
            )
        )
        print("=" * 90)

        high = glance[
            "highest_team_score"
        ]
        low = glance[
            "lowest_team_score"
        ]
        close = glance[
            "closest_matchup"
        ]
        blowout = glance[
            "biggest_blowout"
        ]
        starter = glance[
            "top_starter"
        ]
        bench_player = glance[
            "top_bench_player"
        ]

        print()
        print(
            "Highest Team Score: {} - {:.2f}".format(
                high["team_name"],
                high["score"],
            )
        )
        print(
            "Lowest Team Score:  {} - {:.2f}".format(
                low["team_name"],
                low["score"],
            )
        )

        if close is not None:
            print(
                "Closest Matchup:    {} {:.2f} over {} {:.2f} "
                "(margin {:.2f})".format(
                    close["winner"],
                    close["winner_points"],
                    close["loser"],
                    close["loser_points"],
                    close["margin"],
                )
            )

        if blowout is not None:
            print(
                "Biggest Blowout:    {} {:.2f} over {} {:.2f} "
                "(margin {:.2f})".format(
                    blowout["winner"],
                    blowout["winner_points"],
                    blowout["loser"],
                    blowout["loser_points"],
                    blowout["margin"],
                )
            )

        if starter is not None:
            print(
                "Top Starter:        {} - {:.2f} pts "
                "({}; {})".format(
                    starter["player_name"],
                    starter["points"],
                    starter["team_name"],
                    starter["lineup_slot"],
                )
            )

        if bench_player is not None:
            print(
                "Top Bench Player:   {} - {:.2f} pts "
                "({})".format(
                    bench_player["player_name"],
                    bench_player["points"],
                    bench_player["team_name"],
                )
            )

        print()
        print(
            "{:<5}{:<30}{:>10}  {:<8}{:<30}".format(
                "Rank",
                "Team",
                "Score",
                "Result",
                "Opponent",
            )
        )
        print("-" * 88)

        for row in glance["weekly_rankings"]:
            print(
                "{:<5}{:<30}{:>10.2f}  {:<8}{:<30}".format(
                    row["rank"],
                    row["team_name"][:29],
                    row["score"],
                    row["result"],
                    row["opponent_team_name"][:29],
                )
            )

    lineup = result["lineup_summary"]

    if lineup is not None:
        print()
        print("=" * 90)
        print(
            "Week {} Lineup Decisions".format(
                lineup["week"]
            )
        )
        print("=" * 90)

        best = lineup["best_efficiency"]
        worst = lineup["worst_efficiency"]
        left = lineup["most_points_left"]
        decision = lineup["worst_decision"]

        print()
        print(
            "Best Efficiency:     {} - {:.1f}% "
            "({:.2f} / {:.2f})".format(
                best["team_name"],
                best["lineup_efficiency"],
                best["actual_lineup_points"],
                best["optimal_lineup_points"],
            )
        )
        print(
            "Worst Efficiency:    {} - {:.1f}% "
            "({:.2f} / {:.2f})".format(
                worst["team_name"],
                worst["lineup_efficiency"],
                worst["actual_lineup_points"],
                worst["optimal_lineup_points"],
            )
        )
        print(
            "Most Points Left:    {} - {:.2f} pts".format(
                left["team_name"],
                left["points_left_on_bench"],
            )
        )

        if decision is not None:
            print(
                "Worst Decision:     {} benched {} ({:.2f}) "
                "while starting {} ({:.2f}) in {}; "
                "legal swap worth +{:.2f}".format(
                    decision["team_name"],
                    decision["biggest_bench_player"],
                    to_float_for_display(
                        decision["biggest_bench_points"]
                    ),
                    decision["replaced_starter"],
                    to_float_for_display(
                        decision["replaced_starter_points"]
                    ),
                    decision["decision_slot"],
                    to_float_for_display(
                        decision["decision_points_gained"]
                    ),
                )
            )

        print()
        print(
            "{:<5}{:<30}{:>10}{:>10}{:>10}{:>10}".format(
                "Rank",
                "Team",
                "Actual",
                "Optimal",
                "Left",
                "Eff %",
            )
        )
        print("-" * 85)

        week_rows = [
            row
            for row in result[
                "lineup_efficiency"
            ]
            if row["week"] == args.through_week
        ]

        week_rows = sorted(
            week_rows,
            key=lambda row: (
                -row["lineup_efficiency"],
                -row["actual_lineup_points"],
            ),
        )

        for rank, row in enumerate(
            week_rows,
            start=1,
        ):
            print(
                "{:<5}{:<30}{:>10.2f}{:>10.2f}{:>10.2f}{:>9.1f}%".format(
                    rank,
                    row["team_name"][:29],
                    row["actual_lineup_points"],
                    row["optimal_lineup_points"],
                    row["points_left_on_bench"],
                    row["lineup_efficiency"],
                )
            )

    power = result["power_rankings"]

    if power:
        print()
        print("=" * 100)
        print(
            "Power Rankings - Through Week {}".format(
                args.through_week
            )
        )
        print("=" * 100)
        print()
        print(
            "Formula: {:.0f}% Season Scoring + {:.0f}% All-Play + "
            "{:.0f}% Recent {}-Week Form + {:.0f}% Record".format(
                POWER_WEIGHT_SEASON_SCORING * 100.0,
                POWER_WEIGHT_ALL_PLAY * 100.0,
                POWER_WEIGHT_RECENT_FORM * 100.0,
                POWER_RECENT_WEEKS,
                POWER_WEIGHT_RECORD * 100.0,
            )
        )

        recent_weight_text = " / ".join(
            "{:.0f}%".format(
                weight * 100.0
            )
            for weight in POWER_RECENT_WEEK_WEIGHTS
        )

        print(
            "Recent form weighting (newest -> oldest): {}".format(
                recent_weight_text
            )
        )
        print()
        print(
            "{:<5}{:<30}{:>9}{:>11}{:>11}{:>12}{:>10}".format(
                "Rank",
                "Team",
                "Power",
                "Season PF",
                "AP Win%",
                "Recent Form",
                "Record",
            )
        )
        print("-" * 98)

        for row in power:
            if row["actual_ties"]:
                record = "{}-{}-{}".format(
                    row["actual_wins"],
                    row["actual_losses"],
                    row["actual_ties"],
                )
            else:
                record = "{}-{}".format(
                    row["actual_wins"],
                    row["actual_losses"],
                )

            print(
                "{:<5}{:<30}{:>9.2f}{:>11.2f}{:>10.1f}%"
                "{:>12.2f}{:>10}".format(
                    row["power_rank"],
                    row["team_name"][:29],
                    row["power_score"],
                    row["season_points"],
                    row["all_play_win_pct"] * 100.0,
                    row["recent_form_points"],
                    record,
                )
            )

    schedule = result[
        "schedule_strength"
    ]

    if schedule:
        print()
        print("=" * 100)
        print(
            "Strength of Schedule - Through Week {}".format(
                args.through_week
            )
        )
        print("=" * 100)
        print()
        print(
            "SOS = average weekly all-play strength of actual opponents."
        )
        print()
        print(
            "{:<5}{:<30}{:>10}{:>12}{:>10}".format(
                "SOS",
                "Team",
                "SOS %",
                "Opp Avg",
                "Games",
            )
        )
        print("-" * 72)

        for row in schedule:
            print(
                "{:<5}{:<30}{:>9.1f}%{:>12.2f}{:>10}".format(
                    row["sos_rank"],
                    row["team_name"][:29],
                    row["strength_of_schedule"] * 100.0,
                    row["avg_opponent_score"],
                    row["games_with_opponent"],
                )
            )

        hardest = schedule[0]
        easiest = schedule[-1]

        print()
        print(
            "Toughest Schedule: {} ({:.1f}%)".format(
                hardest["team_name"],
                hardest["strength_of_schedule"] * 100.0,
            )
        )
        print(
            "Easiest Schedule:  {} ({:.1f}%)".format(
                easiest["team_name"],
                easiest["strength_of_schedule"] * 100.0,
            )
        )

    print()
    print("Saved:")
    print(
        "  {}".format(
            result["all_play_path"]
        )
    )
    print(
        "  {}".format(
            result["weekly_analytics_path"]
        )
    )
    print(
        "  {}".format(
            result["luck_path"]
        )
    )
    print(
        "  {}".format(
            result["week_at_a_glance_path"]
        )
    )
    print(
        "  {}".format(
            result["lineup_efficiency_path"]
        )
    )
    print(
        "  {}".format(
            result["power_rankings_path"]
        )
    )
    print(
        "  {}".format(
            result["schedule_strength_path"]
        )
    )
    print()


if __name__ == "__main__":
    main()
