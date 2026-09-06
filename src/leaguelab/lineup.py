from functools import lru_cache


DEFAULT_STARTING_SLOTS = (
    "QB1",
    "RB1",
    "RB2",
    "WR1",
    "WR2",
    "TE1",
    "FLEX1",
    "FLEX2",
    "DEF1",
)


INACTIVE_POSITIONS = {
    "IR",
    "IL",
    "NA",
}


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_eligible_positions(value):
    """
    Convert normalized pipe-delimited eligible positions
    into a set.
    """

    if value is None:
        return set()

    if isinstance(value, (list, tuple, set)):
        return {
            str(item).strip()
            for item in value
            if str(item).strip()
        }

    return {
        item.strip()
        for item in str(value).split("|")
        if item.strip()
    }


def slot_base_position(slot):
    """
    Convert LeagueLab slot names to eligibility positions.

    Examples:
        QB1   -> QB
        RB2   -> RB
        WR1   -> WR
        TE1   -> TE
        DEF1  -> DEF
        FLEX1 -> FLEX
    """

    if slot.startswith("FLEX"):
        return "FLEX"

    if slot.startswith("DEF"):
        return "DEF"

    if slot.startswith("QB"):
        return "QB"

    if slot.startswith("RB"):
        return "RB"

    if slot.startswith("WR"):
        return "WR"

    if slot.startswith("TE"):
        return "TE"

    if slot.startswith("K"):
        return "K"

    return slot


def player_can_fill_slot(player, slot):
    eligible = parse_eligible_positions(
        player.get("eligible_positions")
    )

    base = slot_base_position(slot)

    if base == "FLEX":
        return bool(
            eligible.intersection(
                {
                    "RB",
                    "WR",
                    "TE",
                    "W/R/T",
                }
            )
        )

    return base in eligible


def is_available_for_optimal_lineup(player):
    """
    Exclude players occupying Yahoo inactive/reserve slots.

    Bench players are included because they could have been
    started. IR/IL/NA players are excluded because they were
    not in an active lineup slot for that week.
    """

    selected_position = str(
        player.get("selected_position")
        or ""
    ).strip()

    return (
        selected_position
        not in INACTIVE_POSITIONS
    )


def solve_optimal_lineup(
    players,
    starting_slots=None,
):
    """
    Return the highest-scoring legal lineup for one team/week.

    Uses exact dynamic programming / backtracking, not a greedy
    assignment, so multi-position eligibility and FLEX slots are
    handled correctly.

    Returns:
        {
            "total_points": float,
            "assignments": [
                {
                    "slot": ...,
                    "player_key": ...,
                    "player_name": ...,
                    "points": ...,
                },
                ...
            ]
        }
    """

    if starting_slots is None:
        starting_slots = DEFAULT_STARTING_SLOTS

    candidate_players = [
        player
        for player in players
        if is_available_for_optimal_lineup(
            player
        )
    ]

    # Stable ordering makes results reproducible.
    candidate_players = sorted(
        candidate_players,
        key=lambda player: (
            str(player.get("player_key") or ""),
            str(player.get("player_name") or ""),
        ),
    )

    points = tuple(
        _to_float(
            player.get("points")
        )
        for player in candidate_players
    )

    eligible_indexes = []

    for slot in starting_slots:
        indexes = tuple(
            index
            for index, player
            in enumerate(candidate_players)
            if player_can_fill_slot(
                player,
                slot,
            )
        )

        eligible_indexes.append(
            indexes
        )

    @lru_cache(maxsize=None)
    def best(slot_index, used_mask):
        if slot_index >= len(
            starting_slots
        ):
            return (
                0.0,
                (),
            )

        best_score = None
        best_assignment = None

        for player_index in (
            eligible_indexes[
                slot_index
            ]
        ):
            bit = (
                1
                << player_index
            )

            if used_mask & bit:
                continue

            remainder_score, remainder = (
                best(
                    slot_index + 1,
                    used_mask | bit,
                )
            )

            score = (
                points[player_index]
                + remainder_score
            )

            if (
                best_score is None
                or score > best_score
            ):
                best_score = score
                best_assignment = (
                    (player_index,)
                    + remainder
                )

        if best_score is None:
            # No legal player for this slot. This supports unusual
            # historical weeks where a roster cannot fill all slots.
            remainder_score, remainder = (
                best(
                    slot_index + 1,
                    used_mask,
                )
            )

            return (
                remainder_score,
                (None,)
                + remainder
            )

        return (
            best_score,
            best_assignment,
        )

    total_points, assignment_indexes = (
        best(
            0,
            0,
        )
    )

    assignments = []

    for slot, player_index in zip(
        starting_slots,
        assignment_indexes,
    ):
        if player_index is None:
            assignments.append(
                {
                    "slot": slot,
                    "player_key": None,
                    "player_name": None,
                    "points": 0.0,
                }
            )
            continue

        player = candidate_players[
            player_index
        ]

        assignments.append(
            {
                "slot": slot,
                "player_key": player.get(
                    "player_key"
                ),
                "player_name": player.get(
                    "player_name"
                ),
                "points": round(
                    points[player_index],
                    2,
                ),
            }
        )

    return {
        "total_points": round(
            total_points,
            2,
        ),
        "assignments": assignments,
    }
