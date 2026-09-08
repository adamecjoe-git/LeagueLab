"""LeagueLab newsletter layout selection. Python 3.8 compatible."""

REGULAR_SEASON = "regular_season"
REGULAR_SEASON_FINAL = "regular_season_final"
PLAYOFFS = "playoffs"
CHAMPIONSHIP = "championship"
POSTSEASON_WRAP = "postseason_wrap"


def newsletter_type_for_week(week, regular_season_end=14, season_end=17, override=None):
    if override:
        valid = {
            REGULAR_SEASON,
            REGULAR_SEASON_FINAL,
            PLAYOFFS,
            CHAMPIONSHIP,
        }
        if override not in valid:
            raise ValueError("Unknown newsletter type: {}".format(override))
        return override

    week = int(week)
    regular_season_end = int(regular_season_end)
    season_end = int(season_end)

    if week < regular_season_end:
        return REGULAR_SEASON
    if week == regular_season_end:
        return REGULAR_SEASON_FINAL
    if week < season_end:
        return PLAYOFFS
    if week == season_end:
        return CHAMPIONSHIP
    raise ValueError(
        "Week {} is after the configured season end (Week {}). "
        "Week {} is the final newsletter.".format(
            week, season_end, season_end
        )
    )


# The order here is the newsletter specification.  Individual blocks are
# allowed to return an empty string when their source data is not available.
LAYOUTS = {
    REGULAR_SEASON: (
        "matchup_results",
        "weekly_highlights",
        "challenge_update",
        "challenge_standings",
        "challenge_leaderboard",
        "next_challenge",
        "standings",
        "power_rankings",
        "beyond_box_score",
        "upcoming_matchups",
        "league_admin",
    ),
    REGULAR_SEASON_FINAL: (
        "matchup_results",
        "weekly_highlights",
        "challenge_results",
        "challenge_standings_final",
        "challenge_leaderboard",
        "final_standings",
        "losers_trophy",
        "power_rankings_final",
        "beyond_box_score",
        "playoff_preview",
        "toilet_bowl_preview",
        "next_round_matchups",
        "league_admin",
    ),
    PLAYOFFS: (
        "playoff_results",
        "toilet_bowl",
        "weekly_highlights",
        "power_rankings",
        "beyond_box_score",
        "next_round_matchups",
        "league_admin",
    ),
    CHAMPIONSHIP: (
        "champion",
        "challenge_winners",
        "total_payouts",
        "season_accolades",
        "playoff_results",
        "toilet_bowl_winner",
        "toilet_bowl",
        "weekly_highlights",
        "power_rankings",
        "beyond_box_score",
        "league_admin",
    ),

}


def blocks_for(newsletter_type):
    return LAYOUTS[newsletter_type]
