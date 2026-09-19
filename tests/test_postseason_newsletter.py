"""Offline regression coverage. Run: PYTHONPATH=src python -m unittest discover -s tests -v."""
import subprocess
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from leaguelab import analytics, postseason_newsletter as postseason, weekly_email as email
from leaguelab import season_accolades
from leaguelab import yahoo_postseason
from leaguelab.newsletter_layouts import blocks_for, newsletter_type_for_week
from leaguelab.postseason import DEFAULT_POSTSEASON_CONFIG, build_regular_season_standings


def fixtures():
    """Deterministic 12-team season, deliberately not real league results."""
    teams, players = [], []
    for week in range(1, 18):
        for seed in range(1, 13):
            points = 140 - seed * 3 + week / 100
            teams.append(dict(season=2025, week=week, team_key=str(seed), team_id=seed,
                              team_name="Team {}".format(seed), points=points,
                              projected_points=120, result="W" if seed <= 6 else "L"))
            players.append(dict(week=week, team_key=str(seed), team_name="Team {}".format(seed),
                                player_key="p{}".format(seed), player_name="Player {}".format(seed),
                                is_starter="1", points=points))
    return teams, players


def data_for(week, teams=None, players=None):
    default_teams, default_players = fixtures()
    teams = default_teams if teams is None else teams
    players = default_players if players is None else players
    standings = build_regular_season_standings(teams, 14)
    raw = yahoo_fixture(standings, teams, players)
    with patch.object(yahoo_postseason, "league_root", return_value=Path("/fixture")), patch.object(
        yahoo_postseason, "read", side_effect=lambda p: raw[str(p)]
    ), patch.object(postseason, "_read_csv", side_effect=[teams, players]), patch.object(
        postseason, "load_postseason_config", return_value=DEFAULT_POSTSEASON_CONFIG
    ):
        return postseason.build_postseason_newsletter_data(2025, week, {})


def yahoo_fixture(standings, teams, players):
    """Build Yahoo-shaped snapshots for deterministic offline seasons."""
    result = {"/fixture/standings.json": {"teams": [{"team": [
        {"team_key": r["team_key"], "name": r["team_name"]},
        {"team_standings": dict(rank=13-r["seed"],
            playoff_seed=str(r["seed"]) if r["seed"] <= 8 else None,
            points_for=r["points_for"], outcome_totals={k: r[k] for k in ("wins", "losses", "ties")})}
    ]} for r in standings]}}
    bracket = postseason._build_playoff_bracket(standings, teams, 17, 14, players)
    for week, matches in [(15, bracket["quarterfinals"]),
                          (16, bracket["championship_semifinals"] + bracket["consolation_semifinals"]),
                          (17, list(bracket["finals"].values()))]:
        result["/fixture/weeks/week_{:02d}/scoreboard.json".format(week)] = {"matchups": [
            {"matchup": dict(status="postevent", winner_team_key=m["winner_key"], teams=[
                {"team": [{"team_key": m[side]["team_key"]}, {"team_points": {
                    "week": str(week), "total": str(m[side]["score"])}}]}
                for side in ("team_a", "team_b")])} for m in matches if m and m["complete"]]}
    return result


def analytics_for(week):
    teams, _ = fixtures()
    teams = [r for r in teams if r["week"] <= week and not (r["week"] == 17 and int(r["team_key"]) > 8)]
    all_play = analytics.build_all_play_rows(teams, week)
    weekly = analytics.enrich_standings_and_streaks(
        analytics.build_weekly_team_analytics(all_play))
    return dict(weekly_analytics=weekly,
                power_rankings=analytics.build_power_rankings(teams, weekly, week),
                luck=analytics.build_season_luck_rows(weekly),
                schedule_strength=analytics.build_schedule_strength_rows(teams, all_play, week))


