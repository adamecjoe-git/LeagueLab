"""Send LeagueLab weekly newsletter email through Gmail SMTP.

Modes:
    --preview    Show exactly who would receive the newsletter; sends nothing.
    --test-self  Send only to LEAGUELAB_EMAIL_ADDRESS.
    --send       Send to managers.json recipients configured for newsletter email.

Required environment variables:
    LEAGUELAB_EMAIL_ADDRESS
    LEAGUELAB_EMAIL_APP_PASSWORD

Python 3.8 compatible.
"""

import argparse
import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"
MANAGERS_PATH = PROJECT_ROOT / "data" / "config" / "managers.json"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _required_env(name):
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError("Required environment variable {} is not set.".format(name))
    return value


def _email_html_path(season, week):
    return (
        OUTPUT_ROOT
        / str(int(season))
        / "newsletter"
        / "week_{:02d}_email.html".format(int(week))
    )


def _load_managers():
    if not MANAGERS_PATH.exists():
        raise FileNotFoundError(
            "Manager configuration not found:\n  {}".format(MANAGERS_PATH)
        )

    with MANAGERS_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise RuntimeError("Unsupported managers.json structure.")

    configured = data.get("managers", {})
    if not isinstance(configured, dict):
        raise RuntimeError("'managers' must be an object keyed by Yahoo GUID.")

    managers = []
    for guid, value in configured.items():
        if not isinstance(value, dict):
            continue
        row = dict(value)
        row["_guid"] = guid
        managers.append(row)

    return managers


def _newsletter_email_enabled(row):
    notifications = row.get("notifications", {}) or {}
    if not isinstance(notifications, dict):
        return False

    pref = str(
        notifications.get("newsletter", "") or ""
    ).strip().lower()

    return pref in ("email", "both")


def _recipient_rows():
    recipients = []
    seen = set()

    for row in _load_managers():
        if not isinstance(row, dict) or not _newsletter_email_enabled(row):
            continue

        email = str(row.get("email", "") or "").strip()
        if not email:
            continue

        key = email.lower()
        if key in seen:
            continue
        seen.add(key)

        name = str(
            row.get("manager_name")
            or row.get("manager")
            or row.get("name")
            or row.get("display_name")
            or row.get("_guid")
            or email
        ).strip()

        team = str(
            row.get("team_name")
            or row.get("team")
            or row.get("fantasy_team")
            or ""
        ).strip()

        recipients.append(
            {
                "name": name,
                "team": team,
                "email": email,
            }
        )

    return recipients


def _build_message(sender, recipient, subject, html, week):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(
        "This message contains the LeagueLab Week {} newsletter. "
        "Please view the HTML version of this email.".format(int(week))
    )
    message.add_alternative(html, subtype="html")
    return message


def _smtp_login(sender, app_password):
    smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    try:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(sender, app_password)
        return smtp
    except Exception:
        smtp.quit()
        raise


def run(season, week, mode, league_name):
    sender = _required_env("LEAGUELAB_EMAIL_ADDRESS")
    html_path = _email_html_path(season, week)

    if not html_path.exists():
        raise FileNotFoundError(
            "Email newsletter HTML was not found:\n  {}\n"
            "Generate the weekly newsletter first.".format(html_path)
        )

    html = html_path.read_text(encoding="utf-8")
    subject = "{} - Week {} Newsletter".format(league_name, int(week))

    if mode == "test-self":
        recipients = [
            {
                "name": "SELF TEST",
                "team": "",
                "email": sender,
            }
        ]
        subject += " [TEST]"
    else:
        recipients = _recipient_rows()

    if not recipients:
        raise RuntimeError(
            "No newsletter-email recipients with email addresses were found in:\n  {}".format(
                MANAGERS_PATH
            )
        )

    print("")
    print("LeagueLab Weekly Email")
    print("======================")
    print("Mode:    {}".format(mode))
    print("From:    {}".format(sender))
    print("Subject: {}".format(subject))
    print("HTML:    {}".format(html_path))
    print("")
    print("Recipients ({}):".format(len(recipients)))

    for row in recipients:
        label = row["name"]
        if row["team"]:
            label += " / " + row["team"]
        print("  {} <{}>".format(label, row["email"]))

    if mode == "preview":
        print("")
        print("PREVIEW ONLY - no email was sent.")
        return 0

    app_password = _required_env(
        "LEAGUELAB_EMAIL_APP_PASSWORD"
    ).replace(" ", "")

    if len(app_password) != 16:
        raise RuntimeError(
            "LEAGUELAB_EMAIL_APP_PASSWORD should be the 16-character "
            "Google App Password (spaces removed)."
        )

    print("")
    print("Connecting to Gmail...")

    smtp = _smtp_login(sender, app_password)
    sent = 0

    try:
        for row in recipients:
            message = _build_message(
                sender=sender,
                recipient=row["email"],
                subject=subject,
                html=html,
                week=week,
            )
            smtp.send_message(message)
            sent += 1
            print("  SENT: {}".format(row["email"]))
    finally:
        smtp.quit()

    print("")
    print("{} EMAIL{} SENT".format(sent, "" if sent == 1 else "S"))
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Preview or send a LeagueLab weekly newsletter through Gmail."
    )

    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)

    parser.add_argument(
        "--league-name",
        default="XTreme Football",
        help="League name used in the email subject.",
    )

    modes = parser.add_mutually_exclusive_group(required=True)

    modes.add_argument(
        "--preview",
        action="store_true",
        help="Show newsletter recipients without sending.",
    )

    modes.add_argument(
        "--test-self",
        action="store_true",
        help="Send only to LEAGUELAB_EMAIL_ADDRESS.",
    )

    modes.add_argument(
        "--send",
        action="store_true",
        help="Send individually to managers configured for newsletter email.",
    )

    args = parser.parse_args()

    if args.preview:
        mode = "preview"
    elif args.test_self:
        mode = "test-self"
    else:
        mode = "send"

    try:
        return run(
            season=args.season,
            week=args.week,
            mode=mode,
            league_name=args.league_name,
        )
    except Exception as exc:
        print("")
        print("EMAIL SEND FAILED")
        print("=================")
        print(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
