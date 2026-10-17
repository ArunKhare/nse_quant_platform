
"""Telegram notifier.

Telegram credentials are secrets and must be supplied through `.env`:
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

import os

import requests
import structlog

logger = structlog.get_logger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LENGTH = 4096


class Notifier:
    """Send operational notifications through Telegram."""

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        session: requests.Session | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, message: str) -> bool:
        """Send a message. Returns True only when Telegram accepts it."""
        if not self.is_configured:
            logger.warning(
                "telegram_notifier_not_configured",
                reason="missing_token_or_chat_id",
            )
            return False

        if not message.strip():
            logger.warning("telegram_notifier_empty_message")
            return False

        payload = {
            "chat_id": self.chat_id,
            "text": self._truncate(message),
        }

        try:
            response = self.session.post(
                TELEGRAM_API_URL.format(token=self.token),
                json=payload,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            logger.warning(
                "telegram_notifier_request_failed",
                error=str(exc),
            )
            return False

        if not response.ok:
            logger.warning(
                "telegram_notifier_rejected",
                status_code=response.status_code,
            )
            return False

        logger.info("telegram_notifier_sent")
        return True

    @staticmethod
    def _truncate(message: str) -> str:
        if len(message) <= MAX_MESSAGE_LENGTH:
            return message

        return message[: MAX_MESSAGE_LENGTH - 3] + "..."


class NullNotifier:
    """No-op notifier for tests and dry-run environments."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    @property
    def is_configured(self) -> bool:
        return True

    def send(self, message: str) -> bool:
        self.sent.append(message)
        return True