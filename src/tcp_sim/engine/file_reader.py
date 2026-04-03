"""Streaming CSV reader with progressive scan support."""

from __future__ import annotations

import csv
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class RowRecord:
    data_line_number: int
    fields: list[str]


@dataclass(frozen=True)
class RawRowRecord:
    data_line_number: int
    fields: list[str]
    raw_text: str


@dataclass(frozen=True)
class PreviewRow:
    raw_row_number: int
    fields: list[str]
    valid: bool


@dataclass(frozen=True)
class ScanSnapshot:
    total_rows: int
    data_rows: int
    valid_rows: int
    invalid_rows: int
    processed_rows: int
    completed: bool


class FileReader:
    """Read delimited files with on-the-fly and background validation."""

    def __init__(
        self,
        file_path: str | Path,
        delimiter: str = ",",
        has_header: bool = True,
        encoding: str = "utf-8",
    ) -> None:
        self._file_path = Path(file_path)
        self._delimiter = delimiter
        self._has_header = has_header
        self._encoding = encoding

        self._header: list[str] | None = None
        self._header_raw: str | None = None
        self._expected_columns: int | None = None
        self._scan_lock = threading.Lock()
        self._scan_thread: threading.Thread | None = None
        self._scan_snapshot = ScanSnapshot(
            total_rows=0,
            data_rows=0,
            valid_rows=0,
            invalid_rows=0,
            processed_rows=0,
            completed=False,
        )

    @property
    def is_ready(self) -> bool:
        return self._file_path.exists()

    @property
    def header(self) -> list[str] | None:
        return list(self._header) if self._header is not None else None

    @property
    def header_raw(self) -> str | None:
        return self._header_raw

    @property
    def expected_columns(self) -> int | None:
        return self._expected_columns

    def _iter_rows_with_raw(self) -> Iterator[tuple[int, str, list[str]]]:
        with self._file_path.open("r", encoding=self._encoding, newline="") as handle:
            raw_lines = handle.readlines()

        with self._file_path.open("r", encoding=self._encoding, newline="") as handle:
            reader = csv.reader(handle, delimiter=self._delimiter)
            consumed_lines = 0
            for row in reader:
                end_line = reader.line_num
                raw_row_number = consumed_lines + 1
                raw_text = "".join(raw_lines[consumed_lines:end_line])
                consumed_lines = end_line
                yield raw_row_number, raw_text, row

    def _iter_rows(self) -> Iterator[tuple[int, list[str]]]:
        for raw_row_number, _, row in self._iter_rows_with_raw():
            yield raw_row_number, row

    def _is_valid_data_row(self, row: list[str]) -> bool:
        if self._expected_columns is None:
            self._expected_columns = len(row)
            return True
        return len(row) == self._expected_columns

    @staticmethod
    def _validate_line_controls(
        start_line: int | None,
        end_line: int | None,
        first_n: int | None,
    ) -> None:
        if start_line is not None and start_line < 1:
            raise ValueError("start_line must be >= 1")
        if end_line is not None and end_line < 1:
            raise ValueError("end_line must be >= 1")
        if first_n is not None and first_n < 1:
            raise ValueError("first_n must be >= 1")
        if start_line is not None and end_line is not None and end_line < start_line:
            raise ValueError("end_line must be >= start_line")

    @staticmethod
    def _line_is_selected(
        line_number: int,
        start_line: int | None,
        end_line: int | None,
    ) -> bool:
        if start_line is not None and line_number < start_line:
            return False
        if end_line is not None and line_number > end_line:
            return False
        return True

    def _reset_scan_state(self) -> None:
        with self._scan_lock:
            self._header = None
            self._header_raw = None
            self._expected_columns = None
            self._scan_snapshot = ScanSnapshot(
                total_rows=0,
                data_rows=0,
                valid_rows=0,
                invalid_rows=0,
                processed_rows=0,
                completed=False,
            )

    def _publish_snapshot(
        self,
        total_rows: int,
        data_rows: int,
        valid_rows: int,
        invalid_rows: int,
        processed_rows: int,
        completed: bool,
    ) -> None:
        with self._scan_lock:
            self._scan_snapshot = ScanSnapshot(
                total_rows=total_rows,
                data_rows=data_rows,
                valid_rows=valid_rows,
                invalid_rows=invalid_rows,
                processed_rows=processed_rows,
                completed=completed,
            )

    def scan_file(self) -> ScanSnapshot:
        self._reset_scan_state()

        total_rows = 0
        data_rows = 0
        valid_rows = 0
        invalid_rows = 0

        for raw_row_number, row in self._iter_rows():
            total_rows += 1

            if self._has_header and self._header is None:
                self._header = row
                self._expected_columns = len(row)
                self._publish_snapshot(
                    total_rows,
                    data_rows,
                    valid_rows,
                    invalid_rows,
                    raw_row_number,
                    completed=False,
                )
                continue

            data_rows += 1
            if self._is_valid_data_row(row):
                valid_rows += 1
            else:
                invalid_rows += 1

            self._publish_snapshot(
                total_rows,
                data_rows,
                valid_rows,
                invalid_rows,
                raw_row_number,
                completed=False,
            )

        self._publish_snapshot(
            total_rows,
            data_rows,
            valid_rows,
            invalid_rows,
            total_rows,
            completed=True,
        )
        return self.get_scan_snapshot()

    def start_background_scan(self) -> None:
        if self._scan_thread and self._scan_thread.is_alive():
            return

        self._scan_thread = threading.Thread(target=self.scan_file, daemon=True)
        self._scan_thread.start()

    def wait_for_scan(self, timeout: float | None = None) -> bool:
        thread = self._scan_thread
        if thread is None:
            return True

        thread.join(timeout=timeout)
        return not thread.is_alive()

    def get_scan_snapshot(self) -> ScanSnapshot:
        with self._scan_lock:
            return self._scan_snapshot

    def load_preview(self, limit: int = 10) -> list[PreviewRow]:
        if limit <= 0:
            return []

        self._reset_scan_state()
        preview: list[PreviewRow] = []

        for raw_row_number, row in self._iter_rows():
            if self._has_header and self._header is None:
                self._header = row
                self._expected_columns = len(row)
                continue

            is_valid = self._is_valid_data_row(row)
            preview.append(
                PreviewRow(
                    raw_row_number=raw_row_number,
                    fields=row,
                    valid=is_valid,
                )
            )

            if len(preview) >= limit:
                break

        return preview

    def iter_valid_rows(
        self,
        start_line: int | None = None,
        end_line: int | None = None,
        first_n: int | None = None,
    ) -> Iterator[RowRecord]:
        self._validate_line_controls(start_line, end_line, first_n)

        self._reset_scan_state()
        data_line_number = 0
        emitted = 0

        for _, row in self._iter_rows():
            if self._has_header and self._header is None:
                self._header = row
                self._expected_columns = len(row)
                continue

            if not self._is_valid_data_row(row):
                continue

            data_line_number += 1

            if not self._line_is_selected(data_line_number, start_line, end_line):
                if end_line is not None and data_line_number > end_line:
                    break
                continue

            if first_n is not None and emitted >= first_n:
                break

            emitted += 1
            yield RowRecord(data_line_number=data_line_number, fields=row)

    def iter_valid_raw_rows(
        self,
        start_line: int | None = None,
        end_line: int | None = None,
        first_n: int | None = None,
    ) -> Iterator[RawRowRecord]:
        self._validate_line_controls(start_line, end_line, first_n)

        self._reset_scan_state()
        data_line_number = 0
        emitted = 0

        for _, raw_text, row in self._iter_rows_with_raw():
            if self._has_header and self._header is None:
                self._header = row
                self._header_raw = raw_text
                self._expected_columns = len(row)
                continue

            if not self._is_valid_data_row(row):
                continue

            data_line_number += 1

            if not self._line_is_selected(data_line_number, start_line, end_line):
                if end_line is not None and data_line_number > end_line:
                    break
                continue

            if first_n is not None and emitted >= first_n:
                break

            emitted += 1
            yield RawRowRecord(
                data_line_number=data_line_number,
                fields=row,
                raw_text=raw_text,
            )
