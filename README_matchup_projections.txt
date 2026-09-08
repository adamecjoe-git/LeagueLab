LeagueLab - Matchup Projection Update

Replace these files under src/leaguelab:
- upcoming_matchups.py
- newsletter_blocks.py
- postseason_newsletter.py

Changes:
- Next Week's Matchups now displays Yahoo projected points when available.
- Main playoff bracket displays "Proj X.X" for future matchups when Yahoo projections are available.
- Toilet Bowl bracket displays projections when available.
- Completed bracket matchups continue to show actual scores instead of projections.
- Missing/zero projections are omitted.
- Historical newsletter generation only exposes actual bracket scores through the newsletter week, so future results do not leak into earlier bracket previews.

Python 3.8 compatible.
