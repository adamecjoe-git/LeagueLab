from collections import Counter


STARTER_REQUIREMENTS = {
    "QB": 1,
    "RB": 2,
    "WR": 2,
    "TE": 1,
    "W/R/T": 2,
    "DEF": 1,
}

NON_STARTER_POSITIONS = {
    "BN",
    "IR",
    "IR+",
    "IL",
    "NA",
}

ALERT_STATUSES = {
    "O",
    "OUT",
    "IR",
    "NA",
}

STATUS_LABELS = {
    "O": "OUT",
    "OUT": "OUT",
    "IR": "IR",
    "NA": "NA",
}


def _iter_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            for item in _iter_dicts(child):
                yield item
    elif isinstance(value, list):
        for child in value:
            for item in _iter_dicts(child):
                yield item


def _find_first(value, key):
    for item in _iter_dicts(value):
        if key in item:
            return item[key]
    return None


def _extract_team_identity(payload):
    return {
        "team_key": str(_find_first(payload, "team_key") or "").strip(),
        "team_name": str(_find_first(payload, "name") or "").strip(),
        "manager_name": str(_find_first(payload, "nickname") or "").strip(),
        "manager_guid": str(_find_first(payload, "guid") or "").strip(),
    }


def _extract_players(payload):
    players = []

    for item in _iter_dicts(payload):
        player = item.get("player")
        if not isinstance(player, list) or not player:
            continue

        metadata = player[0]

        player_key = str(_find_first(metadata, "player_key") or "").strip()
        if not player_key:
            continue

        name_value = _find_first(metadata, "name")
        if isinstance(name_value, dict):
            player_name = str(name_value.get("full", "") or "").strip()
        else:
            player_name = ""

        status = str(_find_first(metadata, "status") or "").strip()
        status_full = str(_find_first(metadata, "status_full") or "").strip()
        injury_note = str(_find_first(metadata, "injury_note") or "").strip()
        nfl_team = str(_find_first(metadata, "editorial_team_abbr") or "").strip()

        bye_week = ""
        bye_value = _find_first(metadata, "bye_weeks")
        if isinstance(bye_value, dict):
            bye_week = str(bye_value.get("week", "") or "").strip()

        selected_position = ""
        selected = _find_first(player, "selected_position")
        if isinstance(selected, list):
            for selected_item in selected:
                if isinstance(selected_item, dict) and "position" in selected_item:
                    selected_position = str(selected_item.get("position") or "").strip()

        players.append(
            {
                "player_key": player_key,
                "player_name": player_name,
                "status": status,
                "status_full": status_full,
                "injury_note": injury_note,
                "nfl_team": nfl_team,
                "bye_week": bye_week,
                "selected_position": selected_position,
            }
        )

    deduped = {}
    for player in players:
        key = (player["player_key"], player["selected_position"])
        if key not in deduped:
            deduped[key] = player

    return list(deduped.values())


def _is_starter(player):
    position = player.get("selected_position", "")
    return bool(position) and position not in NON_STARTER_POSITIONS


def _status_issue(player):
    short_status = str(player.get("status", "") or "").strip().upper()
    full_status = str(player.get("status_full", "") or "").strip().upper()

    # Yahoo may represent the same unavailable state in several ways.
    # Keep Questionable/Doubtful non-alerting, but catch statuses that mean
    # the player cannot currently be used in the lineup.
    if full_status == "INJURED RESERVE":
        return "IR"

    if short_status.startswith("PUP"):
        return "PUP"

    if "PHYSICALLY UNABLE TO PERFORM" in full_status:
        return "PUP"

    if short_status in ALERT_STATUSES:
        return STATUS_LABELS.get(short_status, short_status)

    if full_status in ALERT_STATUSES:
        return STATUS_LABELS.get(full_status, full_status)

    return ""


def _build_empty_slot_issues(players):
    counts = Counter()

    for player in players:
        if not _is_starter(player):
            continue
        counts[player["selected_position"]] += 1

    issues = []

    for position, required_count in STARTER_REQUIREMENTS.items():
        actual_count = counts.get(position, 0)
        for _ in range(max(required_count - actual_count, 0)):
            issues.append(
                {
                    "type": "empty_starter",
                    "position": position,
                    "player_key": "",
                    "player_name": "",
                    "nfl_team": "",
                    "kickoff_label": "",
                    "detail": "{} - EMPTY".format(position),
                }
            )

    return issues


