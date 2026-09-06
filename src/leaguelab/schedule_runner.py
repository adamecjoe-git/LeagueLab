import argparse
from pathlib import Path

from leaguelab.roster_alert_runner import (
    PROJECT_ROOT,
    _build_schedule_source,
    _load_notification_config,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force a fresh download instead of using a fresh cache.",
    )
    args = parser.parse_args()

    config = _load_notification_config()
    source, label = _build_schedule_source(
        config=config,
        season=args.season,
        week=args.week,
        force_refresh=args.force,
    )
    payload = source.load_payload()

    print("")
    print("LeagueLab NFL Schedule")
    print("======================")
    print("Schedule: {}".format(label))
    print("Season: {}".format(args.season))
    print("Week: {}".format(args.week))
    print("Games: {}".format(len(payload.get("games", []))))
    print("Cache: {}".format(Path(source.path)))
    print("Primary source: {}".format(payload.get("primary_source") or payload.get("source") or "?"))
    print("Verified by: {}".format(payload.get("verified_by") or "-"))

    warnings = payload.get("warnings") or []
    if warnings:
        print("Warnings: {}".format("; ".join(warnings)))
    if payload.get("refresh_warning"):
        print("Refresh warning: {}".format(payload.get("refresh_warning")))
    print("")

    for game in payload.get("games", []):
        flags = []
        if game.get("espn_verified"):
            flags.append("ESPN verified")
        if game.get("schedule_difference"):
            flags.append("TIME UPDATED BY ESPN")
        if game.get("nflverse_missing"):
            flags.append("ESPN fallback")

        suffix = " [{}]".format(", ".join(flags)) if flags else ""
        print(
            "{} @ {}  {}{}".format(
                game.get("away", "?"),
                game.get("home", "?"),
                game.get("kickoff", "?"),
                suffix,
            )
        )


if __name__ == "__main__":
    main()
