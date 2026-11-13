// SPDX-License-Identifier: AGPL-3.0-or-later
// DuckDB-WASM for the SQL explorer, loaded only when someone opens it.
//
// The rows are handed to DuckDB as an Arrow table, so DuckDB never needs to
// download its Parquet extension from a third-party server.

import * as duckdb from '@duckdb/duckdb-wasm';
import ehWasm from '@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url';
import ehWorker from '@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url';
import { tableFromArrays } from 'apache-arrow';
import type { PriceEngine } from './engine';
import { PRICE_COLUMNS } from './engine';

const NUMERIC = new Set(['rate', 'pct', 'gross', 'cash', 'min', 'max']);

export interface SqlResult {
  columns: string[];
  rows: unknown[][];
}

export class SqlEngine {
  private conn: duckdb.AsyncDuckDBConnection | null = null;
  private ready: Promise<void> | null = null;

  constructor(private readonly prices: PriceEngine) {}

  init(): Promise<void> {
    this.ready ??= this.start().catch((err: unknown) => {
      this.ready = null;
      throw err;
    });
    return this.ready;
  }

  private async start(): Promise<void> {
    // Only the "exception handling" build is shipped (every browser since 2022).
    const features = await duckdb.getPlatformFeatures();
    if (!features.wasmExceptions) {
      throw new Error('This browser is too old to run DuckDB-WASM.');
    }
    const worker = new Worker(ehWorker);
    const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
    await db.instantiate(ehWasm);
    // Never fetch extensions from the network.
    await db.open({ query: { castBigIntToDouble: true } });
    const conn = await db.connect();
    await conn.query(`SET autoinstall_known_extensions = false`).catch(() => undefined);
    await conn.query(`SET autoload_known_extensions = false`).catch(() => undefined);

    const rows = await this.prices.allRows();
    const arrays: Record<string, unknown[] | Float64Array> = {};
    for (const col of PRICE_COLUMNS) {
      if (NUMERIC.has(col)) {
        arrays[col] = Float64Array.from(rows, (r) => {
          const v = r[col];
          return v === null || v === undefined ? NaN : Number(v);
        });
      } else {
        arrays[col] = rows.map((r) =>
          r[col] === null || r[col] === undefined ? null : String(r[col]),
        );
      }
    }
    const table = tableFromArrays(arrays as Parameters<typeof tableFromArrays>[0]);
    await conn.insertArrowTable(table, { name: 'prices_raw' });
    // NaN marks missing numbers in the Float64 arrays; expose them as NULL.
    const cols = PRICE_COLUMNS.map((c) =>
      NUMERIC.has(c) ? `CASE WHEN isnan(${c}) THEN NULL ELSE ${c} END AS ${c}` : c,
    );
    await conn.query(`CREATE VIEW prices AS SELECT ${cols.join(', ')} FROM prices_raw`);
    this.conn = conn;
  }

  async query(sql: string): Promise<SqlResult> {
    await this.init();
    const table = await this.conn!.query(sql);
    const columns = table.schema.fields.map((f) => f.name);
    const rows = table.toArray().map((r) => {
      const obj = r.toJSON() as Record<string, unknown>;
      return columns.map((c) => {
        const v = obj[c];
        return typeof v === 'bigint' ? Number(v) : v;
      });
    });
    return { columns, rows };
  }
}
