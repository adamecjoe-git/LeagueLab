from collections import defaultdict

from .base import (
    Challenge,
    ChallengeStanding,
    rank_descending,
)
from .registry import register_challenge
from leaguelab.lineup import solve_optimal_lineup


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_bool(value):
    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
        "y",
    }


def _team_identity(row):
    return (
        str(row["team_key"]),
        str(row["team_id"]),
        str(row["team_name"]),
    )


def _starter_rows(context, start_week, end_week):
    return [
        row
        for row in context.player_rows
        if start_week <= int(row["week"]) <= end_week
        and _to_bool(row["is_starter"])
    ]


@register_challenge
class HotStartChallenge(Challenge):
    type_name = "hot_start"

    def calculate(self, context):
        totals = defaultdict(float)
        teams = {}

        for row in _starter_rows(
            context,
            self.start_week,
            self.end_week,
        ):
            key = str(row["team_key"])
            totals[key] += _to_float(row["points"])
            teams[key] = _team_identity(row)

        standings = [
            ChallengeStanding(
                team_key=key,
                team_id=teams[key][1],
                team_name=teams[key][2],
                value=round(value, 2),
                detail="Total starting lineup points",
            )
            for key, value in totals.items()
        ]

        return self.result(
            standings=rank_descending(standings)
        )


@register_challenge
class DynamicDuoChallenge(Challenge):
    type_name = "dynamic_duo"

    def calculate(self, context):
        weekly = defaultdict(list)
        teams = {}

        for row in _starter_rows(
            context,
            self.start_week,
            self.end_week,
        ):
            key = str(row["team_key"])
            week = int(row["week"])

            weekly[(key, week)].append(
                _to_float(row["points"])
            )
            teams[key] = _team_identity(row)

        totals = defaultdict(float)

        for (team_key, _week), scores in weekly.items():
            totals[team_key] += sum(
                sorted(scores, reverse=True)[:2]
            )

        standings = [
            ChallengeStanding(
                team_key=key,
                team_id=teams[key][1],
                team_name=teams[key][2],
                value=round(value, 2),
                detail="Top two starters each week, combined",
            )
            for key, value in totals.items()
        ]

        return self.result(
            standings=rank_descending(standings)
        )


@register_challenge
class FlexAppealChallenge(Challenge):
    type_name = "flex_appeal"

    def calculate(self, context):
        totals = defaultdict(float)
        teams = {}

        for row in _starter_rows(
            context,
            self.start_week,
            self.end_week,
        ):
            if row["selected_position"] != "W/R/T":
                continue

            key = str(row["team_key"])
            totals[key] += _to_float(row["points"])
            teams[key] = _team_identity(row)

        standings = [
            ChallengeStanding(
                team_key=key,
                team_id=teams[key][1],
                team_name=teams[key][2],
                value=round(value, 2),
                detail="Starting W/R/T points",
            )
            for key, value in totals.items()
        ]

        return self.result(
            standings=rank_descending(standings)
        )


@register_challenge
class NoWeakLinksChallenge(Challenge):
    type_name = "no_weak_links"

    def calculate(self, context):
        weekly = defaultdict(list)
        teams = {}

        for row in _starter_rows(
            context,
            self.start_week,
            self.end_week,
        ):
            key = str(row["team_key"])
            week = int(row["week"])

            weekly[(key, week)].append(
                _to_float(row["points"])
            )
            teams[key] = _team_identity(row)

        totals = defaultdict(float)

        for (team_key, _week), scores in weekly.items():
            if scores:
                totals[team_key] += min(scores)

        standings = [
            ChallengeStanding(
                team_key=key,
                team_id=teams[key][1],
                team_name=teams[key][2],
                value=round(value, 2),
                detail="Lowest-scoring starter each week, combined",
            )
            for key, value in totals.items()
        ]

        return self.result(
            standings=rank_descending(standings)
        )


@register_challenge
class FinishStrongChallenge(Challenge):
    type_name = "finish_strong"

    def calculate(self, context):
        baseline_end_week = int(
            self.definition.get(
                "baseline_end_week",
                self.start_week - 1,
            )
        )

        team_week_scores = {}
        teams = {}

        for row in context.team_rows:
            week = int(row["week"])

            if week > self.end_week:
                continue

            key = str(row["team_key"])
            team_week_scores[(key, week)] = _to_float(
                row["points"]
            )
            teams[key] = _team_identity(row)

        standings = []

        for team_key, identity in teams.items():
            baseline_scores = [
                team_week_scores[(team_key, week)]
                for week in range(1, baseline_end_week + 1)
                if (team_key, week) in team_week_scores
            ]

            challenge_scores = [
                team_week_scores[(team_key, week)]
                for week in range(
                    self.start_week,
                    self.end_week + 1,
                )
                if (team_key, week) in team_week_scores
            ]

            if not baseline_scores or not challenge_scores:
                continue

            baseline_average = (
                sum(baseline_scores)
                / len(baseline_scores)
            )

            expected = (
                baseline_average
                * len(challenge_scores)
            )

            actual = sum(challenge_scores)
            improvement = actual - expected

            standings.append(
                ChallengeStanding(
                    team_key=team_key,
                    team_id=identity[1],
                    team_name=identity[2],
                    value=round(improvement, 2),
                    detail=(
                        "Challenge points {:.2f}; "
                        "baseline expectation {:.2f}"
                    ).format(actual, expected),
                )
            )

        return self.result(
            standings=rank_descending(standings)
        )


