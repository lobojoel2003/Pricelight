# SPDX-License-Identifier: AGPL-3.0-or-later
"""Terminal reports: compliance summary and price lookups."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from .build import sql_path
from .manifest import DataDir


def quality_report(data: DataDir) -> dict[str, Any]:
    """Summarize file quality across hospitals (Polars over hospitals.parquet)."""
    df = pl.read_parquet(data.hospitals_table)
    ok = df.filter(pl.col("status") == "ok")
    issues: Counter[str] = Counter()
    for raw in ok["issues_json"].to_list():
        for issue in json.loads(raw or "[]"):
            issues[issue["code"]] += 1
    by_format = (
        ok.group_by("format").len().sort("len", descending=True).to_dicts() if ok.height else []
    )
    cash = (
        ok.select(
            (pl.col("rows_with_cash") > 0).sum().alias("with_cash"),
            pl.col("issue_errors").gt(0).sum().alias("with_errors"),
            pl.col("attestation_confirmed").fill_null(False).sum().alias("attested"),
        ).to_dicts()[0]
        if ok.height
        else {"with_cash": 0, "with_errors": 0, "attested": 0}
    )
    return {
        "hospitals": df.height,
        "parsed": ok.height,
        "failed": df.filter(pl.col("status") == "failed").height,
        "missing": df.filter(pl.col("status") == "missing").height,
        "formats": by_format,
        "with_cash_prices": cash["with_cash"],
        "with_errors": cash["with_errors"],
        "attested": cash["attested"],
        "most_common_issues": issues.most_common(10),
    }


def lookup(
    site_dir: Path,
    query: str,
    *,
    state: str | None = None,
    payer: str | None = None,
    limit: int = 25,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Find a service by code or words and list hospital prices, cheapest cash first."""
    services = json.loads((site_dir / "services.json").read_text("utf-8"))
    hospitals = {h["id"]: h for h in json.loads((site_dir / "hospitals.json").read_text("utf-8"))}
    q = query.strip().lower()
    match = next((s for s in services if s["code"].lower() == q or s["id"].lower() == q), None)
    if match is None:
        words = q.split()
        scored = [
            (sum(w in (s["label"] + " " + " ".join(s["keywords"])).lower() for w in words), s)
            for s in services
        ]
        scored = [x for x in scored if x[0] == len(words)]
        match = max(scored, key=lambda x: x[1]["hospitals"])[1] if scored else None
    if match is None:
        return None, []
    con = duckdb.connect()
    rows = con.sql(
        f"""
        WITH p AS (SELECT * FROM read_parquet('{sql_path(site_dir / "prices.parquet")}') WHERE service = ?)
        SELECT i.hospital, i.cash, i.gross, i.min, i.max,
               (SELECT median(rate) FROM p r WHERE r.hospital = i.hospital AND r.payer IS NOT NULL) AS median_rate,
               (SELECT min(rate) FROM p r WHERE r.hospital = i.hospital AND r.payer = ?) AS payer_rate
        FROM p i WHERE i.payer IS NULL
        """,
        params=[match["id"], payer],
    ).pl()
    out = []
    for r in rows.iter_rows(named=True):
        h = hospitals.get(r["hospital"], {})
        if state and h.get("state") != state.upper():
            continue
        if payer and r["payer_rate"] is None:
            continue
        out.append(
            {
                **r,
                "name": h.get("name", r["hospital"]),
                "city": h.get("city"),
                "state": h.get("state"),
            }
        )
    key = "payer_rate" if payer else "cash"
    out.sort(key=lambda r: (r[key] is None, r[key] or 0))
    return match, out[:limit]
