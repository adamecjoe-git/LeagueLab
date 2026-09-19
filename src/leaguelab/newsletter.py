"""LeagueLab newsletter output orchestration. Python 3.8 compatible.

LeagueLab has one newsletter renderer: the Outlook/Gmail-safe HTML renderer in
weekly_email.py. The same generated HTML file is used for browser review and
email delivery.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"


def write_newsletter(
    season,
    week,
    analytics_result,
    league_name="XTreme Football",
    challenge_data=None,
    admin_data=None,
    upcoming_data=None,
    postseason_data=None,
    newsletter_type=None,
    regular_season_end=14,
    season_end=17,
):
    """Render the single LeagueLab newsletter HTML file and return its path."""
    from leaguelab.weekly_email import build_weekly_email_html

    out = OUTPUT_ROOT / str(season) / "newsletter"
    out.mkdir(parents=True, exist_ok=True)

    newsletter_path = out / "week_{:02d}.html".format(int(week))
    html = build_weekly_email_html(
        season,
        week,
        analytics_result,
        league_name,
        challenge_data,
        admin_data,
        upcoming_data,
        postseason_data,
        newsletter_type,
        regular_season_end,
        season_end,
    )

    # utf-8-sig matches the proven email output and avoids mojibake when the
    # file passes through Windows/Outlook tooling.
    with newsletter_path.open("w", encoding="utf-8-sig") as handle:
        handle.write(html)

    return newsletter_path
