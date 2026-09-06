from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChallengeContext:
    season: int
    team_rows: List[Dict[str, Any]]
    player_rows: List[Dict[str, Any]]


@dataclass
class ChallengeStanding:
    team_key: str
    team_id: str
    team_name: str
    value: float
    rank: Optional[int] = None
    detail: Optional[str] = None


@dataclass
class ChallengeResult:
    challenge_id: str
    challenge_type: str
    name: str
    start_week: int
    end_week: int
    payout: float
    status: str
    standings: List[ChallengeStanding] = field(default_factory=list)
    message: Optional[str] = None


class Challenge:
    type_name = "base"

    def __init__(self, definition):
        self.definition = definition

    @property
    def challenge_id(self):
        return str(self.definition["id"])

    @property
    def name(self):
        return str(self.definition["name"])

    @property
    def start_week(self):
        return int(self.definition["start_week"])

    @property
    def end_week(self):
        return int(self.definition["end_week"])

    @property
    def payout(self):
        return float(self.definition.get("payout", 0))

    def calculate(self, context):
        raise NotImplementedError

    def result(
        self,
        standings=None,
        status="complete",
        message=None,
    ):
        return ChallengeResult(
            challenge_id=self.challenge_id,
            challenge_type=self.type_name,
            name=self.name,
            start_week=self.start_week,
            end_week=self.end_week,
            payout=self.payout,
            status=status,
            standings=standings or [],
            message=message,
        )


def rank_descending(standings):
    ordered = sorted(
        standings,
        key=lambda row: (-row.value, row.team_name.lower()),
    )

    previous_value = None
    previous_rank = 0

    for index, row in enumerate(ordered, start=1):
        if previous_value is None or row.value != previous_value:
            previous_rank = index

        row.rank = previous_rank
        previous_value = row.value

    return ordered
