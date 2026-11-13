<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
  import { percentileRank } from '../lib/aggregate';
  import {
    bytes,
    formatDate,
    formatName,
    methodologyName,
    money,
    moneyRange,
    percent,
    settingName,
  } from '../lib/format';
  import type { AppState } from '../lib/state.svelte';
  import RangeBar from './RangeBar.svelte';
  import RangeAxis from './RangeAxis.svelte';

  let { app }: { app: AppState } = $props();

  const hospital = $derived(app.selectedHospital!);
  const prices = $derived(app.selected);
  const service = $derived(app.service);

  const cashPeers = $derived(app.results.map((r) => r.cash).filter((v): v is number => v !== null));
  const cashRank = $derived(
    prices?.cash != null && cashPeers.length > 2 ? percentileRank(prices.cash, cashPeers) : null,
  );
  const cashVsInsurers = $derived(
    prices && prices.cash !== null && prices.rateMedian !== null
      ? prices.cash - prices.rateMedian
      : null,
  );

  const q = $derived(hospital.quality);
  const coverage = $derived(
    hospital.services ? hospital.services_with_cash / hospital.services : 0,
  );

  function rankText(rank: number): string {
    if (rank <= 0.2) return 'among the lowest';
    if (rank <= 0.4) return 'below most';
    if (rank < 0.6) return 'near the middle';
    if (rank < 0.8) return 'above most';
    return 'among the highest';
  }
</script>

