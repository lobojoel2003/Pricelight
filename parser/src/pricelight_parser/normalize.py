# SPDX-License-Identifier: Apache-2.0
"""Value cleaning shared by the JSON and CSV parsers.

Real-world MRFs are messy: dollar signs in numeric columns, ``N/A`` instead
of blanks, ``MSDRG`` instead of ``MS-DRG``, dates as ``7/1/2024``. These
helpers make values comparable across hospitals while recording what was
wrong in an :class:`IssueLog` instead of silently dropping it.
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from collections.abc import Iterable, Sequence

from .models import Code, Issue, Severity

# ---------------------------------------------------------------------------
# Issue log
# ---------------------------------------------------------------------------


class IssueLog:
    """Collects issues, merging repeats so huge files stay cheap to report."""

    def __init__(self, max_examples: int = 5) -> None:
        self._issues: dict[str, Issue] = {}
        self._max_examples = max_examples

    def add(
        self,
        code: str,
        message: str,
        *,
        severity: Severity = Severity.WARNING,
        where: str | None = None,
    ) -> None:
        issue = self._issues.get(code)
        if issue is None:
            issue = Issue(code=code, severity=severity, message=message, count=0)
            self._issues[code] = issue
        issue.count += 1
        if where is not None and len(issue.examples) < self._max_examples:
            issue.examples.append(where)

    def error(self, code: str, message: str, where: str | None = None) -> None:
        self.add(code, message, severity=Severity.ERROR, where=where)

    def warn(self, code: str, message: str, where: str | None = None) -> None:
        self.add(code, message, severity=Severity.WARNING, where=where)

    @property
    def issues(self) -> list[Issue]:
        order = {Severity.ERROR: 0, Severity.WARNING: 1}
        return sorted(self._issues.values(), key=lambda i: (order[i.severity], -i.count, i.code))

    @property
    def has_errors(self) -> bool:
        return any(i.severity is Severity.ERROR for i in self._issues.values())

    def __len__(self) -> int:
        return len(self._issues)


# ---------------------------------------------------------------------------
# Scalars
# ---------------------------------------------------------------------------

_NULL_TOKENS = frozenset({"", "n/a", "na", "null", "none", "nan", "-", "--", "not applicable"})
_NUMBER_JUNK = re.compile(r"[\s$,]")


_MAX_NULL_TOKEN = max(len(t) for t in _NULL_TOKENS)


def clean_str(value: object) -> str | None:
    """Return a stripped string, or ``None`` for blanks and null tokens."""
    if not value:
        return None
    text = value if isinstance(value, str) else str(value)
    text = text.strip()
    if len(text) <= _MAX_NULL_TOKEN and text.lower() in _NULL_TOKENS:
        return None
    return text


def parse_number(
    value: object,
    log: IssueLog | None = None,
    *,
    field_name: str = "value",
    where: str | None = None,
) -> float | None:
    """Parse a numeric MRF value.

    Accepts ints/floats (JSON) and strings such as ``"1,234.50"`` or
    ``"$99"`` (CSV). Dollar signs and thousands separators are tolerated but
    logged, because the CMS templates require bare numbers.
    """
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and (fast := _fast_float(value)) is not None:
        number = fast
    else:
        text = str(value).strip()
        if text.lower() in _NULL_TOKENS:
            return None
        cleaned = _NUMBER_JUNK.sub("", text)
        if cleaned.endswith("%"):
            cleaned = cleaned[:-1]
        try:
            number = float(cleaned)
        except ValueError:
            if log is not None:
                log.warn(
                    "non-numeric-value",
                    f"A numeric field contained text that is not a number ({field_name}).",
                    where=where,
                )
            return None
        if cleaned != text and log is not None:
            log.warn(
                "formatted-number",
                "Numeric values contained '$', ',' or spaces; CMS requires bare numbers.",
                where=where,
            )
    if math.isnan(number) or math.isinf(number):
        return None
    if number <= 0 and log is not None:
        log.warn(
            "non-positive-number",
            "A price was zero or negative; CMS requires positive numbers.",
            where=where,
        )
    return number


def _fast_float(text: str) -> float | None:
    """``float()`` for the common case of a clean number; None if it needs cleanup."""
    try:
        return float(text)
    except ValueError:
        return None


_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%m-%d-%Y", "%Y%m%d")


def parse_date(value: object, log: IssueLog | None = None) -> str | None:
    """Normalize an MRF date to ISO 8601 (``YYYY-MM-DD``)."""
    text = clean_str(value)
    if text is None:
        return None
    candidate = text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}T", text) else text
    for fmt in _DATE_FORMATS:
        try:
            return _dt.datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            continue
    if log is not None:
        log.warn("invalid-date", "last_updated_on is not a recognizable date.", where=text)
    return text


def parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = clean_str(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {"true", "t", "yes", "y", "1"}:
        return True
    if lowered in {"false", "f", "no", "n", "0"}:
        return False
    return None


def split_multi(value: object, sep: str = "|") -> list[str]:
    """Split a pipe-delimited CSV cell (locations, addresses, NPIs)."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [s for s in (clean_str(v) for v in value) if s]
    text = clean_str(value)
    if text is None:
        return []
    return [part for part in (p.strip() for p in text.split(sep)) if part]


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

