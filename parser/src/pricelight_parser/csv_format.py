# SPDX-License-Identifier: Apache-2.0
"""Streaming parser for the CMS CSV templates ("tall" and "wide").

Both layouts share the same first three rows:

1. general data element *names* (``hospital_name``, ``license_number|CA``, ...)
2. their *values*
3. the column headers of the standard charge table

In the tall layout each row is one payer/plan. In the wide layout every
payer/plan gets its own block of columns
(``standard_charge|<payer>|<plan>|negotiated_dollar``, ...), which we unpivot
into tall rows. Files are read row by row with :mod:`csv`, so memory use is
bounded by the longest row, not the file size.
"""

from __future__ import annotations

import csv
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .base import BaseParser, template_major_version
from .json_format import check_payer_row
from .models import ChargeRow, MRFFormat
from .normalize import (
    IssueLog,
    clean_str,
    make_codes,
    normalize_methodology,
    normalize_setting,
    parse_bool,
    parse_date,
    parse_number,
    primary_code,
    split_modifiers,
    split_multi,
)
from .sources import UnsupportedFileError, normalize_header

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

_ATTESTATION_PREFIX = "to the best of its knowledge"

_ITEM_COLUMNS = {
    "description": "description",
    "setting": "setting",
    "modifiers": "modifiers",
    "billing_class": "billing_class",
    "drug_unit_of_measurement": "drug_unit",
    "drug_type_of_measurement": "drug_type",
    "standard_charge|gross": "gross_charge",
    "standard_charge|discounted_cash": "discounted_cash",
    "standard_charge|min": "min_negotiated",
    "standard_charge|max": "max_negotiated",
    "additional_generic_notes": "additional_generic_notes",
}

_TALL_PAYER_COLUMNS = {
    "payer_name": "payer_name",
    "plan_name": "plan_name",
    "standard_charge|negotiated_dollar": "negotiated_dollar",
    "standard_charge|negotiated_percentage": "negotiated_percentage",
    "standard_charge|negotiated_algorithm": "negotiated_algorithm",
    "standard_charge|methodology": "methodology",
    "estimated_amount": "estimated_amount",
    "median_amount": "median_amount",
    "10th_percentile": "p10_amount",
    "90th_percentile": "p90_amount",
    "count": "allowed_count",
    "additional_payer_notes": "additional_payer_notes",
}

#: Wide headers shaped ``standard_charge|<payer>|<plan>|<field>``.
_WIDE_SC_FIELDS = {
    "negotiated_dollar": "negotiated_dollar",
    "negotiated_percentage": "negotiated_percentage",
    "negotiated_algorithm": "negotiated_algorithm",
    "methodology": "methodology",
}
#: Wide headers shaped ``<field>|<payer>|<plan>``.
_WIDE_PREFIX_FIELDS = {
    "estimated_amount": "estimated_amount",
    "median_amount": "median_amount",
    "10th_percentile": "p10_amount",
    "90th_percentile": "p90_amount",
    "count": "allowed_count",
    "additional_payer_notes": "additional_payer_notes",
}

_NUMERIC_FIELDS = frozenset(
    {
        "drug_unit",
        "gross_charge",
        "discounted_cash",
        "min_negotiated",
        "max_negotiated",
        "negotiated_dollar",
        "negotiated_percentage",
        "estimated_amount",
        "median_amount",
        "p10_amount",
        "p90_amount",
    }
)


@dataclass(slots=True)
class PayerBlock:
    """Column indexes of one payer/plan in a wide file."""

    payer_name: str
    plan_name: str | None
    columns: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class ColumnMap:
    item: dict[str, int] = field(default_factory=dict)
    codes: list[tuple[int, int | None]] = field(default_factory=list)
    tall_payer: dict[str, int] = field(default_factory=dict)
    payer_blocks: list[PayerBlock] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    width: int = 0
    #: Cells that describe the item (everything except payer columns).
    item_indexes: tuple[int, ...] = ()


