import json
from pathlib import Path

from leaguelab.notifications.dispatcher import NotificationDispatcher
from leaguelab.notifications.router import NotificationRouter


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_json(path):
    with open(str(path), "r", encoding="utf-8") as handle:
        return json.load(handle)


def _build_recipients(managers):
    recipients = []
    for guid, manager in sorted(
        managers.items(),
        key=lambda item: (
            str(item[1].get("team_name", "") or "").lower(),
            str(item[1].get("manager_name", "") or "").lower(),
        ),
    ):
        notifications = manager.get("notifications", {}) or {}
        preference = str(
            notifications.get("roster_alerts", "off") or "off"
        ).strip().lower()
        if preference == "off":
            continue

        router = NotificationRouter(mode="live")
        delivery = router.build_delivery(
            manager_contact=manager,
            subject="",
            message="",
        )

        recipients.append({
            "guid": guid,
            "manager": manager,
            "delivery": delivery,
            "preference": preference,
        })
    return recipients


def _print_recipient_preview(recipients):
    print("")
    print("Eligible managers")
    print("-----------------")

    if not recipients:
        print("None.")
        return

    for item in recipients:
        manager = item["manager"]
        delivery = item["delivery"]
        channels = ", ".join(
            channel.upper() for channel in delivery.get("channels", [])
        ) or "NO VALID DESTINATION"

        print(
            "{} / {} -> {} [{}]".format(
                manager.get("manager_name") or item["guid"],
                manager.get("team_name") or "",
                channels,
                item["preference"],
            )
        )


def main():
    managers_path = PROJECT_ROOT / "data" / "config" / "managers.json"
    notifications_path = PROJECT_ROOT / "data" / "config" / "notifications.json"

    managers = _load_json(managers_path).get("managers", {}) or {}
    config = _load_json(notifications_path)

    print("")
    print("LeagueLab Manual Notification")
    print("=============================")

    recipients = _build_recipients(managers)
    _print_recipient_preview(recipients)

    valid_recipients = [
        item for item in recipients if item["delivery"].get("send", False)
    ]
    invalid_recipients = [
        item for item in recipients if not item["delivery"].get("send", False)
    ]

    if invalid_recipients:
        print("")
        print("WARNING: {} opted-in manager(s) have no valid destination.".format(
            len(invalid_recipients)
        ))

    if not valid_recipients:
        print("")
        print("No opted-in managers have a valid notification destination.")
        return

    print("")
    subject = input("Subject [LeagueLab League Alert]: ").strip()
    if not subject:
        subject = "LeagueLab League Alert"

    print("")
    print("Enter message. Press Enter on a blank line when finished.")
    print("")

    lines = []
    while True:
        line = input("> ")
        if not line:
            break
        lines.append(line)

    message = "\n".join(lines).strip()
    if not message:
        print("")
        print("No message entered. Nothing sent.")
        return

    for item in valid_recipients:
        item["delivery"]["subject"] = subject
        item["delivery"]["message"] = message
        item["delivery"]["sms_message"] = message

    print("")
    print("Message preview")
    print("---------------")
    print("Subject: {}".format(subject))
    print("")
    print(message)
    print("")
    print("Managers: {}".format(len(valid_recipients)))
    print("Delivery attempts: {}".format(sum(
        len(item["delivery"].get("channels", []))
        for item in valid_recipients
    )))

    confirmation = input(
        "Send this notification now? Type SEND to confirm: "
    ).strip()

    if confirmation != "SEND":
        print("Cancelled. Nothing sent.")
        return

    dispatcher = NotificationDispatcher(config.get("delivery", {}))

    print("")
    print("Sending")
    print("-------")

    sent = 0
    failed = 0

    for item in valid_recipients:
        manager = item["manager"]
        delivery = item["delivery"]
        label = "{} / {}".format(
            manager.get("manager_name") or item["guid"],
            manager.get("team_name") or "",
        )

        try:
            results = dispatcher.dispatch(delivery)
        except Exception as exc:
            failed += len(delivery.get("channels", [])) or 1
            print("FAILED: {} -> {}".format(label, exc))
            continue

        if not results:
            failed += len(delivery.get("channels", [])) or 1
            print("FAILED: {} -> dispatcher returned no results".format(label))
            continue

        for result in results:
            status = "SENT" if result.get("success") else "FAILED"
            if result.get("success"):
                sent += 1
            else:
                failed += 1

            print(
                "{}: {} / {} -> {} ({})".format(
                    status,
                    label,
                    result.get("channel", "").upper(),
                    result.get("recipient", "") or "-",
                    result.get("detail", ""),
                )
            )

    print("")
    print("Complete.")
    print("Successful deliveries: {}".format(sent))
    print("Failed deliveries: {}".format(failed))


if __name__ == "__main__":
    main()
