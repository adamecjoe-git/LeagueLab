"""LeagueLab newsletter layout selection. Python 3.8 compatible.

This file is the authoritative specification for which modular newsletter
blocks appear and in what order.
"""

WEEK_1 = "week_1"
REGULAR_SEASON = "regular_season"
REGULAR_SEASON_FINAL = "regular_season_final"
PLAYOFFS = "playoffs"
CHAMPIONSHIP = "championship"
POSTSEASON_WRAP = "postseason_wrap"


def newsletter_type_for_week(week, regular_season_end=14, season_end=17, override=None):
    if override:
        valid = {
            WEEK_1,
            REGULAR_SEASON,
            REGULAR_SEASON_FINAL,
            PLAYOFFS,
            CHAMPIONSHIP,
            POSTSEASON_WRAP,
        }
        if override not in valid:
            raise ValueError("Unknown newsletter type: {}".format(override))
        return override

    week = int(week)
    regular_season_end = int(regular_season_end)
    season_end = int(season_end)

    if week == 1:
        return WEEK_1
    if 2 <= week < regular_season_end:
        return REGULAR_SEASON
    if week == regular_season_end:
        return REGULAR_SEASON_FINAL
    if regular_season_end < week < season_end - 1:
        return PLAYOFFS
    if week == season_end - 1:
        return CHAMPIONSHIP
    if week == season_end:
        return POSTSEASON_WRAP
    raise ValueError(
        "Week {} is outside the configured newsletter season (Weeks 1-{}).".format(
            week, season_end
        )
    )


# Every visible newsletter section belongs here. A block may return an empty
# string when its source data is unavailable or the block is intentionally
# conditional for that week.
LAYOUTS = {
    # Week 1 uses the golden regular-season structure. Individual renderers
    # handle the intentional differences: League Pulse omits season-to-date
    # measures, while Challenge Leaderboard and Next Challenge are even-week only.
    WEEK_1: (
        "from_commish",
        "matchup_results",
        "weekly_highlights",
        "league_pulse",
        "challenge_update",
        "challenge_leaderboard",
        "next_challenge",
        "standings",
        "power_rankings",
        "upcoming_matchups",
        "league_admin",
    ),

    # Weeks 2-13: normal regular-season newsletter.
    REGULAR_SEASON: (
        "from_commish",
        "matchup_results",
        "weekly_highlights",
        "league_pulse",
        "challenge_update",
        "challenge_leaderboard",
        "next_challenge",
        "standings",
        "power_rankings",
        "upcoming_matchups",
        "league_admin",
    ),

    # Week 14: final regular-season results plus postseason setup.
    REGULAR_SEASON_FINAL: (
        "from_commish",
        "matchup_results",
        "weekly_highlights",
        "league_pulse",
        "challenge_results",
        "challenge_standings_final",
        "challenge_leaderboard",
        "final_standings",
        "losers_trophy",
        "power_rankings_final",
        "playoff_preview",
        "toilet_bowl_preview",
        "next_round_matchups",
        "league_admin",
    ),

    # Week 15: postseason progress and the next round.
    PLAYOFFS: (
        "from_commish",
        "playoff_results",
        "toilet_bowl",
        "weekly_highlights",
        "league_pulse",
        "power_rankings",
        "next_round_matchups",
        "league_admin",
    ),

    # Week 16: Toilet Bowl winner / championship-preview edition.
    CHAMPIONSHIP: (
        "from_commish",
        "champion",
        "toilet_bowl_winner",
        "playoff_results",
        "toilet_bowl",
        "weekly_highlights",
        "league_pulse",
        "power_rankings",
        "next_round_matchups",
        "league_admin",
    ),

    # Week 17: final season newsletter. This is season-level material rather than
    # another weekly matchup edition.
    POSTSEASON_WRAP: (
        "from_commish",
        "champion",
        "final_playoff_results",
        "toilet_bowl_winner",
        "weekly_highlights",
        "league_pulse",
        "challenge_winners",
        "total_payouts",
        "season_accolades",
        "final_season_results",
        "power_rankings_final",
        "league_admin",
    ),
}


def blocks_for(newsletter_type):
    return LAYOUTS[newsletter_type]
