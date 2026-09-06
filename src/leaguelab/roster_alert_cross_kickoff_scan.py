import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from leaguelab.alerts.roster_alerts import build_roster_alert
from leaguelab.roster_alert_runner import (
    PROJECT_ROOT,
    _build_schedule_source,
    _find_roster_files,
    _load_notification_config,
)


TEAM_ALIASES = {
    "WSH": "WAS",
    "JAC": "JAX",
    "LA": "LAR",
    "STL": "LAR",
    "SD": "LAC",
    "OAK": "LV",
}


def _load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_team(value):
    team = str(value or "").strip().upper()
    return TEAM_ALIASES.get(team, team)


def _format_clock(dt):
    return dt.strftime("%a %I:%M %p").replace(" 0", " ")


def _schedule_maps(source, now):
    games = source.load_games()

    kickoff_dt_by_team = {}
    kickoff_label_by_team = {}
    all_teams = set()

    for game in games:
        kickoff_text = str(game.get("kickoff", "") or "").strip()
        if not kickoff_text:
            continue

        value = kickoff_text
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        kickoff = datetime.fromisoformat(value)

        if now.tzinfo is not None and kickoff.tzinfo is not None:
            kickoff = kickoff.astimezone(now.tzinfo)

        label = kickoff.strftime("%I:%M %p").lstrip("0")

        for key in ("away", "home"):
            team = _normalize_team(game.get(key))
            if not team:
                continue
            all_teams.add(team)
            kickoff_dt_by_team[team] = kickoff
            kickoff_label_by_team[team] = label

    return sorted(all_teams), kickoff_dt_by_team, kickoff_label_by_team


def _cross_kickoff_candidates(season, fantasy_week, schedule_teams,
                              kickoff_dt_by_team, kickoff_label_by_team):
    results = []

    for roster_path in _find_roster_files(season, fantasy_week):
        payload = _load_json(str(roster_path))

        # IMPORTANT: this is the production alert builder. The scanner does not
        # reimplement Yahoo roster parsing, starter rules, BYE rules, status
        # rules, or EMPTY-slot rules.
        alert = build_roster_alert(
            payload=payload,
            fantasy_week=fantasy_week,
            kickoff_teams=schedule_teams,
            kickoff_by_team=kickoff_label_by_team,
        )

        timed = []
        global_issues = []

        for issue in alert.get("issues", []):
            issue_type = str(issue.get("type", "") or "")
            team = _normalize_team(issue.get("nfl_team"))

            if issue_type in ("bye", "empty_starter"):
                global_issues.append(issue)
                continue

            kickoff = kickoff_dt_by_team.get(team)
            if kickoff is not None:
                timed.append((kickoff, issue))

        distinct = sorted(set(item[0] for item in timed))
        if len(distinct) < 2:
            continue

        results.append({
            "week": fantasy_week,
            "manager_name": alert.get("manager_name") or "Unknown",
            "team_name": alert.get("team_name") or "Unknown Team",
            "team_key": alert.get("team_key") or "",
            "timed": timed,
            "global": global_issues,
            "distinct": distinct,
        })

    return results


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Find real historical LeagueLab rosters with alert-worthy starters "
            "spanning multiple NFL kickoff windows. Uses the production roster "
            "alert builder and production schedule provider."
        )
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--schedule-season", type=int, required=True)
    parser.add_argument("--schedule-week", type=int, required=True)
    parser.add_argument(
        "--fantasy-week",
        type=int,
        default=None,
        help=(
            "Yahoo roster week to scan. Defaults to --schedule-week. "
            "Use this when intentionally pairing a different roster week "
            "with the selected NFL schedule."
        ),
    )
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument(
        "--refresh-schedule",
        action="store_true",
        help="Force LeagueLab's production schedule provider to refresh first.",
    )
    args = parser.parse_args()

    fantasy_week = (
        args.fantasy_week
        if args.fantasy_week is not None
        else args.schedule_week
    )

    config = _load_notification_config()

    # Noon on the selected Sunday is not required here; timezone is only used
    # to render schedule clock labels. Use the machine's local timezone.
    now = datetime.now().astimezone()

    source, schedule_label = _build_schedule_source(
        config=config,
        season=args.schedule_season,
        week=args.schedule_week,
        force_refresh=args.refresh_schedule,
    )

    schedule_teams, kickoff_dt_by_team, kickoff_label_by_team = _schedule_maps(
        source,
        now,
    )

    candidates = _cross_kickoff_candidates(
        season=args.season,
        fantasy_week=fantasy_week,
        schedule_teams=schedule_teams,
        kickoff_dt_by_team=kickoff_dt_by_team,
        kickoff_label_by_team=kickoff_label_by_team,
    )

    candidates.sort(
        key=lambda x: (
            -len(x["distinct"]),
            -len(x["timed"]),
            x["team_name"],
        )
    )

    print("")
    print("LeagueLab Cross-Kickoff Alert Candidate Scan")
    print("===========================================")
    print("Roster data: Season {} Week {}".format(args.season, fantasy_week))
    print(
        "NFL schedule: Season {} Week {}".format(
            args.schedule_season,
            args.schedule_week,
        )
    )
    print("Schedule: {}".format(schedule_label))
    print("Production build_roster_alert(): YES")
    print("NFL teams in schedule: {}".format(len(schedule_teams)))
    print("")

    if not candidates:
        print(
            "No fantasy team in this roster week has alert-worthy "
            "player-specific issues in two or more kickoff windows."
        )
        print("")
        print(
            "Note: BYE and EMPTY are global issues and do not count as "
            "separate kickoff windows for this particular scan."
        )
        return

    for index, candidate in enumerate(candidates[:args.top], 1):
        print(
            "#{}  {} / {}".format(
                index,
                candidate["manager_name"],
                candidate["team_name"],
            )
        )
        print(
            "    Distinct player-specific kickoff windows: {}".format(
                len(candidate["distinct"])
            )
        )

        grouped = defaultdict(list)
        for kickoff, issue in candidate["timed"]:
            grouped[kickoff].append(issue)

        for kickoff in sorted(grouped):
            print("    {}".format(_format_clock(kickoff)))
            for issue in grouped[kickoff]:
                print(
                    "      {} [{}]".format(
                        issue.get("detail", ""),
                        _normalize_team(issue.get("nfl_team")),
                    )
                )

        if candidate["global"]:
            print("    GLOBAL (would also be included in the notification)")
            for issue in candidate["global"]:
                print("      {}".format(issue.get("detail", "")))

        earliest = min(candidate["distinct"])
        test_time = earliest.replace(
            minute=(earliest.minute - 30) % 60
        )
        print("")
        print(
            "    Test with roster Week {} at 30 minutes before {}.".format(
                candidate["week"],
                _format_clock(earliest),
            )
        )
        print("")


if __name__ == "__main__":
    main()
