"""
LeagueLab Yahoo refresh orchestration.

Provides targeted refresh modes for:
- daily maintenance
- pre-game roster alerts
- newsletter generation
- manual selected-week refreshes
- full season rebuilds

Python 3.8 compatible.
"""

import argparse
import json
import sys
from pathlib import Path

from leaguelab.yahoo.client import (
    DATA_DIR,
    YahooFantasyClient,
    find_league_keys,
    find_team_keys,
    is_valid_json_file,
)


VALID_MODES = ("daily", "pregame", "newsletter", "manual", "full")
DEFAULT_MAX_WEEK = 17


def _atomic_save_json(data, path):
    """Write JSON atomically so a failed/interrupted refresh cannot corrupt cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")

    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)

    temp_path.replace(path)


def _load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _walk_draft_results(value, results):
    """Recursively collect Yahoo draft_result dictionaries."""
    if isinstance(value, dict):
        draft_result = value.get("draft_result")
        if isinstance(draft_result, dict):
            if draft_result.get("player_key"):
                results.append(draft_result)
        for child in value.values():
            _walk_draft_results(child, results)
    elif isinstance(value, list):
        for child in value:
            _walk_draft_results(child, results)


def _draft_player_keys(draft_payload):
    results = []
    _walk_draft_results(draft_payload, results)
    ordered = sorted(
        results,
        key=lambda item: int(item.get("pick") or 999999),
    )
    return list(dict.fromkeys(
        item.get("player_key") for item in ordered if item.get("player_key")
    ))


def _fetch_draft_analysis(yahoo, player_keys, batch_size=25):
    """Fetch Yahoo draft analysis for drafted players in stable-sized batches."""
    payloads = []
    for start in range(0, len(player_keys), int(batch_size)):
        batch = player_keys[start:start + int(batch_size)]
        path = "/players;player_keys={}/draft_analysis?format=json".format(
            ",".join(batch)
        )
        print(
            "  {:<28} batch {}-{}".format(
                "draft analysis",
                start + 1,
                start + len(batch),
            )
        )
        # YahooFantasyClient exposes its authenticated JSON request as get().
        payloads.append(yahoo.get(path))

    return {
        "season_snapshot": True,
        "player_count": len(player_keys),
        "player_keys": player_keys,
        "batches": payloads,
    }


def _capture_draft_analysis(yahoo, output_dir, overwrite=False):
    """Capture/freeze post-draft Yahoo ADP for the league's drafted players."""
    path = output_dir / "draft_analysis.json"
    if not overwrite and is_valid_json_file(path):
        print("  {:<28} keep existing".format("draft analysis"))
        return False

    draft_path = output_dir / "draft_results.json"
    if not is_valid_json_file(draft_path):
        raise RuntimeError(
            "Cannot capture draft analysis without valid draft_results.json."
        )

    draft_payload = _load_json(draft_path)
    player_keys = _draft_player_keys(draft_payload)
    if not player_keys:
        raise RuntimeError("No drafted player keys found in draft_results.json.")

    payload = _fetch_draft_analysis(yahoo, player_keys)
    _atomic_save_json(payload, path)
    return True


def _write(fetch_function, path, label, overwrite=True):
    """Fetch and save one endpoint, optionally preserving an existing valid file."""
    if not overwrite and is_valid_json_file(path):
        print("  {:<28} keep existing".format(label))
        return False

    print("  {:<28} refresh".format(label))
    payload = fetch_function()
    _atomic_save_json(payload, path)
    return True


def _discover_league(yahoo, season, requested_league_key=None):
    profile = yahoo.get_profile()
    leagues = yahoo.get_leagues(season)
    league_keys = list(dict.fromkeys(find_league_keys(leagues)))

    if requested_league_key:
        if requested_league_key not in league_keys:
            raise RuntimeError(
                "Yahoo league {} was not found for season {}. Found: {}".format(
                    requested_league_key,
                    season,
                    ", ".join(league_keys) if league_keys else "none",
                )
            )
        league_key = requested_league_key
    else:
        if len(league_keys) != 1:
            raise RuntimeError(
                "Expected exactly one Yahoo NFL league for season {}, found {}: {}. "
                "Use --league-key to choose one explicitly.".format(
                    season,
                    len(league_keys),
                    ", ".join(league_keys) if league_keys else "none",
                )
            )
        league_key = league_keys[0]

    return profile, leagues, league_key


def _load_or_refresh_teams(yahoo, league_key, output_dir, overwrite=True):
    teams_path = output_dir / "teams.json"

    if overwrite or not is_valid_json_file(teams_path):
        print("  {:<28} refresh".format("teams"))
        teams = yahoo.get_teams(league_key)
        _atomic_save_json(teams, teams_path)
    else:
        print("  {:<28} keep existing".format("teams"))
        teams = _load_json(teams_path)

    team_keys = list(dict.fromkeys(find_team_keys(teams)))
    if not team_keys:
        raise RuntimeError("No Yahoo team keys found for {}.".format(league_key))

    return teams, team_keys


