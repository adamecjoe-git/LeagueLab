import json
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
            headless=False,
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

    def get(self, path):
        """
        Fetch a Yahoo Fantasy endpoint from inside the authenticated
        Yahoo browser session.
        """

        url = f"{BASE_URL}{path}"

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

        if result["status"] != 200:
            raise RuntimeError(
                f"Yahoo request failed.\n"
                f"URL: {url}\n"
                f"Status: {result['status']}\n"
                f"Response: {result['body']}"
            )

        return json.loads(result["body"])

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


def find_league_keys(data):
    """
    Recursively find league_key values in Yahoo's JSON.

    We intentionally don't parse Yahoo's full response structure here.
    Yahoo's nested JSON format is inconsistent, so discovery only needs
    the league keys.
    """

    league_keys = []

    if isinstance(data, dict):
        for key, value in data.items():
            if key == "league_key":
                league_keys.append(value)
            else:
                league_keys.extend(find_league_keys(value))

    elif isinstance(data, list):
        for item in data:
            league_keys.extend(find_league_keys(item))

    return league_keys


def save_json(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


def capture_league(season=2026):
    print("Connecting to Yahoo...")

    with YahooFantasyClient() as yahoo:
        print("Checking authentication...")

        profile = yahoo.get_profile()

        print("Authenticated.")
        print(f"Discovering {season} leagues...")

        leagues = yahoo.get_leagues(season)

        league_keys = list(dict.fromkeys(
            find_league_keys(leagues)
        ))

        if not league_keys:
            raise RuntimeError(
                f"No Yahoo NFL leagues found for {season}."
            )

        print()
        print("Found league(s):")

        for league_key in league_keys:
            print(f"  {league_key}")

        for league_key in league_keys:
            print()
            print(f"Capturing {league_key}...")

            output_dir = (
                DATA_DIR
                / str(season)
                / league_key
            )

            save_json(
                profile,
                output_dir / "profile.json",
            )

            save_json(
                leagues,
                output_dir / "leagues.json",
            )

            print("  settings")
            save_json(
                yahoo.get_league_settings(league_key),
                output_dir / "settings.json",
            )

            print("  teams")
            save_json(
                yahoo.get_teams(league_key),
                output_dir / "teams.json",
            )

            print("  standings")
            save_json(
                yahoo.get_standings(league_key),
                output_dir / "standings.json",
            )

            print("  rosters")
            save_json(
                yahoo.get_rosters(league_key),
                output_dir / "rosters.json",
            )

            print("  draft results")
            save_json(
                yahoo.get_draft_results(league_key),
                output_dir / "draft_results.json",
            )

            print(f"Saved to: {output_dir}")

    print()
    print("Capture complete.")


if __name__ == "__main__":
    capture_league()