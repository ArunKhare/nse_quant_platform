"""Independent bounded Kite binary decoder, version kite-binary@1."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import UTC, datetime

DECODER_VERSION = "kite-binary@1"


@dataclass(frozen=True)
class Packet:
    ordinal: int
    length_offset: int
    payload_offset: int
    size: int
    instrument_token: int
    provider_segment: int
    price_divisor: int
    mode: str
    raw_fields: tuple[tuple[str, int], ...]
    exchange_event_time: datetime | None
    last_trade_time: datetime | None
    depth: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class DecodedFrame:
    classification: str
    reason_code: str
    packets: tuple[Packet, ...] = ()
    failure_ordinal: int | None = None
    failure_offset: int | None = None


def _time(value: int) -> datetime | None:
    return datetime.fromtimestamp(value, UTC) if value else None


def decode(payload: bytes, payload_format: str) -> DecodedFrame:
    """Strict whole-frame policy; no clocks, I/O or partial salvage."""
    if not isinstance(payload, bytes):
        raise TypeError("Exact immutable bytes required")
    if len(payload) > 1_048_576:
        return DecodedFrame("quarantine", "FRAME_BYTE_LIMIT")
    if payload_format in {"kite_ws_text_bytes", "kite_ws_text_reencoded_utf8"}:
        return DecodedFrame("text_notification", "OPAQUE_TEXT_NOT_NORMALIZED")
    if payload_format != "kite_ws_binary_payload":
        return DecodedFrame("unsupported", "UNSUPPORTED_PAYLOAD_FORMAT")
    if len(payload) == 1:
        return DecodedFrame("heartbeat_control", "ONE_BYTE_HEARTBEAT")
    if len(payload) < 2:
        return DecodedFrame("quarantine", "TRUNCATED_FRAME_HEADER")
    count = struct.unpack_from(">H", payload)[0]
    if count > 4096:
        return DecodedFrame("quarantine", "PACKET_COUNT_LIMIT")
    if not count:
        return DecodedFrame("unsupported", "ZERO_PACKET_FRAME")
    spans = []
    offset = 2
    for ordinal in range(count):
        if offset + 2 > len(payload):
            return DecodedFrame("quarantine", "TRUNCATED_PACKET_HEADER", (), ordinal, offset)
        size = struct.unpack_from(">H", payload, offset)[0]
        if not size or offset + 2 + size > len(payload):
            return DecodedFrame("quarantine", "INVALID_PACKET_LENGTH", (), ordinal, offset)
        spans.append((offset, offset + 2, size))
        offset += 2 + size
    if offset != len(payload):
        return DecodedFrame("quarantine", "TRAILING_FRAME_BYTES", (), None, offset)
    packets = []
    for ordinal, (length_offset, start, size) in enumerate(spans):
        if size not in {8, 28, 32, 44, 184}:
            return DecodedFrame("unsupported", "UNSUPPORTED_PACKET_SIZE", (), ordinal, start)
        raw = payload[start : start + size]
        token = struct.unpack_from(">I", raw)[0]
        segment = token & 255
        if segment not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 12}:
            return DecodedFrame("unsupported", "UNKNOWN_PROVIDER_SEGMENT", (), ordinal, start)
        if (size in {28, 32} and segment != 9) or (size in {44, 184} and segment == 9):
            return DecodedFrame("quarantine", "LAYOUT_SEGMENT_MISMATCH", (), ordinal, start)
        divisor = 10_000_000 if segment == 3 else 10_000 if segment in {6, 12} else 100
        names = ["last_price_raw"]
        if size in {28, 32}:
            names += ["high_raw", "low_raw", "open_raw", "close_raw", "index_change_bits"]
        elif size in {44, 184}:
            names += [
                "last_quantity",
                "average_price_raw",
                "volume",
                "buy_quantity",
                "sell_quantity",
                "open_raw",
                "high_raw",
                "low_raw",
                "close_raw",
            ]
        fields = [(key, struct.unpack_from(">I", raw, 4 + i * 4)[0]) for i, key in enumerate(names)]
        exchange = trade = None
        depth: tuple[tuple[int, int, int], ...] = ()
        if size == 32:
            seconds = struct.unpack_from(">I", raw, 28)[0]
            fields.append(("exchange_epoch_seconds", seconds))
            exchange = _time(seconds)
        if size == 184:
            values = struct.unpack_from(">IIIII", raw, 44)
            fields.extend(
                zip(
                    (
                        "last_trade_epoch_seconds",
                        "oi",
                        "oi_high",
                        "oi_low",
                        "exchange_epoch_seconds",
                    ),
                    values,
                    strict=True,
                )
            )
            trade, exchange = _time(values[0]), _time(values[4])
            depth = tuple(struct.unpack_from(">IIH", raw, i) for i in range(64, 184, 12))
        mode = "ltp" if size == 8 else "quote" if size in {28, 44} else "full"
        packets.append(
            Packet(
                ordinal,
                length_offset,
                start,
                size,
                token,
                segment,
                divisor,
                mode,
                tuple(fields),
                exchange,
                trade,
                depth,
            )
        )
    return DecodedFrame("quote_ticks", "DECODED", tuple(packets))
