"""Offline tests only: every connection is an in-memory double."""

import gzip
import http.client
import io
import json
import socket
import ssl
from datetime import UTC, datetime
from typing import cast

import pytest

from nse_quant.data_platform.kite_instrument_http import (
    HOST,
    HttpPolicy,
    KiteHttpCredentials,
    fetch_instrument_response,
    request_path,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakeSocket:
    def __init__(self, wire=b""):
        self.wire = wire
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value

    def makefile(self, mode):
        return io.BytesIO(self.wire)


class Response:
    def __init__(self, chunks=(), *, status=200, headers=()):
        self.status = status
        self.headers = list(headers)
        self.chunks = list(chunks)
        self.closed = False
        self.requested = []

    def getheaders(self):
        return self.headers

    def read1(self, amount):
        self.requested.append(amount)
        if not self.chunks:
            return b""
        value = self.chunks.pop(0)
        if isinstance(value, BaseException):
            raise value
        if len(value) > amount:
            self.chunks.insert(0, value[amount:])
        return value[:amount]

    def close(self):
        self.closed = True


class Connection:
    def __init__(self, response, failure=None):
        self.response = response
        self.failure = failure
        self.sock = FakeSocket()
        self.closed = False
        self.calls = []

    def connect(self):
        if self.failure:
            raise self.failure

    def request(self, method, path, headers):
        self.calls.append((method, path, headers))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def capture(response=None, *, failure=None, **kwargs):
    response = response if response is not None else Response((b"csv",))
    connection = Connection(response, failure)
    seen = []

    def factory(host, **options):
        seen.append((host, options))
        return connection

    result = fetch_instrument_response(
        KiteHttpCredentials("API_KEY_SECRET", "TOKEN_SECRET"),
        connection_factory=factory,
        clock=lambda: NOW,
        **kwargs,
    )
    return result, connection, seen


def test_exact_gzip_body_and_verified_https():
    raw = gzip.compress(b"instrument_token,exchange_token\n258,1\n", mtime=0)
    response = Response(
        (raw[:3], raw[3:]),
        headers=(("Content-Encoding", "gzip"), ("Content-Length", str(len(raw)))),
    )
    result, connection, seen = capture(response, exchange="NSE")
    assert result.raw_body == raw and result.accepted_transport
    assert result.disposition_code == "UNVALIDATED_HTTP_CAPTURE"
    assert seen[0][0] == HOST
    assert seen[0][1]["context"].verify_mode == ssl.CERT_REQUIRED
    assert seen[0][1]["context"].check_hostname
    assert connection.calls[0][:2] == ("GET", "/instruments/NSE")
    assert connection.calls[0][2]["X-Kite-Version"] == "3"
    assert connection.calls[0][2]["Authorization"] == "token API_KEY_SECRET:TOKEN_SECRET"
    assert connection.sock.timeout == 10.0 and connection.closed and response.closed
    assert result.headers_received_at == NOW and result.first_chunk_returned_at == NOW
    encoded = json.dumps(result.metadata())
    assert "TOKEN_SECRET" not in encoded and "API_KEY_SECRET" not in encoded
    assert result.metadata()["csv_validated"] is False
    assert "instrument_token" not in repr(result)


@pytest.mark.parametrize("status", [301, 302, 304, 401, 403, 429, 500])
def test_http_status_no_redirect_or_retry(status):
    response = Response(
        (b"error body",), status=status, headers=(("Location", "https://other.invalid/secret"),)
    )
    result, connection, _ = capture(response)
    assert result.raw_body == b"error body" and result.body_complete
    assert not result.accepted_transport and result.disposition_code == "HTTP_STATUS_REJECTED"
    assert len(connection.calls) == 1
    assert "other.invalid" not in json.dumps(result.metadata())


@pytest.mark.parametrize(
    "headers,reason",
    [
        ((("Content-Length", "2"), ("Content-Length", "2")), "AMBIGUOUS_HTTP_FRAMING"),
        ((("Content-Length", "2"), ("Transfer-Encoding", "chunked")), "AMBIGUOUS_HTTP_FRAMING"),
        ((("Content-Length", "-1"),), "INVALID_CONTENT_LENGTH"),
        ((("Content-Length", "x"),), "INVALID_CONTENT_LENGTH"),
        ((("Transfer-Encoding", "gzip"),), "UNSUPPORTED_TRANSFER_ENCODING"),
        ((("Content-Length", "999"),), "ADVERTISED_BODY_LIMIT"),
        ((("ETag", "x" * 2049),), "HEADER_CAPTURE_LIMIT"),
    ],
)
def test_framing_before_body(headers, reason):
    response = Response((b"unread",), headers=headers)
    result, _, _ = capture(response, policy=HttpPolicy(max_body_bytes=10))
    assert result.reason_code == reason and not result.body_complete
    assert not response.requested and result.raw_body == b""


def test_body_limit_retains_sentinel():
    result, _, _ = capture(Response((b"abcdef",)), policy=HttpPolicy(max_body_bytes=3))
    assert result.raw_body == b"abcd" and result.reason_code == "BODY_BYTE_LIMIT"
    assert not result.body_complete and result.metadata()["payload_is_incomplete"] is True


def test_boundary_and_empty():
    result, _, _ = capture(Response((b"abc",)), policy=HttpPolicy(max_body_bytes=3))
    assert result.raw_body == b"abc" and result.body_complete
    empty, _, _ = capture(Response(()))
    assert empty.body_complete and not empty.accepted_transport
    assert empty.disposition_code == "EMPTY_RESPONSE"
    assert empty.metadata()["body_observed"] is False


def test_length_mismatch():
    result, _, _ = capture(Response((b"ab",), headers=(("Content-Length", "3"),)))
    assert result.raw_body == b"ab" and result.reason_code == "CONTENT_LENGTH_MISMATCH"


def test_timeout_retains_prefix():
    result, connection, _ = capture(Response((b"abc", TimeoutError("SECRET_TEXT"))))
    assert result.raw_body == b"abc" and result.reason_code == "HTTP_TIMEOUT"
    assert not result.body_complete and connection.closed and "SECRET_TEXT" not in repr(result)


def test_incomplete_read_partial():
    result, _, _ = capture(Response((b"ab", http.client.IncompleteRead(b"cd", 10))))
    assert result.raw_body == b"abcd" and result.reason_code == "TRUNCATED_HTTP_BODY"


@pytest.mark.parametrize(
    "error,reason",
    [
        (OSError("SECRET"), "NETWORK_ERROR"),
        (ssl.SSLError("SECRET"), "TLS_ERROR"),
        (http.client.BadStatusLine("SECRET"), "HTTP_PROTOCOL_ERROR"),
    ],
)
def test_sanitized_connection_failure(error, reason):
    result, connection, _ = capture(failure=error)
    assert result.reason_code == reason and not result.body_complete
    assert result.status_code is None and result.headers_received_at is None
    assert result.raw_body == b"" and connection.closed
    assert "SECRET" not in json.dumps(result.metadata())


def test_elapsed_boundary_check():
    ticks = iter((0.0, 61.0))
    response = Response((b"unread",))
    result, _, _ = capture(response, monotonic=lambda: next(ticks))
    assert result.reason_code == "ELAPSED_BUDGET_EXCEEDED" and not response.requested


def test_stdlib_chunked_parser_preserves_gzip():
    raw = gzip.compress(b"a,b\n1,2\n", mtime=0)
    wire = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        b"Content-Encoding: gzip\r\n\r\n"
        + f"{len(raw):x}".encode()
        + b"\r\n"
        + raw
        + b"\r\n0\r\n\r\n"
    )
    response = http.client.HTTPResponse(cast(socket.socket, FakeSocket(wire)))
    response.begin()
    result, _, _ = capture(response)
    assert result.raw_body == raw and result.accepted_transport


