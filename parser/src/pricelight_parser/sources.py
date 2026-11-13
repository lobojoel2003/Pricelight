# SPDX-License-Identifier: Apache-2.0
"""Opening MRFs: decompression, encoding detection and format sniffing.

Hospitals publish files as plain JSON/CSV, but also gzip, zip, bzip2 and xz
archives. Compression is detected from magic bytes (not file extensions,
which are frequently wrong) and every stream is read incrementally, so a
multi-gigabyte file never has to fit in memory.
"""

from __future__ import annotations

import bz2
import codecs
import csv
import gzip
import io
import lzma
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO, BinaryIO

from .models import MRFFormat

PathLike = str | os.PathLike[str]

_MAGIC_GZIP = b"\x1f\x8b"
_MAGIC_ZIP = b"PK\x03\x04"
_MAGIC_BZ2 = b"BZh"
_MAGIC_XZ = b"\xfd7zXZ\x00"
_MAGIC_ZSTD = b"\x28\xb5\x2f\xfd"

_DATA_SUFFIXES = (".json", ".csv", ".txt")


class UnsupportedFileError(ValueError):
    """Raised when a file is not a recognizable hospital price MRF."""


@dataclass(frozen=True, slots=True)
class SourceInfo:
    path: Path
    compression: str | None
    member: str | None
    size_bytes: int


def _sniff_compression(path: Path) -> str | None:
    with path.open("rb") as fh:
        head = fh.read(8)
    if head.startswith(_MAGIC_GZIP):
        return "gzip"
    if head.startswith(_MAGIC_ZIP):
        return "zip"
    if head.startswith(_MAGIC_BZ2):
        return "bz2"
    if head.startswith(_MAGIC_XZ):
        return "xz"
    if head.startswith(_MAGIC_ZSTD):
        return "zstd"
    return None


def _pick_zip_member(zf: zipfile.ZipFile) -> str:
    candidates = [
        info
        for info in zf.infolist()
        if not info.is_dir()
        and not info.filename.startswith("__MACOSX/")
        and info.filename.lower().endswith(_DATA_SUFFIXES)
    ]
    if not candidates:
        candidates = [info for info in zf.infolist() if not info.is_dir()]
    if not candidates:
        raise UnsupportedFileError("zip archive is empty")
    # The MRF is almost always the largest member (readme files are tiny).
    return max(candidates, key=lambda info: info.file_size).filename


class _CountingReader(io.RawIOBase):
    """Wraps a binary stream and counts bytes for progress reporting."""

    def __init__(self, raw: BinaryIO) -> None:
        self._raw = raw
        self.count = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray | memoryview) -> int:  # type: ignore[override]
        data = self._raw.read(len(buffer))
        n = len(data)
        buffer[:n] = data
        self.count += n
        return n

    def close(self) -> None:
        try:
            self._raw.close()
        finally:
            super().close()


