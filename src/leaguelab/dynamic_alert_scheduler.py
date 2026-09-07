"""
LeagueLab dynamic roster-alert scheduler.

Purpose
-------
Build today's alert checkpoint plan from the real NFL schedule.  This module
does not send notifications and does not create Windows tasks; the companion
PowerShell script consumes its JSON output and manages Task Scheduler.

Python 3.8 compatible.
"""

import argparse
import csv
import io
import json
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from leaguelab.roster_alert_runner import (
    PROJECT_ROOT,
    _build_schedule_source,
    _load_notification_config,
)


DEFAULT_NFLVERSE_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "schedules/games.csv"
)


def _parse_iso_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _download_text(url, timeout_seconds):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "LeagueLab/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
    return raw.decode("utf-8-sig")


def _discover_regular_season_week(target_date, config):
    """
    Discover the NFL season/week for target_date from nflverse's full schedule.

    Returns None on a day with no regular-season NFL game.
    """
    schedule_cfg = config.get("schedule", {}) or {}
    url = str(
        schedule_cfg.get("nflverse_url")
        or DEFAULT_NFLVERSE_URL
    )
    timeout_seconds = int(schedule_cfg.get("timeout_seconds", 15))

    text = _download_text(url, timeout_seconds)
    reader = csv.DictReader(io.StringIO(text))

    target_text = target_date.isoformat()
    matches = []

    for row in reader:
        gameday = str(row.get("gameday", "") or "").strip()
        game_type = str(row.get("game_type", "") or "").strip().upper()

        if gameday != target_text:
            continue
        if game_type and game_type != "REG":
            continue

        try:
            season = int(row.get("season"))
            week = int(row.get("week"))
        except (TypeError, ValueError):
            continue

        matches.append((season, week))

    distinct = sorted(set(matches))
    if not distinct:
        return None

    if len(distinct) != 1:
        raise RuntimeError(
            "Expected one NFL regular-season season/week for {}, found {}.".format(
                target_text,
                distinct,
            )
        )

    return {
        "season": distinct[0][0],
        "week": distinct[0][1],
    }


def _localize_kickoff(kickoff, local_now):
    if kickoff is None:
        return None

    if kickoff.tzinfo is not None and local_now.tzinfo is not None:
        return kickoff.astimezone(local_now.tzinfo)

    return kickoff


def build_daily_plan(target_date, force_refresh=True, include_past=False, now=None):
    config = _load_notification_config()
    local_now = now or datetime.now().astimezone()

    week_info = _discover_regular_season_week(target_date, config)

    empty = {
        "date": target_date.isoformat(),
        "season": None,
        "week": None,
        "schedule": None,
        "checkpoints": [],
    }

    if week_info is None:
        return empty

    season = int(week_info["season"])
    week = int(week_info["week"])

    source, schedule_label = _build_schedule_source(
        config=config,
        season=season,
        week=week,
        force_refresh=bool(force_refresh),
    )

    alert_cfg = config.get("roster_alerts", {}) or {}
    checkpoint_minutes = sorted(
        set(
            int(value)
            for value in alert_cfg.get(
                "alert_minutes_before_kickoff",
                [30, 5],
            )
        ),
        reverse=True,
    )

    groups = {}

    for game in source.load_games():
        kickoff = _localize_kickoff(
            _parse_iso_datetime(game.get("kickoff")),
            local_now,
        )
        if kickoff is None:
            continue

        if kickoff.date() != target_date:
            continue

        away = str(game.get("away", "") or "").strip().upper()
        home = str(game.get("home", "") or "").strip().upper()

        for minutes_before in checkpoint_minutes:
            run_at = kickoff - timedelta(minutes=minutes_before)

            # A normal morning run should never create tasks for times that have
            # already passed.  --include-past exists only for plan validation.
            if (
                not include_past
                and target_date == local_now.date()
                and run_at <= local_now
            ):
                continue

            key = run_at.isoformat()
            group = groups.setdefault(
                key,
                {
                    "run_at": run_at.isoformat(),
                    "kickoffs": [],
                },
            )
            group["kickoffs"].append(
                {
                    "kickoff_at": kickoff.isoformat(),
                    "minutes_before": minutes_before,
                    "away": away,
                    "home": home,
                }
            )

    checkpoints = [groups[key] for key in sorted(groups)]

    return {
        "date": target_date.isoformat(),
        "season": season,
        "week": week,
        "schedule": schedule_label,
        "checkpoints": checkpoints,
    }


def _format_plan(plan):
    lines = []
    lines.append("")
    lines.append("LeagueLab Dynamic Alert Plan")
    lines.append("============================")
    lines.append("Date: {}".format(plan["date"]))

    if plan.get("season") is None:
        lines.append("No NFL regular-season games today.")
        return "\n".join(lines)

    lines.append(
        "NFL: {} Week {}".format(
            plan["season"],
            plan["week"],
        )
    )
    lines.append("Schedule: {}".format(plan.get("schedule") or "unknown"))
    lines.append("")

    if not plan["checkpoints"]:
        lines.append("No future alert checkpoints remain today.")
        return "\n".join(lines)

    for item in plan["checkpoints"]:
        run_at = datetime.fromisoformat(item["run_at"])
        lines.append(
            "{}  RUN".format(
                run_at.strftime("%a %I:%M %p").replace(" 0", " ")
            )
        )
        for kickoff in item["kickoffs"]:
            kickoff_at = datetime.fromisoformat(kickoff["kickoff_at"])
            lines.append(
                "    {} min before {} {} @ {}".format(
                    kickoff["minutes_before"],
                    kickoff_at.strftime("%I:%M %p").lstrip("0"),
                    kickoff["away"],
                    kickoff["home"],
                )
            )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build today's LeagueLab roster-alert checkpoints from the "
            "real NFL schedule."
        )
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Local calendar date YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Use the production schedule cache when possible.",
    )
    parser.add_argument(
        "--include-past",
        action="store_true",
        help="Include checkpoints that have already passed (planning/testing only).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON only.",
    )
    args = parser.parse_args()

    target_date = (
        date.fromisoformat(args.date)
        if args.date
        else datetime.now().astimezone().date()
    )

    plan = build_daily_plan(
        target_date=target_date,
        force_refresh=not args.no_refresh,
        include_past=args.include_past,
    )

    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(_format_plan(plan))


if __name__ == "__main__":
    main()