def parse_wide_header(cell: str) -> tuple[str, str, str | None] | None:
    """Split a wide payer column header into ``(field, payer, plan)``.

    Payer and plan names keep their original capitalization.

    >>> parse_wide_header("standard_charge | Aetna | PPO | negotiated_dollar")
    ('negotiated_dollar', 'Aetna', 'PPO')
    >>> parse_wide_header("median_amount|Cigna|Open Access")
    ('median_amount', 'Cigna', 'Open Access')
    """
    parts = [p.strip() for p in cell.split("|")]
    head = parts[0].lower()
    if head == "standard_charge" and len(parts) >= 3:
        tail = parts[-1].lower()
        if tail in _WIDE_SC_FIELDS:
            payer = parts[1]
            plan = "|".join(parts[2:-1]) or None
            return _WIDE_SC_FIELDS[tail], payer, plan
        return None
    if head in _WIDE_PREFIX_FIELDS and len(parts) >= 2:
        payer = parts[1]
        plan = "|".join(parts[2:]) or None
        return _WIDE_PREFIX_FIELDS[head], payer, plan
    return None


def build_column_map(header_row: list[str], fmt: MRFFormat, log: IssueLog) -> ColumnMap:
    cmap = ColumnMap(width=len(header_row))
    code_cols: dict[str, int] = {}
    code_type_cols: dict[str, int] = {}
    blocks: dict[tuple[str, str | None], PayerBlock] = {}
    seen: set[str] = set()
    for idx, raw in enumerate(header_row):
        name = normalize_header(raw)
        if not name:
            continue
        if name in seen:
            log.warn("duplicate-column", "A column header appears more than once.", where=raw)
            continue
        seen.add(name)
        if name in _ITEM_COLUMNS:
            cmap.item[_ITEM_COLUMNS[name]] = idx
            continue
        parts = name.split("|")
        if parts[0] == "code" and len(parts) in (2, 3):
            if len(parts) == 2:
                code_cols[parts[1]] = idx
            elif parts[2] == "type":
                code_type_cols[parts[1]] = idx
            continue
        if fmt is MRFFormat.CSV_TALL and name in _TALL_PAYER_COLUMNS:
            cmap.tall_payer[_TALL_PAYER_COLUMNS[name]] = idx
            continue
        if fmt is MRFFormat.CSV_WIDE:
            parsed = parse_wide_header(raw)
            if parsed is not None:
                fld, payer, plan = parsed
                block = blocks.get((payer, plan))
                if block is None:
                    block = PayerBlock(payer_name=payer, plan_name=plan)
                    blocks[(payer, plan)] = block
                block.columns[fld] = idx
                continue
        cmap.unknown.append(raw.strip())

    for key in sorted(code_cols, key=_code_sort_key):
        cmap.codes.append((code_cols[key], code_type_cols.get(key)))
    cmap.payer_blocks = list(blocks.values())
    item_idx = set(cmap.item.values())
    for code_idx, type_idx in cmap.codes:
        item_idx.add(code_idx)
        if type_idx is not None:
            item_idx.add(type_idx)
    cmap.item_indexes = tuple(sorted(item_idx))
    if "description" not in cmap.item:
        raise UnsupportedFileError("row 3 has no 'description' column")
    if "setting" not in cmap.item:
        log.error("missing-setting-column", "The CSV has no 'setting' column.")
    if not cmap.codes:
        log.warn("missing-code-columns", "The CSV has no code|N columns.")
    return cmap


def _code_sort_key(key: str) -> tuple[int, str]:
    return (int(key), key) if key.isdigit() else (1 << 30, key)


