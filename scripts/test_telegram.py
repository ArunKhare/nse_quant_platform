"""telegram working test
uv run scripts\test_telegram.py --force --message "Forced Telegram connectivity test"
uv run scripts\test_telegram.py --message "NSE Quant platform Telegram check"
uv run scripts\test_telegram.py
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from nse_quant.ops.notifier import Notifier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a test message to the configured Telegram chat.",
    )

    parser.add_argument(
        "--message",
        default="NSE Quant Telegram test message",
        help="Optional message text to send.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Send even if Telegram notifications are disabled in settings. "
            "Credentials must still be configured."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    notifier = Notifier(enabled=True if args.force else None)

    if not notifier.is_configured:
        print("Telegram is not configured.")
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.")
        return 2

    message = f"{args.message}\nSent at: {datetime.now(UTC).isoformat()}"

    sent = notifier.send(message)

    if sent:
        print("Telegram test message sent successfully.")
        return 0

    print("Telegram test message failed.")
    print("Check notifier settings, bot token, chat ID, and network access.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