@register_challenge
class SeasonScoringChallenge(Challenge):
    type_name = "season_scoring"

    def calculate(self, context):
        totals = defaultdict(float)
        teams = {}

        for row in context.team_rows:
            week = int(row["week"])

            if not (
                self.start_week
                <= week
                <= self.end_week
            ):
                continue

            key = str(row["team_key"])
            totals[key] += _to_float(row["points"])
            teams[key] = _team_identity(row)

        standings = [
            ChallengeStanding(
                team_key=key,
                team_id=teams[key][1],
                team_name=teams[key][2],
                value=round(value, 2),
                detail="Regular-season points",
            )
            for key, value in totals.items()
        ]

        return self.result(
            standings=rank_descending(standings)
        )


@register_challenge
class PerfectLineupChallenge(Challenge):
    type_name = "perfect_lineup"

    def calculate(self, context):
        """
        Highest lineup efficiency across the configured weeks.

        Efficiency =
            total actual starter points
            /
            total optimal legal lineup points

        Using totals across the full challenge period avoids
        weighting a low-scoring week differently from a
        high-scoring week.
        """

        grouped = defaultdict(list)
        teams = {}

        for row in context.player_rows:
            week = int(row["week"])

            if not (
                self.start_week
                <= week
                <= self.end_week
            ):
                continue

            key = str(row["team_key"])
            grouped[(key, week)].append(row)
            teams[key] = _team_identity(row)

        team_actual = defaultdict(float)
        team_optimal = defaultdict(float)
        weekly_details = defaultdict(list)

        for (
            team_key,
            week,
        ), players in grouped.items():

            actual = sum(
                _to_float(
                    player["points"]
                )
                for player in players
                if _to_bool(
                    player["is_starter"]
                )
            )

            optimal_result = (
                solve_optimal_lineup(
                    players
                )
            )

            optimal = _to_float(
                optimal_result[
                    "total_points"
                ]
            )

            team_actual[
                team_key
            ] += actual

            team_optimal[
                team_key
            ] += optimal

            weekly_details[
                team_key
            ].append(
                (
                    week,
                    actual,
                    optimal,
                )
            )

        standings = []

        for team_key, actual in (
            team_actual.items()
        ):
            optimal = team_optimal[
                team_key
            ]

            if optimal <= 0:
                continue

            efficiency = (
                actual
                / optimal
                * 100.0
            )

            details = sorted(
                weekly_details[
                    team_key
                ],
                key=lambda item: item[0],
            )

            detail = "; ".join(
                "W{} {:.2f}/{:.2f} ({:.1f}%)".format(
                    week,
                    week_actual,
                    week_optimal,
                    (
                        week_actual
                        / week_optimal
                        * 100.0
                    )
                    if week_optimal > 0
                    else 0.0,
                )
                for (
                    week,
                    week_actual,
                    week_optimal,
                ) in details
            )

            detail += (
                "; Total {:.2f}/{:.2f}".format(
                    actual,
                    optimal,
                )
            )

            standings.append(
                ChallengeStanding(
                    team_key=team_key,
                    team_id=teams[
                        team_key
                    ][1],
                    team_name=teams[
                        team_key
                    ][2],
                    value=round(
                        efficiency,
                        2,
                    ),
                    detail=detail,
                )
            )

        return self.result(
            standings=rank_descending(
                standings
            )
        )


@register_challenge
class DepthChargeChallenge(Challenge):
    type_name = "depth_charge"

    def calculate(self, context):
        """
        Most combined points from:
        RB2 + WR2 + FLEX1 + FLEX2
        across the configured challenge weeks.
        """

        target_slots = {
            "RB2",
            "WR2",
            "FLEX1",
            "FLEX2",
        }

        totals = defaultdict(float)
        teams = {}
        detail_scores = defaultdict(list)

        for row in _starter_rows(
            context,
            self.start_week,
            self.end_week,
        ):
            lineup_slot = row.get(
                "lineup_slot"
            )

            if lineup_slot not in target_slots:
                continue

            key = str(row["team_key"])
            points = _to_float(
                row["points"]
            )

            totals[key] += points
            teams[key] = _team_identity(row)

            detail_scores[key].append(
                (
                    int(row["week"]),
                    lineup_slot,
                    str(row["player_name"]),
                    points,
                )
            )

        standings = []

        for key, value in totals.items():
            contributions = sorted(
                detail_scores[key],
                key=lambda item: (
                    item[0],
                    item[1],
                ),
            )

            detail = "; ".join(
                "W{} {} {} {:.2f}".format(
                    week,
                    slot,
                    player,
                    points,
                )
                for (
                    week,
                    slot,
                    player,
                    points,
                ) in contributions
            )

            standings.append(
                ChallengeStanding(
                    team_key=key,
                    team_id=teams[key][1],
                    team_name=teams[key][2],
                    value=round(value, 2),
                    detail=detail,
                )
            )

        return self.result(
            standings=rank_descending(
                standings
            )
        )
