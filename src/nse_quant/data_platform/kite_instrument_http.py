"""Single-attempt Kite HTTP acquisition, with content coding preserved."""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

CAPTURE_VERSION = "kite-instrument-http@2"
HOST = "api.kite.trade"
ALLOWED_HEADERS = frozenset(
    {
        "content-type",
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "date",
        "last-modified",
        "etag",
        "cache-control",
        "expires",
        "vary",
    }
)


@dataclass(frozen=True)
class HttpPolicy:
    max_body_bytes: int = 8_388_608
    chunk_bytes: int = 65_536
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    elapsed_budget_seconds: float = 60.0

    def __post_init__(self) -> None:
        if type(self.max_body_bytes) is not int or not 1 <= self.max_body_bytes <= 8_388_608:
            raise ValueError("INVALID_BODY_LIMIT")
        if type(self.chunk_bytes) is not int or not 1 <= self.chunk_bytes <= 65_536:
            raise ValueError("INVALID_CHUNK_LIMIT")
        for value in (
            self.connect_timeout_seconds,
            self.read_timeout_seconds,
            self.elapsed_budget_seconds,
        ):
            if not 0 < value <= 120:
                raise ValueError("INVALID_TIMEOUT")


DEFAULT_HTTP_POLICY = HttpPolicy()


@dataclass(frozen=True)
class KiteHttpCredentials:
    api_key: str = field(repr=False)
    access_token: str = field(repr=False)

    def __post_init__(self) -> None:
        for value in (self.api_key, self.access_token):
            if not isinstance(value, str) or not 1 <= len(value) <= 1024:
                raise ValueError("INVALID_CREDENTIAL_FORMAT")
            if any(not 33 <= ord(char) <= 126 or char == ":" for char in value):
                raise ValueError("INVALID_CREDENTIAL_FORMAT")


def request_path(exchange: str | None = None) -> str:
    if exchange is None:
        return "/instruments"
    if not isinstance(exchange, str) or not re.fullmatch(r"[A-Z]{2,8}", exchange):
        raise ValueError("INVALID_EXCHANGE_PATH")
    return "/instruments/" + exchange


