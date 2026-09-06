import csv
import io
from datetime import date, datetime, timedelta, timezone
from urllib.request import Request, urlopen

from leaguelab.schedule.espn_source import canonical_team_abbr


NFLVERSE_SCHEDULE_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
)


def _nth_weekday(year, month, weekday, n):
    first = date(year, month, 1)
    delta = (weekday - first.weekday()) % 7
    return first + timedelta(days=delta + 7 * (n - 1))


def _eastern_offset(game_date):
    """Return the US Eastern UTC offset for a date, without third-party tz deps."""
    year = game_date.year
    dst_start = _nth_weekday(year, 3, 6, 2)   # second Sunday in March
    dst_end = _nth_weekday(year, 11, 6, 1)    # first Sunday in November
    if dst_start <= game_date < dst_end:
        return timezone(timedelta(hours=-4))
    return timezone(timedelta(hours=-5))


def _parse_nflverse_kickoff(gameday, gametime):
    gameday = str(gameday or "").strip()
    gametime = str(gametime or "").strip()
    if not gameday or not gametime:
        return ""

    parsed_date = datetime.strptime(gameday, "%Y-%m-%d").date()

    parsed_time = None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            parsed_time = datetime.strptime(gametime, fmt).time()
            break
        except ValueError:
            continue

    if parsed_time is None:
        raise ValueError("Unsupported nflverse gametime: {}".format(gametime))

    kickoff = datetime.combine(parsed_date, parsed_time).replace(
        tzinfo=_eastern_offset(parsed_date)
    )
    return kickoff.isoformat()


def normalize_nflverse_csv(text, season, week, game_type="REG"):
    games = []
    reader = csv.DictReader(io.StringIO(text))

    for row in reader:
        try:
            row_season = int(row.get("season", -1))
            row_week = int(row.get("week", -1))
        except (TypeError, ValueError):
            continue

        if row_season != int(season) or row_week != int(week):
            continue

        if game_type and str(row.get("game_type", "")).upper() != str(game_type).upper():
            continue

        away = canonical_team_abbr(row.get("away_team"))
        home = canonical_team_abbr(row.get("home_team"))
        kickoff = _parse_nflverse_kickoff(row.get("gameday"), row.get("gametime"))
        if not away or not home or not kickoff:
            continue

        games.append(
            {
                "game_id": str(row.get("game_id") or ""),
                "away": away,
                "home": home,
                "kickoff": kickoff,
                "source": "nflverse",
            }
        )

    games.sort(key=lambda item: item.get("kickoff", ""))
    return games


class NflverseScheduleSource(object):
    def __init__(self, timeout_seconds=15, url=NFLVERSE_SCHEDULE_URL):
        self.timeout_seconds = int(timeout_seconds)
        self.url = url

    def fetch_csv(self):
        request = Request(
            self.url,
            headers={
                "User-Agent": "LeagueLab/1.0",
                "Accept": "text/csv,text/plain,*/*",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return response.read().decode("utf-8-sig")

    def fetch_week(self, season, week, game_type="REG"):
        text = self.fetch_csv()
        return normalize_nflverse_csv(
            text=text,
            season=season,
            week=week,
            game_type=game_type,
        )
