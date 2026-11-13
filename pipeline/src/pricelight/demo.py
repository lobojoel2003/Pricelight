# SPDX-License-Identifier: AGPL-3.0-or-later
"""Synthetic demo dataset.

Generates *fictional* hospitals in real US cities, each publishing a
machine-readable file in one of the CMS layouts (JSON v3, CSV tall v3, CSV
wide v3, plus a few legacy v2 files and compressed archives). Prices follow
a plausible model -- a reference payment scaled by a regional cost index,
per-payer contract leverage and chargemaster markup -- but **none of the
numbers are real**. The demo exists so the whole pipeline and the web app
can be exercised end to end without downloading gigabytes of real files.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import math
import random
import zipfile
import zlib
from dataclasses import dataclass, field
from typing import Any

from .catalog import SERVICES, Service
from .manifest import DataDir, HospitalEntry, slugify, write_manifest

ATTESTATION_V3 = (
    "To the best of its knowledge and belief, this hospital has included all applicable "
    "standard charge information in accordance with the requirements of 45 CFR 180.50, and "
    "the information encoded is true, accurate, and complete as of the date in the file. This "
    "hospital has included all payer-specific negotiated charges in dollars that can be "
    "expressed as a dollar amount. For payer-specific negotiated charges that cannot be "
    "expressed as a dollar amount in the machine-readable file or not knowable in advance, the "
    "hospital attests that the payer-specific negotiated charge is based on a contractual "
    "algorithm, percentage or formula that precludes the provision of a dollar amount and has "
    "provided all necessary information available to the hospital for the public to be able to "
    "derive the dollar amount, including, but not limited to, the specific fee schedule or "
    "components referenced in such percentage, algorithm or formula."
)
ATTESTATION_V2 = (
    "To the best of its knowledge and belief, the hospital has included all applicable standard "
    "charge information in accordance with the requirements of 45 CFR 180.50, and the "
    "information encoded is true, accurate, and complete as of the date indicated."
)

# (city, state, zip, lat, lon, regional cost index)
CITIES: tuple[tuple[str, str, str, float, float, float], ...] = (
    ("Seattle", "WA", "98104", 47.6062, -122.3321, 1.22),
    ("Spokane", "WA", "99201", 47.6588, -117.4260, 1.02),
    ("Portland", "OR", "97205", 45.5152, -122.6784, 1.15),
    ("San Francisco", "CA", "94110", 37.7749, -122.4194, 1.45),
    ("Sacramento", "CA", "95814", 38.5816, -121.4944, 1.28),
    ("Los Angeles", "CA", "90012", 34.0522, -118.2437, 1.35),
    ("San Diego", "CA", "92101", 32.7157, -117.1611, 1.27),
    ("Las Vegas", "NV", "89101", 36.1699, -115.1398, 1.05),
    ("Phoenix", "AZ", "85004", 33.4484, -112.0740, 1.00),
    ("Tucson", "AZ", "85701", 32.2226, -110.9747, 0.95),
    ("Salt Lake City", "UT", "84111", 40.7608, -111.8910, 0.98),
    ("Boise", "ID", "83702", 43.6150, -116.2023, 0.97),
    ("Denver", "CO", "80202", 39.7392, -104.9903, 1.12),
    ("Albuquerque", "NM", "87102", 35.0844, -106.6504, 0.93),
    ("Billings", "MT", "59101", 45.7833, -108.5007, 1.04),
    ("Fargo", "ND", "58102", 46.8772, -96.7898, 0.99),
    ("Omaha", "NE", "68102", 41.2565, -95.9345, 0.94),
    ("Minneapolis", "MN", "55401", 44.9778, -93.2650, 1.08),
    ("Kansas City", "MO", "64106", 39.0997, -94.5786, 0.93),
    ("St. Louis", "MO", "63101", 38.6270, -90.1994, 0.95),
    ("Oklahoma City", "OK", "73102", 35.4676, -97.5164, 0.86),
    ("Dallas", "TX", "75201", 32.7767, -96.7970, 1.01),
    ("Houston", "TX", "77002", 29.7604, -95.3698, 1.03),
    ("Austin", "TX", "78701", 30.2672, -97.7431, 1.04),
    ("San Antonio", "TX", "78205", 29.4241, -98.4936, 0.94),
    ("New Orleans", "LA", "70112", 29.9511, -90.0715, 0.92),
    ("Memphis", "TN", "38103", 35.1495, -90.0490, 0.84),
    ("Nashville", "TN", "37203", 36.1627, -86.7816, 0.97),
    ("Chicago", "IL", "60611", 41.8781, -87.6298, 1.14),
    ("Milwaukee", "WI", "53202", 43.0389, -87.9065, 1.10),
    ("Detroit", "MI", "48201", 42.3314, -83.0458, 0.99),
    ("Indianapolis", "IN", "46202", 39.7684, -86.1581, 1.06),
    ("Columbus", "OH", "43215", 39.9612, -82.9988, 0.98),
    ("Cleveland", "OH", "44113", 41.4993, -81.6944, 0.97),
    ("Louisville", "KY", "40202", 38.2527, -85.7585, 0.90),
    ("Atlanta", "GA", "30303", 33.7490, -84.3880, 1.02),
    ("Birmingham", "AL", "35203", 33.5186, -86.8104, 0.83),
    ("Jackson", "MS", "39201", 32.2988, -90.1848, 0.80),
    ("Charlotte", "NC", "28202", 35.2271, -80.8431, 1.05),
    ("Raleigh", "NC", "27601", 35.7796, -78.6382, 1.03),
    ("Charleston", "SC", "29401", 32.7765, -79.9311, 0.96),
    ("Miami", "FL", "33130", 25.7617, -80.1918, 1.12),
    ("Orlando", "FL", "32801", 28.5383, -81.3792, 1.00),
    ("Tampa", "FL", "33602", 27.9506, -82.4572, 0.99),
    ("Jacksonville", "FL", "32202", 30.3322, -81.6557, 0.95),
    ("Richmond", "VA", "23219", 37.5407, -77.4360, 1.01),
    ("Washington", "DC", "20001", 38.9072, -77.0369, 1.24),
    ("Baltimore", "MD", "21201", 39.2904, -76.6122, 1.06),
    ("Philadelphia", "PA", "19107", 39.9526, -75.1652, 1.16),
    ("Pittsburgh", "PA", "15222", 40.4406, -79.9959, 1.00),
    ("New York", "NY", "10016", 40.7128, -74.0060, 1.48),
    ("Buffalo", "NY", "14203", 42.8864, -78.8784, 1.02),
    ("Boston", "MA", "02114", 42.3601, -71.0589, 1.40),
    ("Hartford", "CT", "06103", 41.7658, -72.6734, 1.25),
    ("Burlington", "VT", "05401", 44.4759, -73.2121, 1.13),
    ("Portland", "ME", "04101", 43.6591, -70.2568, 1.09),
    ("Anchorage", "AK", "99501", 61.2181, -149.9003, 1.60),
    ("Honolulu", "HI", "96813", 21.3069, -157.8583, 1.30),
)

_NAME_FIRST = (
    "Larkspur", "Copperleaf", "Bluefinch", "Thistledown", "Marigold", "Silverpine",
    "Wrenfield", "Amberline", "Juniperhill", "Foxglove", "Brightwater", "Quillstone",
    "Saffron Ridge", "Lanternfield", "Cinderoak", "Mossbrook", "Kestrel Point", "Ivyhaven",
    "Starling", "Hollowell", "Rosemallow", "Tidewell", "Granitebrook", "Ashgrove",
    "Meadowlark", "Driftwood", "Sunmere", "Elderglen", "Pebblecreek", "Oriole Bay",
)  # fmt: skip
_NAME_LAST = (
    "Medical Center", "Regional Hospital", "General Hospital", "Community Hospital",
    "Health Center", "University Hospital", "Memorial Hospital", "Regional Medical Center",
)  # fmt: skip
_STREETS = ("Larch", "Beacon", "Harbor", "Union", "Cedar", "Meridian", "Summit", "Grove", "Prairie")


@dataclass(frozen=True, slots=True)
class Payer:
    name: str
    multiplier: float
    plans: tuple[str, ...]
    #: Probability a hospital contracts with this payer.
    reach: float = 0.8
    #: Spellings used by different hospitals' files, to exercise normalization.
    spellings: tuple[str, ...] = ()
    percent_of_charges: bool = False


PAYERS: tuple[Payer, ...] = (
    Payer("Northwind Health", 2.05, ("PPO", "HMO"), 0.95, ("NORTHWIND HEALTH INC", "Northwind Health Plan")),
    Payer("Summitline Mutual", 2.35, ("Open Access", "EPO"), 0.85, ("SUMMITLINE MUTUAL",)),
    Payer("Evergreen Shield", 1.85, ("Choice PPO", "Value HMO"), 0.9, ("Evergreen Shield, LLC",)),
    Payer("Harborlight Health", 1.7, ("Commercial",), 0.7),
    Payer("Cobalt Care", 2.6, ("Premier PPO",), 0.6, ("COBALT CARE CORP",), percent_of_charges=True),
    Payer("Pinnacle Advantage", 1.06, ("Medicare Advantage HMO", "Medicare Advantage PPO"), 0.9),
    Payer("Lakeshore Medicaid Partners", 0.86, ("Medicaid Managed Care",), 0.75),
    Payer("Granite Benefit Trust", 2.15, ("Self-Funded",), 0.5),
    Payer("Bluebird Health Co-op", 1.78, ("Co-op PPO",), 0.55, ("BLUEBIRD HEALTH CO-OP",)),
    Payer("Coralline Health", 2.25, ("Gold PPO", "Silver HMO"), 0.6),
)  # fmt: skip


@dataclass(slots=True)
class DemoHospital:
    entry: HospitalEntry
    cost_index: float
    markup: float
    cash_ratio: float
    publishes_cash: bool
    payers: list[tuple[Payer, float]]
    layout: str
    compression: str | None
    services: list[Service] = field(default_factory=list)
    last_updated: str = "2026-01-01"
    license: str = ""
    npi: str = ""
    #: Realistic defects some files have (exercise the data-quality report).
    quirks: frozenset[str] = frozenset()


def _round(x: float) -> float:
    if x >= 1000:
        return float(round(x))
    return round(x, 2)


def _lognormal(rng: random.Random, sigma: float) -> float:
    return math.exp(rng.gauss(0.0, sigma))


def _npi(rng: random.Random) -> str:
    """A syntactically valid (Luhn) NPI for a fictional organization."""
    body = "1" + "".join(str(rng.randrange(10)) for _ in range(8))
    digits = [int(d) for d in "80840" + body]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    check = (10 - total % 10) % 10
    return body + str(check)


def plan_hospitals(n: int = 60, seed: int = 20260101) -> list[DemoHospital]:
    rng = random.Random(seed)
    names = [f"{a} {b}" for a in _NAME_FIRST for b in _NAME_LAST]
    rng.shuffle(names)
    cities = list(CITIES)
    # big metros get a second hospital when n exceeds the city count
    extra = [
        c for c in cities if c[5] >= 1.1 or c[0] in {"Houston", "Dallas", "Atlanta", "Chicago"}
    ]
    order = cities + extra
    hospitals: list[DemoHospital] = []
    used_ids: set[str] = set()
    layouts = (
        ["json-v3"] * 8 + ["csv-tall-v3"] * 6 + ["csv-wide-v3"] * 4 + ["json-v2", "csv-tall-v2"]
    )
    for i in range(n):
        city, state, zipcode, lat, lon, cost = order[i % len(order)]
        name = names[i % len(names)]
        hid = slugify(f"{name}-{city}")
        while hid in used_ids:
            hid += "-2"
        used_ids.add(hid)
        jitter = 0.06 if i >= len(cities) else 0.0
        street = f"{rng.randrange(100, 9900)} {rng.choice(_STREETS)} {rng.choice(['St', 'Ave', 'Blvd', 'Way', 'Dr'])}"
        entry = HospitalEntry(
            id=hid,
            name=name,
            address=f"{street}, {city}, {state} {zipcode}",
            city=city,
            state=state,
            zip=zipcode,
            lat=round(lat + rng.uniform(-jitter, jitter), 4),
            lon=round(lon + rng.uniform(-jitter, jitter), 4),
            website="",
        )
        payers = [(p, _lognormal(rng, 0.17)) for p in PAYERS if rng.random() < p.reach] or [
            (PAYERS[0], 1.0)
        ]
        layout = layouts[i % len(layouts)]
        compression = None
        roll = rng.random()
        if roll < 0.25:
            compression = "gzip"
        elif roll < 0.32:
            compression = "zip"
        h = DemoHospital(
            entry=entry,
            cost_index=cost * _lognormal(rng, 0.12),
            markup=rng.uniform(2.6, 5.4),
            cash_ratio=rng.uniform(0.32, 0.72),
            publishes_cash=rng.random() > 0.07,
            payers=payers,
            layout=layout,
            compression=compression,
            last_updated=f"2026-{rng.randrange(1, 11):02d}-{rng.randrange(1, 28):02d}",
            license=f"{state}-{rng.randrange(1000, 99999)}",
            npi=_npi(rng),
            quirks=_pick_quirks(rng),
        )
        small = "Community" in name or "Health Center" in name
        for s in SERVICES:
            if s.code_type == "MS-DRG" and small and rng.random() < 0.5:
                continue
            if rng.random() < 0.9:
                h.services.append(s)
        hospitals.append(h)
    return hospitals


QUIRKS = ("dollar-signs", "abbreviated-setting", "no-min-max", "no-npi", "unattested")


def _pick_quirks(rng: random.Random) -> frozenset[str]:
    if rng.random() > 0.3:
        return frozenset()
    weights = {
        "dollar-signs": 0.5,
        "abbreviated-setting": 0.5,
        "no-min-max": 0.4,
        "no-npi": 0.35,
        "unattested": 0.08,
    }
    picked = {q for q, w in weights.items() if rng.random() < w}
    return frozenset(picked or {"no-min-max"})


def _fmt_money(h: DemoHospital, value: float | None) -> str | float:
    if value is None:
        return ""
    if "dollar-signs" in h.quirks:
        return f"${value:,.2f}"
    return value


def _csv_setting(h: DemoHospital, setting: str) -> str:
    if "abbreviated-setting" in h.quirks:
        return {"outpatient": "OP", "inpatient": "IP"}.get(setting, setting)
    return setting


def _price_points(h: DemoHospital, s: Service, rng: random.Random) -> dict[str, Any]:
    reference = s.base * h.cost_index * _lognormal(rng, 0.08)
    gross = _round(reference * h.markup * _lognormal(rng, 0.1))
    cash = _round(gross * h.cash_ratio) if h.publishes_cash else None
    payer_rows = []
    for payer, leverage in h.payers:
        for j, plan in enumerate(payer.plans):
            amount = (
                reference * payer.multiplier * leverage * (1 + 0.04 * j) * _lognormal(rng, 0.05)
            )
            amount = min(amount, gross * 0.95)
            row: dict[str, Any] = {"payer": payer, "plan": plan}
            if payer.percent_of_charges and s.setting == "inpatient":
                pct = round(rng.uniform(42, 68), 1)
                row["percentage"] = pct
                row["allowed"] = _round(gross * pct / 100)
                row["methodology"] = "percent of total billed charges"
                row["count"] = str(rng.randrange(11, 240))
            else:
                row["dollar"] = _round(amount)
                row["methodology"] = "case rate" if s.code_type == "MS-DRG" else "fee schedule"
            payer_rows.append(row)
    dollars = [r["dollar"] for r in payer_rows if "dollar" in r]
    return {
        "gross": gross,
        "cash": cash,
        "min": min(dollars) if dollars else None,
        "max": max(dollars) if dollars else None,
        "payers": payer_rows,
    }


def _spelling(h: DemoHospital, payer: Payer) -> str:
    """Pick a stable spelling of a payer name for one hospital."""
    if not payer.spellings:
        return payer.name
    choices = (payer.name, *payer.spellings)
    return choices[sum(map(ord, h.entry.id + payer.name)) % len(choices)]


def _setting(s: Service, rng: random.Random) -> str:
    return s.setting if s.setting != "both" else rng.choice(["both", "outpatient"])


def _cdm(s: Service, i: int) -> str:
    return f"{zlib.crc32(s.key.encode()) % 9000 + 1000}{i:03d}"


def _json_document(h: DemoHospital, rng: random.Random, version: str) -> dict[str, Any]:
    v3 = version.startswith("3")
    items = []
    for i, s in enumerate(h.services):
        pts = _price_points(h, s, rng)
        payers = []
        for r in pts["payers"]:
            p: dict[str, Any] = {
                "payer_name": _spelling(h, r["payer"]),
                "plan_name": r["plan"],
                "methodology": r["methodology"],
            }
            if "dollar" in r:
                p["standard_charge_dollar"] = r["dollar"]
            if "percentage" in r:
                p["standard_charge_percentage"] = r["percentage"]
                if v3:
                    p["median_amount"] = r["allowed"]
                    p["10th_percentile"] = _round(r["allowed"] * 0.78)
                    p["90th_percentile"] = _round(r["allowed"] * 1.31)
                    p["count"] = r["count"]
                else:
                    p["estimated_amount"] = r["allowed"]
            payers.append(p)
        charge: dict[str, Any] = {"setting": _setting(s, rng), "gross_charge": pts["gross"]}
        if pts["cash"] is not None:
            charge["discounted_cash"] = pts["cash"]
        if pts["min"] is not None and "no-min-max" not in h.quirks:
            charge["minimum"] = pts["min"]
            charge["maximum"] = pts["max"]
        charge["payers_information"] = payers
        codes = [{"code": s.code, "type": s.code_type}, {"code": _cdm(s, i), "type": "CDM"}]
        items.append(
            {
                "description": _chargemaster_label(s),
                "code_information": codes,
                "standard_charges": [charge],
            }
        )
    doc: dict[str, Any] = {
        "hospital_name": h.entry.name,
        "last_updated_on": h.last_updated,
        "version": version,
    }
    if v3:
        doc["location_name"] = [h.entry.name]
        doc["hospital_address"] = [h.entry.address]
        doc["type_2_npi"] = [] if "no-npi" in h.quirks else [h.npi]
        doc["license_information"] = {"license_number": h.license, "state": h.entry.state}
        doc["attestation"] = {
            "attestation": ATTESTATION_V3,
            "confirm_attestation": "unattested" not in h.quirks,
            "attester_name": "Demo Attester",
        }
    else:
        doc["hospital_location"] = [h.entry.name]
        doc["hospital_address"] = [h.entry.address]
        doc["license_information"] = {"license_number": h.license, "state": h.entry.state}
        doc["affirmation"] = {"affirmation": ATTESTATION_V2, "confirm_affirmation": True}
    doc["standard_charge_information"] = items
    return doc


def _chargemaster_label(s: Service) -> str:
    """Mimic terse, upper-case chargemaster descriptions."""
    words = (
        s.label.upper()
        .replace(", WITHOUT", " W/O")
        .replace(", WITH", " W/")
        .replace(" AND ", " & ")
    )
    return words.replace("WITHOUT", "W/O").replace("WITH", "W/")[:60]


def _general_rows(h: DemoHospital, version: str) -> tuple[list[str], list[str]]:
    if version.startswith("3"):
        names = [
            "hospital_name", "last_updated_on", "version", "location_name", "hospital_address",
            f"license_number|{h.entry.state}", "type_2_npi", ATTESTATION_V3, "attester_name",
        ]  # fmt: skip
        values = [
            h.entry.name, h.last_updated, version, h.entry.name, h.entry.address,
            h.license, "" if "no-npi" in h.quirks else h.npi,
            "false" if "unattested" in h.quirks else "true", "Demo Attester",
        ]  # fmt: skip
    else:
        names = [
            "hospital_name", "last_updated_on", "version", "hospital_location", "hospital_address",
            f"license_number|{h.entry.state}", ATTESTATION_V2,
        ]  # fmt: skip
        month, day = h.last_updated[5:7], h.last_updated[8:10]
        values = [
            h.entry.name, f"{int(month)}/{int(day)}/{h.last_updated[:4]}", version, h.entry.name,
            h.entry.address, h.license, "true",
        ]  # fmt: skip
    return names, values


def _csv_tall(h: DemoHospital, rng: random.Random, version: str) -> str:
    v3 = version.startswith("3")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    names, values = _general_rows(h, version)
    w.writerow(names)
    w.writerow(values)
    header = [
        "description", "code|1", "code|1|type", "code|2", "code|2|type", "modifiers", "setting",
        "drug_unit_of_measurement", "drug_type_of_measurement", "standard_charge|gross",
        "standard_charge|discounted_cash", "payer_name", "plan_name",
        "standard_charge|negotiated_dollar", "standard_charge|negotiated_percentage",
        "standard_charge|negotiated_algorithm",
    ]  # fmt: skip
    header += (
        ["median_amount", "10th_percentile", "90th_percentile", "count"]
        if v3
        else ["estimated_amount"]
    )
    header += [
        "standard_charge|methodology",
        "standard_charge|min",
        "standard_charge|max",
        "additional_generic_notes",
    ]
    w.writerow(header)
    for i, s in enumerate(h.services):
        pts = _price_points(h, s, rng)
        setting = _setting(s, rng)
        base = [
            _chargemaster_label(s),
            s.code,
            s.code_type,
            _cdm(s, i),
            "CDM",
            "",
            _csv_setting(h, setting),
            "",
            "",
        ]
        money = [_fmt_money(h, pts["gross"]), _fmt_money(h, pts["cash"])]
        no_range = "no-min-max" in h.quirks
        tail_minmax = (
            ["", ""] if no_range else [_fmt_money(h, pts["min"]), _fmt_money(h, pts["max"])]
        )
        for r in pts["payers"]:
            row = [
                *base,
                *money,
                _spelling(h, r["payer"]),
                r["plan"],
                _fmt_money(h, r.get("dollar")),
                r.get("percentage", ""),
                "",
            ]
            if v3:
                if "allowed" in r:
                    row += [
                        r["allowed"],
                        _round(r["allowed"] * 0.78),
                        _round(r["allowed"] * 1.31),
                        r["count"],
                    ]
                else:
                    row += ["", "", "", ""]
            else:
                row += [r.get("allowed", "")]
            row += [r["methodology"], *tail_minmax, ""]
            w.writerow(row)
    return buf.getvalue()


def _csv_wide(h: DemoHospital, rng: random.Random, version: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    names, values = _general_rows(h, version)
    w.writerow(names)
    w.writerow(values)
    blocks = [(p, plan) for p, _ in h.payers for plan in p.plans]
    header = [
        "description", "code|1", "code|1|type", "code|2", "code|2|type", "modifiers", "setting",
        "drug_unit_of_measurement", "drug_type_of_measurement", "standard_charge|gross",
        "standard_charge|discounted_cash",
    ]  # fmt: skip
    fields = ("negotiated_dollar", "negotiated_percentage", "negotiated_algorithm")
    for p, plan in blocks:
        name = _spelling(h, p)
        header += [f"standard_charge|{name}|{plan}|{f}" for f in fields]
        header += [
            f"{f}|{name}|{plan}"
            for f in ("median_amount", "10th_percentile", "90th_percentile", "count")
        ]
        header += [
            f"standard_charge|{name}|{plan}|methodology",
            f"additional_payer_notes|{name}|{plan}",
        ]
    header += ["standard_charge|min", "standard_charge|max", "additional_generic_notes"]
    w.writerow(header)
    for i, s in enumerate(h.services):
        pts = _price_points(h, s, rng)
        setting = _csv_setting(h, _setting(s, rng))
        row: list[Any] = [
            _chargemaster_label(s),
            s.code,
            s.code_type,
            _cdm(s, i),
            "CDM",
            "",
            setting,
            "",
            "",
        ]
        row += [_fmt_money(h, pts["gross"]), _fmt_money(h, pts["cash"])]
        by_block = {(r["payer"].name, r["plan"]): r for r in pts["payers"]}
        for p, plan in blocks:
            r = by_block.get((p.name, plan))
            if r is None:
                row += [""] * 9
                continue
            row += [_fmt_money(h, r.get("dollar")), r.get("percentage", ""), ""]
            if "allowed" in r:
                row += [
                    r["allowed"],
                    _round(r["allowed"] * 0.78),
                    _round(r["allowed"] * 1.31),
                    r["count"],
                ]
            else:
                row += ["", "", "", ""]
            row += [r["methodology"], ""]
        if "no-min-max" in h.quirks:
            row += ["", "", ""]
        else:
            row += [_fmt_money(h, pts["min"]), _fmt_money(h, pts["max"]), ""]
        w.writerow(row)
    return buf.getvalue()


def _ein(h: DemoHospital) -> str:
    n = sum(ord(c) * (i + 1) for i, c in enumerate(h.entry.id)) % 10_000_000
    return f"99{n:07d}"


def render(h: DemoHospital, seed: int) -> tuple[str, bytes]:
    """Return (file name, bytes) of a hospital's MRF following CMS naming."""
    rng = random.Random(f"{seed}:{h.entry.id}")
    if h.layout.startswith("json"):
        version = "3.0.0" if h.layout.endswith("v3") else "2.0.0"
        data = json.dumps(_json_document(h, rng, version), separators=(",", ":")).encode()
        ext = "json"
    elif h.layout.startswith("csv-tall"):
        version = "3.0.0" if h.layout.endswith("v3") else "2.0.0"
        data = _csv_tall(h, rng, version).encode()
        ext = "csv"
    else:
        data = _csv_wide(h, rng, "3.0.0").encode()
        ext = "csv"
    name = f"{_ein(h)}_{h.entry.id}_standardcharges.{ext}"
    if h.compression == "gzip":
        return name + ".gz", gzip.compress(data, mtime=0)
    if h.compression == "zip":
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
        return name + ".zip", out.getvalue()
    return name, data


def generate(data_dir: DataDir, n: int = 60, seed: int = 20260101) -> list[HospitalEntry]:
    """Write a synthetic demo dataset (raw MRFs + manifest) into ``data_dir``."""
    hospitals = plan_hospitals(n, seed)
    entries = []
    for h in hospitals:
        name, payload = render(h, seed)
        folder = data_dir.raw_dir(h.entry.id)
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.iterdir():
            if old.is_file():
                old.unlink()
        (folder / name).write_bytes(payload)
        h.entry.mrf_path = str((folder / name).relative_to(data_dir.root))
        h.entry.mrf_url = ""
        entries.append(h.entry)
    write_manifest(data_dir.manifest, entries)
    (data_dir.root / "DEMO").write_text(
        "This data directory holds SYNTHETIC demo data generated by `pricelight demo`.\n"
        "Hospitals, payers and prices are fictional.\n",
        encoding="utf-8",
    )
    return entries
