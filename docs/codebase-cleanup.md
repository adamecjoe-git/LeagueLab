# Codebase cleanup

Work branch: `cleanup/codebase-review`. Newsletter generation and delivery remain
separate. The approved newsletter templates are unchanged.

## Completed

- Consolidated normalization in `src/leaguelab/normalize.py`. It includes ordered
  lineup slots, touchdown extraction, and reciprocal matchup score/result repair.
- Kept `python -m leaguelab.normalize_with_slots` as a compatibility entry point.
  Existing imports of public normalization helpers also continue to work.
- Made the weekly pipeline load the canonical normalizer directly. Import errors
  now surface instead of silently choosing another implementation.
- Missing scores remain pending; real zero scores still produce legitimate results.
  Teams without a matchup do not acquire fabricated opponents or results.
- Extracted shared bracket presentation helpers into `bracket_helpers.py` so the
  Yahoo postseason loader no longer imports the newsletter adapter.
- Added offline normalization regression tests alongside existing newsletter tests.

## Remaining review

- Challenge formulas are duplicated between the newsletter adapter and standalone
  challenge package. Consolidation needs parity checks for rounding, tied ranks,
  details, and configurable Finish Strong baselines. Do not change payout rules
  during this refactor.
- Legacy playoff simulation helpers still support existing tests; replace those
  fixtures before removing the helpers.
- Confirm the currently used Windows and GitHub alert schedules before retiring
  any scheduler. Their planner interfaces differ and need a separate repair.
- Review historical-season manager refresh behavior before changing manager storage.
- Retain standalone/manual tools, old patch archives, generated examples, and
  authentication assets until their operational use is established.

## Verification

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

The suite runs offline. A full-history checkout is required for the approved
Weeks 1–13 renderer comparison. Real Yahoo data is not included in these tests;
regenerate the 2025 newsletters locally before merging this branch.
