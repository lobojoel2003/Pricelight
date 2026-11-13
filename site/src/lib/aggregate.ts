// SPDX-License-Identifier: AGPL-3.0-or-later
// Turn flat prices.parquet rows into one record per hospital.

import { median } from './format';
import type { Hospital, HospitalPrices, PayerRate, PriceRow, SortKey } from './types';

export function groupByHospital(
  rows: PriceRow[],
  hospitals: Map<string, Hospital>,
  payer: string | null,
): HospitalPrices[] {
  const byHospital = new Map<string, HospitalPrices>();
  for (const row of rows) {
    const hospital = hospitals.get(row.hospital);
    if (!hospital) continue;
    let entry = byHospital.get(row.hospital);
    if (!entry) {
      entry = {
        hospital,
        setting: row.setting,
        description: null,
        gross: null,
        cash: null,
        min: null,
        max: null,
        rates: [],
        rateMedian: null,
        payerRate: null,
      };
      byHospital.set(row.hospital, entry);
    }
    if (row.payer === null) {
      entry.description = row.description;
      entry.gross = row.gross;
      entry.cash = row.cash;
      entry.min = row.min;
      entry.max = row.max;
      entry.setting = row.setting ?? entry.setting;
    } else {
      const rate: PayerRate = {
        payer: row.payer,
        plan: row.plan,
        rate: row.rate,
        basis: row.rate_basis,
        pct: row.pct,
        algorithm: row.algorithm,
        methodology: row.methodology,
      };
      entry.rates.push(rate);
    }
  }
  for (const entry of byHospital.values()) {
    entry.rates.sort(
      (a, b) => (a.rate ?? Infinity) - (b.rate ?? Infinity) || a.payer.localeCompare(b.payer),
    );
    const values = entry.rates.map((r) => r.rate).filter((r): r is number => r !== null);
    entry.rateMedian = median(values);
    if (entry.min === null && values.length) entry.min = Math.min(...values);
    if (entry.max === null && values.length) entry.max = Math.max(...values);
    if (payer) {
      const mine = entry.rates
        .filter((r) => r.payer === payer && r.rate !== null)
        .map((r) => r.rate!);
      entry.payerRate = mine.length ? Math.min(...mine) : null;
    }
  }
  return [...byHospital.values()];
}

export function metricValue(
  h: HospitalPrices,
  key: SortKey | 'cash' | 'payer' | 'median',
): number | null {
  switch (key) {
    case 'cash':
      return h.cash;
    case 'payer':
      return h.payerRate;
    case 'median':
      return h.rateMedian;
    default:
      return null;
  }
}

/** Sort ascending by the chosen price; hospitals without that price go last. */
export function sortResults(results: HospitalPrices[], key: SortKey): HospitalPrices[] {
  const out = [...results];
  if (key === 'name') {
    return out.sort((a, b) => a.hospital.name.localeCompare(b.hospital.name));
  }
  return out.sort((a, b) => {
    const va = metricValue(a, key);
    const vb = metricValue(b, key);
    if (va === null && vb === null) return a.hospital.name.localeCompare(b.hospital.name);
    if (va === null) return 1;
    if (vb === null) return -1;
    return va - vb;
  });
}

export interface ResultFilters {
  state: string | null;
  payer: string | null;
  /** Only hospitals whose ids are in this set (e.g. visible on the map). */
  within: Set<string> | null;
}

export function filterResults(results: HospitalPrices[], f: ResultFilters): HospitalPrices[] {
  return results.filter((r) => {
    if (f.state && r.hospital.state !== f.state) return false;
    if (f.payer && !r.rates.some((x) => x.payer === f.payer)) return false;
    if (f.within && !f.within.has(r.hospital.id)) return false;
    return true;
  });
}

/** Where a value sits among peers: share of hospitals with a lower value (0..1). */
export function percentileRank(value: number, peers: number[]): number {
  const valid = peers.filter((p) => Number.isFinite(p));
  if (valid.length <= 1) return 0.5;
  const below = valid.filter((p) => p < value).length;
  const equal = valid.filter((p) => p === value).length;
  return (below + (equal - 1) / 2) / (valid.length - 1);
}
