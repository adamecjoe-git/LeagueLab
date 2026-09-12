"""
LeagueLab live-mode preflight validator.

Purpose
-------
Perform a zero-send production-readiness check before enabling roster alerts.

Checks:
- notification config is present and valid enough for live use
- SMS/Textbelt configuration and API-key environment variable
- admin failure-SMS configuration
- manager directory safety:
  * current Yahoo managers are represented in managers.json
  * roster-alert preferences are explicitly set to off/email/sms/both
  * enabled channels have the required contact information
  * unknown/stale manager rows are reported
- NFL schedule source can load the requested week
- optional Yahoo authentication + fresh-roster refresh

This script NEVER dispatches notifications.

Python 3.8 compatible.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from leaguelab.notifications.dispatcher import NotificationDispatcher
from leaguelab.roster_alert_runner import (
    PROJECT_ROOT,
    _build_schedule_source,
    _find_league_dir,
    _load_managers,
    _load_notification_config,
)
from leaguelab.yahoo.client import refresh_week_rosters


ALLOWED_PREFERENCES = {"off", "email", "sms", "both"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class Preflight(object):
    def __init__(self):
        self.rows = []

    def add(self, level, name, detail):
        self.rows.append({
            "level": str(level).upper(),
            "name": str(name),
            "detail": str(detail),
        })

    def ok(self, name, detail):
        self.add("PASS", name, detail)

    def warn(self, name, detail):
        self.add("WARN", name, detail)

    def fail(self, name, detail):
        self.add("FAIL", name, detail)

    @property
    def failures(self):
        return [row for row in self.rows if row["level"] == "FAIL"]

    @property
    def warnings(self):
        return [row for row in self.rows if row["level"] == "WARN"]

    def render(self):
        print("")
        print("LeagueLab Live Preflight")
        print("========================")
        for row in self.rows:
            print("[{:<4}] {:<28} {}".format(
                row["level"],
                row["name"] + ":",
                row["detail"],
            ))
        print("")
        print("Result: {} failure(s), {} warning(s)".format(
            len(self.failures),
            len(self.warnings),
        ))
        if self.failures:
            print("LIVE READY: NO")
        else:
            print("LIVE READY: YES{}".format(
                " (with warnings)" if self.warnings else ""
            ))


def _load_json(path):
    with open(str(path), "r", encoding="utf-8") as handle:
        return json.load(handle)


def _walk_team_records(value, output):
    """
    Extract Yahoo team identity from the common nested Fantasy API response.
    """
    if isinstance(value, dict):
        if "team" in value:
            _parse_team(value.get("team"), output)
        for child in value.values():
            _walk_team_records(child, output)
    elif isinstance(value, list):
        for child in value:
            _walk_team_records(child, output)


def _parse_team(team_value, output):
    if not isinstance(team_value, list):
        return

    # Yahoo often wraps the metadata list one level deeper.
    parts = team_value
    if len(parts) == 1 and isinstance(parts[0], list):
        parts = parts[0]

    team_key = ""
    team_name = ""
    manager_guid = ""
    manager_name = ""

    def walk(value):
        nonlocal team_key, team_name, manager_guid, manager_name
        if isinstance(value, dict):
            if "team_key" in value and not team_key:
                team_key = str(value.get("team_key") or "").strip()
            if "name" in value and not team_name and team_key:
                # Team metadata usually places name near team_key.
                possible = value.get("name")
                if isinstance(possible, str):
                    team_name = possible.strip()
            if "manager" in value and isinstance(value["manager"], dict):
                manager = value["manager"]
                if not manager_guid:
                    manager_guid = str(manager.get("guid") or "").strip()
                if not manager_name:
                    manager_name = str(manager.get("nickname") or "").strip()
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(parts)

    # Safer second pass for team name because Yahoo's team metadata is a list
    # of one-key dictionaries and "name" is normally a sibling of team_key.
    if team_key and not team_name:
        for item in parts:
            if isinstance(item, dict) and "name" in item:
                possible = item.get("name")
                if isinstance(possible, str):
                    team_name = possible.strip()
                    break

    if team_key and manager_guid:
        output[manager_guid] = {
            "guid": manager_guid,
            "manager_name": manager_name,
            "team_name": team_name,
            "team_key": team_key,
        }


def _current_yahoo_managers(season):
    league_dir = _find_league_dir(season)

    preferred = [
        league_dir / "teams.json",
        league_dir / "standings.json",
        league_dir / "league.json",
        league_dir / "profile.json",
    ]
    paths = [path for path in preferred if path.exists()]
    if not paths:
        paths = sorted(league_dir.glob("*.json"))

    output = {}
    for path in paths:
        try:
            payload = _load_json(path)
        except Exception:
            continue
        _walk_team_records(payload, output)
        if output:
            break

    return output


def _manager_preference(row):
    notifications = row.get("notifications", {}) or {}
    value = notifications.get("roster_alerts", "MISSING")
    return str(value or "").strip().lower()


def _audit_managers(report, season, managers_payload):
    configured = managers_payload.get("managers", {})
    if not isinstance(configured, dict):
        report.fail("Manager config", "'managers' must be an object keyed by Yahoo GUID.")
        return

    try:
        yahoo = _current_yahoo_managers(season)
    except Exception as exc:
        report.fail("Yahoo team metadata", str(exc))
        return

    if not yahoo:
        report.fail(
            "Yahoo team metadata",
            "Could not extract current manager GUIDs from local Yahoo season data.",
        )
        return

    report.ok(
        "Yahoo manager count",
        "{} current manager(s) found for season {}.".format(len(yahoo), season),
    )

    missing = sorted(set(yahoo) - set(configured))
    stale = sorted(set(configured) - set(yahoo))

    if missing:
        report.fail(
            "Manager coverage",
            "{} Yahoo manager(s) missing from managers.json: {}".format(
                len(missing), ", ".join(missing)
            ),
        )
    else:
        report.ok(
            "Manager coverage",
            "Every current Yahoo manager GUID exists in managers.json.",
        )

    if stale:
        report.warn(
            "Stale manager rows",
            "{} configured GUID(s) are not in the current Yahoo league.".format(
                len(stale)
            ),
        )
    else:
        report.ok("Stale manager rows", "None.")

    pref_counts = {"off": 0, "email": 0, "sms": 0, "both": 0}
    manager_errors = []
    manager_warnings = []

    for guid, identity in sorted(yahoo.items(), key=lambda item: item[1].get("team_name", "")):
        row = configured.get(guid)
        label = "{} / {}".format(
            identity.get("manager_name") or guid,
            identity.get("team_name") or identity.get("team_key"),
        )

        if not isinstance(row, dict):
            continue

        pref = _manager_preference(row)
        if pref == "missing":
            manager_errors.append(
                "{}: notifications.roster_alerts is missing (require explicit off/email/sms/both).".format(label)
            )
            continue

        if pref not in ALLOWED_PREFERENCES:
            manager_errors.append(
                "{}: invalid roster_alerts preference {!r}.".format(label, pref)
            )
            continue

        pref_counts[pref] += 1

        notification_email = str(row.get("notification_email", "") or "").strip()
        phone = str(row.get("phone", "") or "").strip()

        if pref in ("email", "both"):
            if not notification_email:
                manager_errors.append("{}: {} requires a notification_email address.".format(label, pref))
            elif not EMAIL_RE.match(notification_email):
                manager_errors.append("{}: notification_email address format looks invalid.".format(label))

        if pref in ("sms", "both"):
            if not phone:
                manager_errors.append("{}: {} requires a phone number.".format(label, pref))
            elif not PHONE_RE.match(phone):
                manager_errors.append(
                    "{}: phone should be E.164 format such as +16085551212.".format(label)
                )

        # Contact info may exist for off managers; that is safe and useful for
        # future opt-in, but the preference itself remains authoritative.
        if pref == "off" and not row.get("notifications"):
            manager_warnings.append(
                "{}: off is implicit rather than explicit.".format(label)
            )

    if manager_errors:
        report.fail(
            "Manager notification safety",
            "{} issue(s): {}".format(len(manager_errors), " | ".join(manager_errors)),
        )
    else:
        report.ok(
            "Manager notification safety",
            "All current managers have explicit, valid roster-alert preferences and required contacts.",
        )

    if manager_warnings:
        report.warn("Manager preference notes", " | ".join(manager_warnings))

    report.ok(
        "Roster preference totals",
        "off={off}, email={email}, sms={sms}, both={both}".format(**pref_counts),
    )


def _audit_delivery(report, config, managers_payload):
    delivery = config.get("delivery", {}) or {}
    sms_cfg = delivery.get("sms", {}) or {}

    if not sms_cfg.get("enabled", False):
        report.fail("SMS provider", "delivery.sms.enabled is false.")
    elif str(sms_cfg.get("provider", "") or "").strip().lower() != "textbelt":
        report.fail(
            "SMS provider",
            "Expected provider 'textbelt'; found {!r}.".format(sms_cfg.get("provider")),
        )
    else:
        report.ok("SMS provider", "Textbelt is enabled.")

    textbelt_cfg = sms_cfg.get("textbelt", {}) or {}
    env_name = str(
        textbelt_cfg.get("api_key_env", "LEAGUELAB_TEXTBELT_API_KEY") or ""
    ).strip()

    if not env_name:
        report.fail("Textbelt API key", "api_key_env is blank.")
    elif not os.environ.get(env_name):
        report.fail(
            "Textbelt API key",
            "{} is not present in this process environment.".format(env_name),
        )
    else:
        report.ok(
            "Textbelt API key",
            "{} is present (value not displayed).".format(env_name),
        )

    try:
        dispatcher = NotificationDispatcher(delivery)
        status = dispatcher.provider_status()
        report.ok(
            "Dispatcher",
            "email={}, sms={}".format(
                status.get("email", "disabled"),
                status.get("sms", "disabled"),
            ),
        )
    except Exception as exc:
        report.fail("Dispatcher", str(exc))

    managers = managers_payload.get("managers", {}) or {}
    admin_cfg = config.get("admin_notifications", {}).get("sms", {}) or {}

    if not admin_cfg.get("enabled", False):
        report.fail("Admin failure SMS", "admin_notifications.sms.enabled is false.")
        return

    if not admin_cfg.get("send_on_errors", True):
        report.fail("Admin failure SMS", "send_on_errors is false.")
        return

    guid = str(admin_cfg.get("manager_guid", "") or "").strip()
    row = managers.get(guid, {}) if guid else {}
    phone = str(row.get("phone", "") or "").strip()

    if not guid:
        report.fail("Admin failure SMS", "manager_guid is blank.")
    elif not isinstance(row, dict) or not row:
        report.fail("Admin failure SMS", "Configured admin GUID is not in managers.json.")
    elif not phone:
        report.fail("Admin failure SMS", "Configured admin manager has no phone number.")
    elif not PHONE_RE.match(phone):
        report.fail("Admin failure SMS", "Admin phone is not in E.164 format.")
    else:
        report.ok("Admin failure SMS", "Enabled and routed to a configured admin phone.")


def _audit_roster_alert_config(report, config):
    cfg = config.get("roster_alerts", {}) or {}

    if not cfg.get("enabled", False):
        report.fail("Roster alerts", "roster_alerts.enabled is false.")
    else:
        report.ok("Roster alerts", "Enabled.")

    try:
        checkpoints = sorted(
            set(int(x) for x in cfg.get("alert_minutes_before_kickoff", [])),
            reverse=True,
        )
    except Exception:
        checkpoints = []

    if not checkpoints:
        report.fail(
            "Alert checkpoints",
            "No valid alert_minutes_before_kickoff values are configured.",
        )
    elif any(x <= 0 for x in checkpoints):
        report.fail(
            "Alert checkpoints",
            "All alert checkpoints must be positive minutes; found {}.".format(
                cfg.get("alert_minutes_before_kickoff")
            ),
        )
    else:
        report.ok(
            "Alert checkpoints",
            "{} minute(s) before kickoff.".format(
                ", ".join(str(x) for x in checkpoints)
            ),
        )

    if bool(cfg.get("repeat_alerts", False)):
        report.warn(
            "Duplicate suppression",
            "repeat_alerts is true; repeated scheduler execution may resend alerts.",
        )
    else:
        report.ok("Duplicate suppression", "repeat_alerts is false.")


def _audit_schedule(report, config, season, week, refresh_schedule):
    try:
        source, label = _build_schedule_source(
            config=config,
            season=season,
            week=week,
            force_refresh=bool(refresh_schedule),
        )
        games = source.load_games()
    except Exception as exc:
        report.fail("NFL schedule", str(exc))
        return

    if not games:
        report.fail(
            "NFL schedule",
            "Schedule source loaded but returned no games for season {} week {}.".format(
                season, week
            ),
        )
        return

    report.ok(
        "NFL schedule",
        "{} game record(s) loaded via {}.".format(len(games), label),
    )


def _audit_yahoo_refresh(report, season, week):
    try:
        result = refresh_week_rosters(season, week)
    except Exception as exc:
        report.fail("Yahoo fresh roster check", str(exc))
        return

    count = int(result.get("rosters_updated", 0) or 0)
    if count <= 0:
        report.fail(
            "Yahoo fresh roster check",
            "Refresh completed but no roster files were updated.",
        )
    else:
        report.ok(
            "Yahoo fresh roster check",
            "{} team roster(s) freshly fetched.".format(count),
        )


def main():
    parser = argparse.ArgumentParser(
        description="Zero-send LeagueLab live-mode preflight validator."
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument(
        "--refresh-schedule",
        action="store_true",
        help="Force the production NFL schedule source to refresh.",
    )
    parser.add_argument(
        "--check-yahoo",
        action="store_true",
        help=(
            "Also authenticate to Yahoo and freshly fetch all week rosters. "
            "This may open the persistent Chrome profile but sends no notifications."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable results instead of the human report.",
    )
    args = parser.parse_args()

    report = Preflight()

    try:
        config = _load_notification_config()
        report.ok("Notification config", "Loaded successfully.")
    except Exception as exc:
        report.fail("Notification config", str(exc))
        config = {}

    try:
        managers_payload = _load_managers()
        count = len(managers_payload.get("managers", {}) or {})
        report.ok("Manager config", "{} configured manager row(s) loaded.".format(count))
    except Exception as exc:
        report.fail("Manager config", str(exc))
        managers_payload = {"managers": {}}

    configured_mode = str(config.get("mode", "preview") or "").strip().lower()
    if configured_mode == "live":
        report.warn(
            "Configured mode",
            "notifications.json is already set to live. Preflight itself still sends nothing.",
        )
    else:
        report.ok(
            "Configured mode",
            "{} (safe while validating).".format(configured_mode or "unset"),
        )

    _audit_roster_alert_config(report, config)
    _audit_delivery(report, config, managers_payload)
    _audit_managers(report, args.season, managers_payload)
    _audit_schedule(
        report,
        config,
        season=args.season,
        week=args.week,
        refresh_schedule=args.refresh_schedule,
    )

    if args.check_yahoo:
        _audit_yahoo_refresh(report, args.season, args.week)
    else:
        report.warn(
            "Yahoo fresh roster check",
            "Skipped. Run again with --check-yahoo after the draft for final production validation.",
        )

    if args.json:
        payload = {
            "live_ready": not bool(report.failures),
            "failures": len(report.failures),
            "warnings": len(report.warnings),
            "checks": report.rows,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        report.render()

    # Non-zero exit code lets PowerShell/Task Scheduler/CI treat failed
    # preflight as a real blocker.
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
