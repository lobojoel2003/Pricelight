# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build the compact search dataset served to the web app.

Input: the Parquet lake written by :mod:`pricelight.ingest`.
Output (``data/site`` by default)::

    meta.json        build info and dataset totals
    hospitals.json   one entry per hospital: location, file facts, data quality
    services.json    searchable services: code, plain-language label, coverage
    payers.json      normalized payer names and how many hospitals list them
    prices.parquet   one row per service x hospital (item prices) and per
                     service x hospital x payer/plan (negotiated rates),
                     sorted by service so the browser can fetch only the row
                     groups it needs with HTTP range requests (DuckDB-WASM)

All heavy lifting happens in DuckDB; Polars shapes the small JSON outputs.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from pricelight_parser import __version__ as parser_version

from .__about__ import __version__
from .catalog import BY_KEY, SEARCHABLE_CODE_TYPES, category_for
from .manifest import DataDir
from .payers import clean_payer_name, normalize_payer

DEMO_MARKER = "DEMO"
SITE_SCHEMA_VERSION = 1


@dataclass(slots=True)
class BuildSummary:
    out_dir: Path
    hospitals: int
    services: int
    payers: int
    price_rows: int

    def __str__(self) -> str:
        return (
            f"{self.hospitals} hospitals, {self.services} services, {self.payers} payers, "
            f"{self.price_rows:,} price rows -> {self.out_dir}"
        )


