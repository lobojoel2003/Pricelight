<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
  import type { AppState } from '../lib/state.svelte';

  let { app, open = $bindable(false) }: { app: AppState; open?: boolean } = $props();
  let dialog: HTMLDialogElement | undefined = $state();

  $effect(() => {
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  });

  const build = __BUILD__;
</script>

<dialog bind:this={dialog} onclose={() => (open = false)} aria-labelledby="about-title">
  <div class="body">
    <header>
      <h2 id="about-title">About Pricelight</h2>
      <button type="button" class="btn ghost" aria-label="Close" onclick={() => (open = false)}
        >✕</button
      >
    </header>

    {#if app.meta?.demo}
      <p class="demo">
        <strong>You are looking at synthetic demo data.</strong> The hospitals, insurers and prices on
        this site were generated to exercise the software and are fictional. Run the pipeline on real
        hospital files to publish real prices.
      </p>
    {/if}

    <h3>Where the prices come from</h3>
    <p>
      Since 2021, US hospitals must publish a machine-readable file listing their standard charges
      for every item and service (<a
        href="https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-E/part-180"
        rel="noopener noreferrer"
        target="_blank">45 CFR Part 180</a
      >), in a format set by
      <a
        href="https://github.com/CMSgov/hospital-price-transparency"
        rel="noopener noreferrer"
        target="_blank">CMS</a
      >. The files are often gigabytes of JSON or CSV. Pricelight's open-source parser streams them
      into a common table, and this page searches the result.
    </p>
    <dl>
      <dt>Cash price</dt>
      <dd>The discounted price for someone paying without insurance.</dd>
      <dt>Insurer rate</dt>
      <dd>
        The rate a hospital negotiated with a specific insurer and plan. When a contract is a
        percentage or formula, the hospital reports the typical amount it was actually paid instead.
      </dd>
      <dt>List price</dt>
      <dd>
        The "gross charge" on the hospital's chargemaster, before any discount. Few people pay it.
      </dd>
    </dl>

    <h3>What these numbers are not</h3>
    <p>
      They are not a quote or a bill. What you pay depends on your plan's deductible and
      coinsurance, and physicians often bill separately. Files can be outdated or incomplete; each
      hospital page shows when its file was last updated and what was missing.
    </p>

    <h3>Your privacy</h3>
    <p>
      The search runs entirely in your browser with <a
        href="https://duckdb.org/docs/api/wasm/overview"
        rel="noopener noreferrer"
        target="_blank">DuckDB-WASM</a
      >. What you look up is never sent to a server, there are no cookies, no analytics and no
      third-party map tiles.
    </p>

    <h3>Open source</h3>
    <p>
      The website and data pipeline are licensed under the
      <a href="https://www.gnu.org/licenses/agpl-3.0.html" rel="noopener noreferrer" target="_blank"
        >GNU AGPL v3</a
      >; the parser library under
      <a
        href="https://www.apache.org/licenses/LICENSE-2.0"
        rel="noopener noreferrer"
        target="_blank">Apache 2.0</a
      >. Source, issues and the full method:
      <a href="https://github.com/lobojoel2003/Pricelight" rel="noopener noreferrer" target="_blank"
        >github.com/lobojoel2003/Pricelight</a
      >.
    </p>

    <p class="build tabular">
      Version {build.version} · build {build.buildNumber}{build.commit ? ` · ${build.commit}` : ''} ·
      {build.date}
      {#if app.meta}
        <br />Dataset generated {app.meta.generated_at.slice(0, 10)} · pipeline {app.meta
          .pipeline_version} · parser {app.meta.parser_version} · {app.meta.counts.price_rows.toLocaleString()}
        price rows
      {/if}
    </p>
  </div>
</dialog>

<style>
  dialog {
    border: 1px solid var(--border-strong);
    border-radius: 16px;
    padding: 0;
    max-width: min(640px, calc(100vw - 32px));
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
    font-size: 15px;
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
  h3 {
    font-size: 15px;
    margin: 18px 0 4px;
  }
  p {
    margin: 0 0 8px;
    color: var(--ink-2);
  }
  dl {
    margin: 8px 0;
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 6px 14px;
  }
  dt {
    font-weight: 600;
  }
  dd {
    margin: 0;
    color: var(--ink-2);
  }
  .demo {
    background: var(--banner);
    color: var(--banner-ink);
    border-radius: var(--radius);
    padding: 10px 12px;
    margin-top: 12px;
  }
  .build {
    margin-top: 18px;
    font-size: 12px;
    color: var(--ink-3);
  }
</style>
