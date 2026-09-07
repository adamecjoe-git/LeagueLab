"""
LeagueLab weekly pipeline.

normalized Yahoo data -> analytics -> challenge update -> newsletter HTML

No email/SMS is sent and the roster-alert production scheduler is untouched.

Python 3.8 compatible.
"""

import argparse
import sys
from pathlib import Path

from leaguelab.analytics import run_weekly_analytics
from leaguelab.admin_newsletter import build_league_admin_newsletter_data
from leaguelab.challenge_newsletter import build_challenge_newsletter_data
from leaguelab.newsletter import write_newsletter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NORMALIZED_ROOT = PROJECT_ROOT / "data" / "normalized"


def _load_normalizer():
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


def run_pipeline(season, week, skip_normalize=False, league_name="XTreme Football"):
    print("")
    print("LeagueLab Weekly Pipeline")
    print("=========================")
    print("Season {} | Week {}".format(season, week))
    print("")

    if week < 1 or week > 18:
        raise ValueError("Week must be between 1 and 18.")

    print("[1/5] Normalize Yahoo data")
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
    print("[2/5] Weekly analytics")
    result = run_weekly_analytics(season, end_week=week)
    print("      OK")

    print("")
    print("[3/5] Challenge update")
    challenge_data = build_challenge_newsletter_data(season, week)
    if challenge_data:
        print("      {} ({})".format(
            challenge_data.get("name", "Challenge"),
            challenge_data.get("status", ""),
        ))
    else:
        print("      No biweekly challenge configured for Week {}".format(week))

    print("")
    print("[4/5] League admin")
    admin_data = build_league_admin_newsletter_data(
        season=season,
        week=week,
        analytics_result=result,
    )
    if admin_data:
        dues = admin_data.get("dues") or {}
        if dues:
            print("      Dues: {}/{} paid; ${:.2f} outstanding".format(
                dues.get("paid_count", 0),
                dues.get("team_count", 0),
                float(dues.get("balance_due", 0.0) or 0.0),
            ))
        if admin_data.get("notes"):
            print("      Commissioner notes: {}".format(len(admin_data.get("notes", []))))
    else:
        print("      No league-admin content configured")

    print("")
    print("[5/5] Newsletter HTML")
    newsletter_path = write_newsletter(
        season=season,
        week=week,
        analytics_result=result,
        league_name=league_name,
        challenge_data=challenge_data,
        admin_data=admin_data,
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
