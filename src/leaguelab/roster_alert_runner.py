import argparse
import glob
import json
from datetime import datetime
from pathlib import Path

from leaguelab.alerts.roster_alerts import (
    build_alert_message,
    build_sms_alert_message,
    build_roster_alert,
)
from leaguelab.notifications.dispatcher import NotificationDispatcher
from leaguelab.notifications.router import NotificationRouter
from leaguelab.schedule.espn_source import EspnScheduleSource
from leaguelab.schedule.hybrid_source import HybridScheduleSource
from leaguelab.schedule.json_source import JsonScheduleSource
from leaguelab.yahoo.refresh import refresh_week_rosters


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_managers():
    path = PROJECT_ROOT / "data" / "config" / "managers.json"
    if not path.exists():
        return {"managers": {}}
    return _load_json(str(path))


def _load_notification_config():
    path = PROJECT_ROOT / "data" / "config" / "notifications.json"
    if not path.exists():
        raise FileNotFoundError(
            "Missing {}".format(path)
        )
    return _load_json(str(path))



def _build_schedule_source(config, season, week, force_refresh=False):
    schedule_config = config.get("schedule", {})
    provider = str(schedule_config.get("provider", "hybrid") or "hybrid").lower()
    cache_file = schedule_config.get(
        "cache_file",
        config.get("schedule_file", "data/cache/nfl_schedule.json"),
    )
    cache_path = PROJECT_ROOT / str(cache_file)
    season_type = int(schedule_config.get("season_type", 2))
    refresh_minutes = int(schedule_config.get("refresh_minutes", 30))
    timeout_seconds = int(schedule_config.get("timeout_seconds", 15))

    if provider in ("hybrid", "nflverse+espn"):
        source = HybridScheduleSource(
            str(cache_path),
            timeout_seconds=timeout_seconds,
            nflverse_url=schedule_config.get("nflverse_url"),
        )
        payload, refreshed, source_label = source.refresh_if_needed(
            season=season,
            week=week,
            season_type=season_type,
            max_age_minutes=refresh_minutes,
            force=force_refresh,
        )
        if refreshed:
            label = "Hybrid refreshed ({})".format(source_label)
        else:
            label = "Hybrid cache"
        warning = payload.get("refresh_warning")
        if warning:
            label += "; refresh warning: {}".format(warning)
        return source, label

    if provider == "espn":
        source = EspnScheduleSource(
            str(cache_path),
            timeout_seconds=timeout_seconds,
        )

        try:
            _, refreshed = source.refresh_if_needed(
                season=season,
                week=week,
                season_type=season_type,
                max_age_minutes=refresh_minutes,
                force=force_refresh,
            )
            return source, "ESPN ({})".format(
                "refreshed" if refreshed else "cached"
            )
        except Exception as exc:
            if cache_path.exists():
                try:
                    cached = source.load_payload()
                    if (
                        int(cached.get("season", -1)) == int(season)
                        and int(cached.get("week", -1)) == int(week)
                    ):
                        return source, "ESPN unavailable; using cache ({})".format(exc)
                except Exception:
                    pass
            raise

    if provider == "json":
        return JsonScheduleSource(str(cache_path)), "JSON cache"

    raise RuntimeError(
        "Unsupported schedule provider '{}'. Use 'hybrid', 'espn', or 'json'.".format(provider)
    )

def _league_name_from_yahoo(season):
    """
    Read the human-readable league name from captured Yahoo league metadata.

    Yahoo capture filenames have changed during LeagueLab development, so do
    not assume the metadata is stored specifically in league.json.
    """
    league_dir = _find_league_dir(season)

    preferred_names = [
        "league.json",
        "profile.json",
        "league_profile.json",
        "settings.json",
        "standings.json",
        "teams.json",
    ]

    paths = []
    seen = set()

    for name in preferred_names:
        path = league_dir / name
        if path.exists():
            paths.append(path)
            seen.add(str(path).lower())

    for path in sorted(league_dir.glob("*.json")):
        key = str(path).lower()
        if key not in seen:
            paths.append(path)
            seen.add(key)

    def clean_name(value):
        if isinstance(value, str):
            return value.strip()
        return ""

    def walk(value):
        if isinstance(value, dict):
            # Common Yahoo representation: league_key and name are siblings.
            if "league_key" in value and "name" in value:
                name = clean_name(value.get("name"))
                if name:
                    return name

            for child in value.values():
                found = walk(child)
                if found:
                    return found

        elif isinstance(value, list):
            # Yahoo frequently represents metadata as a list of one-key dicts.
            league_key_present = any(
                isinstance(item, dict) and "league_key" in item
                for item in value
            )
            if league_key_present:
                for item in value:
                    if isinstance(item, dict) and "name" in item:
                        name = clean_name(item.get("name"))
                        if name:
                            return name

            for child in value:
                found = walk(child)
                if found:
                    return found

        return ""

    for path in paths:
        try:
            payload = _load_json(str(path))
        except (OSError, ValueError):
            continue

        name = walk(payload)
        if name:
            return name

    return "Fantasy League"