@dataclass(frozen=True)
class HttpCapture:
    path: str
    request_started_at: datetime
    headers_received_at: datetime | None
    first_chunk_returned_at: datetime | None
    capture_finished_at: datetime
    status_code: int | None
    selected_headers: tuple[tuple[str, str], ...]
    headers_complete: bool
    body_complete: bool
    reason_code: str
    raw_body: bytes = field(repr=False)
    returned_bytes_not_retained: int = 0

    def __post_init__(self) -> None:
        if (
            type(self.returned_bytes_not_retained) is not int
            or self.returned_bytes_not_retained < 0
        ):
            raise ValueError("INVALID_UNRETAINED_BYTE_COUNT")
        if not isinstance(self.raw_body, bytes):
            raise TypeError("EXACT_BODY_BYTES_REQUIRED")
        for value in (
            self.request_started_at,
            self.headers_received_at,
            self.first_chunk_returned_at,
            self.capture_finished_at,
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("AWARE_CAPTURE_CLOCK_REQUIRED")

    @property
    def disposition_code(self) -> str:
        if self.reason_code != "COMPLETE":
            return self.reason_code
        if self.status_code != 200:
            return "HTTP_STATUS_REJECTED"
        if not self.raw_body:
            return "EMPTY_RESPONSE"
        return "UNVALIDATED_HTTP_CAPTURE"

    @property
    def accepted_transport(self) -> bool:
        return (
            self.body_complete
            and self.headers_complete
            and self.status_code == 200
            and bool(self.raw_body)
            and not self.returned_bytes_not_retained
            and self.reason_code == "COMPLETE"
        )

    def metadata(self) -> dict[str, object]:
        return {
            "capture_version": CAPTURE_VERSION,
            "host": HOST,
            "method": "GET",
            "path": self.path,
            "request_started_at": self.request_started_at.isoformat(),
            "headers_received_at": (
                self.headers_received_at.isoformat() if self.headers_received_at else None
            ),
            "first_chunk_returned_at": (
                self.first_chunk_returned_at.isoformat() if self.first_chunk_returned_at else None
            ),
            "capture_finished_at": self.capture_finished_at.isoformat(),
            "status_code": self.status_code,
            "selected_headers": self.selected_headers,
            "headers_complete": self.headers_complete,
            "body_complete": self.body_complete,
            "header_scope": "SELECTED_ALLOWLIST_ONLY_NOT_RAW_HEADERS",
            "body_observed": bool(self.raw_body),
            "reason_code": self.reason_code,
            "body_bytes": len(self.raw_body),
            "returned_bytes_not_retained": self.returned_bytes_not_retained,
            "captured_body_hash": hashlib.sha256(self.raw_body).hexdigest(),
            "body_representation": "HTTP_ENTITY_BODY_CONTENT_CODING_PRESERVED",
            "payload_is_incomplete": not self.body_complete,
            "provider_published_at": None,
            "platform_published_at": None,
            "csv_validated": False,
            "disposition_code": self.disposition_code,
            "transport_accepted": self.accepted_transport,
        }


def _selected_headers(pairs: list[tuple[str, str]]) -> tuple[tuple[tuple[str, str], ...], bool]:
    selected: list[tuple[str, str]] = []
    size = 0
    for key, value in pairs:
        key = key.lower()
        if key not in ALLOWED_HEADERS:
            continue
        size += len(json.dumps((key, value), ensure_ascii=True))
        if len(selected) >= 32 or len(value) > 2048 or size > 16384:
            return tuple(selected), False
        selected.append((key, value))
    return tuple(selected), True


def fetch_instrument_response(
    credentials: KiteHttpCredentials,
    *,
    exchange: str | None = None,
    policy: HttpPolicy = DEFAULT_HTTP_POLICY,
    connection_factory: Callable[..., Any] | None = None,
    clock: Callable[[], datetime] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> HttpCapture:
    """One GET; elapsed budget is checked between blocking socket reads.

    This captures entity-body bytes, not HTTP/TLS wire framing. In-progress
    response memory is not crash durable before the later Bronze transaction.
    """
    path = request_path(exchange)
    now = clock or (lambda: datetime.now(UTC))
    started = now()
    if started.tzinfo is None or started.utcoffset() is None:
        raise ValueError("AWARE_CAPTURE_CLOCK_REQUIRED")
    start_mono = monotonic()
    connection = None
    response = None
    received = first = None
    status = None
    headers: tuple[tuple[str, str], ...] = ()
    header_complete = False
    body_complete = False
    body = bytearray()
    reason = "TRANSPORT_ERROR"
    not_retained = 0
    try:
        factory = connection_factory or http.client.HTTPSConnection
        connection = factory(
            HOST, timeout=policy.connect_timeout_seconds, context=ssl.create_default_context()
        )
        connection.connect()
        if connection.sock is None:
            raise OSError("NO_CONNECTED_SOCKET")
        connection.sock.settimeout(policy.read_timeout_seconds)
        connection.request(
            "GET",
            path,
            headers={
                "X-Kite-Version": "3",
                "Authorization": "token " + credentials.api_key + ":" + credentials.access_token,
                "Accept-Encoding": "gzip, identity",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        received = now()
        status = int(response.status)
        headers, header_complete = _selected_headers(response.getheaders())
        lengths = [v for k, v in headers if k == "content-length"]
        transfers = [v for k, v in headers if k == "transfer-encoding"]
        length = None
        framing_error = None
        if not header_complete:
            framing_error = "HEADER_CAPTURE_LIMIT"
        elif len(lengths) > 1 or len(transfers) > 1 or (lengths and transfers):
            framing_error = "AMBIGUOUS_HTTP_FRAMING"
        elif transfers and transfers[0].lower() != "chunked":
            framing_error = "UNSUPPORTED_TRANSFER_ENCODING"
        elif bool(transfers) != (getattr(response, "chunked", False) is True):
            framing_error = "TRANSFER_FRAMING_MISMATCH"
        elif lengths:
            if not re.fullmatch(r"[0-9]{1,20}", lengths[0].strip()):
                framing_error = "INVALID_CONTENT_LENGTH"
            else:
                length = int(lengths[0])
                if length > policy.max_body_bytes:
                    framing_error = "ADVERTISED_BODY_LIMIT"
        if framing_error is not None:
            reason = framing_error
        else:
            while True:
                if monotonic() - start_mono > policy.elapsed_budget_seconds:
                    reason = "ELAPSED_BUDGET_EXCEEDED"
                    break
                amount = min(policy.chunk_bytes, policy.max_body_bytes + 1 - len(body))
                chunk = response.read1(amount)
                if not isinstance(chunk, bytes) or len(chunk) > amount:
                    reason = "TRANSPORT_CONTRACT_VIOLATION"
                    break
                if chunk:
                    if first is None:
                        first = now()
                    body.extend(chunk)
                    if len(body) > policy.max_body_bytes:
                        reason = "BODY_BYTE_LIMIT"
                        break
                else:
                    if length is not None and len(body) != length:
                        reason = "CONTENT_LENGTH_MISMATCH"
                    else:
                        body_complete = True
                        reason = "COMPLETE"
                    break
    except http.client.IncompleteRead as error:
        partial = error.partial
        reason = "TRUNCATED_HTTP_BODY"
        if isinstance(partial, bytes):
            remaining = policy.max_body_bytes + 1 - len(body)
            if partial and first is None:
                first = now()
            body.extend(partial[:remaining])
            not_retained = max(0, len(partial) - remaining)
            if not_retained:
                reason = "BODY_BYTE_LIMIT"
    except TimeoutError:
        reason = "HTTP_TIMEOUT"
    except ssl.SSLError:
        reason = "TLS_ERROR"
    except http.client.HTTPException:
        reason = "HTTP_PROTOCOL_ERROR"
    except OSError:
        reason = "NETWORK_ERROR"
    except Exception:
        reason = "TRANSPORT_ERROR"
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                body_complete = False
                reason = "RESPONSE_CLOSE_ERROR"
        if connection is not None:
            try:
                connection.close()
            except Exception:
                body_complete = False
                reason = "CONNECTION_CLOSE_ERROR"
    return HttpCapture(
        path,
        started,
        received,
        first,
        now(),
        status,
        headers,
        header_complete,
        body_complete,
        reason,
        bytes(body),
        not_retained,
    )
