<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- For researchers and reporters: run SQL over the published dataset, in the browser. -->
<script lang="ts">
  import type { SqlEngine } from '../lib/sql';
  import type { AppState } from '../lib/state.svelte';

  let { app, open = $bindable(false) }: { app: AppState; open?: boolean } = $props();
  let dialog: HTMLDialogElement | undefined = $state();

  const EXAMPLES = [
    {
      label: 'Cash vs. insurer spread by service',
      sql: `SELECT service,
       count(*) FILTER (WHERE payer IS NULL)          AS hospitals,
       round(median(cash), 2)                          AS median_cash,
       round(median(rate) FILTER (WHERE payer IS NOT NULL), 2) AS median_insurer_rate
FROM prices
GROUP BY service
ORDER BY hospitals DESC
LIMIT 20`,
    },
    {
      label: 'Where is an MRI cheapest for cash?',
      sql: `SELECT hospital, cash, min, max
FROM prices
WHERE service = 'CPT:70553' AND payer IS NULL AND cash IS NOT NULL
ORDER BY cash
LIMIT 10`,
    },
    {
      label: 'Insurers with the widest rate range',
      sql: `SELECT payer, service,
       round(min(rate), 2) AS lowest, round(max(rate), 2) AS highest,
       round(max(rate) / min(rate), 1) AS ratio
FROM prices
WHERE payer IS NOT NULL AND rate > 0
GROUP BY payer, service
HAVING count(*) > 5
ORDER BY ratio DESC
LIMIT 15`,
    },
  ];

  let sql = $state(EXAMPLES[0]!.sql);
  let running = $state(false);
  let error = $state<string | null>(null);
  let result = $state.raw<{ columns: string[]; rows: unknown[][] } | null>(null);
  let elapsed = $state(0);
  let loading = $state(false);
  let engine: SqlEngine | null = null;

  async function getEngine(): Promise<SqlEngine> {
    if (!engine) {
      if (!app.engine) throw new Error('The dataset is not loaded yet.');
      const { SqlEngine } = await import('../lib/sql');
      engine = new SqlEngine(app.engine);
    }
    loading = true;
    try {
      await engine.init();
    } finally {
      loading = false;
    }
    return engine;
  }

  $effect(() => {
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  });

  async function run() {
    running = true;
    error = null;
    const t0 = performance.now();
    try {
      const r = await (await getEngine()).query(sql);
      result = { columns: r.columns, rows: r.rows.slice(0, 500) };
    } catch (err) {
      result = null;
      error = err instanceof Error ? err.message : String(err);
    } finally {
      elapsed = performance.now() - t0;
      running = false;
    }
  }

  function cell(v: unknown): string {
    if (v === null || v === undefined) return '∅';
    if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
    return String(v);
  }
</script>

<dialog bind:this={dialog} onclose={() => (open = false)} aria-labelledby="sql-title">
  <div class="body">
    <header>
      <h2 id="sql-title">Explore the data with SQL</h2>
      <button type="button" class="btn ghost" aria-label="Close" onclick={() => (open = false)}
        >✕</button
      >
    </header>
    <p class="muted">
      Queries run on your device with DuckDB-WASM against the table <code>prices</code> (columns: service,
      hospital, setting, payer, plan, rate, rate_basis, pct, algorithm, methodology, gross, cash, min,
      max, description). Item rows have no payer; payer rows carry each insurer's rate.
    </p>
    <div class="examples">
      {#each EXAMPLES as ex (ex.label)}
        <button type="button" class="chip" onclick={() => (sql = ex.sql)}>{ex.label}</button>
      {/each}
    </div>
    <label for="sql-input" class="visually-hidden">SQL query</label>
    <textarea
      id="sql-input"
      bind:value={sql}
      spellcheck="false"
      rows="9"
      onkeydown={(e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') void run();
      }}></textarea>
    <div class="actions">
      <button type="button" class="btn primary" onclick={run} disabled={running}>
        {loading ? 'Starting DuckDB…' : running ? 'Running…' : 'Run query'}
      </button>
      <span class="muted small">Ctrl/⌘ + Enter</span>
      {#if result && !running}
        <span class="muted small">{result.rows.length} rows · {elapsed.toFixed(0)} ms</span>
      {/if}
    </div>
    {#if error}
      <pre class="error" role="alert">{error}</pre>
    {/if}
    {#if result}
      <div class="table-wrap">
        <table>
          <thead>
            <tr
              >{#each result.columns as c (c)}<th scope="col">{c}</th>{/each}</tr
            >
          </thead>
          <tbody>
            {#each result.rows as row, i (i)}
              <tr
                >{#each row as v, j (j)}<td class:num={typeof v === 'number'}>{cell(v)}</td
                  >{/each}</tr
              >
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
</dialog>

<style>
  dialog {
    border: 1px solid var(--border-strong);
    border-radius: 16px;
    padding: 0;
    width: min(920px, calc(100vw - 32px));
    max-height: calc(100vh - 48px);
    background: var(--surface);
    color: var(--ink);
    box-shadow: var(--shadow-lg);
  }
  dialog::backdrop {
    background: rgba(0, 0, 0, 0.35);
  }
  .body {
    padding: 20px 24px 24px;
    display: grid;
    gap: 10px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  h2 {
    margin: 0;
    font-size: 20px;
  }
  p {
    margin: 0;
    font-size: 14px;
  }
  .examples {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  textarea {
    width: 100%;
    font-family: var(--mono);
    font-size: 13px;
    line-height: 1.5;
    padding: 10px 12px;
    border-radius: var(--radius);
    border: 1px solid var(--border-strong);
    background: var(--surface-2);
    resize: vertical;
  }
  .actions {
    display: flex;
    gap: 12px;
    align-items: center;
  }
  .primary {
    background: var(--accent);
    color: var(--accent-ink);
    border-color: transparent;
  }
  .primary:hover {
    background: var(--accent);
    filter: brightness(1.08);
  }
  .small {
    font-size: 12px;
  }
  .error {
    margin: 0;
    padding: 10px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--critical) 10%, var(--surface));
    white-space: pre-wrap;
    font-size: 13px;
  }
  .table-wrap {
    overflow: auto;
    max-height: 45vh;
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  table {
    border-collapse: collapse;
    font-size: 13px;
    width: 100%;
  }
  th,
  td {
    text-align: left;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  th {
    position: sticky;
    top: 0;
    background: var(--surface-2);
    font-weight: 600;
  }
  td.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
</style>