#: Code types accepted by the CMS templates (v2.x and v3.0).
VALID_CODE_TYPES = frozenset(
    {
        "CPT",
        "NDC",
        "HCPCS",
        "RC",
        "ICD",
        "DRG",
        "MS-DRG",
        "R-DRG",
        "S-DRG",
        "APS-DRG",
        "AP-DRG",
        "APR-DRG",
        "APC",
        "LOCAL",
        "EAPG",
        "HIPPS",
        "CDT",
        "CDM",
        "TRIS-DRG",
        "CMG",
        "MS-LTC-DRG",
    }
)

_CODE_TYPE_ALIASES = {
    "MSDRG": "MS-DRG",
    "MS DRG": "MS-DRG",
    "MS_DRG": "MS-DRG",
    "APRDRG": "APR-DRG",
    "APR DRG": "APR-DRG",
    "APR_DRG": "APR-DRG",
    "HCPC": "HCPCS",
    "HCPCS/CPT": "HCPCS",
    "CPT/HCPCS": "CPT",
    "CPT4": "CPT",
    "CPT-4": "CPT",
    "REV": "RC",
    "REV CODE": "RC",
    "REVENUE": "RC",
    "REVENUE CODE": "RC",
    "CHARGEMASTER": "CDM",
    "CHARGE CODE": "CDM",
    "ICD-10": "ICD",
    "ICD10": "ICD",
    "ICD-10-PCS": "ICD",
    "MSLTCDRG": "MS-LTC-DRG",
    "TRISDRG": "TRIS-DRG",
}

#: Which code is the "billing code" of an item when it lists several.
#: Grouping codes (DRGs) beat procedure codes, which beat internal codes.
CODE_PRIORITY: tuple[str, ...] = (
    "MS-DRG",
    "APR-DRG",
    "DRG",
    "AP-DRG",
    "APS-DRG",
    "R-DRG",
    "S-DRG",
    "TRIS-DRG",
    "MS-LTC-DRG",
    "CPT",
    "HCPCS",
    "CDT",
    "NDC",
    "APC",
    "EAPG",
    "HIPPS",
    "CMG",
    "ICD",
    "RC",
    "CDM",
    "LOCAL",
)
_PRIORITY_RANK = {t: i for i, t in enumerate(CODE_PRIORITY)}
_DRG_TYPES = frozenset(t for t in CODE_PRIORITY if t.endswith("DRG"))


def normalize_code_type(value: object, log: IssueLog | None = None) -> str | None:
    text = clean_str(value)
    if text is None:
        return None
    upper = text.upper()
    if upper in VALID_CODE_TYPES:
        return upper
    alias = _CODE_TYPE_ALIASES.get(upper)
    if alias is not None:
        if log is not None:
            log.warn(
                "nonstandard-code-type",
                "A code type was written in a non-standard way and was normalized.",
                where=text,
            )
        return alias
    if log is not None:
        log.warn("unknown-code-type", "A code type is not one of the CMS valid values.", where=text)
    return upper