def _format_clock(dt):
    # LeagueLab runs on the league host in Wisconsin; suppress timezone suffix
    # and avoid a leading zero for human-friendly SMS output.
    return dt.strftime("%a %I:%M %p").replace(" 0", " ")


def _kickoff_by_team(window):
    result = {}
    for game in window.get("games", []):
        kickoff = game.get("_local_kickoff")
        if kickoff is None:
            continue
        label = kickoff.strftime("%I:%M %p").lstrip("0")
        for key in ("away", "home"):
            team = str(game.get(key, "") or "").strip().upper()
            if team:
                result[team] = label
    return result


def _find_league_dir(season):
    base = PROJECT_ROOT / "data" / "raw" / "yahoo" / str(season)
    candidates = [path for path in base.glob("*") if path.is_dir()]

    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one Yahoo league directory under {}, found {}.".format(
                base,
                len(candidates),
            )
        )

    return candidates[0]


def _find_roster_files(season, fantasy_week):
    league_dir = _find_league_dir(season)
    week_dir = league_dir / "weeks" / "week_{:02d}".format(int(fantasy_week))

    files = sorted(week_dir.glob("team_*_roster.json"))
    if not files:
        raise FileNotFoundError(
            "No roster files found in {}".format(week_dir)
        )

    return files


def _issue_key(alert, kickoff_text):
    issue_parts = []

    for issue in alert.get("issues", []):
        issue_parts.append(
            "{}:{}:{}:{}".format(
                issue.get("type", ""),
                issue.get("player_key", ""),
                issue.get("position", ""),
                issue.get("detail", ""),
            )
        )

    issue_parts.sort()

    return "{}|{}|{}".format(
        alert.get("team_key", ""),
        kickoff_text,
        "|".join(issue_parts),
    )


def _load_state(season, fantasy_week):
    path = (
        PROJECT_ROOT
        / "data"
        / "state"
        / "roster_alerts"
        / str(season)
        / "week_{:02d}.json".format(int(fantasy_week))
    )

    if not path.exists():
        return path, {"sent_keys": []}

    return path, _load_json(str(path))


def _save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)



