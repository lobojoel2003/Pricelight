# SPDX-License-Identifier: Apache-2.0
"""Shared parser plumbing: header validation, row statistics."""

from __future__ import annotations

import re
from collections.abc import Iterator

from .models import ChargeRow, HospitalHeader, Issue, MRFFormat, ParseStats
from .normalize import IssueLog
from .sources import Source

_MAX_TRACKED_PAYERS = 10_000


class BaseParser:
    """Common interface of the JSON and CSV parsers.

    Use :func:`pricelight_parser.open_mrf` rather than instantiating
    subclasses directly.
    """

    format: MRFFormat

    def __init__(self, source: Source, log: IssueLog | None = None) -> None:
        self.source = source
        self.log = log or IssueLog()
        self.header = HospitalHeader()
        self.stats = ParseStats()
        self._payers: set[str] = set()
        self._consumed = False

    # -- public API ---------------------------------------------------------

    def rows(self) -> Iterator[ChargeRow]:
        """Stream every normalized :class:`ChargeRow` in the file.

        Can only be iterated once per parser instance; header validation
        runs when the stream is exhausted.
        """
        if self._consumed:
            raise RuntimeError("rows() can only be consumed once; call open_mrf() again")
        self._consumed = True
        for row in self._iter_rows():
            self._count(row)
            yield row
        self._finish()

    @property
    def issues(self) -> list[Issue]:
        return self.log.issues

    # -- hooks for subclasses ----------------------------------------------

    def _iter_rows(self) -> Iterator[ChargeRow]:  # pragma: no cover - abstract
        raise NotImplementedError

    # -- helpers ------------------------------------------------------------

    def _count(self, row: ChargeRow) -> None:
        stats = self.stats
        stats.rows += 1
        if row.discounted_cash is not None:
            stats.rows_with_cash += 1
        if row.gross_charge is not None:
            stats.rows_with_gross += 1
        if row.payer_name is not None:
            stats.payer_rows += 1
            if row.negotiated_dollar is not None:
                stats.rows_with_negotiated_dollar += 1
            if len(self._payers) < _MAX_TRACKED_PAYERS:
                self._payers.add(row.payer_name.lower())

    def _finish(self) -> None:
        self.stats.payers = len(self._payers)
        reader = self.source.last_reader
        if reader is not None:
            self.stats.bytes_read = max(self.stats.bytes_read, reader.count)
        validate_header(self.header, self.log)
        if self.stats.rows and not self.stats.rows_with_cash:
            self.log.warn(
                "no-discounted-cash",
                "The file lists no discounted cash prices at all.",
            )
        if self.stats.rows == 0:
            self.log.error("no-charges", "The file contains no standard charges.")


_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?")


def template_major_version(version: str | None) -> int | None:
    if not version:
        return None
    match = _VERSION_RE.search(version)
    return int(match.group(1)) if match else None


def validate_header(header: HospitalHeader, log: IssueLog) -> None:
    """Check the CMS "general data elements" of a parsed file."""
    if not header.hospital_name:
        log.error("missing-hospital-name", "hospital_name is missing.")
    if not header.last_updated_on:
        log.error("missing-last-updated", "last_updated_on is missing.")
    if not header.version:
        log.error("missing-version", "The CMS template version is missing.")
    if not header.location_names:
        log.warn("missing-location-name", "No hospital location name is listed.")
    if not header.addresses:
        log.warn("missing-hospital-address", "No hospital address is listed.")
    if not header.license_state:
        log.warn("missing-license-state", "The hospital licensure state is missing.")
    if header.attestation_confirmed is None:
        log.error("missing-attestation", "The attestation (affirmation) statement is missing.")
    elif header.attestation_confirmed is False:
        log.warn("attestation-not-confirmed", "The hospital did not confirm the attestation.")
    major = template_major_version(header.version)
    if major is not None and major >= 3:
        if not header.type_2_npis:
            log.warn("missing-type-2-npi", "Template v3 requires Type 2 NPI(s).")
        if not header.attester_name:
            log.warn("missing-attester-name", "Template v3 requires the attester's name.")
