#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Benchmark the streaming parser on large synthetic files.

Writes a JSON and a CSV-tall MRF of roughly ``--size-mb`` each (streamed to
disk, never held in memory), converts both to Parquet and reports
throughput and peak memory.

    uv run python scripts/benchmark.py --size-mb 1000
"""

from __future__ import annotations

import argparse
import json
import random
import resource
import sys
import tempfile
import time
from pathlib import Path

from pricelight_parser import to_parquet

PAYERS = [f"Benchmark Payer {i}" for i in range(12)]


def _item(i: int, rng: random.Random) -> dict:
    gross = round(rng.uniform(50, 9000), 2)
    return {
        "description": f"BENCHMARK SERVICE {i}",
        "code_information": [
            {"code": str(10000 + i % 89999), "type": "CPT"},
            {"code": str(1000000 + i), "type": "CDM"},
        ],
        "standard_charges": [
            {
                "setting": "outpatient",
                "gross_charge": gross,
                "discounted_cash": round(gross * 0.5, 2),
                "minimum": round(gross * 0.2, 2),
                "maximum": round(gross * 0.6, 2),
                "payers_information": [
                    {
                        "payer_name": p,
                        "plan_name": "PPO",
                        "standard_charge_dollar": round(gross * rng.uniform(0.2, 0.6), 2),
                        "methodology": "fee schedule",
                    }
                    for p in PAYERS
                ],
            }
        ],
    }


def write_json(path: Path, size_mb: int, rng: random.Random) -> None:
    limit = size_mb * 1_000_000
    with path.open("w") as fh:
        fh.write('{"hospital_name":"Benchmark Hospital","last_updated_on":"2026-01-01",')
        fh.write('"version":"3.0.0","standard_charge_information":[')
        i = 0
        while fh.tell() < limit:
            if i:
                fh.write(",")
            fh.write(json.dumps(_item(i, rng), separators=(",", ":")))
            i += 1
        fh.write("]}")


def write_csv(path: Path, size_mb: int, rng: random.Random) -> None:
    limit = size_mb * 1_000_000
    with path.open("w") as fh:
        fh.write("hospital_name,last_updated_on,version\nBenchmark Hospital,2026-01-01,3.0.0\n")
        fh.write(
            "description,code|1,code|1|type,setting,standard_charge|gross,"
            "standard_charge|discounted_cash,payer_name,plan_name,"
            "standard_charge|negotiated_dollar,standard_charge|methodology,"
            "standard_charge|min,standard_charge|max\n"
        )
        i = 0
        while fh.tell() < limit:
            gross = round(rng.uniform(50, 9000), 2)
            for p in PAYERS:
                fh.write(
                    f"BENCHMARK SERVICE {i},{10000 + i % 89999},CPT,outpatient,{gross},"
                    f"{gross * 0.5:.2f},{p},PPO,{gross * rng.uniform(0.2, 0.6):.2f},"
                    f"fee schedule,{gross * 0.2:.2f},{gross * 0.6:.2f}\n"
                )
            i += 1


def run(path: Path) -> dict:
    size = path.stat().st_size
    started = time.perf_counter()
    result = to_parquet(path, path.with_suffix(".parquet"))
    elapsed = time.perf_counter() - started
    return {
        "file": path.name,
        "mb": round(size / 1e6, 1),
        "rows": result.stats.rows,
        "seconds": round(elapsed, 1),
        "mb_per_s": round(size / 1e6 / elapsed, 1),
        "rows_per_s": int(result.stats.rows / elapsed),
        "parquet_mb": round(path.with_suffix(".parquet").stat().st_size / 1e6, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--size-mb", type=int, default=200)
    ap.add_argument("--dir", default=None)
    args = ap.parse_args()
    rng = random.Random(1)
    with tempfile.TemporaryDirectory(dir=args.dir) as tmp:
        folder = Path(tmp)
        results = []
        for name, writer in (("bench.json", write_json), ("bench.csv", write_csv)):
            path = folder / name
            writer(path, args.size_mb, rng)
            results.append(run(path))
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    if sys.platform == "darwin":  # pragma: no cover - macOS reports bytes
        peak_mb /= 1024
    print(
        json.dumps(
            {"python": sys.version.split()[0], "peak_rss_mb": round(peak_mb), "results": results},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
