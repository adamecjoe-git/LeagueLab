import argparse
import json
from pathlib import Path

from leaguelab.notifications.dispatcher import NotificationDispatcher


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(
        description="Safely send a LeagueLab provider test only to the configured test manager."
    )
    parser.add_argument(
        "--channel",
        choices=["email", "sms"],
        default="email",
    )
    args = parser.parse_args()

    config_path = PROJECT_ROOT / "data" / "config" / "notifications.json"
    managers_path = PROJECT_ROOT / "data" / "config" / "managers.json"
    config = _load_json(str(config_path))
    managers = _load_json(str(managers_path)).get("managers", {})

    test_manager = config.get("test_manager", {}) or {}
    guid = str(test_manager.get("guid", config.get("test_manager_guid", "")) or "").strip()
    label = str(test_manager.get("manager_name", "") or "").strip()
    if not guid or guid == "YOUR_YAHOO_MANAGER_GUID":
        raise RuntimeError("Set test_manager.guid in data/config/notifications.json first.")

    contact = managers.get(guid)
    if not contact:
        raise RuntimeError("test_manager.guid was not found in data/config/managers.json.")

    dispatcher = NotificationDispatcher(config.get("delivery", {}))
    status = dispatcher.provider_status()

    print("")
    print("LeagueLab Notification Test")
    print("===========================")
    print("Safety: configured test manager only ({})".format(label or contact.get("manager_name", guid)))
    print("Email provider: {}".format(status.get("email")))
    print("SMS provider: {}".format(status.get("sms")))

    if args.channel == "email":
        recipient = str(contact.get("notification_email", "") or "").strip()
        if not recipient:
            raise RuntimeError("The test manager has no notification_email address in managers.json.")
        delivery = {
            "channels": ["email"],
            "email_to": recipient,
            "phone_to": "",
            "subject": "LeagueLab Email Test",
            "message": (
                "LeagueLab email delivery is working.\n\n"
                "This message was sent by the test-only notification runner."
            ),
        }
    else:
        recipient = str(contact.get("phone", "") or "").strip()
        if not recipient:
            raise RuntimeError("The test manager has no phone number in managers.json.")
        delivery = {
            "channels": ["sms"],
            "email_to": "",
            "phone_to": recipient,
            "subject": "",
            "message": "LeagueLab SMS delivery test.",
        }

    results = dispatcher.dispatch(delivery)
    for result in results:
        print("{}: {} via {} -> {}".format(
            result.get("channel", "").upper(),
            "SENT" if result.get("success") else "FAILED",
            result.get("provider", "unknown"),
            result.get("recipient", "") or "-",
        ))
        print("Detail: {}".format(result.get("detail", "")))

    if not results or not all(r.get("success", False) for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
