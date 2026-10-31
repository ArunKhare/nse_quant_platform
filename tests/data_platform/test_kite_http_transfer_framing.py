"""Regression tests using real stdlib HTTP parsing, with no network connections."""

import gzip
import http.client
import inspect
import io
import socket
from datetime import UTC, datetime
from typing import cast

import pytest

from nse_quant.data_platform.kite_instrument_http import (
    CAPTURE_VERSION,
    DEFAULT_HTTP_POLICY,
    HOST,
    KiteHttpCredentials,
    fetch_instrument_response,
)

_UNSET = object()
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


class MemorySocket:
    def __init__(self, wire: bytes = b"") -> None:
        self.wire = wire
        self.timeout: float | None = None

    def makefile(self, mode: str) -> io.BytesIO:
        return io.BytesIO(self.wire)

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout


class ObservedResponse:
    def __init__(self, wire: bytes, override: object = _UNSET) -> None:
        self.response = http.client.HTTPResponse(cast(socket.socket, MemorySocket(wire)))
        self.response.begin()
        self.status = self.response.status
        self.chunked = self.response.chunked if override is _UNSET else override
        self.reads = 0
        self.closed = False

    def getheaders(self) -> list[tuple[str, str]]:
        return self.response.getheaders()

    def read1(self, amount: int) -> bytes:
        self.reads += 1
        return self.response.read1(amount)

    def close(self) -> None:
        self.closed = True
        self.response.close()


class MemoryConnection:
    def __init__(self, response: ObservedResponse) -> None:
        self.response = response
        self.sock = MemorySocket()
        self.requests: list[tuple[str, str]] = []
        self.closed = False

    def connect(self) -> None:
        pass

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        assert headers["X-Kite-Version"] == "3"
        self.requests.append((method, path))

    def getresponse(self) -> ObservedResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def run_capture(wire: bytes, override: object = _UNSET):
    response = ObservedResponse(wire, override)
    connection = MemoryConnection(response)
    hosts: list[str] = []

    def factory(host: str, **kwargs: object) -> MemoryConnection:
        hosts.append(host)
        return connection

    result = fetch_instrument_response(
        KiteHttpCredentials("fixture-key", "fixture-token"),
        connection_factory=factory,
        clock=lambda: _NOW,
    )
    assert hosts == [HOST]
    assert connection.requests == [("GET", "/instruments")]
    assert connection.closed and response.closed
    return result, response


def chunked_wire(encoding: bytes, body: bytes = b"abc") -> bytes:
    return (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: "
        + encoding
        + b"\r\n\r\n"
        + f"{len(body):x}".encode()
        + b"\r\n"
        + body
        + b"\r\n0\r\n\r\n"
    )


@pytest.mark.parametrize("encoding", [b"chunked", b"CHUNKED", b"cHuNkEd"])
def test_real_parser_chunked_gzip_bytes_preserved(encoding):
    body = gzip.compress(b"a,b\n1,2\n", mtime=0)
    result, response = run_capture(chunked_wire(encoding, body))
    assert response.chunked is True
    assert result.accepted_transport and result.body_complete
    assert result.raw_body == body
    assert result.metadata()["csv_validated"] is False


@pytest.mark.parametrize(
    "encoding",
    [
        pytest.param(b"chunked ", id="trailing-space"),
        pytest.param(b"chunked\t", id="trailing-tab"),
        pytest.param(b"gzip, chunked", id="stacked-gzip-chunked"),
        pytest.param(b"chunked, gzip", id="stacked-chunked-gzip"),
        pytest.param(b"identity", id="identity-transfer"),
        pytest.param(b"gzip", id="gzip-transfer"),
        pytest.param(b"chunked;foo=bar", id="chunked-parameter"),
    ],
)
def test_noncanonical_or_unsupported_transfer_rejected_before_read(encoding):
    result, response = run_capture(chunked_wire(encoding))
    assert result.reason_code == "UNSUPPORTED_TRANSFER_ENCODING"
    assert not result.accepted_transport and not result.body_complete
    assert result.raw_body == b"" and response.reads == 0
    assert result.metadata()["payload_is_incomplete"] is True


@pytest.mark.parametrize("override", [False, None])
def test_declared_chunked_requires_parser_confirmation(override):
    result, response = run_capture(chunked_wire(b"chunked"), override)
    assert result.reason_code == "TRANSFER_FRAMING_MISMATCH"
    assert not result.accepted_transport and result.raw_body == b""
    assert response.reads == 0


def test_parser_chunked_without_declared_encoding_rejected():
    result, response = run_capture(b"HTTP/1.1 200 OK\r\n\r\nabc", True)
    assert result.reason_code == "TRANSFER_FRAMING_MISMATCH"
    assert not result.accepted_transport and response.reads == 0


@pytest.mark.parametrize("header", [b"", b"Content-Length: 3\r\n"])
def test_nonchunked_responses_unchanged(header):
    result, response = run_capture(b"HTTP/1.1 200 OK\r\n" + header + b"\r\nabc")
    assert response.chunked is False
    assert result.accepted_transport and result.raw_body == b"abc"


def test_b008_singleton_default_preserved():
    assert (
        inspect.signature(fetch_instrument_response).parameters["policy"].default
        is DEFAULT_HTTP_POLICY
    )


def test_capture_policy_version_is_explicit():
    assert CAPTURE_VERSION == "kite-instrument-http@2"
    result, _ = run_capture(chunked_wire(b"chunked"))
    assert result.metadata()["capture_version"] == "kite-instrument-http@2"
    assert result.metadata()["provider_published_at"] is None
    assert result.metadata()["platform_published_at"] is None
