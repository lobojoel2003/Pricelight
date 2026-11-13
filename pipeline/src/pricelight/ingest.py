# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse every hospital in the manifest into the Parquet "lake".

Each hospital is converted independently (in parallel processes) with the
streaming :mod:`pricelight_parser`, so one malformed file never blocks the
rest. Re-runs are incremental: a hospital is skipped when its source file
and the parser version are unchanged since the last successful ingest.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import multiprocessing
import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from pricelight_parser import UnsupportedFileError, to_parquet
from pricelight_parser import __version__ as parser_version

from .manifest import DataDir, HospitalEntry, read_manifest

log = logging.getLogger(__name__)

STATE_FILE = "_ingest.json"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


@dataclass(slots=True)
class IngestOutcome:
    hospital_id: str
    status: str  # ok | skipped | failed | missing
    record: dict[str, Any]
    message: str = ""


def _fingerprint(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {"path": str(path), "bytes": st.st_size, "mtime_ns": st.st_mtime_ns}


def _base_record(entry: HospitalEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "name": entry.name,
        "address": entry.address,
        "city": entry.city,
        "state": entry.state,
        "zip": entry.zip,
        "lat": entry.lat,
        "lon": entry.lon,
        "website": entry.website,
        "source_page_url": entry.source_page_url,
        "mrf_url": entry.mrf_url,
        "ccn": entry.ccn,
    }


def ingest_one(entry: HospitalEntry, data_root: str, force: bool = False) -> IngestOutcome:
    """Parse one hospital's MRF into ``lake/charges/hospital_id=<id>/``.

    Runs in a worker process; returns a plain record for hospitals.parquet.
    """
    data = DataDir.at(data_root)
    record = _base_record(entry)
    source = data.resolve_mrf(entry)
    if source is None or not source.is_file():
        record.update(status="missing", error_message="no local file; run `pricelight fetch`")
        return IngestOutcome(entry.id, "missing", record, "no local file")

    out = data.charges_file(entry.id)
    state_path = out.parent / STATE_FILE
    fingerprint = _fingerprint(source)
    if not force and state_path.is_file() and out.is_file():
        previous = json.loads(state_path.read_text("utf-8"))
        if (
            previous.get("fingerprint") == fingerprint
            and previous.get("parser_version") == parser_version
            and previous.get("record", {}).get("status") == "ok"
        ):
            prev_record = previous["record"]
            prev_record.update(_base_record(entry))
            return IngestOutcome(entry.id, "skipped", prev_record)

    record["mrf_file"] = source.name
    record["file_bytes"] = fingerprint["bytes"]
    record["file_sha256"] = sha256_file(source)
    try:
        result = to_parquet(source, out)
    except (UnsupportedFileError, OSError, ValueError) as exc:
        out.unlink(missing_ok=True)
        record.update(status="failed", error_message=str(exc)[:500])
        return IngestOutcome(entry.id, "failed", record, str(exc))

    h = result.header
    s = result.stats
    errors = sum(1 for i in result.issues if i.severity.value == "error")
    record.update(
        status="ok",
        error_message="",
        format=result.format.value,
        compression=result.compression or "",
        template_version=h.version or "",
        last_updated_on=h.last_updated_on or "",
        hospital_name_in_file=h.hospital_name or "",
        license_number=h.license_number or "",
        license_state=h.license_state or "",
        attestation_confirmed=h.attestation_confirmed,
        attester_name=h.attester_name or "",
        type_2_npis=",".join(h.type_2_npis),
        n_locations=len(h.location_names),
        items=s.items,
        rows=s.rows,
        payer_rows=s.payer_rows,
        rows_with_cash=s.rows_with_cash,
        rows_with_gross=s.rows_with_gross,
        rows_with_negotiated_dollar=s.rows_with_negotiated_dollar,
        payers=s.payers,
        issue_errors=errors,
        issue_warnings=len(result.issues) - errors,
        issues_json=json.dumps([i.to_dict() for i in result.issues]),
        parse_seconds=round(result.elapsed_seconds, 3),
        parser_version=result.parser_version,
        ingested_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    )
    if not record["name"]:
        record["name"] = h.hospital_name or entry.id
    state_path.write_text(
        json.dumps(
            {"fingerprint": fingerprint, "parser_version": parser_version, "record": record}
        ),
        "utf-8",
    )
    return IngestOutcome(entry.id, "ok", record)


HOSPITAL_SCHEMA: dict[str, Any] = {
    "id": pl.String,
    "name": pl.String,
    "address": pl.String,
    "city": pl.String,
    "state": pl.String,
    "zip": pl.String,
    "lat": pl.Float64,
    "lon": pl.Float64,
    "website": pl.String,
    "source_page_url": pl.String,
    "mrf_url": pl.String,
    "ccn": pl.String,
    "status": pl.String,
    "error_message": pl.String,
    "mrf_file": pl.String,
    "file_bytes": pl.Int64,
    "file_sha256": pl.String,
    "format": pl.String,
    "compression": pl.String,
    "template_version": pl.String,
    "last_updated_on": pl.String,
    "hospital_name_in_file": pl.String,
    "license_number": pl.String,
    "license_state": pl.String,
    "attestation_confirmed": pl.Boolean,
    "attester_name": pl.String,
    "type_2_npis": pl.String,
    "n_locations": pl.Int64,
    "items": pl.Int64,
    "rows": pl.Int64,
    "payer_rows": pl.Int64,
    "rows_with_cash": pl.Int64,
    "rows_with_gross": pl.Int64,
    "rows_with_negotiated_dollar": pl.Int64,
    "payers": pl.Int64,
    "issue_errors": pl.Int64,
    "issue_warnings": pl.Int64,
    "issues_json": pl.String,
    "parse_seconds": pl.Float64,
    "parser_version": pl.String,
    "ingested_at": pl.String,
}


def ingest(
    data: DataDir,
    *,
    jobs: int | None = None,
    force: bool = False,
    only: set[str] | None = None,
    progress: Callable[[IngestOutcome, int, int], None] | None = None,
) -> pl.DataFrame:
    """Ingest all manifest entries and write ``lake/hospitals.parquet``."""
    entries = read_manifest(data.manifest)
    if only:
        entries = [e for e in entries if e.id in only]
    jobs = jobs or min(8, os.cpu_count() or 1)
    outcomes: list[IngestOutcome] = []
    total = len(entries)
    if jobs <= 1 or total <= 1:
        for entry in entries:
            outcome = ingest_one(entry, str(data.root), force)
            outcomes.append(outcome)
            if progress:
                progress(outcome, len(outcomes), total)
    else:
        # "spawn" avoids forking a process that already runs DuckDB/Arrow threads.
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=jobs, mp_context=context) as pool:
            futures = [pool.submit(ingest_one, e, str(data.root), force) for e in entries]
            for future in as_completed(futures):
                outcome = future.result()
                outcomes.append(outcome)
                if progress:
                    progress(outcome, len(outcomes), total)

    # Keep hospitals that were not part of this (partial) run.
    records = {o.hospital_id: o.record for o in outcomes}
    if only and data.hospitals_table.is_file():
        for row in pl.read_parquet(data.hospitals_table).to_dicts():
            records.setdefault(row["id"], row)
    manifest_ids = {e.id for e in read_manifest(data.manifest)}
    _remove_orphans(data, manifest_ids)
    order = {e.id: i for i, e in enumerate(read_manifest(data.manifest))}
    rows = sorted(
        (r for r in records.values() if r["id"] in manifest_ids), key=lambda r: order[r["id"]]
    )
    frame = pl.DataFrame(
        [{k: r.get(k) for k in HOSPITAL_SCHEMA} for r in rows], schema=HOSPITAL_SCHEMA
    )
    data.lake.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(data.hospitals_table, compression="zstd")
    return frame


def _remove_orphans(data: DataDir, keep: set[str]) -> None:
    """Delete lake partitions of hospitals that left the manifest."""
    if not data.charges.is_dir():
        return
    for part in data.charges.iterdir():
        if part.is_dir() and part.name.startswith("hospital_id="):
            hid = part.name.split("=", 1)[1]
            if hid not in keep:
                for f in part.iterdir():
                    f.unlink()
                part.rmdir()
                log.info("removed lake partition for %s", hid)
