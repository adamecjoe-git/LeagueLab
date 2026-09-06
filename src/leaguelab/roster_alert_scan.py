import argparse
import json
from collections import defaultdict
from pathlib import Path

from leaguelab.alerts.roster_alerts import (
    _extract_players,
    _extract_team_identity,
    _is_starter,
    _status_issue,
    _build_empty_slot_issues,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_json(path):
    with open(str(path), "r", encoding="utf-8") as handle:
        return json.load(handle)


def _find_league_dir(season):
    base = PROJECT_ROOT / "data" / "raw" / "yahoo" / str(season)
    candidates = [path for path in base.glob("*") if path.is_dir()]
    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one Yahoo league directory under {}, found {}.".format(
                base, len(candidates)
            )
        )
    return candidates[0]


def _roster_files_by_week(season):
    league_dir = _find_league_dir(season)
    weeks_dir = league_dir / "weeks"
    result = []
    for week_dir in sorted(weeks_dir.glob("week_*")):
        try:
            week = int(week_dir.name.split("_")[-1])
        except ValueError:
            continue
        files = sorted(week_dir.glob("team_*_roster.json"))
        if files:
            result.append((week, files))
    return result


def _issue_rows(payload, fantasy_week):
    identity = _extract_team_identity(payload)
    rows = []
    players = _extract_players(payload)

    # EMPTY starter slots use the same production logic as the live alert engine.
    for issue in _build_empty_slot_issues(players):
        rows.append(
            {
                "manager": identity.get("manager_name") or "Unknown",
                "team": identity.get("team_name") or "Unknown Team",
                "team_key": identity.get("team_key") or "",
                "player": "EMPTY",
                "position": issue.get("position") or "",
                "nfl_team": "",
                "issue": "EMPTY",
            }
        )

    for player in players:
        if not _is_starter(player):
            continue

        issue = ""
        bye_week = str(player.get("bye_week", "") or "").strip()
        if bye_week == str(fantasy_week):
            issue = "BYE"

        status_issue = _status_issue(player)
        if status_issue:
            # If both somehow apply, status is more useful for this diagnostic.
            issue = status_issue

        if not issue:
            continue

        rows.append(
            {
                "manager": identity.get("manager_name") or "Unknown",
                "team": identity.get("team_name") or "Unknown Team",
                "team_key": identity.get("team_key") or "",
                "player": player.get("player_name") or "Unknown Player",
                "position": player.get("selected_position") or "",
                "nfl_team": str(player.get("nfl_team", "") or "").upper(),
                "issue": issue,
            }
        )

    return rows


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Scan captured Yahoo roster files for alert-worthy STARTING players and "
            "EMPTY required starter slots so real historical examples can be selected "
            "for roster-alert testing."
        )
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of richest weeks to display (default: 10).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Display every week containing at least one issue.",
    )
    args = parser.parse_args()

    week_rows = defaultdict(list)
    scanned_files = 0

    for week, roster_files in _roster_files_by_week(args.season):
        for roster_path in roster_files:
            scanned_files += 1
            payload = _load_json(roster_path)
            week_rows[week].extend(_issue_rows(payload, week))

    ranked = sorted(
        week_rows.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )
    ranked = [(week, rows) for week, rows in ranked if rows]

    if not args.all:
        ranked = ranked[: max(int(args.top), 1)]

    print("LeagueLab Historical Roster Alert Scan")
    print("======================================")
    print("Season: {}".format(args.season))
    print("Roster files scanned: {}".format(scanned_files))
    print("Starting-player BYE/O/OUT/IR/NA/PUP issues and EMPTY required starter slots are shown.")
    print()

    if not ranked:
        print("No alert-worthy starting-player issues found.")
        return

    for week, rows in ranked:
        nfl_teams = sorted(set(row["nfl_team"] for row in rows if row["nfl_team"]))
        fantasy_teams = sorted(set(row["team"] for row in rows))
        print(
            "Week {} - {} issue(s), {} fantasy team(s), {} NFL team(s)".format(
                week, len(rows), len(fantasy_teams), len(nfl_teams)
            )
        )
        for row in sorted(
            rows,
            key=lambda r: (r["team"].lower(), r["nfl_team"], r["player"].lower()),
        ):
            print(
                "  {} / {}: {} ({}) [{}] - {}".format(
                    row["manager"],
                    row["team"],
                    row["player"],
                    row["position"],
                    row["nfl_team"] or "?",
                    row["issue"],
                )
            )
        print("  NFL teams represented: {}".format(", ".join(nfl_teams) or "None"))
        print()


if __name__ == "__main__":
    main()