def build_roster_alert(payload, fantasy_week, kickoff_teams, kickoff_by_team=None):
    """
    Build an alert for one Yahoo team.

    Only player-specific issues for NFL teams in kickoff_teams are included.
    Empty starter slots are included because an empty slot has no NFL team and
    therefore cannot be tied to a kickoff window.
    """
    identity = _extract_team_identity(payload)
    players = _extract_players(payload)

    kickoff_by_team = kickoff_by_team or {}
    kickoff_teams_normalized = set()
    for team in kickoff_teams:
        kickoff_teams_normalized.add(str(team).strip().upper())

    issues = _build_empty_slot_issues(players)

    for player in players:
        if not _is_starter(player):
            continue

        nfl_team = str(player.get("nfl_team", "") or "").strip().upper()

        # BYE has no kickoff, so treat it as a global unresolved starter issue
        # for the game day rather than tying it to one NFL kickoff window.
        if str(player.get("bye_week", "") or "") == str(fantasy_week):
            issues.append(
                {
                    "type": "bye",
                    "position": player["selected_position"],
                    "player_key": player["player_key"],
                    "player_name": player["player_name"],
                    "nfl_team": nfl_team,
                    "kickoff_label": "",
                    "detail": "{} ({}) - BYE".format(
                        player["player_name"],
                        player["selected_position"],
                    ),
                }
            )
            continue

        if not nfl_team or nfl_team not in kickoff_teams_normalized:
            continue

        status_label = _status_issue(player)
        if status_label:
            issues.append(
                {
                    "type": "unavailable",
                    "position": player["selected_position"],
                    "player_key": player["player_key"],
                    "player_name": player["player_name"],
                    "nfl_team": nfl_team,
                    "kickoff_label": str(kickoff_by_team.get(nfl_team, "") or ""),
                    "detail": "{} ({}) - {}".format(
                        player["player_name"],
                        player["selected_position"],
                        status_label,
                    ),
                }
            )

    # A notification is triggered only when the approaching kickoff has an
    # actionable issue. Once triggered, the message still contains every
    # unresolved issue remaining today. Global issues (EMPTY/BYE) have no NFL
    # kickoff of their own, so they are treated as actionable at the next
    # kickoff checkpoint.
    trigger_teams_normalized = set()
    for team in (kickoff_by_team.get("__trigger_teams__", []) or []):
        trigger_teams_normalized.add(str(team).strip().upper())

    trigger_issues = []
    for issue in issues:
        issue_team = str(issue.get("nfl_team", "") or "").strip().upper()
        if issue.get("type") in ("empty_starter", "bye"):
            trigger_issues.append(issue)
        elif issue_team and issue_team in trigger_teams_normalized:
            trigger_issues.append(issue)

    return {
        "fantasy_week": int(fantasy_week),
        "team_key": identity["team_key"],
        "team_name": identity["team_name"],
        "manager_name": identity["manager_name"],
        "manager_guid": identity["manager_guid"],
        "issues": issues,
        "trigger_issues": trigger_issues,
        "has_alert": bool(issues),
        "should_notify": bool(trigger_issues),
        "players_checked": len(players),
    }


def _issue_display(issue, include_kickoff=False):
    text = str(issue.get("detail", "") or "").strip()
    kickoff = str(issue.get("kickoff_label", "") or "").strip()
    if include_kickoff and kickoff:
        return "{} {}".format(kickoff, text)
    return text


def build_alert_message(alert, kickoff_label, league_name="Fantasy League"):
    if not alert.get("has_alert"):
        return ""

    lines = [
        "LeagueLab - {} Starting Roster Notification".format(league_name),
        "W{} {}".format(alert["fantasy_week"], alert.get("team_name") or "Fantasy Team"),
    ]
    for issue in alert.get("issues", []):
        lines.append(_issue_display(issue, include_kickoff=True))
    lines.append("Fix before {}".format(kickoff_label))
    return "\n".join(lines)


def build_sms_alert_message(alert, kickoff_label, league_name="Fantasy League"):
    """One compact SMS per fantasy team, with all remaining issues today."""
    if not alert.get("has_alert"):
        return ""

    lines = [
        "LeagueLab {} Starting Roster Notification".format(league_name),
        "W{} {}".format(alert["fantasy_week"], alert.get("team_name") or "Fantasy Team"),
    ]
    for issue in alert.get("issues", []):
        lines.append(_issue_display(issue, include_kickoff=True))
    lines.append("Fix before {}".format(kickoff_label))
    return "\n".join(lines)