def _send_admin_failure(config, manager_contacts, dispatcher, mode, season, week, failure_text):
    """
    Send a commissioner/admin SMS when a roster-alert run fails before manager
    notifications can be evaluated.

    This is intentionally independent of each manager's roster-alert preference.
    Preview mode never sends. Test/live may send only when explicitly enabled
    under admin_notifications.sms.
    """
    if mode not in ("test", "live"):
        print("ADMIN SMS not sent in preview mode.")
        return None

    admin_cfg = config.get("admin_notifications", {}).get("sms", {}) or {}
    if not admin_cfg.get("enabled", False):
        print("ADMIN SMS skipped - admin_notifications.sms is disabled.")
        return None

    if not admin_cfg.get("send_on_errors", True):
        print("ADMIN SMS skipped - send_on_errors is disabled.")
        return None

    admin_guid = str(admin_cfg.get("manager_guid", "") or "").strip()
    admin_contact = manager_contacts.get(admin_guid, {})
    phone = str(admin_contact.get("phone", "") or "").strip()

    if not phone:
        print("ADMIN SMS skipped - configured admin manager has no phone number.")
        return None

    message = (
        "LeagueLab ALERT FAILURE\n"
        "Season {} Week {}\n"
        "{}\n"
        "Manager alerts aborted; cached Yahoo rosters were NOT used."
    ).format(season, week, str(failure_text))

    delivery = {
        "send": True,
        "channels": ["sms"],
        "phone_to": phone,
        "email_to": "",
        "subject": "LeagueLab roster alert failure",
        "message": message,
        "sms_message": message,
        "manager_preference": "admin",
    }

    try:
        results = dispatcher.dispatch(delivery)
    except Exception as exc:
        print("ADMIN SMS FAILED -> {}".format(exc))
        return None

    if not results:
        print("ADMIN SMS FAILED -> dispatcher returned no result.")
        return None

    result = results[0]
    print("ADMIN SMS {} via {} ({})".format(
        "SENT" if result.get("success") else "FAILED",
        result.get("provider", "unknown"),
        result.get("detail", ""),
    ))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument(
        "--schedule-season",
        type=int,
        default=None,
        help=(
            "Optional NFL schedule season override for testing. "
            "Defaults to --season."
        ),
    )
    parser.add_argument(
        "--schedule-week",
        type=int,
        default=None,
        help=(
            "Optional NFL schedule week override for testing. "
            "Defaults to --week."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["preview", "test", "live"],
        default=None,
    )
    parser.add_argument(
        "--now",
        default=None,
        help=(
            "Optional ISO datetime for testing, e.g. "
            "2026-09-13T10:45:00-05:00"
        ),
    )
    parser.add_argument(
        "--refresh-schedule",
        action="store_true",
        help="Force a fresh NFL schedule download before evaluating alerts.",
    )
    parser.add_argument(
        "--refresh-yahoo",
        action="store_true",
        help=(
            "Refresh all Yahoo roster files for --season/--week before "
            "evaluating alerts. Live runs and non-simulated test runs do "
            "this automatically."
        ),
    )
    parser.add_argument(
        "--only-team",
        default=None,
        help=(
            "Preview/test safety filter: process only the exact fantasy team "
            "name supplied. This option is not allowed in live mode."
        ),
    )
    parser.add_argument(
        "--simulate-yahoo-failure",
        action="store_true",
        help=(
            "Safety test only: simulate a Yahoo refresh failure before any "
            "manager alerts are evaluated. Not allowed in live mode."
        ),
    )
    args = parser.parse_args()

    config = _load_notification_config()
    mode = args.mode or config.get("mode", "preview")
    if args.only_team and mode == "live":
        raise RuntimeError(
            "--only-team is a preview/test safety filter and cannot be used in live mode."
        )
    if args.simulate_yahoo_failure and mode == "live":
        raise RuntimeError(
            "--simulate-yahoo-failure is a safety test and cannot be used in live mode."
        )
    schedule_season = args.schedule_season if args.schedule_season is not None else args.season
    schedule_week = args.schedule_week if args.schedule_week is not None else args.week
    alert_config = config.get("roster_alerts", {}) or {}
    checkpoints = sorted(
        set(int(x) for x in alert_config.get("alert_minutes_before_kickoff", [30, 5])),
        reverse=True,
    )
    lookahead_minutes = max(checkpoints)

    if args.now:
        now = datetime.fromisoformat(args.now)
    else:
        now = datetime.now().astimezone()

    schedule, schedule_label = _build_schedule_source(
        config=config,
        season=schedule_season,
        week=schedule_week,
        force_refresh=args.refresh_schedule,
    )
    window = schedule.alert_day_window(now, lookahead_minutes)

    print("")
    print("LeagueLab Roster Alerts")
    print("=======================")
    print("Mode: {}".format(mode))
    print("Schedule: {}".format(schedule_label))
    print("Yahoo data: Season {} Week {}".format(args.season, args.week))
    print("NFL schedule: Season {} Week {}".format(schedule_season, schedule_week))
    print("Now: {}".format(now.isoformat()))

    if not window:
        print("No NFL kickoff window within {} minutes.".format(lookahead_minutes))
        return

    # Load delivery/admin context before Yahoo refresh so authentication or
    # refresh failures can still notify the commissioner safely.
    managers_payload = _load_managers()
    manager_contacts = managers_payload.get("managers", {})
    dispatcher = NotificationDispatcher(config.get("delivery", {}))

    # Sending modes must evaluate fresh Yahoo roster data. Historical/simulated
    # test runs that provide --now intentionally keep using cached roster data
    # unless --refresh-yahoo is explicitly requested.
    yahoo_refresh_required = bool(
        args.refresh_yahoo
        or (mode in ("test", "live") and not args.now)
    )

    if yahoo_refresh_required:
        print("Yahoo roster refresh: REQUIRED")
        try:
            if args.simulate_yahoo_failure:
                raise RuntimeError("SIMULATED Yahoo refresh failure")
            refresh_result = refresh_week_rosters(args.season, args.week)
        except Exception as exc:
            print("Yahoo roster refresh: FAILED")
            print("{}".format(exc))
            print("Roster alerts aborted - cached Yahoo rosters were not used.")
            _send_admin_failure(
                config=config,
                manager_contacts=manager_contacts,
                dispatcher=dispatcher,
                mode=mode,
                season=args.season,
                week=args.week,
                failure_text="Yahoo refresh failed: {}".format(exc),
            )
            return
        print(
            "Yahoo roster refresh: OK ({} teams)".format(
                refresh_result.get("rosters_updated", 0)
            )
        )
    else:
        print("Yahoo roster refresh: cached data")

    kickoff = window["kickoff"]
    kickoff_text = kickoff.isoformat()
    minutes_to_kickoff = max(0, int(round((kickoff - now).total_seconds() / 60.0)))
    eligible = [x for x in checkpoints if minutes_to_kickoff <= x]
    checkpoint = min(eligible) if eligible else max(checkpoints)
    kickoff_label = _format_clock(kickoff)

    print("Next kickoff: {}".format(kickoff_label))
    print("Checkpoint: {} minutes".format(checkpoint))
    print("NFL teams remaining today: {}".format(", ".join(window["teams"])))
    print("")

    league_name = _league_name_from_yahoo(args.season)
    kickoff_by_team = _kickoff_by_team(window)
    kickoff_by_team["__trigger_teams__"] = list(window.get("trigger_teams", []))
    print("League: {}".format(league_name))
    print("")

    test_manager_config = config.get("test_manager", {}) or {}
    test_manager_guid = str(test_manager_config.get("guid", config.get("test_manager_guid", "")) or "").strip()
    test_contact = manager_contacts.get(test_manager_guid, {})

    router = NotificationRouter(
        mode=mode,
        test_contact=test_contact,
        test_channels=config.get("test_channels", ["email", "sms"]),
    )
    provider_status = dispatcher.provider_status()
    print("Delivery providers: email={}, sms={}".format(
        provider_status.get("email", "disabled"),
        provider_status.get("sms", "disabled"),
    ))
    print("")

    state_path, state = _load_state(args.season, args.week)
    sent_keys = set(state.get("sent_keys", []))

    alerts_found = 0
    admin_rows = []
    run_errors = []

    for roster_path in _find_roster_files(args.season, args.week):
        payload = _load_json(str(roster_path))
        alert = build_roster_alert(
            payload=payload,
            fantasy_week=args.week,
            kickoff_teams=window["teams"],
            kickoff_by_team=kickoff_by_team,
        )

        if args.only_team:
            actual_team = str(alert.get("team_name", "") or "").strip()
            if actual_team != str(args.only_team).strip():
                continue

        if not alert["has_alert"]:
            continue

        if not alert.get("should_notify", False):
            continue

        alerts_found += 1
        key = "{}|checkpoint:{}".format(_issue_key(alert, kickoff_text), checkpoint)

        manager_contact = manager_contacts.get(
            alert.get("manager_guid", ""),
            {},
        )

        subject = "LeagueLab Week {} Lineup Alert".format(args.week)
        message = build_alert_message(alert, kickoff_label, league_name=league_name)
        sms_message = build_sms_alert_message(alert, kickoff_label, league_name=league_name)

        delivery = router.build_delivery(
            manager_contact=manager_contact,
            subject=subject,
            message=message,
        )
        delivery["sms_message"] = sms_message

        duplicate = key in sent_keys

        print("----------------------------------------")
        print("{} / {}".format(
            alert.get("manager_name") or "Unknown Manager",
            alert.get("team_name") or "Unknown Team",
        ))
        print("Preference: {}".format(
            delivery.get("manager_preference", "off")
        ))
        print("Duplicate: {}".format("YES" if duplicate else "NO"))
        print("")
        print(message)
        print("")

        if mode == "test":
            print("TEST route email: {}".format(delivery.get("email_to") or "-"))
            print("TEST route phone: {}".format(delivery.get("phone_to") or "-"))
        elif mode == "live":
            print("LIVE channels: {}".format(
                ", ".join(delivery.get("channels", [])) or "none"
            ))
        else:
            print("PREVIEW only - nothing will be sent.")

        repeat_alerts = bool(
            config.get("roster_alerts", {}).get("repeat_alerts", False)
        )
        should_dispatch = (
            mode in ("test", "live")
            and delivery.get("send", False)
            and (not duplicate or repeat_alerts)
        )

        if duplicate and not repeat_alerts:
            print("Suppressed by alert history.")
        elif should_dispatch:
            results = dispatcher.dispatch(delivery)
            all_success = bool(results) and all(r.get("success", False) for r in results)
            for result in results:
                status = "SENT" if result.get("success") else "FAILED"
                admin_rows.append({
                    "team": alert.get("team_name") or "Unknown Team",
                    "manager": alert.get("manager_name") or "Unknown Manager",
                    "channel": result.get("channel", ""),
                    "success": bool(result.get("success")),
                    "issues": len(alert.get("issues", [])),
                    "detail": result.get("detail", ""),
                })
                if not result.get("success"):
                    run_errors.append("{} {}: {}".format(
                        alert.get("team_name") or "Unknown Team",
                        result.get("channel", ""),
                        result.get("detail", ""),
                    ))
                print("{} {} via {} -> {} ({})".format(
                    result.get("channel", "").upper(),
                    status,
                    result.get("provider", "unknown"),
                    result.get("recipient", "") or "-",
                    result.get("detail", ""),
                ))
            if all_success and not repeat_alerts:
                sent_keys.add(key)
                state["sent_keys"] = sorted(sent_keys)
        elif mode in ("test", "live") and not delivery.get("send", False):
            print("No delivery channel/address is available for this alert.")

    if alerts_found == 0:
        print("No roster alerts for this kickoff window.")

    _save_state(state_path, state)

    # Optional commissioner/admin run summary. It is independent of manager
    # roster-alert preferences and is sent only when configured conditions match.
    admin_cfg = config.get("admin_notifications", {}).get("email", {}) or {}
    if mode == "live" and admin_cfg.get("enabled", False):
        send_summary = (admin_rows and admin_cfg.get("send_on_alerts", True)) or (
            run_errors and admin_cfg.get("send_on_errors", True)
        ) or (
            not admin_rows and not run_errors and admin_cfg.get("send_on_no_activity", False)
        )
        if send_summary:
            admin_guid = str(admin_cfg.get("manager_guid", "") or "").strip()
            admin_contact = manager_contacts.get(admin_guid, {})
            admin_email = str(admin_contact.get("email", "") or "").strip()
            if admin_email:
                lines = [
                    "LeagueLab roster-alert run summary",
                    "League: {}".format(league_name),
                    "Week: {}".format(args.week),
                    "Checkpoint: {} ({} min before kickoff)".format(kickoff_label, checkpoint),
                    "",
                ]
                if admin_rows:
                    lines.append("Delivery attempts: {}".format(len(admin_rows)))
                    for row in admin_rows:
                        lines.append("- {} / {} / {} / {} issue(s) / {}".format(
                            row["team"], row["manager"], row["channel"].upper(),
                            row["issues"], "SENT" if row["success"] else "FAILED",
                        ))
                else:
                    lines.append("No manager notifications were sent.")
                if run_errors:
                    lines.extend(["", "Errors:"] + ["- " + x for x in run_errors])
                subject = "LeagueLab Roster Alerts - W{} - {}".format(args.week, kickoff_label)
                result = dispatcher.email_sender.send(admin_email, subject, "\n".join(lines)).as_dict()
                print("ADMIN EMAIL {} -> {} ({})".format(
                    "SENT" if result.get("success") else "FAILED",
                    admin_email, result.get("detail", ""),
                ))
            else:
                print("ADMIN EMAIL skipped - configured admin manager has no email address.")

    print("")
    if mode == "preview":
        print("Preview complete - no messages were sent.")
    else:
        print("Notification run complete.")


if __name__ == "__main__":
    main()
