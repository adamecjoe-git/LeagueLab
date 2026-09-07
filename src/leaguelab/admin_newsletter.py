"""
LeagueLab newsletter league-admin adapter.

Reads dues and optional commissioner-note configuration without mutating any
LeagueLab configuration files.

Python 3.8 compatible.
"""

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = PROJECT_ROOT / "data" / "config"


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_json(path):
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _team_directory(analytics_result, week):
    """Return current team_key -> team_name from the requested week's analytics."""
    output = {}
    for row in analytics_result.get("weekly_analytics", []):
        if int(row.get("week", 0) or 0) != int(week):
            continue
        team_key = str(row.get("team_key") or "").strip()
        team_name = str(row.get("team_name") or "").strip()
        if team_key and team_name:
            output[team_key] = team_name
    return output


def _normalize_dues_rows(dues_config, teams):
    amount_per_team = _to_float(dues_config.get("amount_per_team"), 40.0)
    raw_teams = dues_config.get("teams", {})
    rows = []

    # Current/canonical format: object keyed by Yahoo team_key.
    if isinstance(raw_teams, dict):
        for team_key, team_name in teams.items():
            entry = raw_teams.get(team_key, {}) or {}
            paid = bool(entry.get("paid", False))
            amount_paid = _to_float(
                entry.get("amount_paid"),
                amount_per_team if paid else 0.0,
            )
            rows.append({
                "team_key": team_key,
                "team_name": team_name,
                "paid": paid,
                "amount_due": amount_per_team,
                "amount_paid": amount_paid,
                "balance_due": max(0.0, amount_per_team - amount_paid),
                "notes": str(entry.get("notes") or "").strip(),
            })
        return rows

    # Legacy format: list keyed by historical team name.
    legacy = {}
    if isinstance(raw_teams, list):
        for entry in raw_teams:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("team_name") or "").strip()
            if name:
                legacy[name.lower()] = entry

    for team_key, team_name in teams.items():
        entry = legacy.get(team_name.lower(), {}) or {}
        paid = bool(entry.get("paid", False))
        amount_paid = _to_float(
            entry.get("amount_paid"),
            amount_per_team if paid else 0.0,
        )
        rows.append({
            "team_key": team_key,
            "team_name": team_name,
            "paid": paid,
            "amount_due": amount_per_team,
            "amount_paid": amount_paid,
            "balance_due": max(0.0, amount_per_team - amount_paid),
            "notes": str(entry.get("notes") or "").strip(),
        })

    return rows


def build_league_admin_newsletter_data(season, week, analytics_result):
    """
    Build read-only newsletter admin data.

    Sources:
      data/config/<season>/dues.json
      data/config/<season>/league_admin.json   (optional)

    league_admin.json example:
      {
        "show_dues": true,
        "notes": [
          "Waivers process Wednesday morning.",
          "Please verify your contact information."
        ]
      }
    """
    teams = _team_directory(analytics_result, week)
    dues_path = CONFIG_ROOT / str(season) / "dues.json"
    admin_path = CONFIG_ROOT / str(season) / "league_admin.json"

    dues_config = _load_json(dues_path)
    admin_config = _load_json(admin_path) or {}

    show_dues = bool(admin_config.get("show_dues", True))
    dues = None

    if dues_config is not None and teams and show_dues:
        rows = _normalize_dues_rows(dues_config, teams)
        rows.sort(key=lambda row: row["team_name"].lower())

        paid_rows = [row for row in rows if row["balance_due"] <= 0.001]
        unpaid_rows = [row for row in rows if row["balance_due"] > 0.001]

        dues = {
            "amount_per_team": _to_float(dues_config.get("amount_per_team"), 40.0),
            "currency": str(dues_config.get("currency") or "USD"),
            "team_count": len(rows),
            "paid_count": len(paid_rows),
            "unpaid_count": len(unpaid_rows),
            "total_paid": round(sum(row["amount_paid"] for row in rows), 2),
            "balance_due": round(sum(row["balance_due"] for row in rows), 2),
            "unpaid": unpaid_rows,
        }

    notes = admin_config.get("notes", [])
    if isinstance(notes, str):
        notes = [notes]
    if not isinstance(notes, list):
        notes = []
    notes = [str(item).strip() for item in notes if str(item).strip()]

    if dues is None and not notes:
        return None

    return {
        "dues": dues,
        "notes": notes,
    }
