import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = "https://pub-api-ro.fantasysports.yahoo.com/fantasy/v2"
YAHOO_FANTASY_URL = "https://football.fantasysports.yahoo.com/"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BROWSER_PROFILE_DIR = PROJECT_ROOT / ".browser-profile"
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "yahoo"


class YahooFantasyClient:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None

    def __enter__(self):
        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            channel="chrome",
            headless=True,
        )

        self.page = (
            self.browser.pages[0]
            if self.browser.pages
            else self.browser.new_page()
        )

        self.page.goto(
            YAHOO_FANTASY_URL,
            wait_until="commit",
            timeout=60000,
        )

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()

    def get(self, path, retries=4, retry_delay=3):
        """
        Fetch a Yahoo Fantasy endpoint from inside the authenticated
        Yahoo browser session.

        Automatically retries transient browser/network failures.
        """

        url = f"{BASE_URL}{path}"
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                result = self.page.evaluate(
                    """async (url) => {
                        const response = await fetch(url, {
                            credentials: 'include'
                        });

                        return {
                            status: response.status,
                            body: await response.text()
                        };
                    }""",
                    url,
                )

                status = result["status"]
                body = result["body"]

                if status == 200:
                    return json.loads(body)

                # Authentication failures probably won't fix themselves
                # through retrying.
                if status in (401, 403):
                    raise RuntimeError(
                        f"Yahoo authentication failed.\n"
                        f"URL: {url}\n"
                        f"Status: {status}\n"
                        f"Response: {body}"
                    )

                raise RuntimeError(
                    f"Yahoo request failed.\n"
                    f"URL: {url}\n"
                    f"Status: {status}\n"
                    f"Response: {body}"
                )

            except Exception as exc:
                last_error = exc

                print(
                    f"        request failed "
                    f"(attempt {attempt}/{retries})"
                )

                if attempt < retries:
                    print(
                        f"        retrying in "
                        f"{retry_delay} seconds..."
                    )

                    time.sleep(retry_delay)

        raise RuntimeError(
            f"Yahoo request failed after "
            f"{retries} attempts.\n"
            f"URL: {url}\n"
            f"Last error: {last_error}"
        )

    # ---------------------------------------------------------
    # User / league
    # ---------------------------------------------------------

    def get_profile(self):
        return self.get(
            "/users;use_login=1/profile?format=json"
        )

    def get_leagues(self, season):
        return self.get(
            f"/users;use_login=1/"
            f"games;game_codes=nfl;seasons={season}/"
            f"leagues?format=json"
        )

    def get_league_settings(self, league_key):
        return self.get(
            f"/league/{league_key}/settings?format=json"
        )

    def get_teams(self, league_key):
        return self.get(
            f"/league/{league_key}/teams?format=json"
        )

    def get_standings(self, league_key):
        return self.get(
            f"/league/{league_key}/standings?format=json"
        )

    def get_rosters(self, league_key):
        return self.get(
            f"/league/{league_key}/teams/roster/players?format=json"
        )

    def get_draft_results(self, league_key):
        return self.get(
            f"/league/{league_key}/draftresults?format=json"
        )

    def get_transactions(self, league_key):
        """
        Return league transaction history.

        Includes roster transactions such as:
        - adds
        - drops
        - add/drop transactions
        - trades
        - commissioner transactions
        """

        return self.get(
            f"/league/{league_key}/transactions?format=json"
        )

    # ---------------------------------------------------------
    # Weekly league
    # ---------------------------------------------------------

    def get_week_scoreboard(self, league_key, week):
        return self.get(
            f"/league/{league_key}/"
            f"scoreboard;week={week}?format=json"
        )

    # ---------------------------------------------------------
    # Weekly team
    # ---------------------------------------------------------

    def get_week_roster(self, team_key, week):
        return self.get(
            f"/team/{team_key}/"
            f"roster;week={week}?format=json"
        )

    def get_week_stats(self, team_key, week):
        return self.get(
            f"/team/{team_key}/"
            f"stats;type=week;week={week}?format=json"
        )

    def get_week_players(self, team_key, week):
        """
        Historical weekly roster including:
        - player identity
        - eligible positions
        - selected lineup position
        - raw NFL stats
        - Yahoo fantasy points
        """

        return self.get(
            f"/team/{team_key}/"
            f"roster;week={week}/"
            f"players/stats;type=week;week={week}"
            f"?format=json"
        )


# =============================================================
# Yahoo JSON helpers
# =============================================================

def find_league_keys(data):
    """
    Recursively find all league_key values in Yahoo JSON.
    """

    league_keys = []

    if isinstance(data, dict):
        for key, value in data.items():
            if key == "league_key":
                league_keys.append(value)
            else:
                league_keys.extend(
                    find_league_keys(value)
                )

    elif isinstance(data, list):
        for item in data:
            league_keys.extend(
                find_league_keys(item)
            )

    return league_keys