class CsvParser(BaseParser):
    def __init__(self, *args: Any, fmt: MRFFormat, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.format = fmt
        self.columns: ColumnMap | None = None
        self._last_item_key: tuple[str, ...] | None = None
        self._last_common: dict[str, Any] | None = None

    # -- header ---------------------------------------------------------

    def _read_general(self, names: list[str], values: list[str]) -> None:
        header = self.header
        log = self.log
        extra: dict[str, Any] = {}
        for idx, raw_name in enumerate(names):
            raw_value = values[idx] if idx < len(values) else ""
            name = normalize_header(raw_name)
            if not name:
                continue
            value = clean_str(raw_value)
            if name == "hospital_name":
                header.hospital_name = value
            elif name == "last_updated_on":
                header.last_updated_on = parse_date(value, log)
            elif name == "version":
                header.version = value
            elif name in ("location_name", "hospital_location"):
                header.location_names = split_multi(value)
            elif name == "hospital_address":
                header.addresses = split_multi(value)
            elif name == "type_2_npi":
                header.type_2_npis = split_multi(value)
            elif name.startswith("license_number"):
                header.license_number = value
                parts = name.split("|")
                if len(parts) > 1 and parts[1] and parts[1] != "[state]":
                    header.license_state = parts[1].upper()
            elif name == "attester_name":
                header.attester_name = value
            elif name.startswith(_ATTESTATION_PREFIX):
                header.attestation = raw_name.strip()
                header.attestation_confirmed = parse_bool(value)
                if value is not None and header.attestation_confirmed is None:
                    log.warn(
                        "invalid-attestation-value",
                        "The attestation value must be true or false.",
                        where=value,
                    )
            elif name == "financial_aid_policy":
                header.financial_aid_policy = value
            elif value is not None:
                extra[raw_name.strip()] = value
        header.extra = extra

    # -- rows -----------------------------------------------------------

    def _iter_rows(self) -> Iterator[ChargeRow]:
        with self.source.open_text() as fh:
            reader = csv.reader(fh)
            try:
                names = next(reader)
                values = next(reader)
                columns = next(reader)
            except StopIteration as exc:
                raise UnsupportedFileError("CSV has fewer than 3 header rows") from exc
            self._read_general(names, values)
            cmap = build_column_map(columns, self.format, self.log)
            self.columns = cmap
            if cmap.unknown:
                self.header.extra["unrecognized_columns"] = cmap.unknown[:50]
            major = template_major_version(self.header.version)
            v3 = major is not None and major >= 3
            line = 3
            for cells in reader:
                line += 1
                if not cells or all(not c.strip() for c in cells):
                    continue
                if len(cells) > cmap.width and any(c.strip() for c in cells[cmap.width :]):
                    self.log.warn(
                        "extra-cells",
                        "A row has more cells than there are column headers.",
                        where=f"row {line}",
                    )
                self.stats.items += 1
                yield from self._row(cells, cmap, line, v3)

    @staticmethod
    def _cell(cells: list[str], idx: int | None) -> str | None:
        if idx is None or idx >= len(cells):
            return None
        value = cells[idx]
        return clean_str(value) if value else None

    def _row(self, cells: list[str], cmap: ColumnMap, line: int, v3: bool) -> Iterator[ChargeRow]:
        # Tall files repeat the item columns on every payer row; parse them once.
        n = len(cells)
        key = tuple(cells[i] if i < n else "" for i in cmap.item_indexes)
        if key == self._last_item_key and self._last_common is not None:
            common = dict(self._last_common)
            common["item_index"] = line
            self.stats.items -= 1  # same item as the previous row
        else:
            common = self._common(cells, cmap, line)
            self._last_item_key = key
            self._last_common = common
        where = f"row {line}"
        if self.format is MRFFormat.CSV_TALL:
            yield from self._tall(cells, cmap, common, where, v3)
        else:
            yield from self._wide(cells, cmap, common, where, v3)

    def _common(self, cells: list[str], cmap: ColumnMap, line: int) -> dict[str, Any]:
        log = self.log
        where = f"row {line}"
        get = self._cell
        item = cmap.item

        def num(fld: str, idx: int | None) -> float | None:
            return parse_number(get(cells, idx), log, field_name=fld, where=where)

        description = get(cells, item.get("description"))
        if description is None:
            log.warn("missing-description", "An item has no description.", where=where)
        codes = make_codes(((get(cells, c), get(cells, t)) for c, t in cmap.codes), log)
        primary = primary_code(codes)
        drug_type = get(cells, item.get("drug_type"))
        drug_unit = num("drug unit", item.get("drug_unit"))
        if drug_unit is None and drug_type is None and any(c.type == "NDC" for c in codes):
            log.warn(
                "ndc-without-drug-information",
                "An NDC-coded item has no drug unit/type of measurement.",
                where=where,
            )
        billing_class = get(cells, item.get("billing_class"))
        common: dict[str, Any] = {
            "item_index": line,
            "description": description,
            "code": primary.code if primary else None,
            "code_type": primary.type if primary else None,
            "codes": codes,
            "setting": normalize_setting(get(cells, item.get("setting")), log),
            "billing_class": billing_class.lower() if billing_class else None,
            "modifiers": split_modifiers(get(cells, item.get("modifiers"))),
            "drug_unit": drug_unit,
            "drug_type": drug_type.upper() if drug_type else None,
            "gross_charge": num("gross", item.get("gross_charge")),
            "discounted_cash": num("discounted cash", item.get("discounted_cash")),
            "min_negotiated": num("min", item.get("min_negotiated")),
            "max_negotiated": num("max", item.get("max_negotiated")),
            "additional_generic_notes": get(cells, item.get("additional_generic_notes")),
        }
        return common

    def _payer_values(
        self, cells: list[str], columns: dict[str, int], where: str
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for fld, idx in columns.items():
            raw = self._cell(cells, idx)
            if raw is None:
                continue
            if fld in _NUMERIC_FIELDS:
                value = parse_number(raw, self.log, field_name=fld, where=where)
                if value is not None:
                    out[fld] = value
            elif fld == "methodology":
                out[fld] = normalize_methodology(raw, self.log)
            else:
                out[fld] = raw
        return out

    def _tall(
        self, cells: list[str], cmap: ColumnMap, common: dict[str, Any], where: str, v3: bool
    ) -> Iterator[ChargeRow]:
        values = self._payer_values(cells, cmap.tall_payer, where)
        has_payer_charge = any(
            k in values
            for k in ("negotiated_dollar", "negotiated_percentage", "negotiated_algorithm")
        )
        if "payer_name" not in values and not has_payer_charge:
            # Item-level row (gross/cash only). Notes columns may still be set.
            values.pop("plan_name", None)
            values.pop("methodology", None)
            extra_notes = values.pop("additional_payer_notes", None)
            row = ChargeRow(**common)
            if extra_notes and not row.additional_generic_notes:
                row.additional_generic_notes = extra_notes
            self._check_item(row, where)
            yield row
            return
        row = ChargeRow(**common, **values)
        check_payer_row(row, self.log, where=where, v3=v3)
        self._check_min_max(row, where)
        yield row

    def _wide(
        self, cells: list[str], cmap: ColumnMap, common: dict[str, Any], where: str, v3: bool
    ) -> Iterator[ChargeRow]:
        emitted = False
        for block in cmap.payer_blocks:
            values = self._payer_values(cells, block.columns, where)
            if not values:
                continue
            charge_keys = ("negotiated_dollar", "negotiated_percentage", "negotiated_algorithm")
            if not any(k in values for k in charge_keys) and set(values) <= {
                "methodology",
                "additional_payer_notes",
            }:
                # A methodology without a charge is noise from a template
                # export; report it but do not invent a payer row.
                self.log.warn(
                    "payer-without-charge",
                    "A payer column block has notes/methodology but no charge.",
                    where=where,
                )
                continue
            row = ChargeRow(
                **common, payer_name=block.payer_name, plan_name=block.plan_name, **values
            )
            check_payer_row(row, self.log, where=where, v3=v3)
            self._check_min_max(row, where)
            emitted = True
            yield row
        if not emitted:
            row = ChargeRow(**common)
            self._check_item(row, where)
            yield row

    def _check_item(self, row: ChargeRow, where: str) -> None:
        if row.gross_charge is None and row.discounted_cash is None:
            self.log.error(
                "no-charge-values",
                "An item has no gross charge, cash price or payer-specific charge.",
                where=where,
            )

    def _check_min_max(self, row: ChargeRow, where: str) -> None:
        if row.negotiated_dollar is not None and (
            row.min_negotiated is None or row.max_negotiated is None
        ):
            self.log.warn(
                "missing-min-max",
                "Negotiated dollar amounts are listed but the de-identified min/max is missing.",
                where=where,
            )