def _refresh_week(
    yahoo,
    league_key,
    team_keys,
    output_dir,
    week,
    include_scoreboard=True,
    include_rosters=True,
    include_stats=True,
    include_players=True,
):
    week = int(week)
    if week < 1 or week > DEFAULT_MAX_WEEK:
        raise ValueError("Week must be between 1 and {}.".format(DEFAULT_MAX_WEEK))

    week_dir = output_dir / "weeks" / "week_{:02d}".format(week)
    counters = {
        "scoreboards_updated": 0,
        "rosters_updated": 0,
        "stats_updated": 0,
        "players_updated": 0,
    }

    print("")
    print("Week {}".format(week))
    print("------")

    if include_scoreboard:
        if _write(
            lambda: yahoo.get_week_scoreboard(league_key, week),
            week_dir / "scoreboard.json",
            "scoreboard",
            overwrite=True,
        ):
            counters["scoreboards_updated"] += 1

    for team_key in team_keys:
        team_id = team_key.split(".")[-1]

        if include_rosters:
            if _write(
                lambda team_key=team_key: yahoo.get_week_roster(team_key, week),
                week_dir / "team_{}_roster.json".format(team_id),
                "team {} roster".format(team_id),
                overwrite=True,
            ):
                counters["rosters_updated"] += 1

        if include_stats:
            if _write(
                lambda team_key=team_key: yahoo.get_week_stats(team_key, week),
                week_dir / "team_{}_stats.json".format(team_id),
                "team {} stats".format(team_id),
                overwrite=True,
            ):
                counters["stats_updated"] += 1

        if include_players:
            if _write(
                lambda team_key=team_key: yahoo.get_week_players(team_key, week),
                week_dir / "team_{}_players.json".format(team_id),
                "team {} players".format(team_id),
                overwrite=True,
            ):
                counters["players_updated"] += 1

    return counters


def _merge_counts(target, source):
    for key, value in source.items():
        target[key] = int(target.get(key, 0)) + int(value or 0)


