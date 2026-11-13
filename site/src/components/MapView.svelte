<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  US map (Albers USA with Alaska/Hawaii insets) drawn from pre-projected
  us-atlas geometry. No tile server: nothing about the visitor's search
  reaches a third party. Dots are colored by the selected price on a
  one-hue ramp (orange = cash, blue = insurer), gray when the hospital
  does not list the service.
-->
<script lang="ts">
  import { geoAlbersUsa, geoPath } from 'd3-geo';
  import { select } from 'd3-selection';
  import 'd3-transition';
  import { zoom as d3zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from 'd3-zoom';
  import { feature, mesh } from 'topojson-client';
  import type { GeometryCollection, Topology } from 'topojson-specification';
  import usAtlas from 'us-atlas/states-albers-10m.json';
  import { metricValue } from '../lib/aggregate';
  import { money, moneyRange } from '../lib/format';
  import type { AppState } from '../lib/state.svelte';
  import type { Hospital, HospitalPrices } from '../lib/types';

  let { app }: { app: AppState } = $props();

  const W = 975;
  const H = 610;
  const us = usAtlas as unknown as Topology<{
    states: GeometryCollection;
    nation: GeometryCollection;
  }>;
  const path = geoPath();
  const statesPath = path(mesh(us, us.objects.states, (a, b) => a !== b)) ?? '';
  const nationPath = path(feature(us, us.objects.nation)) ?? '';
  const projection = geoAlbersUsa().scale(1300).translate([487.5, 305]);

  let svg: SVGSVGElement | undefined = $state();
  let container: HTMLDivElement | undefined = $state();
  let transform = $state<ZoomTransform>(zoomIdentity);
  let zoomer: ZoomBehavior<SVGSVGElement, unknown> | null = null;
  let tip = $state<{ x: number; y: number; id: string } | null>(null);

  interface Point {
    h: Hospital;
    x: number;
    y: number;
  }

  const points = $derived.by(() => {
    const out: Point[] = [];
    for (const h of app.hospitals) {
      if (h.lat === null || h.lon === null) continue;
      const p = projection([h.lon, h.lat]);
      if (p) out.push({ h, x: p[0], y: p[1] });
    }
    return out;
  });

  const priced = $derived(new Map(app.visible.map((r) => [r.hospital.id, r])));
  const hasService = $derived(app.serviceId !== null);

  /** Draw order: empty dots, then priced (cheapest on top), then hovered/selected. */
  const ordered = $derived.by(() => {
    const rank = (p: Point) => {
      if (p.h.id === app.selectedId || p.h.id === app.hoveredId) return 3;
      return priced.has(p.h.id) ? 2 : 1;
    };
    return [...points].sort((a, b) => rank(a) - rank(b));
  });

  function fill(p: Point): string {
    if (!hasService) return 'var(--accent)';
    const r = priced.get(p.h.id);
    if (!r) return 'var(--dot-empty)';
    return app.colorScale.color(metricValue(r, app.mapMetric)) ?? 'var(--surface)';
  }

  function stroke(p: Point): string {
    if (!hasService) return 'var(--surface)';
    const r = priced.get(p.h.id);
    if (r && app.colorScale.color(metricValue(r, app.mapMetric)) === null) return 'var(--muted)';
    return 'var(--surface)';
  }

  $effect(() => {
    if (!svg) return;
    const z = d3zoom<SVGSVGElement, unknown>()
      .scaleExtent([1, 14])
      .translateExtent([
        [-60, -60],
        [W + 60, H + 60],
      ])
      .on('zoom', (event: { transform: ZoomTransform }) => {
        transform = event.transform;
        tip = null;
      });
    zoomer = z;
    const sel = select(svg).call(z);
    sel.on('dblclick.zoom', null);
    return () => {
      sel.on('.zoom', null);
    };
  });

  function zoomBy(k: number) {
    if (svg && zoomer) select(svg).transition().duration(250).call(zoomer.scaleBy, k);
  }

  function reset() {
    if (svg && zoomer) select(svg).transition().duration(400).call(zoomer.transform, zoomIdentity);
  }

  function fitTo(ids: Set<string>) {
    if (!svg || !zoomer) return;
    const pts = points.filter((p) => ids.has(p.h.id));
    if (pts.length === 0) return reset();
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const w = Math.max(x1 - x0, 60);
    const h = Math.max(y1 - y0, 40);
    const k = Math.min(8, 0.75 / Math.max(w / W, h / H));
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    const t = zoomIdentity
      .translate(W / 2, H / 2)
      .scale(k)
      .translate(-cx, -cy);
    select(svg).transition().duration(600).call(zoomer.transform, t);
  }

  // Zoom to the chosen state; back out when the filter is cleared.
  let lastState: string | null = null;
  $effect(() => {
    const st = app.stateFilter;
    if (!svg || st === lastState) return;
    lastState = st;
    if (st) fitTo(new Set(app.hospitals.filter((h) => h.state === st).map((h) => h.id)));
    else reset();
  });

  // Bring the selected hospital into view if it is off-screen.
  $effect(() => {
    const id = app.selectedId;
    if (!id || !svg || !zoomer) return;
    const p = points.find((q) => q.h.id === id);
    if (!p) return;
    const [sx, sy] = transform.apply([p.x, p.y]);
    if (sx < 40 || sx > W - 40 || sy < 40 || sy > H - 40) {
      const k = Math.max(transform.k, 2);
      const t = zoomIdentity
        .translate(W / 2, H / 2)
        .scale(k)
        .translate(-p.x, -p.y);
      select(svg).transition().duration(500).call(zoomer.transform, t);
    }
  });

  function showTip(event: PointerEvent, id: string) {
    if (!container) return;
    const box = container.getBoundingClientRect();
    tip = { x: event.clientX - box.left, y: event.clientY - box.top, id };
    app.hoveredId = id;
  }

  function hideTip() {
    tip = null;
    app.hoveredId = null;
  }

  const tipData = $derived.by(() => {
    if (!tip) return null;
    const h = app.hospitalsById.get(tip.id);
    if (!h) return null;
    return { h, prices: (priced.get(tip.id) ?? null) as HospitalPrices | null };
  });

  const radius = $derived(Math.max(2.5, 6 / Math.sqrt(transform.k)) / transform.k);

  const legendLabel = $derived(
    app.mapMetric === 'payer'
      ? `${app.payer} rate`
      : app.mapMetric === 'median'
        ? 'Typical insurer rate'
        : 'Cash price',
  );
  const pricedCount = $derived(app.visible.length);
  const ariaSummary = $derived(
    hasService
      ? `Map of ${pricedCount} hospitals listing ${app.service?.label ?? 'this service'}, colored by ${legendLabel.toLowerCase()}. The list beside the map has the same information.`
      : `Map of ${app.hospitals.length} hospitals in the dataset.`,
  );
</script>

<div class="map" bind:this={container}>
  <svg
    bind:this={svg}
    viewBox="0 0 {W} {H}"
    role="img"
    aria-label={ariaSummary}
    preserveAspectRatio="xMidYMid meet"
  >
    <g transform={transform.toString()}>
      <path class="nation" d={nationPath} />
      <path class="states" d={statesPath} />
      {#each ordered as p (p.h.id)}
        {@const active = p.h.id === app.selectedId || p.h.id === app.hoveredId}
        <g class="dot" class:dim={hasService && !priced.has(p.h.id)}>
          <circle
            cx={p.x}
            cy={p.y}
            r={active ? radius * 1.6 : radius}
            fill={fill(p)}
            stroke={active ? 'var(--ink)' : stroke(p)}
            stroke-width={(active ? 2 : 1.5) / transform.k}
          />
          <circle
            class="hit"
            cx={p.x}
            cy={p.y}
            r={12 / transform.k}
            role="presentation"
            onpointerenter={(e) => showTip(e, p.h.id)}
            onpointermove={(e) => showTip(e, p.h.id)}
            onpointerleave={hideTip}
            onclick={() => app.selectHospital(p.h.id)}
          />
        </g>
      {/each}
    </g>
  </svg>

  <div class="controls">
    <button type="button" class="ctl" aria-label="Zoom in" onclick={() => zoomBy(1.6)}>+</button>
    <button type="button" class="ctl" aria-label="Zoom out" onclick={() => zoomBy(1 / 1.6)}
      >−</button
    >
    <button type="button" class="ctl" aria-label="Reset map" onclick={reset}>
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"
        ><path
          d="M2 7a5 5 0 1 0 1.5-3.5M2 2v3h3"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        /></svg
      >
    </button>
  </div>

  {#if hasService && pricedCount > 0}
    {@const [lo, hi] = app.colorScale.domain}
    <div class="legend" aria-hidden="true">
      <span class="legend-title">{legendLabel}</span>
      <span
        class="ramp"
        style:background="linear-gradient(90deg, {app.colorScale.stops.join(', ')})"
      ></span>
      <span class="ends tabular"><span>{money(lo)}</span><span>{money(hi)}+</span></span>
      <span class="none"
        ><span class="swatch hollow"></span>
        {app.mapMetric === 'payer' ? `No ${app.payer} rate` : 'No cash price listed'}</span
      >
      <span class="none"><span class="swatch"></span> Service not in the hospital's file</span>
    </div>
  {/if}

  {#if tip && tipData}
    <div class="tip" style:left="{tip.x}px" style:top="{tip.y}px" role="tooltip">
      {#if tipData.prices}
        {@const v = metricValue(tipData.prices, app.mapMetric)}
        <strong class="tabular">{v !== null ? money(v) : '—'}</strong>
        <span class="tip-sub">{legendLabel}</span>
      {/if}
      <span class="tip-name">{tipData.h.name}</span>
      <span class="tip-sub">{tipData.h.city}, {tipData.h.state}</span>
      {#if tipData.prices && (tipData.prices.min !== null || tipData.prices.max !== null)}
        <span class="tip-sub tabular"
          >Insurers {moneyRange(tipData.prices.min, tipData.prices.max)}</span
        >
      {:else if hasService}
        <span class="tip-sub">No price listed for this service</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .map {
    position: relative;
    width: 100%;
    height: 100%;
    min-height: 0;
    overflow: hidden;
    background: var(--surface);
    touch-action: none;
  }
  svg {
    display: block;
    width: 100%;
    height: 100%;
    cursor: grab;
  }
  svg:active {
    cursor: grabbing;
  }
  .nation {
    fill: var(--land);
  }
  .states {
    fill: none;
    stroke: var(--land-stroke);
    stroke-width: 1.2;
    vector-effect: non-scaling-stroke;
    stroke-linejoin: round;
  }
  .dot circle {
    transition: r 120ms;
  }
  .dot.dim {
    opacity: 0.85;
  }
  .hit {
    fill: transparent;
    stroke: none;
    cursor: pointer;
  }
  .controls {
    position: absolute;
    right: 12px;
    top: 12px;
    display: grid;
    gap: 6px;
  }
  .ctl {
    width: 34px;
    height: 34px;
    display: grid;
    place-items: center;
    border-radius: 8px;
    border: 1px solid var(--border-strong);
    background: var(--surface);
    box-shadow: var(--shadow);
    font-size: 18px;
    line-height: 1;
  }
  .ctl:hover {
    background: var(--surface-2);
  }
  .legend {
    position: absolute;
    left: 12px;
    bottom: 12px;
    display: grid;
    gap: 4px;
    padding: 10px 12px;
    background: color-mix(in srgb, var(--surface) 92%, transparent);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-size: 12px;
    color: var(--ink-2);
    width: 230px;
    box-shadow: var(--shadow);
  }
  .legend-title {
    font-weight: 600;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .ramp {
    height: 8px;
    border-radius: 4px;
  }
  .ends {
    display: flex;
    justify-content: space-between;
  }
  .none {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--dot-empty);
    flex: none;
  }
  .swatch.hollow {
    background: var(--surface);
    border: 1.5px solid var(--muted);
  }
  @media (max-width: 640px) {
    .legend {
      width: 150px;
      left: 8px;
      bottom: 8px;
      padding: 6px 8px;
      gap: 2px;
      font-size: 11px;
    }
    .none {
      display: none;
    }
    .controls {
      right: 8px;
      top: 8px;
      gap: 4px;
    }
    .ctl {
      width: 30px;
      height: 30px;
      font-size: 16px;
    }
  }
  .tip {
    position: absolute;
    transform: translate(-50%, calc(-100% - 14px));
    display: grid;
    gap: 1px;
    min-width: 170px;
    max-width: 260px;
    padding: 8px 11px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-strong);
    background: var(--surface);
    box-shadow: var(--shadow);
    pointer-events: none;
    font-size: 13px;
    z-index: 4;
  }
  .tip strong {
    font-size: 17px;
  }
  .tip-name {
    font-weight: 600;
    margin-top: 2px;
  }
  .tip-sub {
    color: var(--ink-3);
    font-size: 12px;
  }
</style>
