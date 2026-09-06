import csv
import json
from dataclasses import asdict
from pathlib import Path

from .base import ChallengeContext
from .registry import get_challenge_class

# Import registers built-in challenge types.
from . import standard  # noqa: F401


PROJECT_ROOT = Path(__file__).resolve().parents[3]

NORMALIZED_ROOT = (
    PROJECT_ROOT
    / "data"
    / "normalized"
)

CONFIG_ROOT = (
    PROJECT_ROOT
    / "data"
    / "config"
)


def read_csv(path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        return list(
            csv.DictReader(file)
        )


def load_challenge_config(season):
    path = (
        CONFIG_ROOT
        / str(season)
        / "challenges.json"
    )

    if not path.exists():
        raise RuntimeError(
            "No challenge configuration found:\n{}".format(path)
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def run_challenges(season):
    season_dir = (
        NORMALIZED_ROOT
        / str(season)
    )

    team_path = (
        season_dir
        / "weekly_team_results.csv"
    )

    player_path = (
        season_dir
        / "weekly_players.csv"
    )

    if not team_path.exists():
        raise RuntimeError(
            "Missing normalized team data:\n{}".format(team_path)
        )

    if not player_path.exists():
        raise RuntimeError(
            "Missing normalized player data:\n{}".format(player_path)
        )

    config = load_challenge_config(
        season
    )

    context = ChallengeContext(
        season=season,
        team_rows=read_csv(team_path),
        player_rows=read_csv(player_path),
    )

    results = []

    for definition in config["challenges"]:
        challenge_class = get_challenge_class(
            definition["type"]
        )

        challenge = challenge_class(
            definition
        )

        result = challenge.calculate(
            context
        )

        results.append(
            asdict(result)
        )

    return results
