import argparse
from datetime import datetime, timedelta

from leaguelab.roster_alert_runner import (
    _build_schedule_source,
    _format_clock,
    _load_notification_config,
)
from leaguelab.schedule.json_source import parse_iso_datetime


def main():
    parser = argparse.ArgumentParser(
        description="Show today's schedule-driven LeagueLab roster alert run times."
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--now", default=None, help="Optional ISO datetime for testing.")
    parser.add_argument("--refresh-schedule", action="store_true")
    args = parser.parse_args()

    config = _load_notification_config()
    alert_config = config.get("roster_alerts", {}) or {}
    checkpoints = alert_config.get("alert_minutes_before_kickoff", [30, 5])
    checkpoints = sorted(set(int(x) for x in checkpoints), reverse=True)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now().astimezone()
    source, label = _build_schedule_source(
        config=config,
        season=args.season,
        week=args.week,
        force_refresh=args.refresh_schedule,
    )

    kickoffs = []
    for game in source.load_games():
        text = str(game.get("kickoff", "") or "").strip()
        if not text:
            continue
        kickoff = parse_iso_datetime(text).astimezone(now.tzinfo)
        if kickoff.date() == now.date():
            kickoffs.append(kickoff)

    unique = []
    seen = set()
    for kickoff in sorted(kickoffs):
        stamp = kickoff.timestamp()
        if stamp not in seen:
            seen.add(stamp)
            unique.append(kickoff)

    print("")
    print("LeagueLab Daily Alert Plan")
    print("==========================")
    print("Schedule: {}".format(label))
    print("Date: {}".format(now.strftime("%Y-%m-%d")))
    print("Alert checkpoints: {} minutes before kickoff".format(
        ", ".join(str(x) for x in checkpoints)
    ))
    print("")

    if not unique:
        print("No NFL games today. No roster-alert runs are needed.")
        return

    for kickoff in unique:
        for checkpoint in checkpoints:
            run_at = kickoff - timedelta(minutes=checkpoint)
            print("{} -> run at {} ({} min)".format(
                _format_clock(kickoff), _format_clock(run_at), checkpoint
            ))


if __name__ == "__main__":
    main()
