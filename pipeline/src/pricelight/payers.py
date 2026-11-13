# SPDX-License-Identifier: AGPL-3.0-or-later
"""Payer name normalization.

The same insurer appears under many spellings across (and within) hospital
files: ``AETNA``, ``Aetna Inc.``, ``Aetna Health of Texas``. To let people
compare "their insurer" across hospitals we fold spellings onto one display
name. Rules are deliberately conservative: unknown names are only cleaned
up (case, whitespace, corporate suffixes), never merged.
"""

from __future__ import annotations

import re
from functools import lru_cache

#: (pattern, canonical name). First match wins; patterns run on the cleaned,
#: upper-cased name.
FAMILY_RULES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), name)
    for pattern, name in (
        (r"\bAETNA\b", "Aetna"),
        (r"\bCIGNA\b", "Cigna"),
        (r"\b(UNITED ?HEALTH ?CARE|UHC|UNITEDHEALTH)\b", "UnitedHealthcare"),
        (r"\bHUMANA\b", "Humana"),
        (r"\bANTHEM\b", "Anthem"),
        (r"\bKAISER\b", "Kaiser Permanente"),
        (r"\b(BCBS|BLUE ?CROSS|BLUE ?SHIELD)\b", "Blue Cross Blue Shield"),
        (r"\bTRICARE\b", "TRICARE"),
        (r"\bMOLINA\b", "Molina Healthcare"),
        (r"\bCENTENE|AMBETTER\b", "Centene / Ambetter"),
        (r"\bOSCAR\b", "Oscar Health"),
        (r"\bMEDICARE ADVANTAGE\b", "Medicare Advantage (other)"),
        (r"^MEDICARE\b", "Medicare"),
        (r"^MEDICAID\b", "Medicaid"),
        # Fictional payers used by the synthetic demo dataset.
        (r"^NORTHWIND\b", "Northwind Health"),
        (r"^SUMMITLINE\b", "Summitline Mutual"),
        (r"^EVERGREEN SHIELD\b", "Evergreen Shield"),
        (r"^HARBORLIGHT\b", "Harborlight Health"),
        (r"^COBALT CARE\b", "Cobalt Care"),
        (r"^PINNACLE ADVANTAGE\b", "Pinnacle Advantage"),
        (r"^LAKESHORE MEDICAID\b", "Lakeshore Medicaid Partners"),
        (r"^GRANITE BENEFIT\b", "Granite Benefit Trust"),
        (r"^BLUEBIRD\b", "Bluebird Health Co-op"),
        (r"^CORALLINE\b", "Coralline Health"),
    )
)

_SUFFIXES = re.compile(
    r"[,\s]+(INC|INCORPORATED|LLC|L\.L\.C|CORP|CORPORATION|CO|COMPANY|LTD|PLC|LP)\.?$",
    re.IGNORECASE,
)
_SPACES = re.compile(r"\s+")
_SMALL_WORDS = frozenset({"of", "and", "the", "for", "in", "a"})
_ACRONYM = re.compile(r"^(HMO|PPO|EPO|POS|HSA|PPO/HMO|MA|USA|US|II|III|IV|[A-Z]{2})$")


def clean_payer_name(name: str) -> str:
    """Tidy capitalization, whitespace and corporate suffixes."""
    text = _SPACES.sub(" ", name.replace("\u00a0", " ")).strip(" ,.-")
    previous = None
    while previous != text:
        previous = text
        text = _SUFFIXES.sub("", text).strip(" ,.-")
    if text.isupper() and len(text) > 4:
        words = []
        for i, word in enumerate(text.split(" ")):
            if i and word.lower() in _SMALL_WORDS:
                words.append(word.lower())
            elif _ACRONYM.match(word):
                words.append(word)
            else:
                words.append(word.capitalize())
        text = " ".join(words)
    return text


@lru_cache(maxsize=65_536)
def normalize_payer(name: str | None) -> str | None:
    """Map a raw payer name to a display name used for cross-hospital comparison.

    >>> normalize_payer("AETNA HEALTH INC.")
    'Aetna'
    >>> normalize_payer("  united healthcare community plan ")
    'UnitedHealthcare'
    >>> normalize_payer("REGIONAL CARE NETWORK, LLC")
    'Regional Care Network'
    """
    if name is None:
        return None
    cleaned = clean_payer_name(name)
    if not cleaned:
        return None
    upper = cleaned.upper()
    for pattern, canonical in FAMILY_RULES:
        if pattern.search(upper):
            return canonical
    return cleaned
