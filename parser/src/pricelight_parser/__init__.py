# SPDX-License-Identifier: Apache-2.0
"""pricelight-parser: stream US hospital price transparency files into tidy rows.

Quick start::

    from pricelight_parser import open_mrf, to_parquet

    mrf = open_mrf("123456789_example-hospital_standardcharges.json.gz")
    print(mrf.format, mrf.header.hospital_name)
    for row in mrf.rows():
        ...

    result = to_parquet("hospital.csv", "hospital.parquet")
    print(result.stats.rows, [i.code for i in result.issues])
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa

from .__about__ import __version__
from .base import BaseParser
from .csv_format import CsvParser, parse_wide_header
from .hpt_txt import HptEntry, MrfFileName, hpt_txt_url, parse_hpt_txt, parse_mrf_filename
from .json_format import JsonParser
from .models import (
    CHARGE_COLUMNS,
    SCHEMA_VERSION,
    ChargeRow,
    Code,
    HospitalHeader,
    Issue,
    MRFFormat,
    ParseStats,
    Severity,
)
from .normalize import IssueLog
from .sources import Source, UnsupportedFileError
from .writer import (
    CHARGE_SCHEMA,
    ParseResult,
    iter_batches,
    read_result_metadata,
    rows_to_batch,
    write_parquet,
)

if TYPE_CHECKING:  # pragma: no cover
    import polars as pl

__all__ = [
    "CHARGE_COLUMNS",
    "CHARGE_SCHEMA",
    "SCHEMA_VERSION",
    "BaseParser",
    "ChargeRow",
    "Code",
    "CsvParser",
    "HospitalHeader",
    "HptEntry",
    "Issue",
    "IssueLog",
    "JsonParser",
    "MRFFormat",
    "MrfFileName",
    "ParseResult",
    "ParseStats",
    "Severity",
    "Source",
    "UnsupportedFileError",
    "__version__",
    "hpt_txt_url",
    "iter_batches",
    "open_mrf",
    "parse_hpt_txt",
    "parse_mrf_filename",
    "parse_wide_header",
    "read_polars",
    "read_result_metadata",
    "record_batch_reader",
    "rows_to_batch",
    "to_parquet",
]


def open_mrf(
    path: str | Path,
    *,
    format: MRFFormat | str | None = None,
    full_metadata: bool = False,
) -> BaseParser:
    """Open a hospital machine-readable file and return a streaming parser.

    Args:
        path: Path to a ``.json`` or ``.csv`` MRF, optionally gzip/zip/bz2/xz
            compressed (detected from the file's magic bytes).
        format: Force a layout instead of sniffing it.
        full_metadata: JSON only. Always read metadata that follows the
            charge array (costs a second pass over the file). By default the
            second pass only runs when required metadata is missing.
    """
    source = Source(path)
    fmt = MRFFormat(format) if format is not None else source.detect_format()
    if fmt is MRFFormat.JSON:
        parser: BaseParser = JsonParser(source, full_metadata=full_metadata)
        parser.prescan()  # type: ignore[attr-defined]
        return parser
    return CsvParser(source, fmt=fmt)


def to_parquet(
    path: str | Path,
    output: str | Path,
    *,
    constants: Mapping[str, str] | None = None,
    format: MRFFormat | str | None = None,
    batch_size: int = 65_536,
    row_group_size: int = 262_144,
    compression: str = "zstd",
    full_metadata: bool = False,
) -> ParseResult:
    """Convert an MRF to Parquet in a single streaming pass.

    ``constants`` adds string columns with a fixed value to every row, e.g.
    ``{"hospital_id": "cms-123456"}`` when combining many hospitals.
    The parse summary (header, stats, issues) is embedded in the Parquet
    key-value metadata under ``pricelight``; see :func:`read_result_metadata`.
    """
    parser = open_mrf(path, format=format, full_metadata=full_metadata)
    return write_parquet(
        parser,
        output,
        constants=constants,
        batch_size=batch_size,
        row_group_size=row_group_size,
        compression=compression,
    )


def record_batch_reader(
    path: str | Path,
    *,
    batch_size: int = 65_536,
    constants: Mapping[str, str] | None = None,
    **kwargs: Any,
) -> pa.RecordBatchReader:
    """Stream an MRF as an Arrow ``RecordBatchReader``.

    DuckDB and Polars can consume the reader directly without materializing
    the whole file::

        import duckdb
        reader = record_batch_reader("hospital.json")
        duckdb.sql("SELECT payer_name, avg(negotiated_dollar) FROM reader GROUP BY 1")
    """
    from .writer import schema_with_constants

    parser = open_mrf(path, **kwargs)
    schema = schema_with_constants(constants)
    return pa.RecordBatchReader.from_batches(
        schema, iter_batches(parser.rows(), batch_size, constants)
    )


def read_polars(path: str | Path, **kwargs: Any) -> pl.DataFrame:
    """Parse an MRF into a Polars DataFrame (requires the ``polars`` extra)."""
    import polars as pl

    reader = record_batch_reader(path, **kwargs)
    return pl.from_arrow(reader.read_all())  # type: ignore[return-value]
