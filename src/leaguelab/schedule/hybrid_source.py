import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from leaguelab.schedule.espn_source import EspnScheduleSource
from leaguelab.schedule.json_source import JsonScheduleSource
from leaguelab.schedule.nflverse_source import NflverseScheduleSource


def _iso_utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _game_key(game):
    teams = sorted([str(game.get("away", "")), str(game.get("home", ""))])
    return "|".join(teams)


def _same_instant(left, right):
    try:
        a = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(right).replace("Z", "+00:00"))
        if a.tzinfo is None or b.tzinfo is None:
            return str(left) == str(right)
        return a.astimezone(timezone.utc) == b.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return str(left) == str(right)


def reconcile_games(nflverse_games, espn_games):
    """
    Use nflverse as the base schedule when available. ESPN verifies each matchup
    and wins on kickoff-time disagreements because it is used as the near-live
    schedule check. ESPN-only games are retained so an incomplete nflverse week
    cannot suppress an alert window.
    """
    nflverse_by_key = {_game_key(game): dict(game) for game in nflverse_games}
    espn_by_key = {_game_key(game): dict(game) for game in espn_games}

    all_keys = sorted(set(nflverse_by_key) | set(espn_by_key))
    merged = []

    for key in all_keys:
        nv = nflverse_by_key.get(key)
        espn = espn_by_key.get(key)

        if nv and espn:
            result = dict(nv)
            result["nflverse_kickoff"] = nv.get("kickoff", "")
            result["espn_kickoff"] = espn.get("kickoff", "")
            result["espn_verified"] = True

            if not _same_instant(nv.get("kickoff"), espn.get("kickoff")):
                result["kickoff"] = espn.get("kickoff")
                result["kickoff_source"] = "espn"
                result["schedule_difference"] = True
            else:
                result["kickoff_source"] = "nflverse"
                result["schedule_difference"] = False

            if espn.get("status"):
                result["status"] = espn.get("status")
            if espn.get("status_state"):
                result["status_state"] = espn.get("status_state")
            merged.append(result)
            continue

        if nv:
            result = dict(nv)
            result["espn_verified"] = False
            result["kickoff_source"] = "nflverse"
            merged.append(result)
            continue

        result = dict(espn)
        result["source"] = "espn"
        result["espn_verified"] = True
        result["kickoff_source"] = "espn"
        result["nflverse_missing"] = True
        merged.append(result)

    merged.sort(key=lambda item: item.get("kickoff", ""))
    return merged


class HybridScheduleSource(JsonScheduleSource):
    def __init__(
        self,
        cache_path,
        timeout_seconds=15,
        nflverse_url=None,
    ):
        super(HybridScheduleSource, self).__init__(cache_path)
        self.cache_path = Path(cache_path)
        self.timeout_seconds = int(timeout_seconds)
        kwargs = {"timeout_seconds": self.timeout_seconds}
        if nflverse_url:
            kwargs["url"] = nflverse_url
        self.nflverse = NflverseScheduleSource(**kwargs)
        self.espn = EspnScheduleSource(
            str(cache_path),
            timeout_seconds=self.timeout_seconds,
        )

    def _read_matching_cache(self, season, week):
        if not self.cache_path.exists():
            return None
        try:
            with open(str(self.cache_path), "r", encoding="utf-8") as handle:
                cached = json.load(handle)
            if (
                int(cached.get("season", -1)) == int(season)
                and int(cached.get("week", -1)) == int(week)
                and cached.get("games")
            ):
                return cached
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return None

    def _cache_age_ok(self, payload, max_age_minutes):
        fetched_at = str(payload.get("fetched_at", "") or "")
        if not fetched_at:
            return False
        if fetched_at.endswith("Z"):
            fetched_at = fetched_at[:-1] + "+00:00"
        try:
            fetched = datetime.fromisoformat(fetched_at)
        except ValueError:
            return False
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - fetched.astimezone(timezone.utc)
        return age <= timedelta(minutes=int(max_age_minutes))

    def refresh(self, season, week, season_type=2):
        errors = []
        nflverse_games = []
        espn_games = []

        try:
            nflverse_games = self.nflverse.fetch_week(
                season=season,
                week=week,
                game_type="REG" if int(season_type) == 2 else None,
            )
            if not nflverse_games:
                errors.append("nflverse returned no matching games")
        except Exception as exc:
            errors.append("nflverse: {}".format(exc))

        try:
            espn_payload = self.espn.fetch_week(
                season=season,
                week=week,
                season_type=season_type,
            )
            from leaguelab.schedule.espn_source import normalize_espn_scoreboard
            espn_games = normalize_espn_scoreboard(espn_payload)
            if not espn_games:
                errors.append("ESPN returned no matching games")
        except Exception as exc:
            errors.append("ESPN: {}".format(exc))

        if nflverse_games and espn_games:
            games = reconcile_games(nflverse_games, espn_games)
            source = "nflverse+espn"
            verified_by = "espn"
        elif nflverse_games:
            games = nflverse_games
            source = "nflverse"
            verified_by = None
        elif espn_games:
            games = []
            for game in espn_games:
                item = dict(game)
                item["source"] = "espn"
                item["kickoff_source"] = "espn"
                item["espn_verified"] = True
                games.append(item)
            source = "espn-fallback"
            verified_by = "espn"
        else:
            cached = self._read_matching_cache(season, week)
            if cached:
                cached["refresh_warning"] = "; ".join(errors)
                return cached, "cache-fallback"
            raise RuntimeError(
                "Unable to build NFL schedule: {}".format("; ".join(errors))
            )

        normalized = {
            "source": source,
            "primary_source": "nflverse",
            "verified_by": verified_by,
            "season": int(season),
            "week": int(week),
            "season_type": int(season_type),
            "fetched_at": _iso_utc_now(),
            "warnings": errors,
            "games": games,
        }

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.cache_path), "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, indent=2, sort_keys=True)

        return normalized, source

    def refresh_if_needed(
        self,
        season,
        week,
        season_type=2,
        max_age_minutes=30,
        force=False,
    ):
        cached = self._read_matching_cache(season, week)
        if not force and cached and self._cache_age_ok(cached, max_age_minutes):
            return cached, False, "cache"

        payload, source_label = self.refresh(
            season=season,
            week=week,
            season_type=season_type,
        )
        return payload, True, source_label
