"""Telegram notifier.

Telegram credentials are secrets and must be supplied through `.env`:
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

import os

import requests
import structlog
from dotenv import load_dotenv

from nse_quant.core.settings import get_settings

load_dotenv()
logger = structlog.get_logger(__name__)
settings = get_settings()


class Notifier:
    """Send operational notifications through Telegram."""

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        session: requests.Session | None = None,
        timeout_seconds: float = 10.0,
        enabled: bool | None = None,
    ) -> None:
        self.secrets = settings.secrets
        self.token = token or self.secrets.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or self.secrets.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.notifier_settings = settings.notifier
        self.enabled = (
            self.notifier_settings.enabled and self.notifier_settings.telegram.enabled
            if enabled is None
            else enabled
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, message: str) -> bool:
        """Send a message. Returns True only when Telegram accepts it."""
        if not self.enabled:
            logger.info("telegram_notifier_disabled")
            return False

        if not self.is_configured:
            logger.debug(
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
                self.notifier_settings.telegram.uri.format(token=self.token),
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

    def _truncate(self, message: str) -> str:
        if len(message) <= self.notifier_settings.telegram.message_length_limit:
            return message

        return message[: self.notifier_settings.telegram.message_length_limit - 3] + "..."


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
