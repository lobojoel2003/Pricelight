# SPDX-License-Identifier: Apache-2.0
"""Arrow batching and Parquet output."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from operator import attrgetter
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq

from .__about__ import __version__
from .models import (
    CHARGE_COLUMNS,
    SCHEMA_VERSION,
    ChargeRow,
    HospitalHeader,
    Issue,
    MRFFormat,
    ParseStats,
)

if TYPE_CHECKING:  # pragma: no cover
    from .base import BaseParser

CODE_STRUCT = pa.struct([("code", pa.string()), ("type", pa.string())])

#: Arrow schema of a normalized charges table.
CHARGE_SCHEMA = pa.schema(
    [
        ("item_index", pa.int64()),
        ("description", pa.string()),
        ("code", pa.string()),
        ("code_type", pa.string()),
        ("codes", pa.list_(CODE_STRUCT)),
        ("setting", pa.string()),
        ("billing_class", pa.string()),
        ("modifiers", pa.list_(pa.string())),
        ("drug_unit", pa.float64()),
        ("drug_type", pa.string()),
        ("gross_charge", pa.float64()),
        ("discounted_cash", pa.float64()),
        ("min_negotiated", pa.float64()),
        ("max_negotiated", pa.float64()),
        ("payer_name", pa.string()),
        ("plan_name", pa.string()),
        ("negotiated_dollar", pa.float64()),
        ("negotiated_percentage", pa.float64()),
        ("negotiated_algorithm", pa.string()),
        ("methodology", pa.string()),
        ("estimated_amount", pa.float64()),
        ("median_amount", pa.float64()),
        ("p10_amount", pa.float64()),
        ("p90_amount", pa.float64()),
        ("allowed_count", pa.string()),
        ("additional_generic_notes", pa.string()),
        ("additional_payer_notes", pa.string()),
    ]
)
assert tuple(CHARGE_SCHEMA.names) == CHARGE_COLUMNS, "schema and dataclass drifted"

METADATA_KEY = b"pricelight"
_ROW_GETTER = attrgetter(*CHARGE_COLUMNS)


def schema_with_constants(constants: Mapping[str, str] | None) -> pa.Schema:
    schema = CHARGE_SCHEMA
    for name in constants or {}:
        schema = schema.append(pa.field(name, pa.string()))
    return schema


def rows_to_batch(
    rows: list[ChargeRow],
    constants: Mapping[str, str] | None = None,
    schema: pa.Schema | None = None,
) -> pa.RecordBatch:
    """Convert rows to an Arrow record batch (column-wise, no pandas)."""
    columns: dict[str, list[Any]]
    if rows:
        transposed = zip(*map(_ROW_GETTER, rows), strict=True)
        columns = dict(zip(CHARGE_COLUMNS, map(list, transposed), strict=True))
    else:
        columns = {name: [] for name in CHARGE_COLUMNS}
    # Rows of one item share the same codes list; convert each list once.
    converted: dict[int, list[dict[str, str]]] = {}
    codes_out = []
    for codes in columns["codes"]:
        value = converted.get(id(codes))
        if value is None:
            value = [{"code": c.code, "type": c.type} for c in codes]
            converted[id(codes)] = value
        codes_out.append(value)
    columns["codes"] = codes_out
    arrays = [
        pa.array(columns[name], type=CHARGE_SCHEMA.field(name).type) for name in CHARGE_COLUMNS
    ]
    for constant in (constants or {}).values():
        arrays.append(pa.array([constant] * len(rows), type=pa.string()))
    return pa.RecordBatch.from_arrays(arrays, schema=schema or schema_with_constants(constants))


def iter_batches(
    rows: Iterable[ChargeRow],
    batch_size: int = 65_536,
    constants: Mapping[str, str] | None = None,
) -> Iterator[pa.RecordBatch]:
    schema = schema_with_constants(constants)
    buffer: list[ChargeRow] = []
    for row in rows:
        buffer.append(row)
        if len(buffer) >= batch_size:
            yield rows_to_batch(buffer, constants, schema)
            buffer = []
    if buffer:
        yield rows_to_batch(buffer, constants, schema)


@dataclass(slots=True)
class ParseResult:
    """Summary returned by :func:`pricelight_parser.to_parquet`."""

    source: str
    format: MRFFormat
    header: HospitalHeader
    stats: ParseStats
    issues: list[Issue]
    output: str | None = None
    elapsed_seconds: float = 0.0
    parser_version: str = __version__
    schema_version: int = SCHEMA_VERSION
    compression: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(i.severity.value == "error" for i in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "format": self.format.value,
            "compression": self.compression,
            "header": self.header.to_dict(),
            "stats": self.stats.to_dict(),
            "issues": [i.to_dict() for i in self.issues],
            "output": self.output,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "parser_version": self.parser_version,
            "schema_version": self.schema_version,
        }

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str, **kwargs)


def write_parquet(
    parser: BaseParser,
    output: str | Path,
    *,
    constants: Mapping[str, str] | None = None,
    batch_size: int = 65_536,
    row_group_size: int = 262_144,
    compression: str = "zstd",
) -> ParseResult:
    """Stream ``parser`` into a Parquet file and return a :class:`ParseResult`."""
    started = time.perf_counter()
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".partial")
    schema = schema_with_constants(constants)
    writer = pq.ParquetWriter(tmp, schema, compression=compression)
    try:
        pending: list[pa.RecordBatch] = []
        pending_rows = 0
        for batch in iter_batches(parser.rows(), batch_size, constants):
            pending.append(batch)
            pending_rows += batch.num_rows
            if pending_rows >= row_group_size:
                writer.write_table(pa.Table.from_batches(pending, schema=schema))
                pending, pending_rows = [], 0
        if pending:
            writer.write_table(pa.Table.from_batches(pending, schema=schema))
        result = ParseResult(
            source=parser.source.display_name,
            format=parser.format,
            header=parser.header,
            stats=parser.stats,
            issues=parser.issues,
            output=str(out),
            compression=parser.source.compression,
        )
        result.elapsed_seconds = time.perf_counter() - started
        writer.add_key_value_metadata({METADATA_KEY: result.to_json().encode("utf-8")})
    except BaseException:
        writer.close()
        tmp.unlink(missing_ok=True)
        raise
    writer.close()
    tmp.replace(out)
    return result


def read_result_metadata(path: str | Path) -> dict[str, Any] | None:
    """Read the parse summary embedded in a Parquet file written by this package."""
    meta = pq.ParquetFile(path).metadata.metadata or {}
    raw = meta.get(METADATA_KEY)
    return json.loads(raw) if raw else None
