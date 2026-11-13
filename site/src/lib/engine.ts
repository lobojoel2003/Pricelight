// SPDX-License-Identifier: AGPL-3.0-or-later
// Price lookups straight from prices.parquet, in the browser.
//
// prices.parquet is sorted by service and written in small row groups, so a
// lookup reads the file footer once and then fetches only the row groups
// whose min/max statistics can contain the requested service, using HTTP
// range requests against a static file. No server sees what anyone
// searches for, and nothing is requested from a third party.

import {
  asyncBufferFromUrl,
  cachedAsyncBuffer,
  parquetMetadataAsync,
  parquetReadObjects,
} from 'hyparquet';
import type { AsyncBuffer, FileMetaData } from 'hyparquet';
import type { PriceRow } from './types';

export class EngineError extends Error {}

export const PRICE_COLUMNS = [
  'service',
  'hospital',
  'setting',
  'payer',
  'plan',
  'rate',
  'rate_basis',
  'pct',
  'algorithm',
  'methodology',
  'gross',
  'cash',
  'min',
  'max',
  'description',
] as const;

export class PriceEngine {
  private file: AsyncBuffer | null = null;
  private metadata: FileMetaData | null = null;
  private ready: Promise<void> | null = null;
  private cache = new Map<string, PriceRow[]>();

  constructor(readonly parquetUrl: string) {}

  /** Read the Parquet footer; safe to call repeatedly. */
  init(): Promise<void> {
    this.ready ??= this.start().catch((err: unknown) => {
      this.ready = null;
      throw err instanceof EngineError ? err : new EngineError(describe(err));
    });
    return this.ready;
  }

  private async start(): Promise<void> {
    const file = cachedAsyncBuffer(await asyncBufferFromUrl({ url: this.parquetUrl }));
    this.metadata = await parquetMetadataAsync(file);
    this.file = file;
  }

  get rowCount(): number {
    return this.metadata ? Number(this.metadata.num_rows) : 0;
  }

  async pricesFor(service: string): Promise<PriceRow[]> {
    const hit = this.cache.get(service);
    if (hit) return hit;
    await this.init();
    const rows = await parquetReadObjects({
      file: this.file!,
      metadata: this.metadata!,
      columns: [...PRICE_COLUMNS],
      filter: { service: { $eq: service } },
    });
    const out = rows.map((r) => normalize(r));
    if (this.cache.size > 24) this.cache.delete(this.cache.keys().next().value!);
    this.cache.set(service, out);
    return out;
  }

  /** Every row of the file (used to load the SQL explorer). */
  async allRows(): Promise<Record<string, unknown>[]> {
    await this.init();
    return parquetReadObjects({
      file: this.file!,
      metadata: this.metadata!,
      columns: [...PRICE_COLUMNS],
    });
  }
}

function describe(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  return `Could not read the price file (${msg}).`;
}

function num(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const n = typeof value === 'bigint' ? Number(value) : Number(value);
  return Number.isFinite(n) ? n : null;
}

function str(value: unknown): string | null {
  return value === null || value === undefined ? null : String(value);
}

export function normalize(row: Record<string, unknown>): PriceRow {
  const basis = str(row.rate_basis);
  return {
    service: String(row.service),
    hospital: String(row.hospital),
    setting: str(row.setting),
    payer: str(row.payer),
    plan: str(row.plan),
    rate: num(row.rate),
    rate_basis: basis === 'dollar' || basis === 'allowed' ? basis : null,
    pct: num(row.pct),
    algorithm: str(row.algorithm),
    methodology: str(row.methodology),
    gross: num(row.gross),
    cash: num(row.cash),
    min: num(row.min),
    max: num(row.max),
    description: str(row.description),
  };
}
