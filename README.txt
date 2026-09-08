LeagueLab Week 17 Final Newsletter + Weekly Overachiever

Replace these files in src\leaguelab\:
- analytics.py
- newsletter.py
- newsletter_blocks.py
- newsletter_layouts.py
- postseason_newsletter.py

Changes:
1. Week 17 is the final newsletter. Weeks after the configured season end
   now raise a clear error instead of creating a postseason-wrap newsletter.
2. Week 17 begins:
   - League Champion
   - Challenge Winners
   - Challenge Payout Leaderboard
   - Total Payouts
   - Playoff Bracket
   - Toilet Bowl Champion
   - Toilet Bowl Bracket
3. Total Payouts uses Team + League + Challenges. League includes 1st/2nd/3rd
   and Toilet Bowl payouts. Challenge payouts are consolidated separately.
4. Beyond the Box Score replaces weekly All-Play King with Weekly Overachiever.
   It uses Yahoo projected_points when present. If projections are unavailable,
   it falls back to points above the team's entering-week scoring average.
5. Includes the validated Week 12 next_challenge() fix.
6. Includes the postseason bracket work with final regular-season seeds.

Default league payouts:
1st $210, 2nd $100, 3rd $40, Toilet Bowl $40.
Optional postseason.json override:
"league_payouts": {"first":210,"second":100,"third":40,"toilet_bowl":40}
