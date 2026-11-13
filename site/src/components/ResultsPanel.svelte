<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
  import { median, money, plural } from '../lib/format';
  import type { AppState } from '../lib/state.svelte';
  import type { SortKey } from '../lib/types';
  import HospitalRow from './HospitalRow.svelte';
  import Legend from './Legend.svelte';
  import RangeAxis from './RangeAxis.svelte';

  let { app }: { app: AppState } = $props();

  const service = $derived(app.service!);
  const cashValues = $derived(
    app.visible.map((r) => r.cash).filter((v): v is number => v !== null),
  );
  const payerValues = $derived(
    app.visible.map((r) => r.payerRate).filter((v): v is number => v !== null),
  );
  const cashMedian = $derived(median(cashValues));
  const spread = $derived(
    cashValues.length > 1 ? Math.max(...cashValues) / Math.max(1, Math.min(...cashValues)) : null,
  );

  const sortOptions = $derived<{ value: SortKey; label: string }[]>([
    ...(app.payer ? [{ value: 'payer' as const, label: `${app.payer} rate` }] : []),
    { value: 'cash', label: 'Cash price' },
    { value: 'median', label: 'Typical insurer rate' },
    { value: 'name', label: 'Hospital name' },
  ]);

  const statesWithService = $derived([...new Set(app.results.map((r) => r.hospital.state))].sort());
</script>

<section class="results" aria-labelledby="service-title">
  <header class="head">
    <p class="crumb">
      <button type="button" class="link" onclick={() => app.goHome()}>All services</button>
      <span aria-hidden="true">›</span>
      <span>{service.category}</span>
    </p>
    <h1 id="service-title">{service.label}</h1>
    <p class="meta">
      <span class="code">{service.type} {service.code}</span>
      {#if app.querying}
        <span>Loading prices…</span>
      {:else}
        <span>{plural(app.visible.length, 'hospital')}</span>
        {#if cashMedian !== null}
          <span>median cash {money(cashMedian)}</span>
        {/if}
      {/if}
    </p>
    {#if !app.querying && spread !== null && spread >= 1.5}
      <p class="insight">
        Cash prices for the same service differ <strong>{spread.toFixed(1)}×</strong> between the cheapest
        and most expensive hospital shown.
      </p>
    {/if}
  </header>

  <div class="filters" role="group" aria-label="Filter and sort">
    <label>
      <span class="visually-hidden">Insurer</span>
      <select
        class="select"
        value={app.payer ?? ''}
        onchange={(e) => app.setPayer(e.currentTarget.value || null)}
      >
        <option value="">Any insurer</option>
        {#each app.payers as p (p.name)}
          <option value={p.name}>{p.name}</option>
        {/each}
      </select>
    </label>
    <label>
      <span class="visually-hidden">State</span>
      <select
        class="select"
        value={app.stateFilter ?? ''}
        onchange={(e) => app.setState(e.currentTarget.value || null)}
      >
        <option value="">All states</option>
        {#each statesWithService as s (s)}
          <option value={s}>{s}</option>
        {/each}
      </select>
    </label>
    <label>
      <span class="visually-hidden">Sort by</span>
      <select
        class="select"
        value={app.sort}
        onchange={(e) => app.setSort(e.currentTarget.value as SortKey)}
      >
        {#each sortOptions as o (o.value)}
          <option value={o.value}>Sort: {o.label}</option>
        {/each}
      </select>
    </label>
  </div>

  <div class="legend-row">
    <Legend payer={app.payer} />
  </div>

  {#if app.engineStatus === 'error'}
    <div class="notice error" role="alert">
      <strong>Prices could not be loaded.</strong>
      <span>{app.engineError}</span>
      <button class="btn" type="button" onclick={() => app.selectService(app.serviceId)}
        >Try again</button
      >
    </div>
  {:else if !app.querying && app.visible.length === 0}
    <div class="notice">
      No hospitals match these filters.
      {#if app.payer || app.stateFilter}
        <button
          class="btn"
          type="button"
          onclick={() => {
            app.setPayer(null);
            app.setState(null);
          }}>Clear filters</button
        >
      {/if}
    </div>
  {:else}
    <div class="axis-row" class:dim={app.querying}>
      <RangeAxis axis={app.axis} />
    </div>
    {#if app.payer && payerValues.length < app.visible.length}
      <p class="hint">
        {app.visible.length - payerValues.length} of these hospitals list {app.payer} without a dollar
        amount (for example a percentage of charges).
      </p>
    {/if}
    <ol
      class="list"
      class:dim={app.querying}
      aria-label="Hospitals, {sortOptions.find((o) => o.value === app.sort)?.label} low to high"
    >
      {#each app.visible as prices (prices.hospital.id)}
        <HospitalRow
          {prices}
          axis={app.axis}
          payer={app.payer}
          hovered={app.hoveredId === prices.hospital.id}
          onselect={(id) => app.selectHospital(id)}
          onhover={(id) => (app.hoveredId = id)}
        />
      {/each}
    </ol>
  {/if}
</section>

<style>
  .results {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .head {
    padding: 18px 16px 8px;
  }
  .crumb {
    display: flex;
    gap: 6px;
    margin: 0 0 6px;
    font-size: 13px;
    color: var(--ink-3);
  }
  .link {
    border: 0;
    background: none;
    padding: 0;
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 2px;
  }
  h1 {
    font-size: 22px;
    line-height: 1.2;
    margin: 0 0 6px;
    letter-spacing: -0.01em;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 12px;
    margin: 0;
    font-size: 14px;
    color: var(--ink-2);
  }
  .code {
    font-family: var(--mono);
    font-size: 13px;
    background: var(--surface-2);
    border-radius: 4px;
    padding: 1px 6px;
  }
  .insight {
    margin: 10px 0 0;
    font-size: 14px;
    color: var(--ink-2);
  }
  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 6px 16px 10px;
  }
  .legend-row {
    padding: 2px 16px 10px;
  }
  .axis-row {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--surface);
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    padding: 6px 16px 4px;
  }
  .list {
    margin: 0;
    padding: 0;
  }
  .dim {
    opacity: 0.55;
    transition: opacity 150ms;
  }
  .hint {
    margin: 0;
    padding: 8px 16px;
    font-size: 13px;
    color: var(--ink-3);
    border-bottom: 1px solid var(--border);
  }
  .notice {
    margin: 12px 16px;
    padding: 14px;
    border-radius: var(--radius);
    background: var(--surface-2);
    display: grid;
    gap: 8px;
    justify-items: start;
    color: var(--ink-2);
  }
  .notice.error {
    background: color-mix(in srgb, var(--critical) 10%, var(--surface));
  }
</style>
