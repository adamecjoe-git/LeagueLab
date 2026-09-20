"""Offline regression checks for the unified Yahoo normalizer."""
import unittest
from pathlib import Path
from unittest.mock import patch

from leaguelab import normalize as normalizer
from leaguelab import normalize_with_slots as legacy


class NormalizerTests(unittest.TestCase):
    def team_rows(self, first, second, paired=True):
        teams = {"a": {"team_id": 1, "team_name": "Alpha"},
                 "b": {"team_id": 2, "team_name": "Beta"}}

        def load(path):
            return path.name

        def points(payload):
            return (first if payload == "team_1_stats.json" else second, 100)

        with patch.object(normalizer, "load_json", side_effect=load), \
             patch.object(normalizer, "extract_team_points", side_effect=points), \
             patch.object(normalizer, "extract_scoreboard_team_records", return_value={}), \
             patch.object(normalizer, "extract_matchups", return_value=[("a", "b")] if paired else []):
            return normalizer.build_weekly_team_results(2025, Path("unused"), teams)

    def test_reciprocal_scores_repair_results(self):
        rows = self.team_rows(100, 80)
        self.assertEqual([(r["opponent_points"], r["result"]) for r in rows[:2]],
                         [(80, "W"), (100, "L")])

    def test_zero_is_a_real_score(self):
        rows = self.team_rows(0, 0)
        self.assertEqual([r["result"] for r in rows[:2]], ["T", "T"])
        rows = self.team_rows(0, 10)
        self.assertEqual([r["result"] for r in rows[:2]], ["L", "W"])

    def test_missing_score_has_no_result(self):
        rows = self.team_rows(None, 10)
        self.assertTrue(all(r["result"] is None for r in rows))

    def test_no_matchup_does_not_invent_results(self):
        rows = self.team_rows(120, 100, paired=False)
        self.assertTrue(all(r["result"] is None and r["opponent_points"] is None for r in rows))

    def test_touchdowns_exclude_passing_and_conversions(self):
        stats = {"stats": [{"stat": {"stat_id": str(i), "value": v}}
                            for i, v in [(5, "4"), (10, "2"), (13, "1"), (15, "1"),
                                         (35, "1"), (49, "1"), (57, "1"), (18, "2")]]}
        self.assertEqual(normalizer.extract_touchdowns(stats), 7)
        self.assertEqual(normalizer.extract_touchdowns(None), 0)

    def test_repeated_lineup_slots_are_preserved(self):
        rows = [{"selected_position": p} for p in ["RB", "RB", "W/R/T", "W/R/T", "BN"]]
        self.assertEqual([r["lineup_slot"] for r in normalizer.assign_lineup_slots(rows)],
                         ["RB1", "RB2", "FLEX1", "FLEX2", "BN1"])

    def test_legacy_entry_point_uses_same_implementation(self):
        self.assertIs(legacy.normalize, normalizer.normalize)
        self.assertIs(legacy.parse_week_players, normalizer.parse_week_players)


if __name__ == "__main__":
    unittest.main()
