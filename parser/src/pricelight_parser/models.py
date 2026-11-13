# SPDX-License-Identifier: Apache-2.0
"""Normalized data model shared by every input format.

Every machine-readable file (MRF) — JSON, CSV "tall" or CSV "wide", CMS
template v2.x or v3.x — is flattened into the same *tall* shape: one
:class:`ChargeRow` per item/service x setting x payer/plan. Rows that carry
only item-level prices (gross charge, discounted cash, min/max) have
``payer_name`` set to ``None``.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field, fields
from typing import Any

#: Bump when the Parquet column layout changes in a backwards-incompatible way.
SCHEMA_VERSION = 1


class MRFFormat(str, enum.Enum):
    """The three layouts allowed by the CMS templates."""

    JSON = "json"
    CSV_TALL = "csv-tall"
    CSV_WIDE = "csv-wide"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass(slots=True)
class Code:
    """A billing or accounting code attached to an item or service."""

    code: str
    type: str


@dataclass(slots=True)
class ChargeRow:
    """One normalized standard charge.

    Item-level attributes (description, codes, gross/cash/min/max) are
    repeated on every payer row of the same item so each row can be read on
    its own, exactly like the CMS CSV "tall" layout.
    """

    item_index: int
    description: str | None = None
    code: str | None = None
    code_type: str | None = None
    codes: list[Code] = field(default_factory=list)
    setting: str | None = None
    billing_class: str | None = None
    modifiers: list[str] = field(default_factory=list)
    drug_unit: float | None = None
    drug_type: str | None = None
    gross_charge: float | None = None
    discounted_cash: float | None = None
    min_negotiated: float | None = None
    max_negotiated: float | None = None
    payer_name: str | None = None
    plan_name: str | None = None
    negotiated_dollar: float | None = None
    negotiated_percentage: float | None = None
    negotiated_algorithm: str | None = None
    methodology: str | None = None
    estimated_amount: float | None = None
    median_amount: float | None = None
    p10_amount: float | None = None
    p90_amount: float | None = None
    allowed_count: str | None = None
    additional_generic_notes: str | None = None
    additional_payer_notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def best_payer_amount(self) -> float | None:
        """Best available dollar figure for a payer row.

        Prefers the negotiated dollar amount, then the v3 median allowed
        amount, then the v2 estimated allowed amount.
        """
        for value in (self.negotiated_dollar, self.median_amount, self.estimated_amount):
            if value is not None:
                return value
        return None


#: Column order used for Parquet output and Arrow batches.
CHARGE_COLUMNS: tuple[str, ...] = tuple(f.name for f in fields(ChargeRow))


@dataclass(slots=True)
class HospitalHeader:
    """File-level metadata ("general data elements") of an MRF."""

    hospital_name: str | None = None
    last_updated_on: str | None = None
    version: str | None = None
    location_names: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    license_number: str | None = None
    license_state: str | None = None
    type_2_npis: list[str] = field(default_factory=list)
    attestation: str | None = None
    attestation_confirmed: bool | None = None
    attester_name: str | None = None
    financial_aid_policy: str | None = None
    modifier_information: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Severity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass(slots=True)
class Issue:
    """An aggregated data-quality finding.

    Identical findings are merged: ``count`` holds how many times the issue
    occurred and ``examples`` keeps the first few locations.
    """

    code: str
    severity: Severity
    message: str
    count: int = 1
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": str(self.severity),
            "message": self.message,
            "count": self.count,
            "examples": list(self.examples),
        }


@dataclass(slots=True)
class ParseStats:
    """Counters collected while streaming a file."""

    items: int = 0
    rows: int = 0
    payer_rows: int = 0
    rows_with_cash: int = 0
    rows_with_gross: int = 0
    rows_with_negotiated_dollar: int = 0
    payers: int = 0
    bytes_read: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)
