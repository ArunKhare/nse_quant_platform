import struct

import pytest

from nse_quant.data_platform.kite_decoder import decode

FMT = "kite_ws_binary_payload"


def packet(size=8, segment=1):
    data = bytearray(size)
    struct.pack_into(">II", data, 0, (123 << 8) | segment, 123456)
    return bytes(data)


def frame(*packets):
    return struct.pack(">H", len(packets)) + b"".join(
        struct.pack(">H", len(p)) + p for p in packets
    )


@pytest.mark.parametrize("size,segment", [(8, 1), (28, 9), (32, 9), (44, 2), (184, 2)])
def test_layouts(size, segment):
    result = decode(frame(packet(size, segment)), FMT)
    assert result.classification == "quote_ticks"
    p = result.packets[0]
    assert (p.ordinal, p.length_offset, p.payload_offset, p.size) == (0, 2, 4, size)
    assert dict(p.raw_fields)["last_price_raw"] == 123456
    assert p.exchange_event_time is None and p.last_trade_time is None
    assert len(p.depth) == (10 if size == 184 else 0)


@pytest.mark.parametrize("segment,divisor", [(1, 100), (3, 10000000), (6, 10000), (12, 10000)])
def test_divisor(segment, divisor):
    assert decode(frame(packet(8, segment)), FMT).packets[0].price_divisor == divisor


@pytest.mark.parametrize(
    "raw,reason",
    [
        (b"", "TRUNCATED_FRAME_HEADER"),
        (b"\x00\x01", "TRUNCATED_PACKET_HEADER"),
        (b"\x00\x01\x00\x00", "INVALID_PACKET_LENGTH"),
        (frame(packet())[:-1], "INVALID_PACKET_LENGTH"),
        (frame(packet()) + b"x", "TRAILING_FRAME_BYTES"),
        (b"\xff\xff", "PACKET_COUNT_LIMIT"),
        pytest.param(
            b"x" * 1_048_577,
            "FRAME_BYTE_LIMIT",
            id="oversized-frame",
        ),
    ],
)
def test_malformed(raw, reason):
    result = decode(raw, FMT)
    assert result.reason_code == reason and not result.packets


def test_no_salvage():
    for raw in [
        frame(packet(), b"abcdefghi"),
        frame(packet(), packet(44, 9)),
        frame(packet(), packet(8, 255)),
        frame(packet(), packet())[:-1],
    ]:
        assert not decode(raw, FMT).packets


@pytest.mark.parametrize("fmt", ["kite_ws_text_bytes", "kite_ws_text_reencoded_utf8"])
def test_opaque(fmt):
    result = decode(b'{"secret":"NEVER_LOG"}', fmt)
    assert result.classification == "text_notification"
    assert "NEVER_LOG" not in repr(result)


def test_times_depth():
    data = bytearray(packet(184, 2))
    struct.pack_into(">IIIII", data, 44, 1700000000, 2**32 - 1, 12, 3, 1700000001)
    struct.pack_into(">IIH", data, 64, 2**32 - 1, 123, 65535)
    p = decode(frame(bytes(data)), FMT).packets[0]
    assert p.last_trade_time.timestamp() == 1700000000
    assert p.exchange_event_time.timestamp() == 1700000001
    assert p.depth[0] == (2**32 - 1, 123, 65535)


def test_offsets():
    result = decode(frame(packet(), packet(44, 2)), FMT)
    assert [p.payload_offset for p in result.packets] == [4, 14]


def test_control():
    assert decode(b"x", FMT).classification == "heartbeat_control"
    assert decode(b"\x00\x00", FMT).reason_code == "ZERO_PACKET_FRAME"
    assert decode(b"x", "unknown").classification == "unsupported"


def test_index_bits():
    data = bytearray(packet(28, 9))
    struct.pack_into(">I", data, 24, 0xFFFFFFFF)
    assert (
        dict(decode(frame(bytes(data)), FMT).packets[0].raw_fields)["index_change_bits"]
        == 0xFFFFFFFF
    )


def test_deterministic():
    result = decode(frame(packet()), FMT)
    assert result == decode(frame(packet()), FMT)
    with pytest.raises(AttributeError):
        result.reason_code = "changed"
