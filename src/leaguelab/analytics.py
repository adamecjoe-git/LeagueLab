import csv
from collections import defaultdict
from pathlib import Path

from leaguelab.lineup import (
    player_can_fill_slot,
    solve_optimal_lineup,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_ROOT = PROJECT_ROOT / "data" / "normalized"
OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"
WEEKLY_PLAYERS_FILE = "weekly_players.csv"


# Power Ranking configuration.
# Weights must total 1.00.
POWER_WEIGHT_SEASON_SCORING = 0.30
POWER_WEIGHT_ALL_PLAY = 0.25
POWER_WEIGHT_RECENT_FORM = 0.35
POWER_WEIGHT_RECORD = 0.10

# Number of most recent weeks used for the recent-form component.
POWER_RECENT_WEEKS = 3

# Recent-form weights are ordered newest -> oldest.
# With 3 weeks: current week 50%, previous week 30%, two weeks ago 20%.
POWER_RECENT_WEEK_WEIGHTS = (0.50, 0.30, 0.20)


def read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def rank_week_rows(week_rows):
    """
    Assign competition rank by weekly score.

    Example:
        120.0 -> 1
        110.0 -> 2
        110.0 -> 2
        100.0 -> 4
    """
    sorted_scores = sorted(
        [to_float(row["points"]) for row in week_rows],
        reverse=True,
    )

    rank_by_score = {}

    for index, score in enumerate(sorted_scores, start=1):
        if score not in rank_by_score:
            rank_by_score[score] = index

    return rank_by_score


def build_all_play_rows(team_rows, end_week=14):
    """
    Build weekly all-play records.

    For each team/week:
      all_play_wins   = number of teams outscored
      all_play_losses = number of teams that outscored this team
      all_play_ties   = number of equal-score opponents

    Expected weekly wins is the team's all-play win probability for that week:
      (wins + 0.5 * ties) / number_of_opponents
    """

    by_week = defaultdict(list)

    for row in team_rows:
        week = int(row["week"])

        if week > end_week:
            continue

        by_week[week].append(row)

    output = []

    for week in sorted(by_week):
        week_rows = by_week[week]
        rank_by_score = rank_week_rows(week_rows)

        for row in week_rows:
            score = to_float(row["points"])
            wins = 0
            losses = 0
            ties = 0

            for other in week_rows:
                if other["team_key"] == row["team_key"]:
                    continue

                other_score = to_float(other["points"])

                if score > other_score:
                    wins += 1
                elif score < other_score:
                    losses += 1
                else:
                    ties += 1

            opponent_count = wins + losses + ties

            if opponent_count:
                expected_weekly_wins = (
                    wins + 0.5 * ties
                ) / opponent_count
            else:
                expected_weekly_wins = 0.0

            output.append(
                {
                    "season": int(row["season"]),
                    "week": week,
                    "team_key": row["team_key"],
                    "team_id": row["team_id"],
                    "team_name": row["team_name"],
                    "points": round(score, 2),
                    "weekly_rank": rank_by_score[score],
                    "actual_result": str(
                        row.get("result") or ""
                    ).strip().upper(),
                    "all_play_wins": wins,
                    "all_play_losses": losses,
                    "all_play_ties": ties,
                    "expected_weekly_wins": round(
                        expected_weekly_wins,
                        4,
                    ),
                }
            )

    return output


def build_weekly_team_analytics(all_play_rows):
    """
    Build cumulative weekly analytics.

    Luck Wins:
        actual equivalent wins - expected wins

    Actual equivalent wins:
        wins + 0.5 * ties

    Expected wins:
        cumulative sum of weekly all-play win probabilities
    """

    by_team = defaultdict(list)

    for row in all_play_rows:
        by_team[row["team_key"]].append(row)

    output = []

    for team_key, team_rows in by_team.items():
        team_rows = sorted(
            team_rows,
            key=lambda row: row["week"],
        )

        actual_wins = 0
        actual_losses = 0
        actual_ties = 0

        all_play_wins = 0
        all_play_losses = 0
        all_play_ties = 0

        expected_wins = 0.0
        points_for = 0.0

        for row in team_rows:
            result = row["actual_result"]

            if result == "W":
                actual_wins += 1
            elif result == "L":
                actual_losses += 1
            elif result == "T":
                actual_ties += 1

            all_play_wins += row["all_play_wins"]
            all_play_losses += row["all_play_losses"]
            all_play_ties += row["all_play_ties"]

            expected_wins += row["expected_weekly_wins"]
            points_for += row["points"]

            all_play_games = (
                all_play_wins
                + all_play_losses
                + all_play_ties
            )

            if all_play_games:
                all_play_win_pct = (
                    all_play_wins
                    + 0.5 * all_play_ties
                ) / all_play_games
            else:
                all_play_win_pct = 0.0

            actual_equivalent_wins = (
                actual_wins
                + 0.5 * actual_ties
            )

            luck_wins = (
                actual_equivalent_wins
                - expected_wins
            )

            output.append(
                {
                    "season": row["season"],
                    "week": row["week"],
                    "team_key": team_key,
                    "team_id": row["team_id"],
                    "team_name": row["team_name"],
                    "weekly_score": row["points"],
                    "weekly_rank": row["weekly_rank"],
                    "actual_result": result,
                    "actual_wins": actual_wins,
                    "actual_losses": actual_losses,
                    "actual_ties": actual_ties,
                    "points_for": round(points_for, 2),
                    "all_play_wins": all_play_wins,
                    "all_play_losses": all_play_losses,
                    "all_play_ties": all_play_ties,
                    "all_play_win_pct": round(
                        all_play_win_pct,
                        4,
                    ),
                    "expected_wins": round(
                        expected_wins,
                        2,
                    ),
                    "luck_wins": round(
                        luck_wins,
                        2,
                    ),
                }
            )

    return sorted(
        output,
        key=lambda row: (
            row["week"],
            -row["weekly_score"],
            row["team_name"].lower(),
        ),
    )



def enrich_standings_and_streaks(weekly_rows):
    """
    Add weekly standings rank, rank movement, and streak information.

    Standings ordering:
      1. Actual win percentage
      2. Points for
      3. Team name

    Rank movement is positive when a team moves UP in the standings.
    Example: previous rank 6, current rank 4 -> +2.

    Current streak examples:
      W3, L2, T1
    """

    by_week = defaultdict(list)

    for row in weekly_rows:
        by_week[row["week"]].append(row)

    previous_rank = {}
    team_history = defaultdict(list)

    for week in sorted(by_week):
        week_rows = by_week[week]

        for row in week_rows:
            games = (
                row["actual_wins"]
                + row["actual_losses"]
                + row["actual_ties"]
            )

            if games:
                row["_standings_pct"] = (
                    row["actual_wins"]
                    + 0.5 * row["actual_ties"]
                ) / games
            else:
                row["_standings_pct"] = 0.0

        ordered = sorted(
            week_rows,
            key=lambda row: (
                -row["_standings_pct"],
                -row["points_for"],
                row["team_name"].lower(),
            ),
        )

        for rank, row in enumerate(ordered, start=1):
            team_key = row["team_key"]
            old_rank = previous_rank.get(team_key)

            row["standings_rank"] = rank
            row["previous_standings_rank"] = (
                old_rank if old_rank is not None else ""
            )

            if old_rank is None:
                row["standings_movement"] = 0
            else:
                row["standings_movement"] = (
                    old_rank - rank
                )

            previous_rank[team_key] = rank

        for row in week_rows:
            history = team_history[row["team_key"]]
            result = row["actual_result"]

            if result:
                history.append(result)

            current_type = ""
            current_length = 0

            if history:
                current_type = history[-1]

                for item in reversed(history):
                    if item == current_type:
                        current_length += 1
                    else:
                        break

            longest_win = 0
            longest_loss = 0
            running_win = 0
            running_loss = 0

            for item in history:
                if item == "W":
                    running_win += 1
                    running_loss = 0
                    longest_win = max(
                        longest_win,
                        running_win,
                    )
                elif item == "L":
                    running_loss += 1
                    running_win = 0
                    longest_loss = max(
                        longest_loss,
                        running_loss,
                    )
                else:
                    running_win = 0
                    running_loss = 0

            if current_type and current_length:
                row["current_streak"] = "{}{}".format(
                    current_type,
                    current_length,
                )
            else:
                row["current_streak"] = ""

            row["longest_win_streak"] = longest_win
            row["longest_loss_streak"] = longest_loss

            del row["_standings_pct"]

    return sorted(
        weekly_rows,
        key=lambda row: (
            row["week"],
            row["standings_rank"],
            row["team_name"].lower(),
        ),
    )


def build_season_luck_rows(weekly_analytics_rows):
    """
    Return each team's latest cumulative row.

    luck_index is retained for analytical use:
        actual win pct - all-play win pct

    luck_wins is the primary human-facing metric.
    """

    latest = {}

    for row in weekly_analytics_rows:
        key = row["team_key"]

        if (
            key not in latest
            or row["week"] > latest[key]["week"]
        ):
            latest[key] = row

    output = []

    for row in latest.values():
        actual_games = (
            row["actual_wins"]
            + row["actual_losses"]
            + row["actual_ties"]
        )

        if actual_games:
            actual_win_pct = (
                row["actual_wins"]
                + 0.5 * row["actual_ties"]
            ) / actual_games
        else:
            actual_win_pct = 0.0

        luck_index = (
            actual_win_pct
            - row["all_play_win_pct"]
        )

        output.append(
            {
                "season": row["season"],
                "through_week": row["week"],
                "team_key": row["team_key"],
                "team_id": row["team_id"],
                "team_name": row["team_name"],
                "points_for": row["points_for"],
                "actual_wins": row["actual_wins"],
                "actual_losses": row["actual_losses"],
                "actual_ties": row["actual_ties"],
                "actual_win_pct": round(
                    actual_win_pct,
                    4,
                ),
                "all_play_wins": row["all_play_wins"],
                "all_play_losses": row["all_play_losses"],
                "all_play_ties": row["all_play_ties"],
                "all_play_win_pct": row["all_play_win_pct"],
                "expected_wins": row["expected_wins"],
                "luck_wins": row["luck_wins"],
                "luck_index": round(
                    luck_index,
                    4,
                ),
            }
        )

    return sorted(
        output,
        key=lambda row: (
            -row["luck_wins"],
            -row["actual_win_pct"],
            row["team_name"].lower(),
        ),
    )



def build_week_at_a_glance(
    team_rows,
    player_rows,
    week,
):
    """
    Build newsletter-ready Week at a Glance metrics.

    Team metrics use official normalized matchup/team scores.

    Highest-scoring player is the highest-scoring rostered player
    captured in weekly_players.csv for the selected week.
    """

    week_team_rows = [
        row
        for row in team_rows
        if int(row["week"]) == int(week)
    ]

    if not week_team_rows:
        return None

    ranked_teams = sorted(
        week_team_rows,
        key=lambda row: (
            -to_float(row["points"]),
            row["team_name"].lower(),
        ),
    )

    weekly_rankings = []

    for index, row in enumerate(
        ranked_teams,
        start=1,
    ):
        weekly_rankings.append(
            {
                "rank": index,
                "team_key": row["team_key"],
                "team_name": row["team_name"],
                "score": round(
                    to_float(row["points"]),
                    2,
                ),
                "result": str(
                    row.get("result") or ""
                ).strip().upper(),
                "opponent_team_name": str(
                    row.get("opponent_team_name")
                    or ""
                ).strip(),
                "opponent_points": (
                    round(
                        to_float(
                            row.get(
                                "opponent_points"
                            )
                        ),
                        2,
                    )
                    if str(
                        row.get("opponent_points")
                        or ""
                    ).strip()
                    else None
                ),
            }
        )

    highest_team = weekly_rankings[0]
    lowest_team = weekly_rankings[-1]

    # De-duplicate reciprocal matchup rows.
    seen_matchups = set()
    matchups = []

    for row in week_team_rows:
        opponent_name = str(
            row.get("opponent_team_name")
            or ""
        ).strip()

        opponent_points_raw = str(
            row.get("opponent_points")
            or ""
        ).strip()

        if (
            not opponent_name
            or not opponent_points_raw
        ):
            continue

        team_name = row["team_name"]
        matchup_key = tuple(
            sorted(
                [
                    team_name,
                    opponent_name,
                ]
            )
        )

        if matchup_key in seen_matchups:
            continue

        seen_matchups.add(matchup_key)

        team_points = to_float(
            row["points"]
        )
        opponent_points = to_float(
            row["opponent_points"]
        )

        margin = abs(
            team_points
            - opponent_points
        )

        if team_points >= opponent_points:
            winner = team_name
            loser = opponent_name
            winner_points = team_points
            loser_points = opponent_points
        else:
            winner = opponent_name
            loser = team_name
            winner_points = opponent_points
            loser_points = team_points

        matchups.append(
            {
                "winner": winner,
                "loser": loser,
                "winner_points": round(
                    winner_points,
                    2,
                ),
                "loser_points": round(
                    loser_points,
                    2,
                ),
                "margin": round(
                    margin,
                    2,
                ),
            }
        )

    closest_matchup = None
    biggest_blowout = None

    if matchups:
        closest_matchup = min(
            matchups,
            key=lambda item: (
                item["margin"],
                -item["winner_points"],
            ),
        )

        biggest_blowout = max(
            matchups,
            key=lambda item: (
                item["margin"],
                item["winner_points"],
            ),
        )

    week_player_rows = [
        row
        for row in player_rows
        if int(row["week"]) == int(week)
    ]

    def player_summary(row):
        if row is None:
            return None

        return {
            "player_key": row.get(
                "player_key",
                "",
            ),
            "player_name": row["player_name"],
            "team_name": row["team_name"],
            "nfl_team": row.get(
                "nfl_team",
                "",
            ),
            "display_position": row.get(
                "display_position",
                "",
            ),
            "lineup_slot": row.get(
                "lineup_slot",
                "",
            ),
            "points": round(
                to_float(row["points"]),
                2,
            ),
        }

    starter_rows = [
        row
        for row in week_player_rows
        if str(
            row.get("is_starter")
            or ""
        ).strip().lower()
        in {"true", "1", "yes"}
    ]

    bench_rows = [
        row
        for row in week_player_rows
        if str(
            row.get("selected_position")
            or ""
        ).strip().upper()
        == "BN"
    ]

    top_starter = None
    top_bench_player = None

    if starter_rows:
        top_starter = player_summary(
            max(
                starter_rows,
                key=lambda row: (
                    to_float(row["points"]),
                    row["player_name"].lower(),
                ),
            )
        )

    if bench_rows:
        top_bench_player = player_summary(
            max(
                bench_rows,
                key=lambda row: (
                    to_float(row["points"]),
                    row["player_name"].lower(),
                ),
            )
        )

    return {
        "week": int(week),
        "highest_team_score": highest_team,
        "lowest_team_score": lowest_team,
        "closest_matchup": closest_matchup,
        "biggest_blowout": biggest_blowout,
        "top_starter": top_starter,
        "top_bench_player": top_bench_player,
        "weekly_rankings": weekly_rankings,
    }



def is_true(value):
    return str(
        value or ""
    ).strip().lower() in {
        "true",
        "1",
        "yes",
    }


def find_biggest_legal_bench_swap(players):
    """
    Find the largest positive one-for-one legal bench substitution.

    This is intentionally stricter than simply comparing the highest
    bench score to the lowest starter score. The bench player must have
    been eligible for the actual starter's lineup slot.
    """

    starters = [
        row
        for row in players
        if is_true(
            row.get("is_starter")
        )
    ]

    bench = [
        row
        for row in players
        if str(
            row.get("selected_position")
            or ""
        ).strip().upper()
        == "BN"
    ]

    best_swap = None

    for bench_player in bench:
        for starter in starters:
            slot = str(
                starter.get("lineup_slot")
                or ""
            ).strip()

            if not slot:
                continue

            if not player_can_fill_slot(
                bench_player,
                slot,
            ):
                continue

            gain = (
                to_float(
                    bench_player.get("points")
                )
                - to_float(
                    starter.get("points")
                )
            )

            if gain <= 0:
                continue

            candidate = {
                "bench_player_key": (
                    bench_player.get(
                        "player_key",
                        "",
                    )
                ),
                "bench_player_name": (
                    bench_player.get(
                        "player_name",
                        "",
                    )
                ),
                "bench_points": round(
                    to_float(
                        bench_player.get(
                            "points"
                        )
                    ),
                    2,
                ),
                "starter_player_key": (
                    starter.get(
                        "player_key",
                        "",
                    )
                ),
                "starter_player_name": (
                    starter.get(
                        "player_name",
                        "",
                    )
                ),
                "starter_points": round(
                    to_float(
                        starter.get(
                            "points"
                        )
                    ),
                    2,
                ),
                "lineup_slot": slot,
                "points_gained": round(
                    gain,
                    2,
                ),
            }

            if (
                best_swap is None
                or candidate[
                    "points_gained"
                ]
                > best_swap[
                    "points_gained"
                ]
            ):
                best_swap = candidate

    return best_swap


def build_lineup_efficiency_rows(
    player_rows,
    end_week,
):
    """
    Calculate actual vs optimal lineup performance for every team/week.

    actual_lineup_points:
        Sum of actual starters from weekly_players.csv.

    optimal_lineup_points:
        Exact legal optimum from LeagueLab's validated lineup solver.

    points_left_on_bench:
        optimal - actual

    lineup_efficiency:
        actual / optimal * 100

    biggest_legal_bench_swap:
        Largest single legal BN-for-starter substitution.
    """

    grouped = defaultdict(list)

    for row in player_rows:
        week = int(row["week"])

        if week > end_week:
            continue

        grouped[
            (
                week,
                row["team_key"],
            )
        ].append(row)

    output = []

    for key in sorted(grouped):
        week, team_key = key
        players = grouped[key]

        starters = [
            row
            for row in players
            if is_true(
                row.get("is_starter")
            )
        ]

        actual_points = sum(
            to_float(row.get("points"))
            for row in starters
        )

        optimal = solve_optimal_lineup(
            players
        )

        optimal_points = to_float(
            optimal["total_points"]
        )

        points_left = max(
            0.0,
            optimal_points
            - actual_points,
        )

        if optimal_points > 0:
            efficiency = (
                actual_points
                / optimal_points
                * 100.0
            )
        else:
            efficiency = 100.0

        swap = find_biggest_legal_bench_swap(
            players
        )

        first = players[0]

        output.append(
            {
                "season": int(
                    first["season"]
                ),
                "week": week,
                "team_key": team_key,
                "team_id": first["team_id"],
                "team_name": (
                    first["team_name"]
                ),
                "actual_lineup_points": round(
                    actual_points,
                    2,
                ),
                "optimal_lineup_points": round(
                    optimal_points,
                    2,
                ),
                "points_left_on_bench": round(
                    points_left,
                    2,
                ),
                "lineup_efficiency": round(
                    efficiency,
                    2,
                ),
                "biggest_bench_player": (
                    swap[
                        "bench_player_name"
                    ]
                    if swap
                    else ""
                ),
                "biggest_bench_points": (
                    swap["bench_points"]
                    if swap
                    else ""
                ),
                "replaced_starter": (
                    swap[
                        "starter_player_name"
                    ]
                    if swap
                    else ""
                ),
                "replaced_starter_points": (
                    swap["starter_points"]
                    if swap
                    else ""
                ),
                "decision_slot": (
                    swap["lineup_slot"]
                    if swap
                    else ""
                ),
                "decision_points_gained": (
                    swap["points_gained"]
                    if swap
                    else 0.0
                ),
            }
        )

    return sorted(
        output,
        key=lambda row: (
            row["week"],
            row["team_name"].lower(),
        ),
    )


def build_weekly_lineup_summary(
    lineup_rows,
    week,
):
    rows = [
        row
        for row in lineup_rows
        if row["week"] == int(week)
    ]

    if not rows:
        return None

    best_efficiency = max(
        rows,
        key=lambda row: (
            row["lineup_efficiency"],
            row["actual_lineup_points"],
        ),
    )

    worst_efficiency = min(
        rows,
        key=lambda row: (
            row["lineup_efficiency"],
            -row["actual_lineup_points"],
        ),
    )

    most_left = max(
        rows,
        key=lambda row: (
            row["points_left_on_bench"],
            -row["lineup_efficiency"],
        ),
    )

    valid_decisions = [
        row
        for row in rows
        if to_float(
            row["decision_points_gained"]
        ) > 0
    ]

    worst_decision = None

    if valid_decisions:
        worst_decision = max(
            valid_decisions,
            key=lambda row: (
                to_float(
                    row[
                        "decision_points_gained"
                    ]
                ),
                row["team_name"].lower(),
            ),
        )

    return {
        "week": int(week),
        "best_efficiency": best_efficiency,
        "worst_efficiency": worst_efficiency,
        "most_points_left": most_left,
        "worst_decision": worst_decision,
    }



def percentile_scores(
    values_by_team,
    higher_is_better=True,
):
    """
    Convert a league-wide metric into a 0-100 percentile score.

    Uses average rank for ties. With 12 teams, the best team receives
    100 and the worst receives 0. This keeps metrics with different
    raw scales comparable before weighting.
    """

    if not values_by_team:
        return {}

    items = list(
        values_by_team.items()
    )

    items = sorted(
        items,
        key=lambda item: (
            item[1],
            item[0],
        ),
        reverse=higher_is_better,
    )

    count = len(items)

    if count == 1:
        return {
            items[0][0]: 100.0
        }

    output = {}
    index = 0

    while index < count:
        value = items[index][1]
        end = index

        while (
            end + 1 < count
            and items[end + 1][1] == value
        ):
            end += 1

        average_rank = (
            (index + 1)
            + (end + 1)
        ) / 2.0

        score = (
            (count - average_rank)
            / (count - 1)
            * 100.0
        )

        for position in range(
            index,
            end + 1,
        ):
            output[
                items[position][0]
            ] = score

        index = end + 1

    return output



def validate_power_ranking_config():
    weights = (
        POWER_WEIGHT_SEASON_SCORING,
        POWER_WEIGHT_ALL_PLAY,
        POWER_WEIGHT_RECENT_FORM,
        POWER_WEIGHT_RECORD,
    )

    if any(weight < 0 for weight in weights):
        raise ValueError(
            "Power Ranking weights cannot be negative."
        )

    total = sum(weights)

    if abs(total - 1.0) > 0.000001:
        raise ValueError(
            "Power Ranking weights must total 1.00; "
            "current total is {:.4f}.".format(
                total
            )
        )

    if POWER_RECENT_WEEKS < 1:
        raise ValueError(
            "POWER_RECENT_WEEKS must be at least 1."
        )

    if len(POWER_RECENT_WEEK_WEIGHTS) != POWER_RECENT_WEEKS:
        raise ValueError(
            "POWER_RECENT_WEEK_WEIGHTS must contain exactly "
            "{} values.".format(
                POWER_RECENT_WEEKS
            )
        )

    if any(
        weight < 0
        for weight in POWER_RECENT_WEEK_WEIGHTS
    ):
        raise ValueError(
            "Recent-form week weights cannot be negative."
        )

    recent_total = sum(
        POWER_RECENT_WEEK_WEIGHTS
    )

    if abs(recent_total - 1.0) > 0.000001:
        raise ValueError(
            "POWER_RECENT_WEEK_WEIGHTS must total 1.00; "
            "current total is {:.4f}.".format(
                recent_total
            )
        )


def build_weighted_recent_form(
    team_rows,
    end_week,
):
    """
    Return recency-weighted scoring form by team.

    POWER_RECENT_WEEK_WEIGHTS is ordered newest -> oldest.
    If fewer than POWER_RECENT_WEEKS are available early in a season,
    the available weights are re-normalized to total 1.00.
    """

    week_points = defaultdict(dict)

    for row in team_rows:
        week = int(row["week"])

        if week > end_week:
            continue

        week_points[
            row["team_key"]
        ][week] = to_float(
            row["points"]
        )

    output = {}

    for team_key, points_by_week in week_points.items():
        weighted_points = 0.0
        used_weight = 0.0

        for offset in range(
            POWER_RECENT_WEEKS
        ):
            week = end_week - offset

            if week < 1:
                continue

            if week not in points_by_week:
                continue

            weight = (
                POWER_RECENT_WEEK_WEIGHTS[
                    offset
                ]
            )

            weighted_points += (
                points_by_week[week]
                * weight
            )
            used_weight += weight

        output[team_key] = (
            weighted_points / used_weight
            if used_weight
            else 0.0
        )

    return output


def build_power_rankings(
    team_rows,
    weekly_analytics_rows,
    end_week,
):
    """
    Build league-relative Power Rankings through end_week.

    Overall formula is controlled by the POWER_WEIGHT_* constants.
    Recent scoring form is recency-weighted using
    POWER_RECENT_WEEK_WEIGHTS.

    Each major component is converted to a 0-100 league percentile
    before weighting.
    """

    validate_power_ranking_config()

    eligible_team_rows = [
        row
        for row in team_rows
        if int(row["week"]) <= end_week
    ]

    if not eligible_team_rows:
        return []

    team_names = {}
    season_points = defaultdict(float)
    recent_points = defaultdict(float)
    recent_games = defaultdict(int)

    recent_start = max(
        1,
        end_week - POWER_RECENT_WEEKS + 1,
    )

    for row in eligible_team_rows:
        team_key = row["team_key"]
        team_names[team_key] = (
            row["team_name"]
        )

        points = to_float(
            row["points"]
        )

        season_points[team_key] += points

        week = int(row["week"])

        if recent_start <= week <= end_week:
            recent_points[team_key] += points
            recent_games[team_key] += 1

    recent_average = {}

    for team_key in team_names:
        games = recent_games.get(
            team_key,
            0,
        )

        recent_average[team_key] = (
            recent_points.get(
                team_key,
                0.0,
            ) / games
            if games
            else 0.0
        )

    recent_form_points = (
        build_weighted_recent_form(
            eligible_team_rows,
            end_week,
        )
    )

    latest = {}

    for row in weekly_analytics_rows:
        if int(row["week"]) != end_week:
            continue

        latest[
            row["team_key"]
        ] = row

    all_play_pct = {}
    actual_win_pct = {}

    for team_key in team_names:
        row = latest.get(
            team_key,
            {},
        )

        all_play_pct[team_key] = (
            to_float(
                row.get(
                    "all_play_win_pct"
                )
            )
        )

        wins = to_float(
            row.get("actual_wins")
        )
        losses = to_float(
            row.get("actual_losses")
        )
        ties = to_float(
            row.get("actual_ties")
        )

        games = wins + losses + ties

        actual_win_pct[team_key] = (
            (wins + 0.5 * ties)
            / games
            if games
            else 0.0
        )

    scoring_component = (
        percentile_scores(
            season_points
        )
    )

    all_play_component = (
        percentile_scores(
            all_play_pct
        )
    )

    recent_component = (
        percentile_scores(
            recent_form_points
        )
    )

    record_component = (
        percentile_scores(
            actual_win_pct
        )
    )

    rankings = []

    for team_key in team_names:
        power_score = (
            scoring_component[
                team_key
            ]
            * POWER_WEIGHT_SEASON_SCORING
            + all_play_component[
                team_key
            ]
            * POWER_WEIGHT_ALL_PLAY
            + recent_component[
                team_key
            ]
            * POWER_WEIGHT_RECENT_FORM
            + record_component[
                team_key
            ]
            * POWER_WEIGHT_RECORD
        )

        latest_row = latest.get(
            team_key,
            {},
        )

        rankings.append(
            {
                "season": int(
                    eligible_team_rows[0][
                        "season"
                    ]
                ),
                "through_week": int(
                    end_week
                ),
                "team_key": team_key,
                "team_name": (
                    team_names[team_key]
                ),
                "power_score": round(
                    power_score,
                    2,
                ),
                "season_points": round(
                    season_points[
                        team_key
                    ],
                    2,
                ),
                "season_scoring_score": round(
                    scoring_component[
                        team_key
                    ],
                    2,
                ),
                "all_play_win_pct": round(
                    all_play_pct[
                        team_key
                    ],
                    4,
                ),
                "all_play_score": round(
                    all_play_component[
                        team_key
                    ],
                    2,
                ),
                "recent_start_week": (
                    recent_start
                ),
                "recent_avg_points": round(
                    recent_average[
                        team_key
                    ],
                    2,
                ),
                "recent_form_points": round(
                    recent_form_points.get(
                        team_key,
                        0.0,
                    ),
                    2,
                ),
                "recent_form_score": round(
                    recent_component[
                        team_key
                    ],
                    2,
                ),
                "actual_wins": int(
                    to_float(
                        latest_row.get(
                            "actual_wins"
                        )
                    )
                ),
                "actual_losses": int(
                    to_float(
                        latest_row.get(
                            "actual_losses"
                        )
                    )
                ),
                "actual_ties": int(
                    to_float(
                        latest_row.get(
                            "actual_ties"
                        )
                    )
                ),
                "actual_win_pct": round(
                    actual_win_pct[
                        team_key
                    ],
                    4,
                ),
                "record_score": round(
                    record_component[
                        team_key
                    ],
                    2,
                ),
            }
        )

    rankings = sorted(
        rankings,
        key=lambda row: (
            -row["power_score"],
            -row["season_points"],
            row["team_name"].lower(),
        ),
    )

    for rank, row in enumerate(
        rankings,
        start=1,
    ):
        row["power_rank"] = rank

    return rankings


def build_schedule_strength_rows(
    team_rows,
    all_play_rows,
    end_week,
):
    """
    Build Strength of Schedule (SOS).

    SOS measures how difficult each team's actual opponents performed
    in the specific weeks they were faced. The opponent's weekly
    all-play win probability is used rather than season record.
    """

    weekly_ap = {}

    for row in all_play_rows:
        weekly_ap[
            (
                int(row["week"]),
                row["team_key"],
            )
        ] = to_float(
            row["expected_weekly_wins"]
        )

    eligible = [
        row
        for row in team_rows
        if int(row["week"]) <= end_week
    ]

    teams = {}
    opponent_strengths = defaultdict(list)
    opponent_scores = defaultdict(list)

    for row in eligible:
        team_key = row["team_key"]
        teams[team_key] = {
            "team_id": row.get(
                "team_id",
                "",
            ),
            "team_name": row["team_name"],
            "season": int(row["season"]),
        }

        opponent_key = str(
            row.get(
                "opponent_team_key"
            )
            or ""
        ).strip()

        opponent_name = str(
            row.get(
                "opponent_team_name"
            )
            or ""
        ).strip()

        if not opponent_key and not opponent_name:
            continue

        week = int(row["week"])

        if opponent_key:
            opponent_ap = weekly_ap.get(
                (
                    week,
                    opponent_key,
                )
            )
        else:
            opponent_ap = None

        if opponent_ap is None:
            # Fallback by opponent name for older normalized data.
            opponent_ap = next(
                (
                    to_float(
                        ap_row[
                            "expected_weekly_wins"
                        ]
                    )
                    for ap_row in all_play_rows
                    if int(ap_row["week"]) == week
                    and ap_row["team_name"] == opponent_name
                ),
                None,
            )

        if opponent_ap is None:
            continue

        opponent_strengths[
            team_key
        ].append(
            opponent_ap
        )

        opponent_score = row.get(
            "opponent_points"
        )

        if str(
            opponent_score
            or ""
        ).strip():
            opponent_scores[
                team_key
            ].append(
                to_float(
                    opponent_score
                )
            )

    rows = []

    for team_key, metadata in teams.items():
        sos_values = opponent_strengths.get(
            team_key,
            [],
        )
        opp_scores = opponent_scores.get(
            team_key,
            [],
        )

        sos = (
            sum(sos_values)
            / len(sos_values)
            if sos_values
            else 0.0
        )

        avg_opponent_score = (
            sum(opp_scores)
            / len(opp_scores)
            if opp_scores
            else 0.0
        )

        rows.append(
            {
                "season": metadata[
                    "season"
                ],
                "through_week": int(
                    end_week
                ),
                "team_key": team_key,
                "team_id": metadata[
                    "team_id"
                ],
                "team_name": metadata[
                    "team_name"
                ],
                "games_with_opponent": len(
                    sos_values
                ),
                "avg_opponent_score": round(
                    avg_opponent_score,
                    2,
                ),
                "strength_of_schedule": round(
                    sos,
                    4,
                ),
            }
        )

    rows = sorted(
        rows,
        key=lambda row: (
            -to_float(
                row[
                    "strength_of_schedule"
                ]
            ),
            row["team_name"].lower(),
        ),
    )

    for rank, row in enumerate(
        rows,
        start=1,
    ):
        row["sos_rank"] = rank

    return rows


def save_week_at_a_glance_csv(
    path,
    glance,
):
    rows = []

    for row in glance["weekly_rankings"]:
        rows.append(
            {
                "week": glance["week"],
                "rank": row["rank"],
                "team_key": row["team_key"],
                "team_name": row["team_name"],
                "score": row["score"],
                "result": row["result"],
                "opponent_team_name": (
                    row["opponent_team_name"]
                ),
                "opponent_points": (
                    row["opponent_points"]
                ),
            }
        )

    save_csv(
        path,
        rows,
        [
            "week",
            "rank",
            "team_key",
            "team_name",
            "score",
            "result",
            "opponent_team_name",
            "opponent_points",
        ],
    )


def save_csv(path, rows, fieldnames):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
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


def run_weekly_analytics(season, end_week=14):
    source = (
        NORMALIZED_ROOT
        / str(season)
        / "weekly_team_results.csv"
    )

    if not source.exists():
        raise RuntimeError(
            "Missing normalized team results:\n{}".format(
                source
            )
        )

    team_rows = read_csv(source)

    player_source = (
        NORMALIZED_ROOT
        / str(season)
        / WEEKLY_PLAYERS_FILE
    )

    if not player_source.exists():
        raise RuntimeError(
            "Missing normalized player results:\n{}".format(
                player_source
            )
        )

    player_rows = read_csv(
        player_source
    )

    all_play_rows = build_all_play_rows(
        team_rows,
        end_week=end_week,
    )

    weekly_analytics_rows = (
        build_weekly_team_analytics(
            all_play_rows
        )
    )

    weekly_analytics_rows = (
        enrich_standings_and_streaks(
            weekly_analytics_rows
        )
    )

    luck_rows = build_season_luck_rows(
        weekly_analytics_rows
    )

    lineup_efficiency_rows = (
        build_lineup_efficiency_rows(
            player_rows,
            end_week,
        )
    )

    lineup_summary = (
        build_weekly_lineup_summary(
            lineup_efficiency_rows,
            end_week,
        )
    )

    power_rankings = (
        build_power_rankings(
            team_rows,
            weekly_analytics_rows,
            end_week,
        )
    )

    schedule_strength = (
        build_schedule_strength_rows(
            team_rows,
            all_play_rows,
            end_week,
        )
    )

    output_dir = (
        OUTPUT_ROOT
        / str(season)
        / "analytics"
    )

    week_at_a_glance = (
        build_week_at_a_glance(
            team_rows,
            player_rows,
            end_week,
        )
    )

    week_at_a_glance_path = (
        output_dir
        / "week_{:02d}_at_a_glance.csv".format(
            end_week
        )
    )

    lineup_efficiency_path = (
        output_dir
        / "weekly_lineup_efficiency.csv"
    )

    power_rankings_path = (
        output_dir
        / "power_rankings.csv"
    )

    schedule_strength_path = (
        output_dir
        / "schedule_strength.csv"
    )

    all_play_path = (
        output_dir
        / "weekly_all_play.csv"
    )

    weekly_analytics_path = (
        output_dir
        / "weekly_team_analytics.csv"
    )

    luck_path = (
        output_dir
        / "season_luck.csv"
    )

    save_csv(
        all_play_path,
        all_play_rows,
        [
            "season",
            "week",
            "team_key",
            "team_id",
            "team_name",
            "points",
            "weekly_rank",
            "actual_result",
            "all_play_wins",
            "all_play_losses",
            "all_play_ties",
            "expected_weekly_wins",
        ],
    )

    save_csv(
        weekly_analytics_path,
        weekly_analytics_rows,
        [
            "season",
            "week",
            "team_key",
            "team_id",
            "team_name",
            "weekly_score",
            "weekly_rank",
            "actual_result",
            "actual_wins",
            "actual_losses",
            "actual_ties",
            "points_for",
            "all_play_wins",
            "all_play_losses",
            "all_play_ties",
            "all_play_win_pct",
            "expected_wins",
            "luck_wins",
            "standings_rank",
            "previous_standings_rank",
            "standings_movement",
            "current_streak",
            "longest_win_streak",
            "longest_loss_streak",
        ],
    )

    save_csv(
        luck_path,
        luck_rows,
        [
            "season",
            "through_week",
            "team_key",
            "team_id",
            "team_name",
            "points_for",
            "actual_wins",
            "actual_losses",
            "actual_ties",
            "actual_win_pct",
            "all_play_wins",
            "all_play_losses",
            "all_play_ties",
            "all_play_win_pct",
            "expected_wins",
            "luck_wins",
            "luck_index",
        ],
    )

    if week_at_a_glance is not None:
        save_week_at_a_glance_csv(
            week_at_a_glance_path,
            week_at_a_glance,
        )

    save_csv(
        lineup_efficiency_path,
        lineup_efficiency_rows,
        [
            "season",
            "week",
            "team_key",
            "team_id",
            "team_name",
            "actual_lineup_points",
            "optimal_lineup_points",
            "points_left_on_bench",
            "lineup_efficiency",
            "biggest_bench_player",
            "biggest_bench_points",
            "replaced_starter",
            "replaced_starter_points",
            "decision_slot",
            "decision_points_gained",
        ],
    )

    save_csv(
        power_rankings_path,
        power_rankings,
        [
            "season",
            "through_week",
            "power_rank",
            "team_key",
            "team_name",
            "power_score",
            "season_points",
            "season_scoring_score",
            "all_play_win_pct",
            "all_play_score",
            "recent_start_week",
            "recent_avg_points",
            "recent_form_points",
            "recent_form_score",
            "actual_wins",
            "actual_losses",
            "actual_ties",
            "actual_win_pct",
            "record_score",
        ],
    )

    save_csv(
        schedule_strength_path,
        schedule_strength,
        [
            "season",
            "through_week",
            "sos_rank",
            "team_key",
            "team_id",
            "team_name",
            "games_with_opponent",
            "avg_opponent_score",
            "strength_of_schedule",
        ],
    )

    return {
        "all_play": all_play_rows,
        "weekly_analytics": weekly_analytics_rows,
        "luck": luck_rows,
        "week_at_a_glance": week_at_a_glance,
        "lineup_efficiency": lineup_efficiency_rows,
        "lineup_summary": lineup_summary,
        "power_rankings": power_rankings,
        "schedule_strength": schedule_strength,
        "all_play_path": all_play_path,
        "weekly_analytics_path": (
            weekly_analytics_path
        ),
        "luck_path": luck_path,
        "week_at_a_glance_path": (
            week_at_a_glance_path
        ),
        "lineup_efficiency_path": (
            lineup_efficiency_path
        ),
        "power_rankings_path": (
            power_rankings_path
        ),
        "schedule_strength_path": (
            schedule_strength_path
        ),
    }
