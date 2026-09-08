LeagueLab Yahoo Refresh Architecture
===================================

Changed files
-------------
src/leaguelab/yahoo/refresh.py          NEW shared Yahoo refresh engine
src/leaguelab/weekly_pipeline.py        Newsletter runs now refresh first
src/leaguelab/roster_alert_runner.py    Pregame alerts now use shared refresh engine

Refresh modes
-------------
daily       league-level mutable data + selected current week
pregame     selected week scoreboard/rosters/player data for roster alerts
newsletter  completed week + following week + league-level mutable data
manual      selected week + league-level mutable data
full        full season weeks 1-17 + all league-level data

Examples
--------
python -m leaguelab.yahoo.refresh --season 2026 --mode daily --week 1
python -m leaguelab.yahoo.refresh --season 2026 --mode pregame --week 1
python -m leaguelab.yahoo.refresh --season 2026 --mode newsletter --week 1
python -m leaguelab.yahoo.refresh --season 2026 --mode manual --week 1
python -m leaguelab.yahoo.refresh --season 2026 --mode full

Weekly pipeline
---------------
Normal run now does:
1. Yahoo newsletter refresh
2. Normalize
3. Analytics
4. Newsletter HTML

python -m leaguelab.weekly_pipeline --season 2026 --week 1

For historical/debug-only runs where Yahoo should not be contacted:
python -m leaguelab.weekly_pipeline --season 2025 --week 14 --skip-refresh

Safety / data behavior
----------------------
- Writes use an atomic temporary file + replace operation.
- Normal refresh modes do not recapture old historical weeks.
- Newsletter mode intentionally refreshes the completed week and next week.
- Pregame mode refreshes only the active week and avoids full-season recapture.
- Draft results are preserved once valid, except in full mode.
- 2025 is untouched unless you explicitly run a 2025 command.
