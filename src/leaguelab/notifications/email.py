import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr


class EmailSendResult(object):
    def __init__(self, success, provider, recipient, detail=""):
        self.success = bool(success)
        self.provider = provider
        self.recipient = recipient
        self.detail = detail

    def as_dict(self):
        return {
            "channel": "email",
            "success": self.success,
            "provider": self.provider,
            "recipient": self.recipient,
            "detail": self.detail,
        }


class EmailSender(object):
    """Provider-neutral email sender interface."""

    provider_name = "base"

    def send(self, to_address, subject, message):
        raise NotImplementedError


class DisabledEmailSender(EmailSender):
    provider_name = "disabled"

    def send(self, to_address, subject, message):
        return EmailSendResult(
            False,
            self.provider_name,
            to_address,
            "Email delivery is disabled.",
        )


class SmtpEmailSender(EmailSender):
    provider_name = "smtp"

    def __init__(self, config):
        self.config = config or {}

    @staticmethod
    def _env_value(name):
        if not name:
            return ""
        return str(os.environ.get(str(name), "") or "").strip()

    def _get_credentials(self):
        username = self._env_value(
            self.config.get("username_env", "LEAGUELAB_SMTP_USERNAME")
        )
        password = self._env_value(
            self.config.get("password_env", "LEAGUELAB_SMTP_PASSWORD")
        )
        return username, password

    def send(self, to_address, subject, message):
        to_address = str(to_address or "").strip()
        if not to_address:
            return EmailSendResult(False, self.provider_name, "", "Missing recipient email address.")

        host = str(self.config.get("host", "") or "").strip()
        port = int(self.config.get("port", 587))
        security = str(self.config.get("security", "starttls") or "starttls").strip().lower()
        timeout_seconds = int(self.config.get("timeout_seconds", 20))
        from_address = str(self.config.get("from_address", "") or "").strip()
        from_name = str(self.config.get("from_name", "LeagueLab") or "LeagueLab").strip()
        username, password = self._get_credentials()

        if not host:
            return EmailSendResult(False, self.provider_name, to_address, "Missing SMTP host.")
        if not from_address:
            from_address = username
        if not from_address:
            return EmailSendResult(False, self.provider_name, to_address, "Missing from_address and SMTP username.")

        email = EmailMessage()
        email["Subject"] = subject
        email["From"] = formataddr((from_name, from_address)) if from_name else from_address
        email["To"] = to_address
        email.set_content(message)

        try:
            if security in ("ssl", "smtps"):
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, timeout=timeout_seconds, context=context) as server:
                    if username:
                        server.login(username, password)
                    server.send_message(email)
            else:
                with smtplib.SMTP(host, port, timeout=timeout_seconds) as server:
                    server.ehlo()
                    if security in ("starttls", "tls"):
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                        server.ehlo()
                    if username:
                        server.login(username, password)
                    server.send_message(email)
        except Exception as exc:
            return EmailSendResult(
                False,
                self.provider_name,
                to_address,
                "{}: {}".format(type(exc).__name__, exc),
            )

        return EmailSendResult(True, self.provider_name, to_address, "Sent.")


def build_email_sender(delivery_config):
    email_config = (delivery_config or {}).get("email", {}) or {}
    enabled = bool(email_config.get("enabled", False))
    provider = str(email_config.get("provider", "smtp") or "smtp").strip().lower()

    if not enabled:
        return DisabledEmailSender()

    if provider == "smtp":
        smtp_config = dict(email_config.get("smtp", {}) or {})
        # Allow common display/address settings at the email level.
        for key in ("from_name", "from_address"):
            if key in email_config and key not in smtp_config:
                smtp_config[key] = email_config[key]
        return SmtpEmailSender(smtp_config)

    raise ValueError("Unsupported email provider: {}".format(provider))
