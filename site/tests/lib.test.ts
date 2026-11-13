// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { filterResults, groupByHospital, percentileRank, sortResults } from '../src/lib/aggregate';
import { normalize } from '../src/lib/engine';
import { compactMoney, formatName, median, money, moneyRange, quantile } from '../src/lib/format';
import { mapColorScale, priceAxis } from '../src/lib/scale';
import { ServiceIndex, highlight, parseCode, tokenize } from '../src/lib/search';
import type { Hospital, PriceRow, Service } from '../src/lib/types';
import { readUrl, writeUrl } from '../src/lib/url';

function hospital(id: string, state = 'TX'): Hospital {
  return {
    id,
    name: `Hospital ${id}`,
    address: '',
    city: 'Austin',
    state,
    zip: '',
    lat: 30,
    lon: -97,
    website: null,
    source_page_url: null,
    mrf_url: null,
    file: {
      name: 'x',
      format: 'json',
      compression: null,
      bytes: 1,
      template_version: '3.0.0',
      last_updated: null,
      sha256: '',
    },
    services: 1,
    services_with_cash: 1,
    payers: 1,
    quality: { attestation: true, errors: 0, warnings: 0, issues: [] },
  };
}

function row(partial: Partial<PriceRow>): PriceRow {
  return {
    service: 'CPT:70553',
    hospital: 'a',
    setting: 'outpatient',
    payer: null,
    plan: null,
    rate: null,
    rate_basis: null,
    pct: null,
    algorithm: null,
    methodology: null,
    gross: null,
    cash: null,
    min: null,
    max: null,
    description: null,
    ...partial,
  };
}

function service(id: string, label: string, extra: Partial<Service> = {}): Service {
  const [type, code] = id.split(':') as [string, string];
  return {
    id,
    type,
    code,
    label,
    category: 'Imaging',
    keywords: [],
    curated: true,
    hospitals: 10,
    with_cash: 10,
    cash: null,
    rate_median: null,
    ...extra,
  };
}

describe('format', () => {
  it('formats money', () => {
    expect(money(1240)).toBe('$1,240');
    expect(money(18.4)).toBe('$18.40');
    expect(money(null)).toBe('—');
    expect(moneyRange(10, 10)).toBe('$10.00');
    expect(moneyRange(980, 3400)).toBe('$980–$3,400');
    expect(moneyRange(null, null)).toBe('—');
  });
  it('compacts axis labels', () => {
    expect(compactMoney(0)).toBe('$0');
    expect(compactMoney(500)).toBe('$500');
    expect(compactMoney(1500)).toBe('$1.5K');
    expect(compactMoney(12000)).toBe('$12K');
    expect(compactMoney(2_500_000)).toBe('$2.5M');
  });
  it('computes median and quantiles', () => {
    expect(median([3, 1, 2])).toBe(2);
    expect(median([1, 2, 3, 4])).toBe(2.5);
    expect(median([])).toBeNull();
    expect(quantile([0, 10], 0.5)).toBe(5);
    expect(formatName('csv-wide')).toBe('CSV (wide)');
  });
});

describe('search', () => {
  const index = new ServiceIndex([
    service('CPT:70553', 'MRI of the brain, without and with contrast', {
      keywords: ['mri', 'head'],
    }),
    service('CPT:70551', 'MRI of the brain, without contrast', {
      keywords: ['mri'],
      hospitals: 30,
    }),
    service('MS-DRG:470', 'Hip or knee replacement', {
      keywords: ['knee replacement'],
      category: 'Hospital stays',
    }),
    service('CPT:71046', 'Chest X-ray, 2 views', { keywords: ['xray', 'x-ray'] }),
    service('CPT:59510', 'Routine pregnancy care with cesarean delivery', {
      keywords: ['c-section'],
    }),
  ]);

  it('finds by words and requires every word', () => {
    expect(index.search('brain mri').map((s) => s.id)).toEqual(['CPT:70551', 'CPT:70553']);
    expect(index.search('knee')[0]!.id).toBe('MS-DRG:470');
    expect(index.search('knee brain')).toEqual([]);
  });
  it('handles synonyms, plurals and prefixes', () => {
    expect(index.search('xray')[0]!.id).toBe('CPT:71046');
    expect(index.search('c-section')[0]!.id).toBe('CPT:59510');
    expect(index.search('kne')[0]!.id).toBe('MS-DRG:470');
    expect(index.search('replacements')[0]!.id).toBe('MS-DRG:470');
  });
  it('finds codes', () => {
    expect(index.search('70553')[0]!.id).toBe('CPT:70553');
    expect(index.search('drg 470')[0]!.id).toBe('MS-DRG:470');
    expect(index.search('cpt 70553')[0]!.id).toBe('CPT:70553');
    expect(parseCode('ms-drg 0470')).toEqual({ type: 'ms-drg', code: '470' });
    expect(parseCode('mri')).toBeNull();
  });
  it('tokenizes and highlights', () => {
    expect(tokenize('How much for an MRI (brain)?')).toEqual(['mri', 'brain']);
    const parts = highlight('MRI of the brain', 'brain');
    expect(parts.filter((p) => p.match).map((p) => p.text)).toEqual(['brain']);
    expect(index.search('')).toEqual([]);
  });
});

