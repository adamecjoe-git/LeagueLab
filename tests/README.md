# Newsletter regression checks

Run from the repository root:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

The suite runs offline with synthetic 12-team data. It does not contact Yahoo,
send notifications, or modify league data. Use a full-history clone: the
Weeks 1–13 test compares entire rendered documents against the renderer at
`171576fdcd619c720b9646dd64146c210b1874ef` (the Round 2 starting point).

Coverage includes progressive Weeks 14–17 bracket scores, missing-official-score
fallback to roster starter totals, preservation of official zero scores, pending
matchups, all twelve final placements, the Week 16 Toilet Bowl cutoff, matchup
cards, awards/payouts, final power-ranking retention, and Week 17 accolade eligibility.

This verifies code behavior, not historical league winners. To finish historical
acceptance, regenerate Weeks 14–17 with the actual season's complete normalized
`weekly_team_results.csv` and `weekly_players.csv`, postseason configuration, and
raw draft results. Check scores against Yahoo and review the generated HTML in
the browser and intended email clients. Accolades currently define five awards;
Best Draft Pick and Waiver Pickup of the Year require draft data.
