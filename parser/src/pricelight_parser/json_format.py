# SPDX-License-Identifier: Apache-2.0
"""Streaming parser for the CMS JSON template (v2.x and v3.x).

Strategy
--------
The ``standard_charge_information`` array holds virtually all of a file's
bytes. We stream it with ijson's C backend (``ijson.items``), which builds
one item at a time at well over 100 MB/s, so memory stays flat no matter how
large the file is.

File-level metadata (hospital name, version, ...) is read by a short
pre-scan that stops as soon as the array begins. The CMS template puts
metadata first, but the JSON spec does not guarantee key order: if required
metadata is missing after the pre-scan, a second, event-level pass reads
whatever follows the array.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import ijson

from .base import BaseParser, template_major_version
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
)

_ITEMS_KEY = "standard_charge_information"
_ITEMS_PREFIX = f"{_ITEMS_KEY}.item"
_REQUIRED_META = ("hospital_name", "last_updated_on", "version")


class JsonParser(BaseParser):
    format = MRFFormat.JSON

    def __init__(self, *args: Any, full_metadata: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._full_metadata = full_metadata
        self._meta: dict[str, Any] = {}
        self._items_seen = False
        self._prescanned = False
        self._v3: bool | None = None

    # -- metadata -----------------------------------------------------------

    def prescan(self) -> None:
        """Read metadata that appears before the charge array."""
        if self._prescanned:
            return
        self._prescanned = True
        self._items_seen = self._scan_metadata(stop_at_items=True)
        self._apply_meta()

    def _scan_metadata(self, *, stop_at_items: bool) -> bool:
        """Collect top-level keys; returns True if the charge array exists."""
        found_items = False
        current: str | None = None
        builder: ijson.ObjectBuilder | None = None
        with self.source.open_binary() as fh:
            try:
                for prefix, event, value in ijson.parse(fh, use_float=True):
                    if prefix == "" and event == "map_key":
                        if current is not None and builder is not None:
                            self._meta.setdefault(current, builder.value)
                        current, builder = value, None
                        if value == _ITEMS_KEY:
                            found_items = True
                            if stop_at_items:
                                return True
                        else:
                            builder = ijson.ObjectBuilder()
                        continue
                    if prefix == "" and event in ("start_map", "end_map"):
                        if event == "end_map" and current is not None and builder is not None:
                            self._meta.setdefault(current, builder.value)
                            current, builder = None, None
                        continue
                    if builder is not None:
                        builder.event(event, value)
            except ijson.JSONError as exc:
                self.log.error("invalid-json", f"The file is not valid JSON: {exc}")
        return found_items

    def _apply_meta(self) -> None:
        meta = self._meta
        header = self.header
        log = self.log
        header.hospital_name = clean_str(meta.get("hospital_name"))
        header.last_updated_on = parse_date(meta.get("last_updated_on"), log)
        header.version = clean_str(meta.get("version"))
        locations = meta.get("location_name", meta.get("hospital_location"))
        header.location_names = _str_list(locations)
        header.addresses = _str_list(meta.get("hospital_address"))
        header.type_2_npis = _str_list(meta.get("type_2_npi"))
        lic = meta.get("license_information")
        if isinstance(lic, dict):
            header.license_number = clean_str(lic.get("license_number"))
            state = clean_str(lic.get("state"))
            header.license_state = state.upper() if state else None
        att = meta.get("attestation", meta.get("affirmation"))
        if isinstance(att, dict):
            header.attestation = clean_str(att.get("attestation", att.get("affirmation")))
            header.attestation_confirmed = parse_bool(
                att.get("confirm_attestation", att.get("confirm_affirmation"))
            )
            header.attester_name = clean_str(att.get("attester_name"))
        header.financial_aid_policy = clean_str(meta.get("financial_aid_policy"))
        mods = meta.get("modifier_information")
        if isinstance(mods, list):
            header.modifier_information = [m for m in mods if isinstance(m, dict)]
        known = {
            "hospital_name",
            "last_updated_on",
            "version",
            "location_name",
            "hospital_location",
            "hospital_address",
            "type_2_npi",
            "license_information",
            "attestation",
            "affirmation",
            "financial_aid_policy",
            "modifier_information",
        }
        header.extra = {k: v for k, v in meta.items() if k not in known and _is_small(v)}
        major = template_major_version(header.version)
        self._v3 = major is not None and major >= 3

    # -- rows ---------------------------------------------------------------

    def _iter_rows(self) -> Iterator[ChargeRow]:
        self.prescan()
        if self._items_seen:
            with self.source.open_binary() as fh:
                try:
                    for index, item in enumerate(ijson.items(fh, _ITEMS_PREFIX, use_float=True)):
                        self.stats.items += 1
                        if not isinstance(item, dict):
                            self.log.error(
                                "invalid-item",
                                "A standard_charge_information entry is not an object.",
                                where=f"item {index}",
                            )
                            continue
                        yield from self._item_rows(item, index)
                except ijson.JSONError as exc:
                    self.log.error(
                        "invalid-json",
                        f"The file is not valid JSON (stopped after {self.stats.items} items): {exc}",
                    )
        else:
            self.log.error(
                "missing-standard-charge-information",
                "The file has no standard_charge_information array.",
            )
        missing = any(not self._meta.get(k) for k in _REQUIRED_META)
        if self._items_seen and (missing or self._full_metadata):
            # Metadata may follow the charge array; read the rest of the file.
            self._scan_metadata(stop_at_items=False)
            self._apply_meta()

    def _item_rows(self, item: dict[str, Any], index: int) -> Iterator[ChargeRow]:
        log = self.log
        where = f"item {index}"
        description = clean_str(item.get("description"))
        if description is None:
            log.warn("missing-description", "An item has no description.", where=where)
        raw_codes = item.get("code_information") or []
        codes = make_codes(
            ((c.get("code"), c.get("type")) for c in raw_codes if isinstance(c, dict)), log
        )
        if not codes:
            log.warn("missing-code", "An item has no billing or accounting code.", where=where)
        primary = primary_code(codes)
        drug = item.get("drug_information")
        drug_unit = drug_type = None
        if isinstance(drug, dict):
            drug_unit = parse_number(drug.get("unit"), field_name="drug unit")
            drug_type = clean_str(drug.get("type"))
            drug_type = drug_type.upper() if drug_type else None
        elif any(c.type == "NDC" for c in codes):
            log.warn(
                "ndc-without-drug-information",
                "An NDC-coded item has no drug unit/type of measurement.",
                where=where,
            )

        charges = item.get("standard_charges")
        if not isinstance(charges, list) or not charges:
            log.error(
                "missing-standard-charges",
                "An item has no standard_charges entries.",
                where=where,
            )
            return

        for charge in charges:
            if not isinstance(charge, dict):
                continue
            gross = parse_number(charge.get("gross_charge"), log, field_name="gross", where=where)
            cash = parse_number(
                charge.get("discounted_cash"), log, field_name="discounted cash", where=where
            )
            minimum = parse_number(charge.get("minimum"), log, field_name="minimum", where=where)
            maximum = parse_number(charge.get("maximum"), log, field_name="maximum", where=where)
            setting = normalize_setting(charge.get("setting"), log)
            modifiers = split_modifiers(charge.get("modifier_code", charge.get("modifiers")))
            billing_class = clean_str(charge.get("billing_class"))
            generic_notes = clean_str(charge.get("additional_generic_notes"))
            payers = charge.get("payers_information") or []

            common = {
                "item_index": index,
                "description": description,
                "code": primary.code if primary else None,
                "code_type": primary.type if primary else None,
                "codes": codes,
                "setting": setting,
                "billing_class": billing_class.lower() if billing_class else None,
                "modifiers": modifiers,
                "drug_unit": drug_unit,
                "drug_type": drug_type,
                "gross_charge": gross,
                "discounted_cash": cash,
                "min_negotiated": minimum,
                "max_negotiated": maximum,
                "additional_generic_notes": generic_notes,
            }

            if not payers:
                if gross is None and cash is None:
                    log.error(
                        "no-charge-values",
                        "An item has no gross charge, cash price or payer-specific charge.",
                        where=where,
                    )
                yield ChargeRow(**common)  # type: ignore[arg-type]
                continue

            has_dollar = False
            for payer in payers:
                if not isinstance(payer, dict):
                    continue
                row = ChargeRow(
                    **common,  # type: ignore[arg-type]
                    payer_name=clean_str(payer.get("payer_name")),
                    plan_name=clean_str(payer.get("plan_name")),
                    negotiated_dollar=parse_number(
                        payer.get("standard_charge_dollar"),
                        log,
                        field_name="negotiated dollar",
                        where=where,
                    ),
                    negotiated_percentage=parse_number(
                        payer.get("standard_charge_percentage"),
                        log,
                        field_name="negotiated percentage",
                        where=where,
                    ),
                    negotiated_algorithm=clean_str(payer.get("standard_charge_algorithm")),
                    methodology=normalize_methodology(payer.get("methodology"), log),
                    estimated_amount=parse_number(
                        payer.get("estimated_amount"), log, field_name="estimated", where=where
                    ),
                    median_amount=parse_number(
                        payer.get("median_amount"), log, field_name="median", where=where
                    ),
                    p10_amount=parse_number(
                        payer.get("10th_percentile"), log, field_name="10th pct", where=where
                    ),
                    p90_amount=parse_number(
                        payer.get("90th_percentile"), log, field_name="90th pct", where=where
                    ),
                    allowed_count=clean_str(payer.get("count")),
                    additional_payer_notes=clean_str(payer.get("additional_payer_notes")),
                )
                check_payer_row(row, log, where=where, v3=bool(self._v3))
                has_dollar = has_dollar or row.negotiated_dollar is not None
                yield row
            if has_dollar and (minimum is None or maximum is None):
                log.warn(
                    "missing-min-max",
                    "Negotiated dollar amounts are listed but the de-identified min/max is missing.",
                    where=where,
                )


def check_payer_row(row: ChargeRow, log: IssueLog, *, where: str, v3: bool) -> None:
    """CMS conditional requirements that apply to one payer-specific charge."""
    if row.payer_name is None:
        log.warn("missing-payer-name", "A payer-specific charge has no payer name.", where=where)
    if (
        row.negotiated_dollar is None
        and row.negotiated_percentage is None
        and row.negotiated_algorithm is None
    ):
        log.error(
            "payer-without-charge",
            "A payer entry has no negotiated dollar amount, percentage or algorithm.",
            where=where,
        )
    if row.methodology is None:
        log.warn("missing-methodology", "A payer-specific charge has no methodology.", where=where)
    elif row.methodology == "other" and not (
        row.additional_payer_notes or row.additional_generic_notes
    ):
        log.warn(
            "other-methodology-without-notes",
            "Methodology 'other' requires an explanation in the notes.",
            where=where,
        )
    if v3 and (row.negotiated_percentage is not None or row.negotiated_algorithm is not None):
        if row.allowed_count is None:
            log.warn(
                "missing-allowed-count",
                "Percentage/algorithm charges require a count of allowed amounts (v3).",
                where=where,
            )
        elif row.allowed_count != "0" and row.median_amount is None:
            log.warn(
                "missing-allowed-amounts",
                "Percentage/algorithm charges require median/10th/90th allowed amounts (v3).",
                where=where,
            )


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = clean_str(value)
        return [text] if text else []
    if isinstance(value, list):
        return [s for s in (clean_str(v) for v in value if not isinstance(v, (dict, list))) if s]
    return []


def _is_small(value: Any, budget: int = 2000) -> bool:
    """Keep extra metadata only if it is small (we store it in Parquet metadata)."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return len(str(value)) <= budget
    if isinstance(value, (list, dict)):
        return len(repr(value)) <= budget
    return False