describe('aggregate', () => {
  const hospitals = new Map([
    ['a', hospital('a')],
    ['b', hospital('b', 'CA')],
    ['c', hospital('c')],
  ]);
  const rows: PriceRow[] = [
    row({ hospital: 'a', cash: 900, gross: 4000, description: 'MRI BRN' }),
    row({ hospital: 'a', payer: 'Northwind', plan: 'PPO', rate: 1200, rate_basis: 'dollar' }),
    row({ hospital: 'a', payer: 'Northwind', plan: 'HMO', rate: 1100, rate_basis: 'dollar' }),
    row({ hospital: 'a', payer: 'Summit', plan: 'EPO', rate: 1500, rate_basis: 'dollar' }),
    row({ hospital: 'b', cash: 700, min: 600, max: 650 }),
    row({ hospital: 'b', payer: 'Summit', rate: 650, rate_basis: 'allowed', pct: 55 }),
    row({ hospital: 'c', cash: null }),
    row({ hospital: 'zzz', cash: 1 }),
  ];
  const grouped = groupByHospital(rows, hospitals, 'Northwind');

  it('groups rows per hospital and derives ranges', () => {
    expect(grouped).toHaveLength(3);
    const a = grouped.find((g) => g.hospital.id === 'a')!;
    expect(a.cash).toBe(900);
    expect(a.description).toBe('MRI BRN');
    expect(a.rates.map((r) => r.rate)).toEqual([1100, 1200, 1500]);
    expect(a.min).toBe(1100);
    expect(a.max).toBe(1500);
    expect(a.rateMedian).toBe(1200);
    expect(a.payerRate).toBe(1100);
    const b = grouped.find((g) => g.hospital.id === 'b')!;
    expect(b.min).toBe(600); // file-reported min wins
    expect(b.payerRate).toBeNull();
  });

  it('sorts with missing values last and filters', () => {
    expect(sortResults(grouped, 'cash').map((g) => g.hospital.id)).toEqual(['b', 'a', 'c']);
    expect(sortResults(grouped, 'payer').map((g) => g.hospital.id)).toEqual(['a', 'b', 'c']);
    expect(sortResults(grouped, 'name').map((g) => g.hospital.id)).toEqual(['a', 'b', 'c']);
    expect(filterResults(grouped, { state: 'CA', payer: null, within: null })).toHaveLength(1);
    expect(filterResults(grouped, { state: null, payer: 'Summit', within: null })).toHaveLength(2);
    expect(
      filterResults(grouped, { state: null, payer: null, within: new Set(['c']) }),
    ).toHaveLength(1);
  });

  it('ranks among peers', () => {
    expect(percentileRank(1, [1, 2, 3, 4, 5])).toBe(0);
    expect(percentileRank(5, [1, 2, 3, 4, 5])).toBe(1);
    expect(percentileRank(3, [1, 2, 3, 4, 5])).toBe(0.5);
    expect(percentileRank(3, [3])).toBe(0.5);
  });

  it('builds a shared axis and color scale', () => {
    const axis = priceAxis(grouped);
    expect(axis.max).toBeGreaterThanOrEqual(1500);
    expect(axis.ticks[0]!.label).toBe('$0');
    expect(axis.x(0)).toBe(0);
    expect(axis.x(axis.max * 2)).toBe(1); // clamped
    const scale = mapColorScale(grouped, 'cash', false);
    expect(scale.color(null)).toBeNull();
    expect(scale.color(800)).toMatch(/^rgb/);
    expect(scale.stops[0]).toBe('#feb79e');
    expect(mapColorScale(grouped, 'payer', true).stops[0]).toBe('#184f95');
  });
});

describe('url state', () => {
  it('round-trips', () => {
    const state = {
      service: 'CPT:70553',
      payer: 'Northwind Health',
      state: 'TX',
      sort: 'payer' as const,
      hospital: 'abc',
    };
    expect(readUrl(writeUrl(state))).toEqual(state);
    expect(
      writeUrl({ service: null, payer: null, state: null, sort: 'cash', hospital: null }),
    ).toBe('');
  });
  it('rejects junk', () => {
    expect(readUrl('?state=Texas&sort=evil')).toMatchObject({ state: null, sort: null });
    expect(readUrl('?state=tx').state).toBe('TX');
  });
});

describe('engine row normalization', () => {
  it('coerces bigint and nulls', () => {
    const r = normalize({
      service: 'CPT:1',
      hospital: 'h',
      rate: 5n,
      cash: undefined,
      rate_basis: 'weird',
    });
    expect(r.rate).toBe(5);
    expect(r.cash).toBeNull();
    expect(r.rate_basis).toBeNull();
    expect(r.payer).toBeNull();
  });
});
