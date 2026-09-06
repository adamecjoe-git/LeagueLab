import json
from datetime import datetime


def parse_iso_datetime(value):
    value = str(value or "").strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


class JsonScheduleSource(object):
    """
    Reads LeagueLab's provider-neutral cached NFL schedule JSON.

    Expected structure:
    {
      "games": [
        {
          "game_id": "...",
          "away": "GB",
          "home": "CHI",
          "kickoff": "2026-09-13T17:00:00Z"
        }
      ]
    }
    """

    def __init__(self, path):
        self.path = path

    def load_payload(self):
        with open(self.path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def load_games(self):
        payload = self.load_payload()
        games = payload.get("games", [])
        if not isinstance(games, list):
            raise ValueError("Schedule JSON must contain a 'games' list.")
        return games

    def next_kickoff_window(self, now, lookahead_minutes):
        games = self.load_games()
        candidates = []

        for game in games:
            kickoff_text = str(game.get("kickoff", "") or "").strip()
            if not kickoff_text:
                continue

            kickoff = parse_iso_datetime(kickoff_text)
            delta_seconds = (kickoff - now).total_seconds()

            if delta_seconds < 0:
                continue

            if delta_seconds <= int(lookahead_minutes) * 60:
                candidates.append((kickoff, game))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        source_kickoff = candidates[0][0]

        # Display the kickoff in the caller's local/test timezone. ESPN emits
        # UTC, while manual caches may already contain a local offset.
        next_kickoff = source_kickoff.astimezone(now.tzinfo)

        # Games starting at exactly the same instant are one alert window,
        # regardless of how their time zones were represented in the source.
        next_timestamp = source_kickoff.timestamp()
        window_games = []
        for kickoff, game in candidates:
            if kickoff.timestamp() == next_timestamp:
                window_games.append(game)

        teams = set()
        for game in window_games:
            for key in ("away", "home"):
                team = str(game.get(key, "") or "").strip().upper()
                if team:
                    teams.add(team)

        return {
            "kickoff": next_kickoff,
            "games": window_games,
            "teams": sorted(teams),
        }
    def alert_day_window(self, now, lookahead_minutes):
        """Return the next kickoff trigger plus every NFL game remaining today.

        The trigger is still the next kickoff within lookahead_minutes, but the
        returned team set covers all games later on the same local calendar day.
        This lets one roster message surface later-day issues too.
        """
        trigger = self.next_kickoff_window(now, lookahead_minutes)
        if not trigger:
            return None

        remaining_games = []
        teams = set()
        local_day = now.date()

        for game in self.load_games():
            kickoff_text = str(game.get("kickoff", "") or "").strip()
            if not kickoff_text:
                continue
            kickoff = parse_iso_datetime(kickoff_text)
            local_kickoff = kickoff.astimezone(now.tzinfo)
            if local_kickoff.date() != local_day:
                continue
            if local_kickoff < now:
                continue
            remaining_games.append(dict(game, _local_kickoff=local_kickoff))
            for key in ("away", "home"):
                team = str(game.get(key, "") or "").strip().upper()
                if team:
                    teams.add(team)

        remaining_games.sort(key=lambda item: item["_local_kickoff"])
        return {
            "kickoff": trigger["kickoff"],
            "trigger_games": trigger["games"],
            "trigger_teams": trigger["teams"],
            "games": remaining_games,
            "teams": sorted(teams),
        }