<article class="detail" aria-labelledby="hospital-title">
  <div class="bar">
    <button type="button" class="btn ghost back" onclick={() => app.closeHospital()}>
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"
        ><path
          d="M10 3 5 8l5 5"
          fill="none"
          stroke="currentColor"
          stroke-width="1.7"
          stroke-linecap="round"
          stroke-linejoin="round"
        /></svg
      >
      {service ? 'All hospitals' : 'Back'}
    </button>
  </div>

  <header class="head">
    <h1 id="hospital-title">{hospital.name}</h1>
    <p class="addr">{hospital.address}</p>
  </header>

  {#if service && prices}
    <section class="block" aria-labelledby="price-title">
      <h2 id="price-title">{service.label}</h2>
      <p class="sub">
        <span class="code">{service.type} {service.code}</span>
        <span>{settingName(prices.setting)}</span>
      </p>
      {#if prices.description}
        <p class="listed">Listed in the hospital's file as <q>{prices.description}</q></p>
      {/if}

      <div class="tiles">
        <div class="tile">
          <span class="tile-label"><span class="key cash" aria-hidden="true"></span>Cash price</span
          >
          <span class="tile-value">{money(prices.cash)}</span>
          {#if cashRank !== null}
            <span class="tile-note">{rankText(cashRank)} of {app.results.length} hospitals</span>
          {:else if prices.cash === null}
            <span class="tile-note">Not listed by this hospital</span>
          {/if}
        </div>
        <div class="tile">
          <span class="tile-label"
            ><span class="key insurer" aria-hidden="true"></span>Insurer rates</span
          >
          <span class="tile-value">{moneyRange(prices.min, prices.max)}</span>
          <span class="tile-note">
            {prices.rates.length} plan{prices.rates.length === 1
              ? ''
              : 's'}{#if prices.rateMedian !== null}, typical {money(prices.rateMedian)}{/if}
          </span>
        </div>
        <div class="tile">
          <span class="tile-label"
            ><span class="key gross" aria-hidden="true"></span>List price</span
          >
          <span class="tile-value">{money(prices.gross)}</span>
          <span class="tile-note">Chargemaster, before discounts</span>
        </div>
      </div>

      {#if cashVsInsurers !== null}
        <p class="insight">
          {#if cashVsInsurers < 0}
            Paying cash here is <strong>{money(-cashVsInsurers)} less</strong> than the typical rate insurers
            negotiated.
          {:else if cashVsInsurers > 0}
            The cash price is <strong>{money(cashVsInsurers)} more</strong> than the typical insurer rate.
          {:else}
            The cash price matches the typical insurer rate.
          {/if}
        </p>
      {/if}

      <div class="chart">
        <RangeAxis axis={app.axis} />
        <RangeBar {prices} axis={app.axis} payer={app.payer} size="lg" />
      </div>

      {#if prices.rates.length}
        <table class="rates">
          <caption class="visually-hidden"
            >Negotiated rates by insurer and plan, lowest first</caption
          >
          <thead>
            <tr>
              <th scope="col">Insurer</th>
              <th scope="col">Plan</th>
              <th scope="col" class="num">Rate</th>
              <th scope="col">Method</th>
            </tr>
          </thead>
          <tbody>
            {#each prices.rates as r, i (i)}
              <tr class:mine={app.payer === r.payer}>
                <th scope="row">{r.payer}</th>
                <td>{r.plan ?? '—'}</td>
                <td class="num tabular">
                  {#if r.rate !== null}
                    {money(r.rate)}{#if r.basis === 'allowed'}<abbr
                        title="Typical allowed amount (the median the hospital was actually paid), because the contract is a percentage or formula"
                        >*</abbr
                      >{/if}
                  {:else if r.pct !== null}
                    {r.pct}% of charges
                  {:else}
                    See formula
                  {/if}
                </td>
                <td class="method">{methodologyName(r.methodology)}</td>
              </tr>
              {#if r.algorithm}
                <tr class="algo"><td colspan="4">{r.algorithm}</td></tr>
              {/if}
            {/each}
          </tbody>
        </table>
        {#if prices.rates.some((r) => r.basis === 'allowed')}
          <p class="foot">
            * Typical allowed amount: contracts based on a percentage or formula have no fixed
            price, so the hospital reports what it was typically paid.
          </p>
        {/if}
      {/if}

      <aside class="caveat">
        <strong>This is not a quote.</strong> Your cost depends on your plan's deductible, copay and coinsurance,
        and doctors often bill separately from the hospital. Call the hospital or your insurer to confirm
        before you schedule care.
      </aside>
    </section>
  {:else if service}
    <section class="block">
      <p class="muted">This hospital's file doesn't list a price for {service.label}.</p>
    </section>
  {:else}
    <section class="block">
      <p class="muted">Search for a service above to see this hospital's prices.</p>
    </section>
  {/if}

  <section class="block" aria-labelledby="file-title">
    <h2 id="file-title">About this hospital's price file</h2>
    <dl class="facts">
      <div>
        <dt>Last updated</dt>
        <dd>{formatDate(hospital.file.last_updated)}</dd>
      </div>
      <div>
        <dt>Format</dt>
        <dd>
          {formatName(hospital.file.format)}{#if hospital.file.template_version}, CMS template v{hospital
              .file.template_version}{/if}
        </dd>
      </div>
      <div>
        <dt>File size</dt>
        <dd>
          {bytes(hospital.file.bytes)}{hospital.file.compression
            ? ` (${hospital.file.compression})`
            : ''}
        </dd>
      </div>
      <div>
        <dt>Services with a cash price</dt>
        <dd>{percent(coverage)} of {hospital.services}</dd>
      </div>
      <div>
        <dt>Insurers listed</dt>
        <dd>{hospital.payers}</dd>
      </div>
    </dl>
    <ul class="quality">
      <li class:ok={q.attestation === true} class:bad={q.attestation !== true}>
        <span class="icon" aria-hidden="true">{q.attestation === true ? '✓' : '!'}</span>
        {q.attestation === true
          ? 'Hospital attests the file is complete and accurate'
          : 'No confirmed attestation'}
      </li>
      <li class:ok={coverage > 0.9} class:bad={coverage <= 0.9}>
        <span class="icon" aria-hidden="true">{coverage > 0.9 ? '✓' : '!'}</span>
        {coverage > 0.9 ? 'Lists cash prices' : 'Cash prices missing for many services'}
      </li>
      {#each q.issues.slice(0, 4) as issue (issue.code)}
        <li class="bad" class:error={issue.severity === 'error'}>
          <span class="icon" aria-hidden="true">{issue.severity === 'error' ? '×' : '!'}</span>
          {issue.message}
          <span class="count">×{issue.count.toLocaleString()}</span>
        </li>
      {/each}
    </ul>
    <p class="links">
      {#if hospital.source_page_url}<a
          href={hospital.source_page_url}
          rel="noopener noreferrer"
          target="_blank">Hospital's price page</a
        >{/if}
      {#if hospital.mrf_url}<a href={hospital.mrf_url} rel="noopener noreferrer" target="_blank"
          >Download the machine-readable file</a
        >{/if}
    </p>
  </section>
</article>

<style>
  .detail {
    padding-bottom: 32px;
  }
  .bar {
    position: sticky;
    top: 0;
    z-index: 3;
    background: var(--surface);
    padding: 8px 8px 0;
  }
  .back {
    font-size: 14px;
  }
  .head {
    padding: 4px 16px 12px;
  }
  h1 {
    font-size: 22px;
    line-height: 1.2;
    margin: 0 0 4px;
    letter-spacing: -0.01em;
  }
  .addr {
    margin: 0;
    color: var(--ink-3);
    font-size: 14px;
  }
  .block {
    padding: 14px 16px;
    border-top: 1px solid var(--border);
  }
  h2 {
    font-size: 16px;
    margin: 0 0 4px;
  }
  .sub {
    display: flex;
    gap: 10px;
    margin: 0 0 6px;
    font-size: 13px;
    color: var(--ink-2);
  }
  .code {
    font-family: var(--mono);
    background: var(--surface-2);
    border-radius: 4px;
    padding: 0 6px;
  }
  .listed {
    margin: 0 0 12px;
    font-size: 13px;
    color: var(--ink-3);
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    margin: 8px 0 10px;
  }
  .tile {
    display: grid;
    gap: 2px;
    align-content: start;
    padding: 10px 12px;
    background: var(--surface-2);
    border-radius: var(--radius);
  }
  .tile-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--ink-2);
  }
  .tile-value {
    font-size: 20px;
    font-weight: 650;
    line-height: 1.2;
    overflow-wrap: anywhere;
  }
  .tile-note {
    font-size: 12px;
    color: var(--ink-3);
  }
  .key {
    width: 10px;
    height: 10px;
    flex: none;
  }
  .key.cash {
    background: var(--cash);
    transform: rotate(45deg) scale(0.85);
  }
  .key.insurer {
    width: 3px;
    height: 12px;
    border-radius: 2px;
    background: var(--insurer);
  }
  .key.gross {
    border-radius: 50%;
    border: 1.5px solid var(--gross);
  }
  .insight {
    margin: 4px 0 8px;
    font-size: 14px;
  }
  .chart {
    margin: 18px 0 8px;
    display: grid;
    gap: 2px;
  }
  .rates {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
    margin-top: 8px;
  }
  .rates th,
  .rates td {
    text-align: left;
    padding: 7px 6px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .rates thead th {
    font-size: 12px;
    font-weight: 600;
    color: var(--ink-3);
  }
  .rates tbody th {
    font-weight: 500;
  }
  .rates .num {
    text-align: right;
    white-space: nowrap;
  }
  .rates .method {
    color: var(--ink-3);
    font-size: 13px;
  }
  .rates tr.mine th,
  .rates tr.mine td {
    background: var(--insurer-wash);
  }
  .rates tr.algo td {
    font-size: 12px;
    color: var(--ink-3);
    padding-top: 0;
  }
  abbr {
    text-decoration: none;
    cursor: help;
    color: var(--ink-3);
  }
  .foot {
    font-size: 12px;
    color: var(--ink-3);
    margin: 8px 0 0;
  }
  .caveat {
    margin-top: 14px;
    padding: 12px 14px;
    border-radius: var(--radius);
    background: var(--surface-2);
    font-size: 13px;
    color: var(--ink-2);
  }
  .facts {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px 16px;
    margin: 8px 0 12px;
  }
  .facts div {
    display: grid;
  }
  dt {
    font-size: 12px;
    color: var(--ink-3);
  }
  dd {
    margin: 0;
    font-size: 14px;
  }
  .quality {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 6px;
    font-size: 14px;
  }
  .quality li {
    display: flex;
    gap: 8px;
    align-items: baseline;
  }
  .icon {
    display: inline-grid;
    place-items: center;
    flex: none;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    font-size: 11px;
    font-weight: 700;
    color: #fff;
    transform: translateY(3px);
  }
  .ok .icon {
    background: var(--good);
  }
  .bad .icon {
    background: var(--warning);
    color: #0b0b0b;
  }
  .error .icon {
    background: var(--critical);
    color: #fff;
  }
  .count {
    color: var(--ink-3);
    font-size: 12px;
    margin-left: auto;
  }
  .links {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
    margin: 12px 0 0;
    font-size: 14px;
  }
  @media (max-width: 520px) {
    .tiles {
      grid-template-columns: 1fr;
    }
  }
</style>