def refresh_yahoo(season, mode, week=None, league_key=None, max_week=DEFAULT_MAX_WEEK):
    """
    Refresh Yahoo data according to a named policy.

    daily:
        Refresh league-level mutable data plus the supplied current week.

    pregame:
        Refresh exactly the data needed by roster-alert evaluation for the
        supplied week. This intentionally avoids historical recapture.

    newsletter:
        Refresh the completed newsletter week plus the following week (when
        <= 17), along with league-level mutable data.

    manual:
        Refresh league-level mutable data plus one selected week.

    full:
        Refresh all league-level data and every week 1..max_week.
    """
    mode = str(mode or "").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError("Mode must be one of: {}.".format(", ".join(VALID_MODES)))

    if mode != "full" and week is None:
        raise ValueError("--week is required for {} refresh mode.".format(mode))

    if week is not None:
        week = int(week)
        if week < 1 or week > DEFAULT_MAX_WEEK:
            raise ValueError("Week must be between 1 and {}.".format(DEFAULT_MAX_WEEK))

    max_week = int(max_week)
    if max_week < 1 or max_week > DEFAULT_MAX_WEEK:
        raise ValueError("max_week must be between 1 and {}.".format(DEFAULT_MAX_WEEK))

    print("")
    print("LeagueLab Yahoo Refresh")
    print("=======================")
    print("Season: {}".format(season))
    print("Mode:   {}".format(mode))
    if week is not None:
        print("Week:   {}".format(week))
    print("")
    print("Connecting to Yahoo...")

    result = {
        "season": int(season),
        "mode": mode,
        "league_key": None,
        "weeks_refreshed": [],
        "scoreboards_updated": 0,
        "rosters_updated": 0,
        "stats_updated": 0,
        "players_updated": 0,
        "league_files_updated": 0,
    }

    with YahooFantasyClient() as yahoo:
        print("Checking authentication...")
        profile, leagues, discovered_league_key = _discover_league(
            yahoo,
            season,
            requested_league_key=league_key,
        )
        league_key = discovered_league_key
        result["league_key"] = league_key

        print("Authenticated.")
        print("League: {}".format(league_key))

        output_dir = DATA_DIR / str(season) / league_key
        output_dir.mkdir(parents=True, exist_ok=True)

        # Always refresh discovery/profile snapshots. They are small and provide
        # a trustworthy marker that authentication and league discovery worked.
        _atomic_save_json(profile, output_dir / "profile.json")
        _atomic_save_json(leagues, output_dir / "leagues.json")
        result["league_files_updated"] += 2

        # Full refreshes everything. Other modes refresh only what may change or
        # is required for their consumer.
        if mode in ("daily", "newsletter", "manual", "full"):
            for label, fetcher, filename in (
                ("settings", lambda: yahoo.get_league_settings(league_key), "settings.json"),
                ("standings", lambda: yahoo.get_standings(league_key), "standings.json"),
                ("league rosters", lambda: yahoo.get_rosters(league_key), "rosters.json"),
                ("transactions", lambda: yahoo.get_transactions(league_key), "transactions.json"),
            ):
                if _write(fetcher, output_dir / filename, label, overwrite=True):
                    result["league_files_updated"] += 1

        # Teams are required to drive all per-team refreshes. Pregame mode also
        # refreshes this because team metadata/manager assignments can change.
        teams, team_keys = _load_or_refresh_teams(
            yahoo,
            league_key,
            output_dir,
            overwrite=True,
        )
        result["league_files_updated"] += 1

        # Draft results become immutable once the draft is complete. Preserve a
        # valid captured copy during normal operation; full mode deliberately
        # replaces it.
        if _write(
            lambda: yahoo.get_draft_results(league_key),
            output_dir / "draft_results.json",
            "draft results",
            overwrite=(mode == "full"),
        ):
            result["league_files_updated"] += 1

        # Freeze Yahoo ADP/draft-analysis at the first successful post-draft
        # capture. Routine refreshes preserve it so later ADP movement cannot
        # rewrite the historical draft evaluation. Full mode intentionally
        # replaces the snapshot along with draft_results.json.
        if _capture_draft_analysis(
            yahoo,
            output_dir,
            overwrite=(mode == "full"),
        ):
            result["league_files_updated"] += 1

        if mode == "pregame":
            counts = _refresh_week(
                yahoo,
                league_key,
                team_keys,
                output_dir,
                week,
                include_scoreboard=True,
                include_rosters=True,
                include_stats=False,
                include_players=True,
            )
            _merge_counts(result, counts)
            result["weeks_refreshed"].append(int(week))

        elif mode == "daily":
            counts = _refresh_week(
                yahoo,
                league_key,
                team_keys,
                output_dir,
                week,
                include_scoreboard=True,
                include_rosters=True,
                include_stats=True,
                include_players=True,
            )
            _merge_counts(result, counts)
            result["weeks_refreshed"].append(int(week))

        elif mode == "manual":
            counts = _refresh_week(
                yahoo,
                league_key,
                team_keys,
                output_dir,
                week,
                include_scoreboard=True,
                include_rosters=True,
                include_stats=True,
                include_players=True,
            )
            _merge_counts(result, counts)
            result["weeks_refreshed"].append(int(week))

        elif mode == "newsletter":
            newsletter_weeks = [int(week)]
            if int(week) < DEFAULT_MAX_WEEK:
                newsletter_weeks.append(int(week) + 1)

            for target_week in newsletter_weeks:
                counts = _refresh_week(
                    yahoo,
                    league_key,
                    team_keys,
                    output_dir,
                    target_week,
                    include_scoreboard=True,
                    include_rosters=True,
                    include_stats=True,
                    include_players=True,
                )
                _merge_counts(result, counts)
                result["weeks_refreshed"].append(target_week)

        elif mode == "full":
            for target_week in range(1, max_week + 1):
                counts = _refresh_week(
                    yahoo,
                    league_key,
                    team_keys,
                    output_dir,
                    target_week,
                    include_scoreboard=True,
                    include_rosters=True,
                    include_stats=True,
                    include_players=True,
                )
                _merge_counts(result, counts)
                result["weeks_refreshed"].append(target_week)

    print("")
    print("Refresh complete")
    print("================")
    print("League: {}".format(result["league_key"]))
    print("Weeks refreshed: {}".format(
        ", ".join(str(x) for x in result["weeks_refreshed"])
        if result["weeks_refreshed"]
        else "none"
    ))
    print("Team rosters updated: {}".format(result["rosters_updated"]))
    print("Player files updated: {}".format(result["players_updated"]))

    return result


def refresh_week_rosters(season, week):
    """
    Backward-compatible entry point used by roster_alert_runner/live_preflight.

    It now uses the shared pregame refresh policy rather than a separate Yahoo
    refresh implementation.
    """
    return refresh_yahoo(
        season=season,
        mode="pregame",
        week=week,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Refresh LeagueLab Yahoo data using a targeted refresh policy."
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--mode", choices=VALID_MODES, required=True)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument(
        "--league-key",
        default=None,
        help="Optional Yahoo league key when more than one league exists for a season.",
    )
    parser.add_argument(
        "--max-week",
        type=int,
        default=DEFAULT_MAX_WEEK,
        help="Full mode only: final week to capture (default 17).",
    )
    args = parser.parse_args()

    try:
        refresh_yahoo(
            season=args.season,
            mode=args.mode,
            week=args.week,
            league_key=args.league_key,
            max_week=args.max_week,
        )
    except Exception as exc:
        print("")
        print("YAHOO REFRESH FAILED")
        print("====================")
        print(str(exc))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
