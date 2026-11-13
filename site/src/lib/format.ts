// SPDX-License-Identifier: AGPL-3.0-or-later

const whole = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});
const cents = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** "$1,240" for larger amounts, "$18.40" below $100. */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return Math.abs(value) < 100 ? cents.format(value) : whole.format(value);
}

/** Compact axis label: $0, $500, $1.5K, $12K, $1.2M. */
export function compactMoney(value: number): string {
  if (value === 0) return '$0';
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `$${trim(value / 1_000_000)}M`;
  if (abs >= 1_000) return `$${trim(value / 1_000)}K`;
  return `$${trim(value)}`;
}

function trim(n: number): string {
  return n >= 100
    ? n.toFixed(0)
    : n >= 10
      ? n.toFixed(1).replace(/\.0$/, '')
      : n.toFixed(2).replace(/\.?0+$/, '');
}

export function moneyRange(lo: number | null, hi: number | null): string {
  if (lo === null && hi === null) return '—';
  if (lo === null || hi === null || lo === hi) return money(lo ?? hi);
  return `${money(lo)}–${money(hi)}`;
}

export function percent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 10 ? 0 : 1)} ${units[i]}`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return 'unknown date';
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

export function median(values: number[]): number | null {
  const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  if (v.length === 0) return null;
  const mid = Math.floor(v.length / 2);
  return v.length % 2 ? v[mid]! : (v[mid - 1]! + v[mid]!) / 2;
}

export function quantile(values: number[], q: number): number | null {
  const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  if (v.length === 0) return null;
  const pos = (v.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return v[lo]! + (v[hi]! - v[lo]!) * (pos - lo);
}

const FORMAT_NAMES: Record<string, string> = {
  json: 'JSON',
  'csv-tall': 'CSV (tall)',
  'csv-wide': 'CSV (wide)',
};

export function formatName(format: string): string {
  return FORMAT_NAMES[format] ?? format;
}

const SETTING_NAMES: Record<string, string> = {
  inpatient: 'Inpatient',
  outpatient: 'Outpatient',
  both: 'Inpatient or outpatient',
};

export function settingName(setting: string | null): string {
  return setting ? (SETTING_NAMES[setting] ?? setting) : 'Setting not listed';
}

export function methodologyName(m: string | null): string {
  if (!m) return '';
  return m.charAt(0).toUpperCase() + m.slice(1);
}
