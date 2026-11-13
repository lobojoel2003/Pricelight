<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  The price-range bar: one hospital's prices for one service on a shared axis.
    band   = range of insurer-negotiated rates (de-identified min..max)
    ticks  = each insurer/plan's negotiated rate (blue)
    diamond= discounted cash price (orange)
    ring   = gross "list" charge (gray, often off the scale)
  Shape and color both encode identity, so it reads without color too.
-->
<script lang="ts">
  import { money } from '../lib/format';
  import type { PriceAxis } from '../lib/scale';
  import type { HospitalPrices, PayerRate } from '../lib/types';

  interface Props {
    prices: HospitalPrices;
    axis: PriceAxis;
    payer?: string | null;
    size?: 'sm' | 'lg';
  }

  let { prices, axis, payer = null, size = 'sm' }: Props = $props();

  let width = $state(0);
  const pad = 8;
  const height = $derived(size === 'lg' ? 64 : 26);
  const mid = $derived(size === 'lg' ? 34 : 13);
  const inner = $derived(Math.max(0, width - pad * 2));

  const x = (v: number) => pad + axis.x(v) * inner;
  const over = (v: number | null) => v !== null && v > axis.max;

  const rated = $derived(
    prices.rates.filter((r): r is PayerRate & { rate: number } => r.rate !== null),
  );
  const bandLo = $derived(prices.min);
  const bandHi = $derived(prices.max);

  let tip = $state<{ x: number; label: string; value: string; note: string } | null>(null);

  function show(r: PayerRate & { rate: number }) {
    if (size !== 'lg') return;
    tip = {
      x: x(r.rate),
      label: r.plan ? `${r.payer} · ${r.plan}` : r.payer,
      value: money(r.rate),
      note: r.basis === 'allowed' ? 'typical allowed amount' : 'negotiated rate',
    };
  }

  function diamond(cx: number, cy: number, s: number): string {
    return `M${cx} ${cy - s}L${cx + s} ${cy}L${cx} ${cy + s}L${cx - s} ${cy}Z`;
  }
</script>

<div class="range {size}" bind:clientWidth={width} aria-hidden="true">
  {#if width > 0}
    <svg {width} {height} role="presentation">
      <line class="base" x1={pad} x2={width - pad} y1={mid} y2={mid} />
      {#if bandLo !== null && bandHi !== null}
        {@const x0 = x(bandLo)}
        {@const x1 = x(bandHi)}
        <rect
          class="band"
          x={Math.min(x0, x1 - 2)}
          y={mid - (size === 'lg' ? 6 : 4)}
          width={Math.max(4, x1 - x0)}
          height={size === 'lg' ? 12 : 8}
          rx={size === 'lg' ? 6 : 4}
        />
      {/if}
      {#each rated as r, i (i)}
        {@const mine = payer !== null && r.payer === payer}
        {@const faded = payer !== null && !mine}
        <line
          class="tick"
          class:faded
          x1={x(r.rate)}
          x2={x(r.rate)}
          y1={mid - (size === 'lg' ? 11 : 7)}
          y2={mid + (size === 'lg' ? 11 : 7)}
        />
        {#if mine}
          <circle class="mine" cx={x(r.rate)} cy={mid} r={size === 'lg' ? 6 : 4.5} />
        {/if}
        {#if size === 'lg'}
          <rect
            class="hit"
            x={x(r.rate) - 6}
            y={mid - 16}
            width="12"
            height="32"
            role="presentation"
            onpointerenter={() => show(r)}
            onpointerleave={() => (tip = null)}
          />
        {/if}
      {/each}
      {#if prices.gross !== null}
        {#if over(prices.gross)}
          <path class="overflow" d={`M${width - pad - 5} ${mid - 5}l5 5l-5 5`} />
        {:else}
          <circle class="gross" cx={x(prices.gross)} cy={mid} r={size === 'lg' ? 5.5 : 4} />
        {/if}
      {/if}
      {#if prices.cash !== null}
        {@const cx = x(Math.min(prices.cash, axis.max))}
        <path class="cash" d={diamond(cx, mid, size === 'lg' ? 8 : 6)} />
        {#if size === 'lg'}
          <text
            class="label cash-label"
            x={cx}
            y={mid - 16}
            text-anchor={cx < 60 ? 'start' : cx > width - 60 ? 'end' : 'middle'}
            >Cash {money(prices.cash)}</text
          >
        {/if}
      {/if}
      {#if size === 'lg' && bandLo !== null && bandHi !== null}
        <text
          class="label"
          x={x(bandLo)}
          y={mid + 25}
          text-anchor={x(bandLo) < 40 ? 'start' : 'middle'}>{money(bandLo)}</text
        >
        {#if x(bandHi) - x(bandLo) > 64}
          <text
            class="label"
            x={x(bandHi)}
            y={mid + 25}
            text-anchor={x(bandHi) > width - 40 ? 'end' : 'middle'}>{money(bandHi)}</text
          >
        {/if}
      {/if}
    </svg>
    {#if tip}
      <div class="tip" style:left="{tip.x}px">
        <strong class="tabular">{tip.value}</strong>
        <span>{tip.label}</span>
        <span class="note">{tip.note}</span>
      </div>
    {/if}
  {/if}
</div>

<style>
  .range {
    position: relative;
    width: 100%;
  }
  .range.sm {
    height: 26px;
  }
  .range.lg {
    height: 64px;
  }
  svg {
    display: block;
    overflow: visible;
  }
  .base {
    stroke: var(--grid);
    stroke-width: 1;
  }
  .band {
    fill: var(--insurer-wash);
  }
  .tick {
    stroke: var(--insurer);
    stroke-width: 2;
    stroke-linecap: round;
  }
  .tick.faded {
    opacity: 0.28;
  }
  .mine {
    fill: var(--insurer);
    stroke: var(--surface);
    stroke-width: 2;
  }
  .cash {
    fill: var(--cash);
    stroke: var(--surface);
    stroke-width: 2;
    stroke-linejoin: round;
  }
  .gross {
    fill: var(--surface);
    stroke: var(--gross);
    stroke-width: 1.5;
  }
  .overflow {
    fill: none;
    stroke: var(--gross);
    stroke-width: 1.5;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .hit {
    fill: transparent;
    cursor: default;
  }
  .label {
    font-size: 12px;
    fill: var(--ink-2);
    font-variant-numeric: tabular-nums;
  }
  .cash-label {
    fill: var(--ink);
    font-weight: 600;
  }
  .tip {
    position: absolute;
    bottom: calc(100% - 4px);
    transform: translateX(-50%);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    box-shadow: var(--shadow);
    border-radius: var(--radius-sm);
    padding: 6px 10px;
    font-size: 13px;
    white-space: nowrap;
    pointer-events: none;
    display: grid;
    gap: 1px;
    z-index: 5;
  }
  .tip strong {
    font-size: 15px;
  }
  .tip .note {
    color: var(--ink-3);
    font-size: 12px;
  }
</style>