class PostseasonTests(unittest.TestCase):
    def test_progressive_scores_and_no_future_results(self):
        for week in range(14, 18):
            data = data_for(week)
            qf = data["playoff"]["quarterfinals"][0]
            self.assertEqual(qf["complete"], week >= 15)
            self.assertEqual(qf["team_a"]["score"] is not None, week >= 15)
            self.assertEqual(bool(data["playoff"]["champion"]), week == 17)
            self.assertEqual(bool(data["toilet_bowl"]["champion"]), week >= 16)
            if week == 15:
                self.assertFalse(data["playoff"]["championship_semifinals"][0]["complete"])
            if week == 16:
                self.assertFalse(data["playoff"]["finals"]["championship"]["complete"])

    def test_missing_official_scores_fall_back_to_starters(self):
        teams, players = fixtures()
        for row in teams:
            if row["week"] >= 15 and int(row["team_key"]) <= 8:
                row["points"] = ""
        data = data_for(17, teams, players)
        self.assertAlmostEqual(data["playoff"]["quarterfinals"][0]["team_a"]["score"], 137.15)
        self.assertEqual(len(data["final_standings"]), 12)
        # Scores beyond the newsletter week must not leak through the fallback.
        self.assertIsNone(data_for(14, teams, players)["playoff"]["quarterfinals"][0]["team_a"]["score"])

    def test_official_zero_is_not_replaced(self):
        teams, players = fixtures()
        for row in teams:
            if row["week"] == 15 and row["team_key"] == "1":
                row["points"] = 0
        qf = data_for(15, teams, players)["playoff"]["quarterfinals"][0]
        self.assertEqual(qf["team_a"]["score"], 0)
        self.assertEqual(qf["winner_key"], "8")
        self.assertIn("0.00", email._bracket_matchup_card(qf, "Quarterfinal"))

    def test_unavailable_scores_remain_pending(self):
        teams, _ = fixtures()
        teams = [r for r in teams if r["week"] < 15]
        standings = build_regular_season_standings(teams, 14)
        data = postseason._build_playoff_bracket(standings, teams, 17, 14)
        self.assertIsNone(data["champion"])
        self.assertFalse(data["quarterfinals"][0]["complete"])

    def test_final_placements_and_toilet_week16_results(self):
        teams, players = fixtures()
        for row in players:
            if row["week"] == 16 and row["team_key"] == "12":
                row["points"] = 500  # Seed 12 beats seed 11 for 11th place.
            if row["week"] == 17 and int(row["team_key"]) >= 9:
                row["points"] = 9999  # Must not affect places 9-12.
        places = data_for(17, teams, players)["final_standings"]
        self.assertEqual([r["place"] for r in places], list(range(1, 13)))
        self.assertEqual([r["team_key"] for r in places],
                         ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "12", "11"])

    def test_next_round_cards_all_three_weeks(self):
        for week, count in [(14, 6), (15, 6), (16, 4)]:
            self.assertIn("next_round_matchups", blocks_for(newsletter_type_for_week(week)))
            html = email._next_round_cards(dict(week=week, postseason_data=data_for(week)))
            self.assertEqual(html.count('height="174" cellspacing'), count)
            self.assertNotIn("MATCHUP TO WATCH", html)
            self.assertEqual(html.count('background:#C58A2A;color:#FFFFFF;'), count)
            self.assertIn("Proj 120.00", html)
            self.assertIn("font-size:15px", html)

    def test_toilet_placement_visible_and_playoff_renderer_runs(self):
        for week in (14, 15, 16, 17):
            ctx = dict(week=week, postseason_data=data_for(week))
            html = email._toilet_bowl(ctx, "Toilet Bowl", preview=week == 14)
            self.assertIn("11th / 12th Place", html)
            self.assertEqual(html.count('border-bottom:2px solid #C6923D;'), 4)
            self.assertNotIn('rowspan=', html)
            if week == 14:
                self.assertEqual(html.count('>TBD</td>'), 4)
            if week >= 15:
                self.assertIn("137.15", email._playoff_bracket(ctx, "Playoffs"))

    def test_awards_use_payouts_without_seeds(self):
        data = data_for(17)
        data["league_payouts"][0]["amount"] = 250
        ctx = dict(week=17, postseason_data=data)
        champion = email._champion(ctx)
        toilet = email._toilet_bowl_winner(ctx)
        self.assertIn("$250 payout", champion)
        self.assertIn("$40 payout", toilet)
        self.assertNotIn("#1 ", champion)
        self.assertNotIn("#9 ", toilet)
        self.assertLess(champion.index("trophy-gold.png"), champion.index("Team 1"))
        trophy = email._losers_trophy(dict(weekly_rows=[dict(standings_rank=12,
            team_name="A & B", actual_wins=3, actual_losses=10, actual_ties=1)]))
        self.assertIn("3-10-1 regular-season record", trophy)
        self.assertIn("A &amp; B", trophy)
        self.assertIn("font-size:64px", trophy)
        self.assertIn("trophy-upside-down.png", trophy)

    def test_final_podium_replaces_toilet_winner_only_in_week17(self):
        ctx = dict(week=17, postseason_data=data_for(17))
        for place, name, amount, metal in [("2nd", "Team 2", 100, "silver"),
                                         ("3rd", "Team 3", 40, "bronze")]:
            html = email._placement_award(ctx, place)
            self.assertIn(name, html)
            self.assertIn("${} payout".format(amount), html)
            self.assertIn("trophy-{}.png".format(metal), html)
        final_blocks = blocks_for(newsletter_type_for_week(17))
        self.assertNotIn("toilet_bowl_winner", final_blocks)
        self.assertIn("second_place", final_blocks)
        self.assertIn("third_place", final_blocks)
        self.assertIn("toilet_bowl_winner", blocks_for(newsletter_type_for_week(16)))
        self.assertEqual(email._placement_award(dict(postseason_data=data_for(16)), "2nd"), "")

    def test_final_power_and_standings_retain_all_twelve_teams(self):
        result = analytics_for(17)
        power = result["power_rankings"]
        self.assertEqual(len(power), 12)
        team12 = next(r for r in power if r["team_key"] == "12")
        self.assertEqual(team12["actual_losses"], 16)
        self.assertAlmostEqual(team12["season_points"], sum(104 + w / 100 for w in range(1, 17)))
        html = email.build_weekly_email_html(2025, 17, result, postseason_data=data_for(17))
        self.assertIn("Final Standings", html)
        self.assertIn("Final Power Rankings", html)
        self.assertIn("Team 12", html)

    def test_accolades_exclude_inactive_week17_players(self):
        teams, players = fixtures()
        for row in players:
            if row["week"] == 17 and row["team_key"] == "12":
                row["points"] = 99999
        with patch.object(yahoo_postseason, "load_standings", return_value=build_regular_season_standings(teams, 14)), patch.object(season_accolades, "_read_csv", side_effect=[players, teams]), patch.object(
            season_accolades, "_load_draft_results", return_value=[]
        ):
            awards = season_accolades.build_season_accolades(2025)
        mvp = next(r for r in awards if r["title"] == "Playoff MVP")
        self.assertEqual(mvp["winner"], "Player 1")

    def test_regular_season_html_matches_approved_base(self):
        # Compare the entire rendered document, not just section names.
        baseline = types.ModuleType("approved_weekly_email")
        source = subprocess.check_output([
            "git", "show", "171576fdcd619c720b9646dd64146c210b1874ef:src/leaguelab/weekly_email.py"
        ], text=True)
        exec(compile(source, "approved_weekly_email.py", "exec"), baseline.__dict__)
        for week in range(1, 14):
            result = analytics_for(week)
            upcoming = dict(week=week + 1, matchup_to_watch=0, matchups=[dict(
                team_a=dict(team_name="Team 1", power_rank=1, record="7-3", projected_points=123),
                team_b=dict(team_name="Team 2", power_rank=2, record="6-4", projected_points=115))])
            kwargs = dict(upcoming_data=upcoming)
            self.assertEqual(email.build_weekly_email_html(2025, week, result, **kwargs),
                             baseline.build_weekly_email_html(2025, week, result, **kwargs),
                             "Week {} changed".format(week))


if __name__ == "__main__":
    unittest.main()
