<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
  import type { PriceAxis } from '../lib/scale';

  let { axis }: { axis: PriceAxis } = $props();
  let width = $state(0);
  const pad = 8;
  const inner = $derived(Math.max(0, width - pad * 2));
</script>

<div class="axis" bind:clientWidth={width} aria-hidden="true">
  {#each axis.ticks as t (t.value)}
    {@const left = pad + axis.x(t.value) * inner}
    <span
      class="tick tabular"
      style:left="{left}px"
      class:first={left < 20}
      class:last={left > width - 24}>{t.label}</span
    >
  {/each}
</div>

<style>
  .axis {
    position: relative;
    height: 18px;
    font-size: 12px;
    color: var(--muted);
  }
  .tick {
    position: absolute;
    top: 0;
    transform: translateX(-50%);
    white-space: nowrap;
  }
  .tick::after {
    content: '';
    position: absolute;
    left: 50%;
    top: 17px;
    height: 4px;
    border-left: 1px solid var(--axis);
  }
  .tick.first {
    transform: translateX(-8px);
  }
  .tick.first::after {
    left: 8px;
  }
  .tick.last {
    transform: translateX(calc(-100% + 8px));
  }
  .tick.last::after {
    left: calc(100% - 8px);
  }
</style>