class Source:
    """A reopenable handle on an MRF on disk.

    The JSON parser may read a file twice (a quick metadata pre-scan and the
    main pass), so a source knows how to reopen its decompressed stream.
    """

    def __init__(self, path: PathLike) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self.compression = _sniff_compression(self.path)
        self.member: str | None = None
        if self.compression == "zip":
            with zipfile.ZipFile(self.path) as zf:
                self.member = _pick_zip_member(zf)
        if self.compression == "zstd":
            try:
                import zstandard  # type: ignore[import-not-found]  # noqa: F401
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise UnsupportedFileError(
                    "zstd-compressed file: install the 'zstandard' package to read it"
                ) from exc
        self.last_reader: _CountingReader | None = None

    @property
    def info(self) -> SourceInfo:
        return SourceInfo(
            path=self.path,
            compression=self.compression,
            member=self.member,
            size_bytes=self.path.stat().st_size,
        )

    @property
    def display_name(self) -> str:
        return self.member or self.path.name

    def open_binary(self) -> BinaryIO:
        """Open the decompressed byte stream (caller must close it)."""
        raw: BinaryIO
        if self.compression is None:
            raw = self.path.open("rb")
        elif self.compression == "gzip":
            raw = gzip.open(self.path, "rb")  # type: ignore[assignment]
        elif self.compression == "bz2":
            raw = bz2.open(self.path, "rb")  # type: ignore[assignment]
        elif self.compression == "xz":
            raw = lzma.open(self.path, "rb")  # type: ignore[assignment]
        elif self.compression == "zip":
            zf = zipfile.ZipFile(self.path)
            assert self.member is not None
            member = zf.open(self.member)
            raw = _ZipMemberStream(zf, member)  # type: ignore[assignment]
        elif self.compression == "zstd":  # pragma: no cover - optional dependency
            import zstandard

            raw = zstandard.ZstdDecompressor().stream_reader(self.path.open("rb"))
        else:  # pragma: no cover - defensive
            raise UnsupportedFileError(f"unsupported compression {self.compression}")
        reader = _CountingReader(raw)
        self.last_reader = reader
        return io.BufferedReader(reader, buffer_size=1 << 20)  # type: ignore[return-value]

    def open_text(self) -> IO[str]:
        """Open the decompressed stream as text, guessing the encoding."""
        encoding = self.detect_encoding()
        binary = self.open_binary()
        return io.TextIOWrapper(binary, encoding=encoding, errors="replace", newline="")

    def head(self, n: int = 1 << 16) -> bytes:
        with self.open_binary() as fh:
            return fh.read(n)

    def detect_encoding(self) -> str:
        head = self.head(1 << 18)
        if head.startswith(codecs.BOM_UTF8):
            return "utf-8-sig"
        if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            return "utf-16"
        try:
            head.decode("utf-8")
        except UnicodeDecodeError as exc:
            # A multi-byte character may be cut at the end of the sample.
            if exc.start < len(head) - 4:
                return "cp1252"
        return "utf-8"

    def detect_format(self) -> MRFFormat:
        """Sniff JSON vs CSV tall vs CSV wide from the first bytes."""
        head = self.head(1 << 20)
        text = head.decode(self.detect_encoding(), errors="replace").lstrip("﻿ \t\r\n")
        if not text:
            raise UnsupportedFileError(f"{self.display_name}: file is empty")
        if text[0] == "{":
            return MRFFormat.JSON
        if text[0] == "[":
            raise UnsupportedFileError(
                f"{self.display_name}: top-level JSON array; the CMS template requires an object"
            )
        rows = list(_first_rows(text, 3))
        if len(rows) < 3:
            raise UnsupportedFileError(f"{self.display_name}: CSV has fewer than 3 header rows")
        return classify_csv_header(rows[2], name=self.display_name)


def _first_rows(text: str, n: int) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text))
    rows: list[list[str]] = []
    for row in reader:
        rows.append(row)
        if len(rows) >= n:
            break
    return rows


def normalize_header(cell: str) -> str:
    """``"Standard_Charge | Gross "`` -> ``"standard_charge|gross"``."""
    return "|".join(part.strip().lower() for part in cell.split("|"))


def classify_csv_header(row: list[str], *, name: str = "file") -> MRFFormat:
    headers = [normalize_header(c) for c in row]
    if "description" not in headers:
        raise UnsupportedFileError(
            f"{name}: row 3 has no 'description' column; not a CMS template CSV"
        )
    if "payer_name" in headers:
        return MRFFormat.CSV_TALL
    for h in headers:
        parts = h.split("|")
        if parts[0] == "standard_charge" and len(parts) >= 4:
            return MRFFormat.CSV_WIDE
        if (
            parts[0] in {"estimated_amount", "median_amount", "additional_payer_notes"}
            and len(parts) >= 3
        ):
            return MRFFormat.CSV_WIDE
    # A file with only gross/cash columns has no payer columns at all; it is
    # structurally identical in both layouts. Treat it as tall.
    return MRFFormat.CSV_TALL


class _ZipMemberStream(io.RawIOBase):
    """Keeps the parent ZipFile alive while a member is being read."""

    def __init__(self, zf: zipfile.ZipFile, member: IO[bytes]) -> None:
        self._zf = zf
        self._member = member

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray | memoryview) -> int:  # type: ignore[override]
        data = self._member.read(len(buffer))
        n = len(data)
        buffer[:n] = data
        return n

    def close(self) -> None:
        try:
            self._member.close()
            self._zf.close()
        finally:
            super().close()
