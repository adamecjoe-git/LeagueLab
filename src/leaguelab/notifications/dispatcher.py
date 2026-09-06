from leaguelab.notifications.email import build_email_sender
from leaguelab.notifications.sms import build_sms_sender


class NotificationDispatcher(object):
    """Dispatches provider-neutral routing instructions to configured providers."""

    def __init__(self, delivery_config=None):
        self.delivery_config = delivery_config or {}
        self.email_sender = build_email_sender(self.delivery_config)
        self.sms_sender = build_sms_sender(self.delivery_config)

    def provider_status(self):
        return {
            "email": self.email_sender.provider_name,
            "sms": self.sms_sender.provider_name,
        }

    def dispatch(self, delivery):
        results = []

        for channel in delivery.get("channels", []):
            if channel == "email":
                result = self.email_sender.send(
                    delivery.get("email_to", ""),
                    delivery.get("subject", ""),
                    delivery.get("message", ""),
                )
                results.append(result.as_dict())
            elif channel == "sms":
                result = self.sms_sender.send(
                    delivery.get("phone_to", ""),
                    delivery.get("sms_message", delivery.get("message", "")),
                )
                results.append(result.as_dict())
            else:
                results.append({
                    "channel": channel,
                    "success": False,
                    "provider": "unknown",
                    "recipient": "",
                    "detail": "Unsupported notification channel.",
                })

        return results
