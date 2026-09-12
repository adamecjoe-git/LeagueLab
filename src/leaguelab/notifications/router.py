class NotificationRouter(object):
    VALID_MODES = {"preview", "test", "live"}
    VALID_PREFERENCES = {"off", "email", "sms", "both"}

    def __init__(self, mode="preview", test_contact=None, test_channels=None):
        mode = str(mode or "preview").strip().lower()
        if mode not in self.VALID_MODES:
            raise ValueError("Unsupported notification mode: {}".format(mode))
        self.mode = mode
        self.test_contact = test_contact or {}
        self.test_channels = [str(x).strip().lower() for x in (test_channels or ["email", "sms"])]

    def build_delivery(self, manager_contact, subject, message):
        manager_contact = manager_contact or {}
        preference = str(
            manager_contact.get("notifications", {}).get("roster_alerts", "off")
        ).strip().lower()
        if preference not in self.VALID_PREFERENCES:
            preference = "off"

        base = {
            "mode": self.mode,
            "send": False,
            "channels": [],
            "email_to": "",
            "phone_to": "",
            "subject": subject,
            "message": message,
            "manager_preference": preference,
        }

        if self.mode == "preview":
            return base

        if self.mode == "test":
            # Critical safety rule: test mode NEVER routes to the triggering manager.
            # It always routes only to the configured test contact.
            test_email = str(self.test_contact.get("notification_email", "") or "").strip()
            test_phone = str(self.test_contact.get("phone", "") or "").strip()
            if test_email and "email" in self.test_channels:
                base["channels"].append("email")
                base["email_to"] = test_email
            if test_phone and "sms" in self.test_channels:
                base["channels"].append("sms")
                base["phone_to"] = test_phone
            base["send"] = bool(base["channels"])
            return base

        if preference == "off":
            return base

        if preference in ("email", "both"):
            email_to = str(manager_contact.get("notification_email", "") or "").strip()
            if email_to:
                base["channels"].append("email")
                base["email_to"] = email_to

        if preference in ("sms", "both"):
            phone_to = str(manager_contact.get("phone", "") or "").strip()
            if phone_to:
                base["channels"].append("sms")
                base["phone_to"] = phone_to

        base["send"] = bool(base["channels"])
        return base
