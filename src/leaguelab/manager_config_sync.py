import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_NOTIFICATIONS = {
    "roster_alerts": "off",
    "newsletter": "email",
}


def load_json(path):
    with open(str(path), "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")


def find_league_dir(season):
    base = PROJECT_ROOT / "data" / "raw" / "yahoo" / str(season)
    candidates = [p for p in base.glob("*") if p.is_dir()]
    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one Yahoo league directory under {}, found {}.".format(
                base, len(candidates)
            )
        )
    return candidates[0]


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            for item in walk(value):
                yield item
    elif isinstance(obj, list):
        for value in obj:
            for item in walk(value):
                yield item


def flatten_team_metadata(team_value):
    """Return the metadata objects that Yahoo stores inside team -> [[...]]."""
    if not isinstance(team_value, list):
        return []

    items = []
    for value in team_value:
        if isinstance(value, list):
            for child in value:
                if isinstance(child, dict):
                    items.append(child)
        elif isinstance(value, dict):
            items.append(value)
    return items


def extract_managers(payload):
    """Extract manager identity at the Yahoo team-object level.

    Yahoo represents each team roughly as:
        {"team": [[{"team_key": ...}, {"name": ...}, ..., {"managers": [...]}]]}

    Parsing the team as a unit prevents unrelated GUIDs from being mistaken for
    league managers and keeps team metadata associated with the correct person.
    """
    found = {}

    for node in walk(payload):
        if "team" not in node:
            continue

        metadata = flatten_team_metadata(node.get("team"))
        if not metadata:
            continue

        team_key = ""
        team_name = ""
        manager_blocks = []

        for item in metadata:
            if not team_key and item.get("team_key") not in (None, ""):
                team_key = str(item.get("team_key"))
            if not team_name and item.get("name") not in (None, ""):
                team_name = str(item.get("name"))
            managers = item.get("managers")
            if isinstance(managers, list):
                manager_blocks.extend(managers)

        if not team_key or not manager_blocks:
            continue

        for block in manager_blocks:
            if not isinstance(block, dict):
                continue
            manager = block.get("manager")
            if not isinstance(manager, dict):
                continue

            guid = str(manager.get("guid") or "").strip()
            if not guid:
                continue

            manager_name = str(
                manager.get("nickname")
                or manager.get("name")
                or manager.get("manager_name")
                or ""
            ).strip()

            found[guid] = {
                "manager_name": manager_name,
                "team_name": team_name,
                "team_key": team_key,
            }

    return found


def identity_history():
    """Read captured Yahoo seasons so retained managers stay human-readable."""
    history = {}
    base = PROJECT_ROOT / "data" / "raw" / "yahoo"
    if not base.exists():
        return history

    season_dirs = []
    for season_dir in base.glob("*"):
        if season_dir.is_dir():
            try:
                season_number = int(season_dir.name)
            except ValueError:
                continue
            season_dirs.append((season_number, season_dir))

    # Oldest -> newest means the latest known identity naturally wins.
    for season_number, season_dir in sorted(season_dirs):
        for teams_path in season_dir.glob("*/teams.json"):
            try:
                identities = extract_managers(load_json(teams_path))
            except (OSError, ValueError, TypeError):
                continue
            for guid, identity in identities.items():
                record = dict(identity)
                record["last_seen_season"] = season_number
                history[guid] = record

    return history


def has_meaningful_private_data(record):
    if not isinstance(record, dict):
        return False
    if str(record.get("email") or "").strip():
        return True
    if str(record.get("phone") or "").strip():
        return True

    prefs = record.get("notifications")
    if isinstance(prefs, dict) and prefs != DEFAULT_NOTIFICATIONS:
        return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Sync human-readable Yahoo manager identity into private LeagueLab contact config."
    )
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()

    teams_path = find_league_dir(args.season) / "teams.json"
    if not teams_path.exists():
        raise FileNotFoundError("Missing {}".format(teams_path))

    yahoo = extract_managers(load_json(teams_path))
    if not yahoo:
        raise RuntimeError("No Yahoo team managers were found in {}".format(teams_path))

    managers_path = PROJECT_ROOT / "data" / "config" / "managers.json"
    existing = load_json(managers_path).get("managers", {}) if managers_path.exists() else {}
    history = identity_history()

    merged = {}

    # Current league managers always appear, with current Yahoo identity.
    for guid, identity in yahoo.items():
        old = existing.get(guid, {}) or {}
        merged[guid] = {
            "manager_name": identity.get("manager_name", ""),
            "team_name": identity.get("team_name", ""),
            "team_key": identity.get("team_key", ""),
            "active_season": args.season,
            "email": old.get("email", ""),
            "phone": old.get("phone", ""),
            "notifications": old.get("notifications", dict(DEFAULT_NOTIFICATIONS)),
        }

    # Retain former managers only when they contain actual LeagueLab contact or
    # preference data. Enrich them from historical Yahoo captures so no person
    # is left as a bare GUID in a human-maintained file.
    retained_inactive = 0
    for guid, old in existing.items():
        if guid in merged or not has_meaningful_private_data(old):
            continue

        known = history.get(guid, {})
        manager_name = old.get("manager_name") or known.get("manager_name") or "Former manager"
        team_name = old.get("team_name") or known.get("team_name") or "Former league team"
        team_key = old.get("team_key") or known.get("team_key") or ""

        merged[guid] = {
            "manager_name": manager_name,
            "team_name": team_name,
            "team_key": team_key,
            "active_season": None,
            "email": old.get("email", ""),
            "phone": old.get("phone", ""),
            "notifications": old.get("notifications", dict(DEFAULT_NOTIFICATIONS)),
        }
        retained_inactive += 1

    save_json(managers_path, {"managers": merged})

    print("LeagueLab Manager Config Sync")
    print("=============================")
    print("Yahoo source: {}".format(teams_path))
    print("Active managers synced: {}".format(len(yahoo)))
    if retained_inactive:
        print("Former managers retained with contact/preferences: {}".format(retained_inactive))
    print("Output: {}".format(managers_path))
    print("")

    for guid, item in merged.items():
        status = "active" if item.get("active_season") == args.season else "inactive"
        print(
            "{} / {} / {} [{}]".format(
                item.get("manager_name") or "Unknown manager",
                item.get("team_name") or "Unknown team",
                status,
                guid,
            )
        )


if __name__ == "__main__":
    main()
