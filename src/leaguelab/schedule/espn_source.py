import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from leaguelab.schedule.json_source import JsonScheduleSource


ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
)


TEAM_ALIASES = {
    "WSH": "WAS",
    "WAS": "WAS",
    "JAC": "JAX",
    "JAX": "JAX",
    "LA": "LAR",
    "LAR": "LAR",
    "STL": "LAR",
    "SD": "LAC",
    "LAC": "LAC",
    "OAK": "LV",
    "LV": "LV",
}


def canonical_team_abbr(value):
    value = str(value or "").strip().upper()
    if not value:
        return ""
    return TEAM_ALIASES.get(value, value)


def _iso_utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _extract_team(competition, home_away):
    competitors = competition.get("competitors", [])
    if not isinstance(competitors, list):
        return ""

    for competitor in competitors:
        if not isinstance(competitor, dict):
            continue
        if str(competitor.get("homeAway", "")).lower() != home_away:
            continue

        team = competitor.get("team", {})
        if not isinstance(team, dict):
            team = {}
        return canonical_team_abbr(team.get("abbreviation"))

    return ""


def normalize_espn_scoreboard(payload):
    """
    Convert ESPN's NFL scoreboard payload into LeagueLab's provider-neutral
    cached schedule format.
    """
    games = []
    events = payload.get("events", []) if isinstance(payload, dict) else []

    if not isinstance(events, list):
        events = []

    for event in events:
        if not isinstance(event, dict):
            continue

        competitions = event.get("competitions", [])
        if not isinstance(competitions, list) or not competitions:
            continue

        competition = competitions[0]
        if not isinstance(competition, dict):
            continue

        kickoff = str(event.get("date") or competition.get("date") or "").strip()
        if not kickoff:
            continue

        away = _extract_team(competition, "away")
        home = _extract_team(competition, "home")
        if not away or not home:
            continue

        status = event.get("status", {})
        if not isinstance(status, dict):
            status = {}
        status_type = status.get("type", {})
        if not isinstance(status_type, dict):
            status_type = {}

        status_name = str(status_type.get("name") or "")
        status_state = str(status_type.get("state") or "")

        # A canceled/postponed game should not create a false alert window.
        upper_status = status_name.upper()
        if "CANCELED" in upper_status or "CANCELLED" in upper_status:
            continue
        if "POSTPONED" in upper_status:
            continue

        games.append(
            {
                "game_id": str(event.get("id") or competition.get("id") or ""),
                "away": away,
                "home": home,
                "kickoff": kickoff,
                "status": status_name,
                "status_state": status_state,
            }
        )

    games.sort(key=lambda item: item.get("kickoff", ""))
    return games


class EspnScheduleSource(JsonScheduleSource):
    """
    NFL schedule source using ESPN's public scoreboard endpoint.

    No API key is required. Because this is a public, undocumented endpoint,
    LeagueLab keeps the normalized response in its own cache file so another
    schedule provider can replace ESPN later without changing alert logic.
    """

    def __init__(self, cache_path, timeout_seconds=15):
        super(EspnScheduleSource, self).__init__(cache_path)
        self.cache_path = Path(cache_path)
        self.timeout_seconds = int(timeout_seconds)

    def fetch_week(self, season, week, season_type=2):
        query = urlencode(
            {
                "dates": int(season),
                "seasontype": int(season_type),
                "week": int(week),
            }
        )
        url = "{}?{}".format(ESPN_SCOREBOARD_URL, query)
        request = Request(
            url,
            headers={
                "User-Agent": "LeagueLab/1.0",
                "Accept": "application/json",
            },
        )

        with urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw)

    def refresh(self, season, week, season_type=2):
        payload = self.fetch_week(season, week, season_type=season_type)
        games = normalize_espn_scoreboard(payload)

        if not games:
            raise RuntimeError(
                "ESPN returned no usable NFL games for season {} week {}.".format(
                    season,
                    week,
                )
            )

        normalized = {
            "source": "espn",
            "season": int(season),
            "week": int(week),
            "season_type": int(season_type),
            "fetched_at": _iso_utc_now(),
            "games": games,
        }

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.cache_path), "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, indent=2, sort_keys=True)

        return normalized

    def refresh_if_needed(
        self,
        season,
        week,
        season_type=2,
        max_age_minutes=30,
        force=False,
    ):
        if not force and self.cache_path.exists():
            try:
                with open(str(self.cache_path), "r", encoding="utf-8") as handle:
                    cached = json.load(handle)

                cached_season = int(cached.get("season", -1))
                cached_week = int(cached.get("week", -1))
                fetched_at = str(cached.get("fetched_at", "") or "")
                if fetched_at.endswith("Z"):
                    fetched_at = fetched_at[:-1] + "+00:00"
                fetched = datetime.fromisoformat(fetched_at)
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=timezone.utc)

                age = datetime.now(timezone.utc) - fetched.astimezone(timezone.utc)
                if (
                    cached_season == int(season)
                    and cached_week == int(week)
                    and age <= timedelta(minutes=int(max_age_minutes))
                ):
                    return cached, False
            except (ValueError, TypeError, OSError, json.JSONDecodeError):
                pass

        return self.refresh(season, week, season_type=season_type), True
