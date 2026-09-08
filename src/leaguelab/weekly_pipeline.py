"""
LeagueLab weekly pipeline.

Current milestone:
    normalized Yahoo data -> analytics -> newsletter HTML

This intentionally does NOT send email/SMS and does not touch the roster-alert
production scheduler.

Python 3.8 compatible.
"""

import argparse
import sys
from pathlib import Path

from leaguelab.analytics import run_weekly_analytics
from leaguelab.newsletter import write_newsletter
from leaguelab.yahoo.refresh import refresh_yahoo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_ROOT = PROJECT_ROOT / "data" / "normalized"


def _load_normalizer():
    """
    Support the current LeagueLab normalizer filename while leaving room for
    a later rename to normalize.py.
    """
    try:
        from leaguelab.normalize_with_slots import normalize
        return normalize
    except ImportError:
        try:
            from leaguelab.normalize import normalize
            return normalize
        except ImportError:
            return None


def _normalized_inputs_exist(season):
    root = NORMALIZED_ROOT / str(season)
    return (
        (root / "weekly_team_results.csv").exists()
        and (root / "weekly_players.csv").exists()
    )


def run_pipeline(
    season,
    week,
    skip_normalize=False,
    skip_refresh=False,
    league_name="XTreme Football",
):
    print("")
    print("LeagueLab Weekly Pipeline")
    print("=========================")
    print("Season {} | Week {}".format(season, week))
    print("")

    if week < 1 or week > 18:
        raise ValueError("Week must be between 1 and 18.")

    # Step 1: refresh the completed newsletter week plus the following week.
    print("[1/4] Refresh Yahoo data")

    if skip_refresh:
        print("      SKIPPED (using existing Yahoo data)")
    else:
        refresh_yahoo(
            season=season,
            mode="newsletter",
            week=week,
        )
        print("      OK")

    # Step 2: normalize the freshly captured Yahoo data.
    print("")
    print("[2/4] Normalize Yahoo data")

    if skip_normalize:
        if not _normalized_inputs_exist(season):
            raise RuntimeError(
                "--skip-normalize was used but normalized inputs do not exist "
                "for season {}.".format(season)
            )
        print("      SKIPPED (using existing normalized files)")
    else:
        normalize = _load_normalizer()
        if normalize is None:
            if not _normalized_inputs_exist(season):
                raise RuntimeError(
                    "LeagueLab normalizer could not be imported and normalized "
                    "inputs are missing."
                )
            print("      Normalizer module not found; using existing normalized files.")
        else:
            normalize(season)
            print("      OK")

    print("")
    print("[3/4] Weekly analytics")
    result = run_weekly_analytics(season, end_week=week)
    print("      OK")

    print("")
    print("[4/4] Newsletter HTML")
    newsletter_path = write_newsletter(
        season=season,
        week=week,
        analytics_result=result,
        league_name=league_name,
    )
    print("      OK")

    print("")
    print("Pipeline complete")
    print("=================")
    print("Newsletter:")
    print("  {}".format(newsletter_path))
    print("")
    print("No email or SMS was sent.")
    return newsletter_path


def main():
    parser = argparse.ArgumentParser(
        description="Build a LeagueLab weekly newsletter from local Yahoo data."
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument(
        "--skip-normalize",
        action="store_true",
        help="Use existing normalized CSV files without rerunning normalization.",
    )
    parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help=(
            "Use existing Yahoo raw data without refreshing. Intended for "
            "historical testing/debug only."
        ),
    )
    parser.add_argument(
        "--league-name",
        default="XTreme Football",
        help="Display name used in the newsletter header.",
    )
    args = parser.parse_args()

    try:
        run_pipeline(
            season=args.season,
            week=args.week,
            skip_normalize=args.skip_normalize,
            skip_refresh=args.skip_refresh,
            league_name=args.league_name,
        )
    except Exception as exc:
        print("")
        print("PIPELINE FAILED")
        print("===============")
        print(str(exc))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
