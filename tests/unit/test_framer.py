"""Unit tests for `tcp_sim.engine.framer`."""

from __future__ import annotations

import pytest

from tcp_sim.engine.framer import FramedRecord, Framer, FramingMode


@pytest.mark.unit
def test_lf_splits_simple_records() -> None:
    framer = Framer(FramingMode.LF)
    out = framer.feed(b"alpha\nbeta\ngamma\n")
    assert out == [
        FramedRecord(b"alpha"),
        FramedRecord(b"beta"),
        FramedRecord(b"gamma"),
    ]
    assert framer.buffered_bytes == 0


@pytest.mark.unit
def test_lf_buffers_partial_tail() -> None:
    framer = Framer(FramingMode.LF)
    assert framer.feed(b"alpha\nbet") == [FramedRecord(b"alpha")]
    assert framer.buffered_bytes == 3
    assert framer.feed(b"a\n") == [FramedRecord(b"beta")]
    assert framer.buffered_bytes == 0


@pytest.mark.unit
def test_lf_handles_empty_feed() -> None:
    framer = Framer(FramingMode.LF)
    assert framer.feed(b"") == []


@pytest.mark.unit
def test_lf_handles_empty_records() -> None:
    framer = Framer(FramingMode.LF)
    assert framer.feed(b"\n\nfoo\n") == [
        FramedRecord(b""),
        FramedRecord(b""),
        FramedRecord(b"foo"),
    ]


@pytest.mark.unit
def test_crlf_splits_across_chunk_boundary() -> None:
    framer = Framer(FramingMode.CRLF)
    # \r and \n split across two feeds: must not emit until we see both.
    assert framer.feed(b"alpha\r") == []
    assert framer.feed(b"\nbeta\r\n") == [
        FramedRecord(b"alpha"),
        FramedRecord(b"beta"),
    ]


@pytest.mark.unit
def test_crlf_does_not_split_on_bare_lf() -> None:
    framer = Framer(FramingMode.CRLF)
    assert framer.feed(b"alpha\nbeta\r\n") == [FramedRecord(b"alpha\nbeta")]


@pytest.mark.unit
def test_raw_chunk_emits_each_feed_as_record() -> None:
    framer = Framer(FramingMode.RAW_CHUNK)
    assert framer.feed(b"hello") == [FramedRecord(b"hello")]
    assert framer.feed(b"world") == [FramedRecord(b"world")]


@pytest.mark.unit
def test_truncation_on_oversized_single_record() -> None:
    framer = Framer(FramingMode.LF, max_record_bytes=4)
    # 10 bytes, no separator: should emit one truncated record of 4 bytes,
    # then discard the rest until the next separator.
    out = framer.feed(b"abcdefghij\ntail\n")
    assert out == [FramedRecord(b"abcd", truncated=True), FramedRecord(b"tail")]


@pytest.mark.unit
def test_truncation_when_complete_record_exceeds_cap() -> None:
    framer = Framer(FramingMode.LF, max_record_bytes=3)
    out = framer.feed(b"xxxxx\n")
    assert out == [FramedRecord(b"xxx", truncated=True)]


@pytest.mark.unit
def test_truncation_in_raw_chunk_mode() -> None:
    framer = Framer(FramingMode.RAW_CHUNK, max_record_bytes=3)
    assert framer.feed(b"abcdef") == [FramedRecord(b"abc", truncated=True)]


@pytest.mark.unit
def test_flush_returns_trailing_unterminated_record() -> None:
    framer = Framer(FramingMode.LF)
    framer.feed(b"alpha\nbeta")
    rec = framer.flush()
    assert rec == FramedRecord(b"beta")
    assert framer.flush() is None


@pytest.mark.unit
def test_flush_none_in_raw_chunk_mode() -> None:
    framer = Framer(FramingMode.RAW_CHUNK)
    framer.feed(b"hello")
    assert framer.flush() is None


@pytest.mark.unit
def test_reset_clears_buffer_and_overflow() -> None:
    framer = Framer(FramingMode.LF, max_record_bytes=2)
    framer.feed(b"xxxxx")  # enters overflow
    framer.reset()
    assert framer.buffered_bytes == 0
    assert framer.feed(b"ok\n") == [FramedRecord(b"ok")]


@pytest.mark.unit
def test_invalid_max_record_bytes_raises() -> None:
    with pytest.raises(ValueError):
        Framer(FramingMode.LF, max_record_bytes=0)