def find_team_keys(data):
    """
    Recursively find all team_key values in Yahoo JSON.
    """

    team_keys = []

    if isinstance(data, dict):
        for key, value in data.items():
            if key == "team_key":
                team_keys.append(value)
            else:
                team_keys.extend(
                    find_team_keys(value)
                )

    elif isinstance(data, list):
        for item in data:
            team_keys.extend(
                find_team_keys(item)
            )

    return team_keys


# =============================================================
# File helpers
# =============================================================

def save_json(data, path):
    """
    Save formatted JSON.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


def is_valid_json_file(path):
    """
    Return True only if the file exists, is non-empty,
    and contains valid JSON.

    This means interrupted/corrupt files will automatically
    be downloaded again on the next run.
    """

    if not path.exists():
        return False

    if path.stat().st_size == 0:
        return False

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            json.load(file)

        return True

    except (json.JSONDecodeError, OSError):
        return False


def save_if_missing(fetch_function, path):
    """
    Skip a file if a valid copy already exists.

    Otherwise fetch and save it.
    """

    if is_valid_json_file(path):
        print("        already exists - skipping")
        return False

    data = fetch_function()

    save_json(
        data,
        path,
    )

    return True


# =============================================================
# League capture
# =============================================================

def capture_league(season=2025):
    print("Connecting to Yahoo...")

    with YahooFantasyClient() as yahoo:
        # -----------------------------------------------------
        # Authentication
        # -----------------------------------------------------

        print("Checking authentication...")

        profile = yahoo.get_profile()

        print("Authenticated.")
        print(f"Discovering {season} leagues...")

        leagues = yahoo.get_leagues(season)

        league_keys = list(
            dict.fromkeys(
                find_league_keys(leagues)
            )
        )

        if not league_keys:
            raise RuntimeError(
                f"No Yahoo NFL leagues found for {season}."
            )

        print()
        print("Found league(s):")

        for league_key in league_keys:
            print(f"  {league_key}")

        # -----------------------------------------------------
        # Each league
        # -----------------------------------------------------

        for league_key in league_keys:
            print()
            print(f"Capturing {league_key}...")

            output_dir = (
                DATA_DIR
                / str(season)
                / league_key
            )

            output_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            # -------------------------------------------------
            # Profile
            # -------------------------------------------------

            profile_path = (
                output_dir
                / "profile.json"
            )

            if is_valid_json_file(profile_path):
                print(
                    "  profile "
                    "(already exists - skipping)"
                )
            else:
                print("  profile")

                save_json(
                    profile,
                    profile_path,
                )

            # -------------------------------------------------
            # League discovery response
            # -------------------------------------------------

            leagues_path = (
                output_dir
                / "leagues.json"
            )

            if is_valid_json_file(leagues_path):
                print(
                    "  leagues "
                    "(already exists - skipping)"
                )
            else:
                print("  leagues")

                save_json(
                    leagues,
                    leagues_path,
                )

            # -------------------------------------------------
            # Settings
            # -------------------------------------------------

            print("  settings")

            save_if_missing(
                lambda: yahoo.get_league_settings(
                    league_key
                ),
                output_dir
                / "settings.json",
            )

            # -------------------------------------------------
            # Teams
            #
            # We need the team data in memory so we can get
            # team keys, even if teams.json already exists.
            # -------------------------------------------------

            teams_path = (
                output_dir
                / "teams.json"
            )

            if is_valid_json_file(teams_path):
                print(
                    "  teams "
                    "(already exists - loading)"
                )

                with teams_path.open(
                    "r",
                    encoding="utf-8",
                ) as file:
                    teams = json.load(file)

            else:
                print("  teams")

                teams = yahoo.get_teams(
                    league_key
                )

                save_json(
                    teams,
                    teams_path,
                )

            team_keys = list(
                dict.fromkeys(
                    find_team_keys(teams)
                )
            )

            print(
                f"  found {len(team_keys)} teams"
            )

            if not team_keys:
                raise RuntimeError(
                    f"No team keys found for "
                    f"{league_key}."
                )

            # -------------------------------------------------
            # Standings
            # -------------------------------------------------

            print("  standings")

            save_if_missing(
                lambda: yahoo.get_standings(
                    league_key
                ),
                output_dir
                / "standings.json",
            )

            # -------------------------------------------------
            # League rosters
            # -------------------------------------------------

            print("  rosters")

            save_if_missing(
                lambda: yahoo.get_rosters(
                    league_key
                ),
                output_dir
                / "rosters.json",
            )

            # -------------------------------------------------
            # Draft
            # -------------------------------------------------

            print("  draft results")

            save_if_missing(
                lambda: yahoo.get_draft_results(
                    league_key
                ),
                output_dir
                / "draft_results.json",
            )

            # -------------------------------------------------
            # Transactions
            # -------------------------------------------------

            print("  transactions")

            save_if_missing(
                lambda: yahoo.get_transactions(
                    league_key
                ),
                output_dir
                / "transactions.json",
            )

            # -------------------------------------------------
            # Weekly data
            # -------------------------------------------------

            print()
            print("  Capturing weekly data...")

            for week in range(1, 18):
                print()
                print(f"    Week {week}")

                week_dir = (
                    output_dir
                    / "weeks"
                    / f"week_{week:02d}"
                )

                week_dir.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                # ---------------------------------------------
                # Scoreboard
                # ---------------------------------------------

                print("      scoreboard")

                save_if_missing(
                    lambda week=week:
                    yahoo.get_week_scoreboard(
                        league_key,
                        week,
                    ),
                    week_dir
                    / "scoreboard.json",
                )

                # ---------------------------------------------
                # Teams
                # ---------------------------------------------

                for team_key in team_keys:
                    team_id = (
                        team_key
                        .split(".")[-1]
                    )

                    # -----------------------------------------
                    # Historical roster
                    # -----------------------------------------

                    print(
                        f"      team {team_id}: "
                        f"roster"
                    )

                    save_if_missing(
                        lambda team_key=team_key,
                        week=week:
                        yahoo.get_week_roster(
                            team_key,
                            week,
                        ),
                        week_dir
                        / (
                            f"team_{team_id}"
                            f"_roster.json"
                        ),
                    )

                    # -----------------------------------------
                    # Weekly team points
                    # -----------------------------------------

                    print(
                        f"      team {team_id}: "
                        f"stats"
                    )

                    save_if_missing(
                        lambda team_key=team_key,
                        week=week:
                        yahoo.get_week_stats(
                            team_key,
                            week,
                        ),
                        week_dir
                        / (
                            f"team_{team_id}"
                            f"_stats.json"
                        ),
                    )

                    # -----------------------------------------
                    # Player weekly stats + fantasy points
                    # -----------------------------------------

                    print(
                        f"      team {team_id}: "
                        f"players + points"
                    )

                    save_if_missing(
                        lambda team_key=team_key,
                        week=week:
                        yahoo.get_week_players(
                            team_key,
                            week,
                        ),
                        week_dir
                        / (
                            f"team_{team_id}"
                            f"_players.json"
                        ),
                    )

            print()
            print(
                f"Saved to: {output_dir}"
            )

    print()
    print("Capture complete.")


def refresh_week_rosters(season, week):
    """
    Refresh every team roster for one Yahoo fantasy week.

    All Yahoo responses are fetched successfully before any existing roster
    file is overwritten. This prevents a failed refresh from leaving the
    league with a mixture of fresh and stale roster files.

    Returns a dictionary describing the refreshed league and file count.
    """
    season = int(season)
    week = int(week)

    if week < 1 or week > 18:
        raise ValueError("Fantasy week must be between 1 and 18.")

    print("Connecting to Yahoo for roster refresh...")

    with YahooFantasyClient() as yahoo:
        print("Checking authentication...")
        yahoo.get_profile()
        print("Authenticated.")

        leagues = yahoo.get_leagues(season)
        league_keys = list(dict.fromkeys(find_league_keys(leagues)))

        if not league_keys:
            raise RuntimeError(
                "No Yahoo NFL leagues found for {}.".format(season)
            )

        season_dir = DATA_DIR / str(season)
        existing_leagues = []
        if season_dir.exists():
            existing_leagues = [
                path.name for path in season_dir.iterdir() if path.is_dir()
            ]

        matching = [key for key in league_keys if key in existing_leagues]
        if len(matching) == 1:
            league_key = matching[0]
        elif len(league_keys) == 1:
            league_key = league_keys[0]
        else:
            raise RuntimeError(
                "Multiple Yahoo NFL leagues found for {} and LeagueLab could "
                "not determine which one to refresh: {}".format(
                    season, ", ".join(league_keys)
                )
            )

        print("Refreshing {} Week {} rosters...".format(league_key, week))

        teams = yahoo.get_teams(league_key)
        team_keys = list(dict.fromkeys(find_team_keys(teams)))
        if not team_keys:
            raise RuntimeError(
                "No team keys found for {}.".format(league_key)
            )

        fetched = []
        for team_key in team_keys:
            team_id = team_key.split(".")[-1]
            print("  team {}: roster".format(team_id))
            payload = yahoo.get_week_roster(team_key, week)
            if not isinstance(payload, dict) or not payload:
                raise RuntimeError(
                    "Yahoo returned an invalid roster payload for {}.".format(
                        team_key
                    )
                )
            fetched.append((team_id, payload))

    output_dir = (
        DATA_DIR
        / str(season)
        / league_key
        / "weeks"
        / "week_{:02d}".format(week)
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Yahoo has been closed and every team fetch succeeded. Only now replace
    # the cached files used by the alert engine.
    for team_id, payload in fetched:
        save_json(
            payload,
            output_dir / "team_{}_roster.json".format(team_id),
        )

    print(
        "Yahoo roster refresh complete: {} team rosters updated.".format(
            len(fetched)
        )
    )

    return {
        "season": season,
        "week": week,
        "league_key": league_key,
        "rosters_updated": len(fetched),
    }


# =============================================================
# Main
# =============================================================

if __name__ == "__main__":
    capture_league(season=2026)