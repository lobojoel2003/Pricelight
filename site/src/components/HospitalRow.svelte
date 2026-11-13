<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
  import { money, moneyRange } from '../lib/format';
  import type { PriceAxis } from '../lib/scale';
  import type { HospitalPrices } from '../lib/types';
  import RangeBar from './RangeBar.svelte';

  interface Props {
    prices: HospitalPrices;
    axis: PriceAxis;
    payer: string | null;
    hovered: boolean;
    onselect: (id: string) => void;
    onhover: (id: string | null) => void;
  }

  let { prices, axis, payer, hovered, onselect, onhover }: Props = $props();
  const h = $derived(prices.hospital);

  const summary = $derived.by(() => {
    const parts = [`${h.name}, ${h.city}, ${h.state}.`];
    parts.push(
      prices.cash !== null ? `Cash price ${money(prices.cash)}.` : 'No cash price listed.',
    );
    if (prices.min !== null || prices.max !== null) {
      parts.push(`Insurer rates ${moneyRange(prices.min, prices.max)}.`);
    }
    if (payer) {
      parts.push(
        prices.payerRate !== null
          ? `${payer} ${money(prices.payerRate)}.`
          : `No ${payer} rate listed.`,
      );
    }
    if (prices.gross !== null) parts.push(`List price ${money(prices.gross)}.`);
    return parts.join(' ');
  });
</script>

<li>
  <button
    type="button"
    class="row"
    class:hovered
    aria-label={summary}
    onclick={() => onselect(h.id)}
    onpointerenter={() => onhover(h.id)}
    onpointerleave={() => onhover(null)}
    onfocus={() => onhover(h.id)}
    onblur={() => onhover(null)}
  >
    <span class="top">
      <span class="who">
        <span class="name">{h.name}</span>
        <span class="where">{h.city}, {h.state}</span>
      </span>
      <span class="prices tabular">
        {#if payer}
          <span class="primary">{prices.payerRate !== null ? money(prices.payerRate) : '—'}</span>
          <span class="secondary">{prices.payerRate !== null ? payer : `no ${payer} rate`}</span>
        {:else}
          <span class="primary">{prices.cash !== null ? money(prices.cash) : '—'}</span>
          <span class="secondary">{prices.cash !== null ? 'cash price' : 'no cash price'}</span>
        {/if}
      </span>
    </span>
    <RangeBar {prices} {axis} {payer} />
    <span class="bottom">
      <span>Insurers {moneyRange(prices.min, prices.max)}</span>
      {#if payer && prices.cash !== null}
        <span>Cash {money(prices.cash)}</span>
      {/if}
      {#if prices.gross !== null}
        <span>List {money(prices.gross)}</span>
      {/if}
    </span>
  </button>
</li>

<style>
  li {
    list-style: none;
  }
  .row {
    display: grid;
    gap: 4px;
    width: 100%;
    text-align: left;
    background: transparent;
    border: 0;
    border-bottom: 1px solid var(--border);
    padding: 12px 16px 10px;
    transition: background 120ms;
  }
  .row:hover,
  .row.hovered {
    background: var(--surface-2);
  }
  .top {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: flex-start;
  }
  .who {
    display: grid;
    min-width: 0;
  }
  .name {
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .where {
    font-size: 13px;
    color: var(--ink-3);
  }
  .prices {
    display: grid;
    justify-items: end;
    flex: none;
  }
  .primary {
    font-weight: 650;
    font-size: 16px;
  }
  .secondary {
    font-size: 12px;
    color: var(--ink-3);
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .bottom {
    display: flex;
    flex-wrap: wrap;
    gap: 2px 14px;
    font-size: 12px;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }
</style>
