import csv
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_ROOT = PROJECT_ROOT / "data" / "normalized"
RAW_YAHOO_ROOT = PROJECT_ROOT / "data" / "raw" / "yahoo"
OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"
CONFIG_ROOT = PROJECT_ROOT / "data" / "config"


DEFAULT_DUES_CONFIG = {
    "currency": "USD",
    "amount_per_team": 40,
    "teams": {}
}


def read_csv(path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def record_text(wins, losses, ties):
    if ties:
        return "{}-{}-{}".format(
            wins,
            losses,
            ties,
        )

    return "{}-{}".format(
        wins,
        losses,
    )


def build_regular_season_standings(
    team_rows,
    end_week,
):
    teams = {}

    for row in team_rows:
        week = to_int(
            row.get("week")
        )

        if week < 1 or week > end_week:
            continue

        team_key = row["team_key"]

        if team_key not in teams:
            teams[team_key] = {
                "team_key": team_key,
                "team_id": row.get(
                    "team_id",
                    "",
                ),
                "team_name": row["team_name"],
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "points_for": 0.0,
            }

        team = teams[team_key]

        # Keep the most recent normalized team name seen.
        team["team_name"] = row["team_name"]

        team["points_for"] += to_float(
            row.get("points")
        )

        result = str(
            row.get("result")
            or ""
        ).strip().upper()

        if result == "W":
            team["wins"] += 1
        elif result == "L":
            team["losses"] += 1
        elif result == "T":
            team["ties"] += 1

    rows = []

    for team in teams.values():
        games = (
            team["wins"]
            + team["losses"]
            + team["ties"]
        )

        win_pct = (
            (
                team["wins"]
                + 0.5 * team["ties"]
            )
            / games
            if games
            else 0.0
        )

        row = dict(team)
        row["win_pct"] = win_pct
        row["points_for"] = round(
            row["points_for"],
            2,
        )
        rows.append(row)

    rows = sorted(
        rows,
        key=lambda row: (
            -row["win_pct"],
            -row["points_for"],
            row["team_name"].lower(),
        ),
    )

    for rank, row in enumerate(
        rows,
        start=1,
    ):
        row["rank"] = rank
        row["record"] = record_text(
            row["wins"],
            row["losses"],
            row["ties"],
        )

    return rows


def build_losers_trophy(
    team_rows,
    regular_season_end_week,
):
    standings = build_regular_season_standings(
        team_rows,
        regular_season_end_week,
    )

    if not standings:
        raise RuntimeError(
            "Could not determine regular-season standings."
        )

    recipient = standings[-1]

    return {
        "regular_season_end_week": int(
            regular_season_end_week
        ),
        "rank": recipient["rank"],
        "team_key": recipient["team_key"],
        "team_id": recipient["team_id"],
        "team_name": recipient["team_name"],
        "record": recipient["record"],
        "points_for": recipient["points_for"],
    }


def find_teams_json(season):
    season_root = (
        RAW_YAHOO_ROOT
        / str(season)
    )

    if not season_root.exists():
        return None

    candidates = sorted(
        season_root.rglob("teams.json")
    )

    if not candidates:
        return None

    # Prefer a league-level teams.json over anything nested more deeply.
    candidates = sorted(
        candidates,
        key=lambda path: (
            len(path.parts),
            str(path).lower(),
        ),
    )

    return candidates[0]


def _walk_json(value):
    if isinstance(value, dict):
        yield value

        for child in value.values():
            for found in _walk_json(child):
                yield found

    elif isinstance(value, list):
        for child in value:
            for found in _walk_json(child):
                yield found


def _extract_manager_name(value):
    """
    Yahoo's fantasy JSON is deeply nested and its manager object shape
    can vary slightly. Prefer nickname/display name, then fall back to
    common name fields.
    """

    preferred_keys = (
        "nickname",
        "display_name",
        "displayName",
        "name",
    )

    for obj in _walk_json(value):
        for key in preferred_keys:
            candidate = obj.get(key)

            if isinstance(candidate, str):
                candidate = candidate.strip()

                if candidate:
                    return candidate

    return ""


def _recursive_find_first(value, target_key):
    """
    Return the first value found for target_key anywhere below value.
    """
    if isinstance(value, dict):
        if target_key in value:
            return value[target_key]

        for child in value.values():
            found = _recursive_find_first(
                child,
                target_key,
            )

            if found is not None:
                return found

    elif isinstance(value, list):
        for child in value:
            found = _recursive_find_first(
                child,
                target_key,
            )

            if found is not None:
                return found

    return None


def _extract_manager_guid(value):
    """
    Return Yahoo's stable manager GUID when present.
    """
    guid = _recursive_find_first(
        value,
        "guid",
    )

    if guid is None:
        return ""

    return str(guid).strip()


def load_yahoo_team_metadata(season):
    """
    Read captured Yahoo teams.json and return metadata keyed by
    Yahoo team_key.

    Yahoo stores each team under a dictionary key named "team".
    The team value is a nested list of small dictionaries, including
    team_key, name, and managers. Parse that entire team value rather
    than trying to infer team boundaries from arbitrary JSON nesting.
    """

    path = find_teams_json(
        season
    )

    if path is None:
        return {}

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    metadata = {}

    def parse_team(team_value):
        team_key = _recursive_find_first(
            team_value,
            "team_key",
        )

        if not team_key:
            return

        team_name = _recursive_find_first(
            team_value,
            "name",
        )

        managers = _recursive_find_first(
            team_value,
            "managers",
        )

        manager_name = ""
        manager_guid = ""

        if managers is not None:
            manager_name = _extract_manager_name(
                managers
            )
            manager_guid = _extract_manager_guid(
                managers
            )

        metadata[str(team_key)] = {
            "team_key": str(team_key),
            "team_name": (
                str(team_name)
                if team_name
                else ""
            ),
            "manager_name": manager_name,
            "manager_guid": manager_guid,
        }

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "team":
                    parse_team(
                        child
                    )
                else:
                    walk(
                        child
                    )

        elif isinstance(value, list):
            for child in value:
                walk(
                    child
                )

    walk(
        payload
    )

    return metadata

def load_manager_contacts():
    """
    Load LeagueLab-maintained contact information keyed by Yahoo manager GUID.

    Yahoo remains authoritative for nickname/team membership. This config
    stores only information Yahoo does not expose, currently email address.
    """
    path = (
        CONFIG_ROOT
        / "managers.json"
    )

    if not path.exists():
        return {
            "managers": {}
        }

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(file)

    managers = config.get(
        "managers",
        {}
    )

    if not isinstance(
        managers,
        dict,
    ):
        managers = {}

    return {
        "managers": managers
    }


def build_manager_contacts_config(
    yahoo_metadata,
    manager_contacts,
):
    """
    Keep one persistent manager record per Yahoo GUID.

    Existing emails are preserved. Newly discovered managers are added
    automatically with a blank email address.
    """
    existing = manager_contacts.get(
        "managers",
        {}
    )

    output = {}

    # Preserve existing manager records, including managers not in the
    # selected historical season.
    for guid, row in existing.items():
        if isinstance(row, dict):
            output[str(guid)] = {
                "email": str(
                    row.get("email")
                    or ""
                ).strip()
            }
        else:
            output[str(guid)] = {
                "email": ""
            }

    for team in yahoo_metadata.values():
        guid = str(
            team.get("manager_guid")
            or ""
        ).strip()

        if not guid:
            continue

        if guid not in output:
            output[guid] = {
                "email": ""
            }

    return {
        "managers": output
    }


def save_manager_contacts_config(config):
    path = (
        CONFIG_ROOT
        / "managers.json"
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            config,
            file,
            indent=2,
        )
        file.write("\n")

    return path


def build_manager_directory(
    yahoo_metadata,
    manager_contacts,
):
    """
    Combine current Yahoo identity/team data with LeagueLab email data.
    """
    contacts = manager_contacts.get(
        "managers",
        {}
    )

    rows = []

    for team_key, team in yahoo_metadata.items():
        guid = str(
            team.get("manager_guid")
            or ""
        ).strip()

        contact = (
            contacts.get(
                guid,
                {}
            )
            if guid
            else {}
        )

        rows.append(
            {
                "manager_guid": guid,
                "manager_name": str(
                    team.get("manager_name")
                    or ""
                ).strip(),
                "email": str(
                    contact.get("email")
                    or ""
                ).strip(),
                "team_key": team_key,
                "team_name": str(
                    team.get("team_name")
                    or ""
                ).strip(),
            }
        )

    rows.sort(
        key=lambda row: (
            row["manager_name"].lower(),
            row["team_name"].lower(),
        )
    )

    return rows


def load_dues_config(season):
    path = (
        CONFIG_ROOT
        / str(season)
        / "dues.json"
    )

    if not path.exists():
        return {
            "currency": "USD",
            "amount_per_team": 40,
            "teams": {},
        }

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def _legacy_dues_by_team_name(config):
    """
    Support the first LeagueLab dues.json format so existing paid
    statuses can be migrated automatically.
    """

    teams = config.get(
        "teams",
        []
    )

    output = {}

    if not isinstance(
        teams,
        list,
    ):
        return output

    for row in teams:
        team_name = str(
            row.get("team_name")
            or ""
        ).strip()

        if team_name:
            output[
                team_name.lower()
            ] = row

    return output


def _canonical_dues_by_team_key(config):
    teams = config.get(
        "teams",
        {}
    )

    if not isinstance(
        teams,
        dict,
    ):
        return {}

    return teams


def normalize_dues(
    standings,
    yahoo_metadata,
    dues_config,
    manager_contacts,
):
    amount_per_team = to_float(
        dues_config.get(
            "amount_per_team",
            40,
        )
    )

    canonical = (
        _canonical_dues_by_team_key(
            dues_config
        )
    )

    legacy = (
        _legacy_dues_by_team_name(
            dues_config
        )
    )

    rows = []

    for team in standings:
        team_key = team[
            "team_key"
        ]

        yahoo = yahoo_metadata.get(
            team_key,
            {},
        )

        # Use current Yahoo display values where available.
        team_name = (
            yahoo.get(
                "team_name"
            )
            or team["team_name"]
        )

        manager_name = yahoo.get(
            "manager_name"
        ) or ""

        manager_guid = yahoo.get(
            "manager_guid"
        ) or ""

        manager_email = ""

        if manager_guid:
            manager_email = str(
                manager_contacts.get(
                    "managers",
                    {}
                ).get(
                    manager_guid,
                    {}
                ).get(
                    "email",
                    ""
                )
                or ""
            ).strip()

        config_row = canonical.get(
            team_key
        )

        # One-time compatibility with the old team-name-based file.
        if config_row is None:
            config_row = legacy.get(
                team["team_name"].lower()
            )

        if config_row is None:
            config_row = {}

        paid = bool(
            config_row.get(
                "paid",
                False,
            )
        )

        amount_paid = to_float(
            config_row.get(
                "amount_paid",
                amount_per_team
                if paid
                else 0.0,
            )
        )

        notes = str(
            config_row.get(
                "notes"
            )
            or ""
        ).strip()

        rows.append(
            {
                "team_key": team_key,
                "team_id": team[
                    "team_id"
                ],
                "manager_guid": (
                    manager_guid
                ),
                "manager_name": (
                    manager_name
                ),
                "manager_email": (
                    manager_email
                ),
                "team_name": team_name,
                "paid": paid,
                "amount_due": round(
                    amount_per_team,
                    2,
                ),
                "amount_paid": round(
                    amount_paid,
                    2,
                ),
                "balance_due": round(
                    max(
                        0.0,
                        amount_per_team
                        - amount_paid,
                    ),
                    2,
                ),
                "notes": notes,
            }
        )

    return rows


def build_canonical_dues_config(
    dues_rows,
    dues_config,
):
    """
    Produce the persistent payment-only configuration.

    Yahoo metadata is deliberately not copied into this file. The only
    stable key is team_key; manager/team display names are refreshed
    from league data each run.
    """

    teams = {}

    for row in dues_rows:
        entry = {
            "paid": bool(
                row["paid"]
            )
        }

        if row["amount_paid"] not in (
            0.0,
            row["amount_due"],
        ):
            entry[
                "amount_paid"
            ] = row[
                "amount_paid"
            ]

        if row["notes"]:
            entry[
                "notes"
            ] = row[
                "notes"
            ]

        teams[
            row["team_key"]
        ] = entry

    return {
        "currency": dues_config.get(
            "currency",
            "USD",
        ),
        "amount_per_team": to_float(
            dues_config.get(
                "amount_per_team",
                40,
            )
        ),
        "teams": teams,
    }


def save_dues_config(
    season,
    config,
):
    path = (
        CONFIG_ROOT
        / str(season)
        / "dues.json"
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            config,
            file,
            indent=2,
        )
        file.write("\n")

    return path


def summarize_dues(
    dues_rows,
):
    paid_count = sum(
        1
        for row in dues_rows
        if row["paid"]
    )

    unpaid_count = (
        len(dues_rows)
        - paid_count
    )

    total_due = sum(
        row["amount_due"]
        for row in dues_rows
    )

    total_paid = sum(
        row["amount_paid"]
        for row in dues_rows
    )

    balance_due = sum(
        row["balance_due"]
        for row in dues_rows
    )

    return {
        "team_count": len(
            dues_rows
        ),
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "total_due": round(
            total_due,
            2,
        ),
        "total_paid": round(
            total_paid,
            2,
        ),
        "balance_due": round(
            balance_due,
            2,
        ),
    }


def save_json(
    path,
    payload,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
        )


def save_csv(
    path,
    rows,
    fieldnames,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(
            rows
        )


def run_league_admin(
    season,
    regular_season_end_week=14,
):
    normalized_dir = (
        NORMALIZED_ROOT
        / str(season)
    )

    team_path = (
        normalized_dir
        / "weekly_team_results.csv"
    )

    if not team_path.exists():
        raise RuntimeError(
            "Missing normalized team results:\n{}".format(
                team_path
            )
        )

    team_rows = read_csv(
        team_path
    )

    standings = build_regular_season_standings(
        team_rows,
        regular_season_end_week,
    )

    losers_trophy = build_losers_trophy(
        team_rows,
        regular_season_end_week,
    )

    yahoo_metadata = (
        load_yahoo_team_metadata(
            season
        )
    )

    manager_contacts = (
        load_manager_contacts()
    )

    canonical_manager_contacts = (
        build_manager_contacts_config(
            yahoo_metadata,
            manager_contacts,
        )
    )

    manager_contacts_path = (
        save_manager_contacts_config(
            canonical_manager_contacts
        )
    )

    manager_directory = (
        build_manager_directory(
            yahoo_metadata,
            canonical_manager_contacts,
        )
    )

    dues_config = load_dues_config(
        season
    )

    dues = normalize_dues(
        standings,
        yahoo_metadata,
        dues_config,
        canonical_manager_contacts,
    )

    # Rewrite old team-name-based config into canonical team_key form
    # while preserving payment state.
    canonical_dues = (
        build_canonical_dues_config(
            dues,
            dues_config,
        )
    )

    dues_config_path = (
        save_dues_config(
            season,
            canonical_dues,
        )
    )

    dues_summary = summarize_dues(
        dues
    )

    output_dir = (
        OUTPUT_ROOT
        / str(season)
        / "league_admin"
    )

    losers_path = (
        output_dir
        / "losers_trophy.json"
    )

    dues_json_path = (
        output_dir
        / "dues_status.json"
    )

    dues_csv_path = (
        output_dir
        / "dues_status.csv"
    )

    manager_json_path = (
        output_dir
        / "manager_directory.json"
    )

    manager_csv_path = (
        output_dir
        / "manager_directory.csv"
    )

    save_json(
        losers_path,
        losers_trophy,
    )

    save_json(
        manager_json_path,
        {
            "season": int(
                season
            ),
            "managers": manager_directory,
        },
    )

    save_csv(
        manager_csv_path,
        manager_directory,
        [
            "manager_guid",
            "manager_name",
            "email",
            "team_key",
            "team_name",
        ],
    )

    save_json(
        dues_json_path,
        {
            "season": int(
                season
            ),
            "summary": dues_summary,
            "teams": dues,
        },
    )

    save_csv(
        dues_csv_path,
        dues,
        [
            "team_key",
            "team_id",
            "manager_guid",
            "manager_name",
            "manager_email",
            "team_name",
            "paid",
            "amount_due",
            "amount_paid",
            "balance_due",
            "notes",
        ],
    )

    return {
        "season": int(
            season
        ),
        "regular_season_end_week": int(
            regular_season_end_week
        ),
        "standings": standings,
        "losers_trophy": losers_trophy,
        "dues": dues,
        "dues_summary": dues_summary,
        "dues_config_path": (
            dues_config_path
        ),
        "manager_contacts_path": (
            manager_contacts_path
        ),
        "manager_directory": (
            manager_directory
        ),
        "yahoo_teams_path": (
            find_teams_json(
                season
            )
        ),
        "losers_trophy_path": (
            losers_path
        ),
        "dues_json_path": (
            dues_json_path
        ),
        "dues_csv_path": (
            dues_csv_path
        ),
        "manager_json_path": (
            manager_json_path
        ),
        "manager_csv_path": (
            manager_csv_path
        ),
    }
