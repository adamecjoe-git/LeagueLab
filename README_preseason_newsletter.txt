LeagueLab Preseason Newsletter

New:
- src/leaguelab/preseason_newsletter.py
- data/config/2026/preseason.json

Sections:
1. Welcome
2. Payout Structure
3. Challenge Schedule -- INCLUDING PAYOUT AMOUNT FOR EVERY CHALLENGE
4. League Dues
5. Draft Report
6. Projected Standings (optimal legal projected lineup)
7. Players to Watch
8. Preseason Power Rankings
9. Week 1 Matchups

Run:
  python -m leaguelab.preseason_newsletter --season 2026

Output:
  output/2026/preseason_newsletter.html

The draft/projection sections intentionally show a pending state until Yahoo
draft results and projections are analyzed. No grades or projections are
invented.

Also included are newsletter.py and newsletter_blocks.py carrying forward the
latest requested bracket styling: blue/larger winner and struck-through loser.
