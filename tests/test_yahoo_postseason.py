from pathlib import Path
import unittest
from unittest.mock import patch

from leaguelab import yahoo_postseason as yahoo
from leaguelab.postseason import build_regular_season_standings
from leaguelab.postseason_newsletter import build_postseason_newsletter_data
from test_postseason_newsletter import fixtures, yahoo_fixture


class OfficialPostseasonTests(unittest.TestCase):
    def setUp(self):
        self.teams, self.players = fixtures()
        standings = build_regular_season_standings(self.teams, 14)
        self.raw = yahoo_fixture(standings, self.teams, self.players)
        self.root_patch = patch.object(yahoo, "league_root", return_value=Path("/fixture"))
        self.read_patch = patch.object(yahoo, "read", side_effect=lambda p: self.raw[str(p)])
        self.root_patch.start()
        self.read_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.read_patch.stop)

    def test_blank_results_and_final_rank_cannot_change_seeds(self):
        for row in self.teams:
            row["result"] = ""
            if int(row["team_key"]) >= 9 and row["week"] > 14:
                row["points"] = 0
        standings = yahoo.load_standings(2025, self.teams)
        self.assertEqual([r["team_key"] for r in standings], [str(i) for i in range(1, 13)])
        bracket = yahoo.build_bracket(2025, self.teams, standings, 17, 14)
        pairs = [(m["team_a"]["seed"], m["team_b"]["seed"]) for m in bracket["quarterfinals"]]
        self.assertEqual(pairs, [(1, 8), (4, 5), (3, 6), (2, 7)])
        self.assertEqual(bracket["champion"]["seed"], 1)

    def test_reported_2025_quarterfinals(self):
        names = ["Hoss Hunter", "Needs Rework", "SCLSU Mud Dogs", "Hawk Tua Taco Viola",
                 "All Gas No Brake", "Freelance Honey Badgers", "MadMagicians",
                 "Krysstynn's Connvyctsss", "T-1000", "Xmus Jaxon Flaxon-Waxon",
                 "Adam's Amazing Team", "Ray Finkle"]
        scores = [147.90, 127.46, 118.58, 99.74, 114.92, 126.00, 115.56, 126.50]
        for i, team in enumerate(self.raw["/fixture/standings.json"]["teams"]):
            team["team"][0]["name"] = names[i]
        for match in self.raw["/fixture/weeks/week_15/scoreboard.json"]["matchups"]:
            raw = match["matchup"]
            keys = []
            for team in raw["teams"]:
                key = team["team"][0]["team_key"]
                keys.append(key)
                team["team"][1]["team_points"]["total"] = str(scores[int(key)-1])
            raw["winner_team_key"] = max(keys, key=lambda k: scores[int(k)-1])
        standings = yahoo.load_standings(2025, self.teams)
        bracket = yahoo.build_bracket(2025, self.teams, standings, 15, 14)
        self.assertEqual([m["winner_name"] for m in bracket["quarterfinals"]],
                         ["Hoss Hunter", "All Gas No Brake", "Freelance Honey Badgers", "Needs Rework"])
        self.assertEqual([r["team_name"] for r in standings[8:]], names[8:])

    def test_scoreboard_overrides_normalized_zero_and_future_is_hidden(self):
        for row in self.teams:
            if row["week"] >= 15:
                row["points"] = 0
        standings = yahoo.load_standings(2025, self.teams)
        for week in (14, 15, 16, 17):
            bracket = yahoo.build_bracket(2025, self.teams, standings, week, 14)
            qf = bracket["quarterfinals"][0]
            self.assertEqual(qf["team_a"]["score"], 137.15 if week >= 15 else None)
            self.assertEqual(bool(bracket["champion"]), week == 17)

    def test_missing_official_game_fails_instead_of_using_player_totals(self):
        self.raw["/fixture/weeks/week_15/scoreboard.json"]["matchups"].pop()
        standings = yahoo.load_standings(2025, self.teams)
        with self.assertRaisesRegex(RuntimeError, "missing expected matchup"):
            yahoo.build_bracket(2025, self.teams, standings, 15, 14)

    def test_incomplete_seeding_rejected(self):
        self.raw["/fixture/standings.json"]["teams"][0]["team"][1]["team_standings"].pop("playoff_seed")
        with self.assertRaisesRegex(RuntimeError, "eight distinct playoff seeds"):
            yahoo.load_standings(2025, self.teams)

    def test_yahoo_winner_controls_tie_advancement(self):
        match = self.raw["/fixture/weeks/week_15/scoreboard.json"]["matchups"][0]["matchup"]
        for team in match["teams"]:
            team["team"][1]["team_points"]["total"] = "100"
        match["winner_team_key"] = "8"
        standings = yahoo.load_standings(2025, self.teams)
        bracket = yahoo.build_bracket(2025, self.teams, standings, 15, 14)
        self.assertEqual(bracket["championship_semifinals"][0]["team_a"]["team_key"], "8")

    def test_nonqualifiers_populate_toilet_bowl(self):
        for row in self.teams:
            row["result"] = ""
        from leaguelab import postseason_newsletter as newsletter
        with patch.object(newsletter, "_read_csv", side_effect=[self.teams, self.players]):
            data = build_postseason_newsletter_data(2025, 17, {})
        self.assertEqual([r["team_key"] for r in data["final_standings"][-4:]], ["9", "10", "11", "12"])
        preview = data["toilet_bowl"]["preview"]
        self.assertEqual({m[s]["team_key"] for m in preview for s in ("team_a", "team_b")}, {"9", "10", "11", "12"})
