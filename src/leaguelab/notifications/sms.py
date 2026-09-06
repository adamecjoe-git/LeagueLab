import json
import os
import urllib.parse
import urllib.request


class SmsSendResult(object):
    def __init__(self, success, provider, recipient, detail=""):
        self.success = bool(success)
        self.provider = provider
        self.recipient = recipient
        self.detail = detail

    def as_dict(self):
        return {
            "channel": "sms",
            "success": self.success,
            "provider": self.provider,
            "recipient": self.recipient,
            "detail": self.detail,
        }


class SmsSender(object):
    provider_name = "base"

    def send(self, phone_number, message):
        raise NotImplementedError


class DisabledSmsSender(SmsSender):
    provider_name = "disabled"

    def send(self, phone_number, message):
        return SmsSendResult(False, self.provider_name, phone_number,
                             "SMS delivery is disabled.")


class TextbeltSmsSender(SmsSender):
    provider_name = "textbelt"

    def __init__(self, config):
        self.config = config or {}
        self.endpoint = self.config.get("endpoint", "https://textbelt.com/text")
        self.timeout = int(self.config.get("timeout_seconds", 20))
        self.api_key_env = self.config.get("api_key_env", "LEAGUELAB_TEXTBELT_API_KEY")

    def send(self, phone_number, message):
        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            return SmsSendResult(False, self.provider_name, phone_number,
                                 "Environment variable {} is not configured.".format(self.api_key_env))
        data = urllib.parse.urlencode({
            "phone": phone_number,
            "message": message,
            "key": api_key,
        }).encode("utf-8")
        request = urllib.request.Request(self.endpoint, data=data, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return SmsSendResult(False, self.provider_name, phone_number,
                                 "Textbelt request failed: {}".format(exc))
        if payload.get("success"):
            detail = "Accepted by Textbelt"
            if payload.get("textId") is not None:
                detail += "; textId={}".format(payload.get("textId"))
            if payload.get("quotaRemaining") is not None:
                detail += "; quota remaining={}".format(payload.get("quotaRemaining"))
            return SmsSendResult(True, self.provider_name, phone_number, detail)
        return SmsSendResult(False, self.provider_name, phone_number,
                             payload.get("error") or "Textbelt rejected the message.")


def build_sms_sender(delivery_config):
    sms_config = (delivery_config or {}).get("sms", {}) or {}
    enabled = bool(sms_config.get("enabled", False))
    provider = str(sms_config.get("provider", "") or "").strip().lower()
    if not enabled or not provider:
        return DisabledSmsSender()
    if provider == "textbelt":
        return TextbeltSmsSender(sms_config.get("textbelt", {}) or {})
    raise ValueError("Unsupported SMS provider: {}".format(provider))