def test_stdlib_truncated_length():
    response = http.client.HTTPResponse(
        cast(socket.socket, FakeSocket(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nabc"))
    )
    response.begin()
    result, _, _ = capture(response)
    assert result.raw_body == b"abc" and not result.accepted_transport
    assert result.reason_code == "CONTENT_LENGTH_MISMATCH"


@pytest.mark.parametrize("exchange", ["../orders", "NSE?secret=x", "nse", "https://evil", ""])
def test_path_restriction(exchange):
    with pytest.raises(ValueError):
        request_path(exchange)


@pytest.mark.parametrize("value", ["", "bad\nsecret", "bad:secret", "a" * 1025])
def test_credential_validation(value):
    with pytest.raises(ValueError, match="INVALID_CREDENTIAL_FORMAT"):
        KiteHttpCredentials(value, "token")
    assert "token" not in repr(KiteHttpCredentials("key", "token"))


@pytest.mark.parametrize(
    "changes",
    [
        {"max_body_bytes": 0},
        {"max_body_bytes": 8_388_609},
        {"chunk_bytes": 0},
        {"read_timeout_seconds": 0},
        {"connect_timeout_seconds": float("nan")},
    ],
)
def test_policy_validation(changes):
    with pytest.raises(ValueError):
        HttpPolicy(**changes)


def test_plan_no_network_db_or_credentials(tmp_path, monkeypatch, capsys):
    from nse_quant.data_platform.kite_instrument_http_cli import main

    monkeypatch.delenv("KITE_API_KEY", raising=False)
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)

    def forbid(*args, **kwargs):
        raise AssertionError("NETWORK_FORBIDDEN")

    monkeypatch.setattr(http.client, "HTTPSConnection", forbid)
    target = tmp_path / "absent.duckdb"
    assert (
        main(
            [
                "--bronze-db",
                str(target),
                "--capture-session-id",
                "s",
                "--initialize",
                "--allow-network",
            ]
        )
        == 0
    )
    assert not target.exists() and '"status": "PLANNED"' in capsys.readouterr().out


def test_execution_network_gate(tmp_path):
    from nse_quant.data_platform.kite_instrument_http_cli import main

    target = tmp_path / "absent.duckdb"
    with pytest.raises(SystemExit):
        main(
            [
                "--bronze-db",
                str(target),
                "--capture-session-id",
                "s",
                "--execute",
                "--initialize",
                "--code-revision",
                "fixture",
            ]
        )
    assert not target.exists()


def test_partial_over_limit_count():
    result, _, _ = capture(
        Response((http.client.IncompleteRead(b"abcdef", 10),)), policy=HttpPolicy(max_body_bytes=3)
    )
    assert result.raw_body == b"abcd" and result.returned_bytes_not_retained == 2
    assert result.reason_code == "BODY_BYTE_LIMIT" and not result.body_complete


def test_json_escaped_header_budget():
    headers = (("ETag", "é" * 2048), ("Last-Modified", "é" * 2048))
    result, _, _ = capture(Response((b"unread",), headers=headers))
    assert result.reason_code == "HEADER_CAPTURE_LIMIT" and not result.body_complete


def test_missing_credentials_before_db_open(tmp_path, monkeypatch, capsys):
    from nse_quant.data_platform.kite_instrument_http_cli import main

    monkeypatch.delenv("KITE_API_KEY", raising=False)
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)
    target = tmp_path / "absent.duckdb"
    assert (
        main(
            [
                "--bronze-db",
                str(target),
                "--capture-session-id",
                "s",
                "--execute",
                "--allow-network",
                "--initialize",
                "--code-revision",
                "fixture",
            ]
        )
        == 1
    )
    assert not target.exists() and "CREDENTIALS_UNAVAILABLE" in capsys.readouterr().out
