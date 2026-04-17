"""Record framer for TCP receiver streams.

Pure-function core (no asyncio, no sockets) so it is trivially unit-testable.
Feed raw bytes in, get fully-framed records out.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class FramingMode(str, Enum):
    """How incoming byte streams are split into records."""

    LF = "lf"
    CRLF = "crlf"
    RAW_CHUNK = "raw_chunk"


_SEPARATORS: dict[FramingMode, bytes] = {
    FramingMode.LF: b"\n",
    FramingMode.CRLF: b"\r\n",
}


@dataclass(frozen=True)
class FramedRecord:
    """A single record produced by the framer.

    `truncated` is True when the record was cut off at `max_record_bytes`
    because the underlying record was larger than the configured cap.
    """

    payload: bytes
    truncated: bool = False


class Framer:
    """Split a byte stream into records.

    In `LF` or `CRLF` mode the separator is stripped from the emitted payload.
    In `RAW_CHUNK` mode each `feed()` call emits exactly one record containing
    the chunk verbatim (useful for length-oblivious binary streams).

    Oversized records (longer than `max_record_bytes`) are truncated; the
    emitted payload is clamped to `max_record_bytes` and its `truncated`
    flag is set. Any trailing data up to the next separator is discarded.
    """

    def __init__(
        self,
        mode: FramingMode = FramingMode.LF,
        max_record_bytes: int = 1 << 20,  # 1 MiB
    ) -> None:
        if max_record_bytes <= 0:
            raise ValueError("max_record_bytes must be > 0")
        self._mode = mode
        self._max = max_record_bytes
        self._buf = bytearray()
        # When the buffer has exceeded the cap we stay in "overflow" until the
        # next separator so we emit exactly one truncated record per oversized
        # logical record rather than many spurious fragments.
        self._overflow = False

    @property
    def mode(self) -> FramingMode:
        return self._mode

    @property
    def buffered_bytes(self) -> int:
        return len(self._buf)

    def feed(self, data: bytes) -> List[FramedRecord]:
        """Consume bytes, return any completed records.

        Safe to call with b"" (returns []).
        """
        if not data:
            return []

        if self._mode is FramingMode.RAW_CHUNK:
            return [self._clamp(data)]

        sep = _SEPARATORS[self._mode]
        sep_len = len(sep)

        self._buf.extend(data)
        out: List[FramedRecord] = []

        start = 0
        while True:
            idx = self._buf.find(sep, start)
            if idx < 0:
                break
            raw = bytes(self._buf[start:idx])
            start = idx + sep_len
            if self._overflow:
                # We already emitted the truncated record for this logical
                # record on an earlier feed; drop the tail up to this separator.
                self._overflow = False
                continue
            out.append(self._clamp(raw))

        # Retain only the unterminated tail.
        if start > 0:
            del self._buf[:start]

        # If the current tail has blown the cap without ever seeing a separator,
        # emit a truncated record now and enter overflow so we swallow the rest.
        if not self._overflow and len(self._buf) > self._max:
            out.append(
                FramedRecord(payload=bytes(self._buf[: self._max]), truncated=True)
            )
            self._buf.clear()
            self._overflow = True

        return out

    def flush(self) -> Optional[FramedRecord]:
        """Emit any remaining buffered bytes as a final record.

        Call when the peer disconnects and you want to preserve a trailing
        unterminated record. Returns None in RAW_CHUNK mode or when the
        buffer is empty / already-overflowed.
        """
        if self._mode is FramingMode.RAW_CHUNK:
            return None
        if self._overflow:
            self._buf.clear()
            self._overflow = False
            return None
        if not self._buf:
            return None
        rec = self._clamp(bytes(self._buf))
        self._buf.clear()
        return rec

    def reset(self) -> None:
        self._buf.clear()
        self._overflow = False

    def _clamp(self, raw: bytes) -> FramedRecord:
        if len(raw) > self._max:
            return FramedRecord(payload=raw[: self._max], truncated=True)
        return FramedRecord(payload=raw, truncated=False)
