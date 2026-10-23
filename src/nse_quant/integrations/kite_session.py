"""Persistent Kite session helper.

Stores only the Kite access token locally under `.local/`. The access token is
sensitive and must never be committed to Git.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.core.settings import get_settings
from nse_quant.integrations.kite_auth import get_authenticated_kite

SESSION_FILE = Path(".local/kite_session.json")


def _load_cached_token() -> str | None:
    if not SESSION_FILE.exists():
        return None

    try:
        payload = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        token = payload.get("access_token")
        saved_at = datetime.fromisoformat(payload["saved_at"])

        # Kite access tokens are generally valid for the trading day.
        if saved_at.date() != datetime.now(UTC).date():
            return None

        return token if token else None

    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def _save_token(access_token: str) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

    SESSION_FILE.write_text(
        json.dumps(
            {
                "access_token": access_token,
                "saved_at": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )


def get_cached_kite(settings: Any | None = None) -> Any:
    """Return a Kite client, reusing today's access token when available."""
    from kiteconnect import KiteConnect

    settings = settings or get_settings()
    api_key = settings.secrets.kite_api_key

    if not api_key:
        raise ValueError("KITE_API_KEY is missing from .env")

    cached_token = _load_cached_token()

    if cached_token:
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(cached_token)

        try:
            # Validate the cached session before using it.
            kite.profile()
            print("Reusing existing Kite session.")
            return kite
        except Exception:  # noqa:BLE001
            print("Cached Kite session is invalid; requesting new login.")

    kite = get_authenticated_kite(settings=settings)

    if getattr(kite, "access_token", None):
        _save_token(kite.access_token)
        print("Saved new Kite session for reuse today.")

    return kite