def normalize_code(code: object, code_type: str | None) -> str | None:
    text = clean_str(code)
    if text is None:
        return None
    text = text.upper()
    if code_type in _DRG_TYPES:
        digits = re.sub(r"\D", "", text)
        if digits:
            return digits.lstrip("0").zfill(3)
        return text
    if code_type == "RC":
        digits = re.sub(r"\D", "", text)
        if digits and len(digits) <= 4:
            return digits.zfill(4)
    if code_type in {"CPT", "HCPCS"}:
        return text.replace(" ", "")
    return text


def make_codes(pairs: Iterable[tuple[object, object]], log: IssueLog | None = None) -> list[Code]:
    """Build a de-duplicated list of :class:`Code` from ``(code, type)`` pairs."""
    seen: set[tuple[str, str]] = set()
    out: list[Code] = []
    for raw_code, raw_type in pairs:
        code_type = normalize_code_type(raw_type, log)
        code = normalize_code(raw_code, code_type)
        if code is None:
            continue
        if code_type is None:
            code_type = "LOCAL"
            if log is not None:
                log.warn("missing-code-type", "A code was listed without a code type.")
        key = (code, code_type)
        if key in seen:
            continue
        seen.add(key)
        out.append(Code(code=code, type=code_type))
    return out


def primary_code(codes: Sequence[Code]) -> Code | None:
    """Pick the code most useful for cross-hospital comparison."""
    if not codes:
        return None
    return min(codes, key=lambda c: _PRIORITY_RANK.get(c.type, len(CODE_PRIORITY)))


_SETTINGS = {
    "inpatient": "inpatient",
    "outpatient": "outpatient",
    "both": "both",
    "ip": "inpatient",
    "i": "inpatient",
    "op": "outpatient",
    "o": "outpatient",
    "in patient": "inpatient",
    "out patient": "outpatient",
    "inpatient/outpatient": "both",
    "inpatient and outpatient": "both",
}


def normalize_setting(value: object, log: IssueLog | None = None) -> str | None:
    text = clean_str(value)
    if text is None:
        if log is not None:
            log.warn("missing-setting", "An item has no setting (inpatient/outpatient/both).")
        return None
    lowered = text.lower()
    setting = _SETTINGS.get(lowered)
    if setting is None:
        if log is not None:
            log.warn("invalid-setting", "Setting is not inpatient, outpatient or both.", where=text)
        return lowered
    if lowered not in {"inpatient", "outpatient", "both"} and log is not None:
        log.warn("nonstandard-setting", "Setting was abbreviated and was normalized.", where=text)
    return setting


VALID_METHODOLOGIES = frozenset(
    {"case rate", "fee schedule", "percent of total billed charges", "per diem", "other"}
)
_METHODOLOGY_ALIASES = {
    "case_rate": "case rate",
    "caserate": "case rate",
    "fee_schedule": "fee schedule",
    "feeschedule": "fee schedule",
    "percent of total billed charge": "percent of total billed charges",
    "percent_of_total_billed_charges": "percent of total billed charges",
    "percentage of total billed charges": "percent of total billed charges",
    "% of total billed charges": "percent of total billed charges",
    "per_diem": "per diem",
    "perdiem": "per diem",
}


def normalize_methodology(value: object, log: IssueLog | None = None) -> str | None:
    text = clean_str(value)
    if text is None:
        return None
    lowered = " ".join(text.lower().split())
    if lowered in VALID_METHODOLOGIES:
        return lowered
    alias = _METHODOLOGY_ALIASES.get(lowered)
    if alias is not None:
        return alias
    if log is not None:
        log.warn(
            "invalid-methodology",
            "Standard charge methodology is not one of the CMS valid values.",
            where=text,
        )
    return lowered


def split_modifiers(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [s.upper() for s in (clean_str(v) for v in value) if s]
    text = clean_str(value)
    if text is None:
        return []
    return [p.upper() for p in re.split(r"[|,;\s]+", text) if p]
