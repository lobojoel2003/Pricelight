// SPDX-License-Identifier: AGPL-3.0-or-later
// Shared price axis and map color ramps.

import { scaleLinear, scaleSequential } from 'd3-scale';
import { interpolateRgbBasis } from 'd3-interpolate';
import { compactMoney, quantile } from './format';
import type { HospitalPrices, MapMetric } from './types';
import { metricValue } from './aggregate';

export interface PriceAxis {
  max: number;
  ticks: { value: number; label: string }[];
  x: (value: number) => number; // 0..1
}

/**
 * One axis for every hospital in the list, so bars are comparable at a
 * glance. The domain ends near the 95th percentile of the highest prices
 * shown (cash and insurer rates, not list prices) so one extreme outlier
 * doesn't squash everyone else; values beyond it are drawn clamped with an
 * overflow marker.
 */
export function priceAxis(results: HospitalPrices[], tickCount = 4): PriceAxis {
  const highs: number[] = [];
  for (const r of results) {
    const candidates = [r.cash, r.max, ...r.rates.map((x) => x.rate)].filter(
      (v): v is number => v !== null && Number.isFinite(v),
    );
    if (candidates.length) highs.push(Math.max(...candidates));
  }
  const p95 = quantile(highs, 0.95) ?? 100;
  const top = Math.max(p95 * 1.04, 1);
  const scale = scaleLinear().domain([0, top]).nice(tickCount);
  const max = scale.domain()[1]!;
  return {
    max,
    ticks: scale.ticks(tickCount).map((value) => ({ value, label: compactMoney(value) })),
    x: (value: number) => Math.max(0, Math.min(1, value / max)),
  };
}

// Sequential one-hue ramps (light -> dark on the light theme, reversed on
// dark). The hue follows the entity being mapped: orange = cash price,
// blue = insurer rates, matching the marks in the price-range bars.
const RAMPS = {
  cash: ['#feb79e', '#fb9671', '#f5723f', '#dd5b25', '#c44400', '#ac2c00', '#940b00'],
  insurer: ['#86b6ef', '#5598e7', '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#0d366b'],
};
const RAMPS_DARK = {
  cash: ['#7a2400', '#9c3300', '#c44400', '#dd5b25', '#f5723f', '#fb9671', '#feb79e'],
  insurer: ['#184f95', '#1c5cab', '#256abf', '#2a78d6', '#3987e5', '#6da7ec', '#9ec5f4'],
};

export function rampFor(metric: MapMetric, dark: boolean): string[] {
  const set = dark ? RAMPS_DARK : RAMPS;
  return metric === 'cash' ? set.cash : set.insurer;
}

export interface ColorScale {
  color: (value: number | null) => string | null;
  domain: [number, number];
  stops: string[];
}

export function mapColorScale(
  results: HospitalPrices[],
  metric: MapMetric,
  dark: boolean,
): ColorScale {
  const values = results
    .map((r) => metricValue(r, metric))
    .filter((v): v is number => v !== null && Number.isFinite(v));
  const lo = quantile(values, 0.05) ?? 0;
  let hi = quantile(values, 0.95) ?? 1;
  if (hi <= lo) hi = lo + 1;
  const stops = rampFor(metric, dark);
  const seq = scaleSequential(interpolateRgbBasis(stops)).domain([lo, hi]).clamp(true);
  return {
    color: (v) => (v === null || !Number.isFinite(v) ? null : seq(v)),
    domain: [lo, hi],
    stops,
  };
}