def sql_path(path: Path) -> str:
    """A filesystem path as a DuckDB string literal body (POSIX separators, quotes escaped)."""
    return path.as_posix().replace("'", "''")


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def _connect(threads: int | None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    if threads:
        con.execute(f"SET threads = {int(threads)}")
    con.execute("SET preserve_insertion_order = false")
    return con


def _title(text: str | None) -> str | None:
    if text is None:
        return None
    text = " ".join(text.split())
    if text.isupper():
        return clean_payer_name(text)
    return text


def build(
    data: DataDir,
    out_dir: Path | None = None,
    *,
    min_hospitals: int = 1,
    threads: int | None = None,
    build_info: Mapping[str, Any] | None = None,
    row_group_size: int = 8192,
) -> BuildSummary:
    out = Path(out_dir) if out_dir else data.site
    if not data.hospitals_table.is_file():
        raise FileNotFoundError(f"{data.hospitals_table} not found; run `pricelight ingest` first")
    out.mkdir(parents=True, exist_ok=True)
    con = _connect(threads)

    hospitals = pl.read_parquet(data.hospitals_table).filter(pl.col("status") == "ok")
    ok_ids = hospitals["id"].to_list()
    if not ok_ids:
        raise RuntimeError("no successfully ingested hospitals to build from")
    pattern = sql_path(data.charges / "*" / "charges.parquet")
    con.execute(
        f"""
        CREATE VIEW charges AS
        SELECT * FROM read_parquet('{pattern}', hive_partitioning = true, union_by_name = true)
        """
    )
    con.register("ok_hospitals", pl.DataFrame({"id": ok_ids}).to_arrow())

    # -- payer normalization (small distinct set, done in Python) ----------
    raw_payers = [
        r[0]
        for r in con.sql(
            "SELECT DISTINCT payer_name FROM charges WHERE payer_name IS NOT NULL"
        ).fetchall()
    ]
    payer_map = pl.DataFrame(
        {"raw": raw_payers, "payer": [normalize_payer(p) for p in raw_payers]},
        schema={"raw": pl.String, "payer": pl.String},
    )
    con.register("payer_map", payer_map.to_arrow())

    searchable = _sql_list(SEARCHABLE_CODE_TYPES)
    # -- one preferred setting per service x hospital -----------------------
    # DRGs are inpatient by definition; for procedure codes people shop the
    # outpatient price. "both" applies to either.
    con.execute(
        f"""
        CREATE TABLE base AS
        WITH c AS (
            SELECT c.*, c.code_type || ':' || c.code AS service,
                   coalesce(c.setting, 'both') AS setting_norm
            FROM charges c
            JOIN ok_hospitals h ON h.id = c.hospital_id
            WHERE c.code IS NOT NULL AND c.code_type IN ({searchable})
        ),
        ranked AS (
            SELECT *,
                CASE
                    WHEN code_type LIKE '%DRG' THEN
                        CASE setting_norm WHEN 'inpatient' THEN 0 WHEN 'both' THEN 1 ELSE 2 END
                    ELSE
                        CASE setting_norm WHEN 'outpatient' THEN 0 WHEN 'both' THEN 1 ELSE 2 END
                END AS setting_rank
            FROM c
        ),
        best AS (
            SELECT service, hospital_id, min(setting_rank) AS best_rank
            FROM ranked GROUP BY ALL
        )
        SELECT r.* EXCLUDE (setting_rank, setting, setting_norm), r.setting_norm AS setting
        FROM ranked r
        JOIN best b USING (service, hospital_id)
        WHERE r.setting_rank = b.best_rank
        -- Prefer lines without modifiers (e.g. professional/technical splits)
        QUALIFY len(r.modifiers) = 0
             OR count(*) FILTER (WHERE len(r.modifiers) = 0)
                OVER (PARTITION BY r.service, r.hospital_id) = 0
        """
    )

    con.execute(
        """
        CREATE TABLE item_prices AS
        SELECT service, hospital_id AS hospital, any_value(setting) AS setting,
               mode(description) AS description,
               median(gross_charge) AS gross,
               median(discounted_cash) AS cash,
               min(min_negotiated) AS min_reported,
               max(max_negotiated) AS max_reported
        FROM base GROUP BY service, hospital_id
        """
    )
    con.execute(
        """
        CREATE TABLE payer_prices AS
        SELECT b.service, b.hospital_id AS hospital, any_value(b.setting) AS setting,
               m.payer, trim(coalesce(b.plan_name, '')) AS plan,
               median(b.negotiated_dollar) AS dollar,
               median(coalesce(b.median_amount, b.estimated_amount)) AS allowed,
               median(b.negotiated_percentage) AS pct,
               left(any_value(b.negotiated_algorithm), 240) AS algorithm,
               mode(b.methodology) AS methodology
        FROM base b JOIN payer_map m ON m.raw = b.payer_name
        WHERE b.payer_name IS NOT NULL
        GROUP BY b.service, b.hospital_id, m.payer, trim(coalesce(b.plan_name, ''))
        """
    )
    con.execute(
        """
        CREATE TABLE prices AS
        WITH payer_rows AS (
            SELECT service, hospital, setting, payer, nullif(plan, '') AS plan,
                   coalesce(dollar, allowed) AS rate,
                   CASE WHEN dollar IS NOT NULL THEN 'dollar'
                        WHEN allowed IS NOT NULL THEN 'allowed' END AS rate_basis,
                   pct, algorithm, methodology,
                   NULL::DOUBLE AS gross, NULL::DOUBLE AS cash,
                   NULL::DOUBLE AS min, NULL::DOUBLE AS max, NULL::VARCHAR AS description
            FROM payer_prices
        ),
        dollar_range AS (
            SELECT service, hospital, min(dollar) AS lo, max(dollar) AS hi
            FROM payer_prices GROUP BY ALL
        ),
        item_rows AS (
            SELECT i.service, i.hospital, i.setting, NULL::VARCHAR AS payer, NULL::VARCHAR AS plan,
                   NULL::DOUBLE AS rate, NULL::VARCHAR AS rate_basis, NULL::DOUBLE AS pct,
                   NULL::VARCHAR AS algorithm, NULL::VARCHAR AS methodology,
                   i.gross, i.cash,
                   coalesce(i.min_reported, d.lo) AS min,
                   coalesce(i.max_reported, d.hi) AS max,
                   i.description
            FROM item_prices i LEFT JOIN dollar_range d USING (service, hospital)
        )
        SELECT * FROM item_rows
        UNION ALL BY NAME
        SELECT * FROM payer_rows
        """
    )

    # -- services index -------------------------------------------------------
    services = con.sql(
        """
        SELECT i.service,
               split_part(i.service, ':', 1) AS code_type,
               split_part(i.service, ':', 2) AS code,
               count(DISTINCT i.hospital) AS hospitals,
               count(i.cash) AS with_cash,
               median(i.cash) AS cash_median,
               min(i.cash) AS cash_min,
               max(i.cash) AS cash_max,
               (SELECT median(p.rate) FROM prices p
                 WHERE p.service = i.service AND p.payer IS NOT NULL) AS rate_median,
               mode(i.description) AS description
        FROM prices i
        WHERE i.payer IS NULL
        GROUP BY i.service
        HAVING count(DISTINCT i.hospital) >= ?
        ORDER BY hospitals DESC, service
        """,
        params=[min_hospitals],
    ).pl()
    keep = set(services["service"].to_list())
    con.register("keep_services", pl.DataFrame({"service": sorted(keep)}).to_arrow())

    service_rows = []
    for row in services.iter_rows(named=True):
        curated = BY_KEY.get(row["service"])
        label = curated.label if curated else (_title(row["description"]) or row["service"])
        service_rows.append(
            {
                "id": row["service"],
                "type": row["code_type"],
                "code": row["code"],
                "label": label,
                "category": category_for(row["code_type"], row["code"]),
                "keywords": list(curated.keywords) if curated else [],
                "curated": curated is not None,
                "hospitals": row["hospitals"],
                "with_cash": row["with_cash"],
                "cash": _stats(row["cash_median"], row["cash_min"], row["cash_max"]),
                "rate_median": _money(row["rate_median"]),
            }
        )
    service_rows.sort(key=lambda r: (not r["curated"], -r["hospitals"], r["label"]))

    # -- prices.parquet --------------------------------------------------------
    prices_path = out / "prices.parquet"
    tmp_prices = out / "prices.parquet.tmp"
    con.execute(
        f"""
        COPY (
            SELECT p.* FROM prices p SEMI JOIN keep_services k USING (service)
            ORDER BY service, hospital, payer NULLS FIRST, plan NULLS FIRST
        ) TO '{sql_path(tmp_prices)}'
        (FORMAT parquet, COMPRESSION snappy, ROW_GROUP_SIZE {int(row_group_size)})
        """
    )
    tmp_prices.replace(prices_path)
    price_rows = con.sql(
        f"SELECT count(*) FROM read_parquet('{sql_path(prices_path)}')"
    ).fetchall()[0][0]

    # -- payers -------------------------------------------------------------
    payers = con.sql(
        """
        SELECT payer AS name, count(DISTINCT hospital) AS hospitals,
               count(DISTINCT plan) AS plans
        FROM prices WHERE payer IS NOT NULL
        GROUP BY payer ORDER BY hospitals DESC, name
        """
    ).pl()

    # -- hospitals -------------------------------------------------------------
    per_hospital = con.sql(
        """
        SELECT hospital AS id,
               count(*) FILTER (WHERE payer IS NULL) AS services,
               count(*) FILTER (WHERE payer IS NULL AND cash IS NOT NULL) AS services_with_cash,
               count(DISTINCT payer) AS payers
        FROM prices GROUP BY hospital
        """
    ).pl()
    hospital_rows = _hospital_rows(hospitals, per_hospital)

    demo = (data.root / DEMO_MARKER).is_file()
    meta = {
        "name": "Pricelight",
        "schema_version": SITE_SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "demo": demo,
        "pipeline_version": __version__,
        "parser_version": parser_version,
        "counts": {
            "hospitals": len(hospital_rows),
            "services": len(service_rows),
            "payers": payers.height,
            "price_rows": int(price_rows),
            "states": len({h["state"] for h in hospital_rows if h["state"]}),
        },
        "build": dict(build_info or {}),
    }
    _write_json(out / "services.json", service_rows)
    _write_json(out / "payers.json", payers.to_dicts())
    _write_json(out / "hospitals.json", hospital_rows)
    _write_json(out / "meta.json", meta, indent=2)
    con.close()
    return BuildSummary(out, len(hospital_rows), len(service_rows), payers.height, int(price_rows))


def _money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _stats(median: float | None, lo: float | None, hi: float | None) -> dict[str, float] | None:
    if median is None:
        return None
    return {"median": _money(median), "min": _money(lo), "max": _money(hi)}  # type: ignore[dict-item]


def _hospital_rows(hospitals: pl.DataFrame, per_hospital: pl.DataFrame) -> list[dict[str, Any]]:
    joined = hospitals.join(per_hospital, on="id", how="left")
    rows = []
    for h in joined.iter_rows(named=True):
        issues = json.loads(h["issues_json"] or "[]")
        rows.append(
            {
                "id": h["id"],
                "name": h["name"],
                "address": h["address"],
                "city": h["city"],
                "state": h["state"],
                "zip": h["zip"],
                "lat": h["lat"],
                "lon": h["lon"],
                "website": h["website"] or None,
                "source_page_url": h["source_page_url"] or None,
                "mrf_url": h["mrf_url"] or None,
                "file": {
                    "name": h["mrf_file"],
                    "format": h["format"],
                    "compression": h["compression"] or None,
                    "bytes": h["file_bytes"],
                    "template_version": h["template_version"] or None,
                    "last_updated": h["last_updated_on"] or None,
                    "sha256": h["file_sha256"],
                },
                "services": h["services"] or 0,
                "services_with_cash": h["services_with_cash"] or 0,
                "payers": h["payers"] or 0,
                "quality": {
                    "attestation": h["attestation_confirmed"],
                    "errors": h["issue_errors"] or 0,
                    "warnings": h["issue_warnings"] or 0,
                    "issues": [
                        {
                            "code": i["code"],
                            "severity": i["severity"],
                            "message": i["message"],
                            "count": i["count"],
                        }
                        for i in issues[:8]
                    ],
                },
            }
        )
    return rows


def _write_json(path: Path, payload: Any, indent: int | None = None) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(
        payload, ensure_ascii=False, separators=None if indent else (",", ":"), indent=indent
    )
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(path)


def publish(site_dataset: Path, destination: Path) -> None:
    """Copy a built dataset into the web app's public folder."""
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("meta.json", "hospitals.json", "services.json", "payers.json", "prices.parquet"):
        shutil.copy2(site_dataset / name, destination / name)
