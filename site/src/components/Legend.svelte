<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
  let { payer = null }: { payer?: string | null } = $props();
</script>

<ul class="legend" aria-label="How to read the price bars">
  <li>
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"
      ><path d="M7 1L13 7L7 13L1 7Z" fill="var(--cash)" /></svg
    >
    Cash price
  </li>
  <li>
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"
      ><line
        x1="7"
        y1="1"
        x2="7"
        y2="13"
        stroke="var(--insurer)"
        stroke-width="2"
        stroke-linecap="round"
      /></svg
    >
    {payer ? 'Other insurer rates' : 'Insurer rates'}
  </li>
  {#if payer}
    <li>
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"
        ><circle cx="7" cy="7" r="5" fill="var(--insurer)" /></svg
      >
      {payer}
    </li>
  {/if}
  <li>
    <svg width="22" height="14" viewBox="0 0 22 14" aria-hidden="true"
      ><rect x="1" y="3" width="20" height="8" rx="4" fill="var(--insurer-wash)" /></svg
    >
    Insurer range
  </li>
  <li>
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"
      ><circle cx="7" cy="7" r="4.5" fill="none" stroke="var(--gross)" stroke-width="1.5" /></svg
    >
    List price
  </li>
</ul>

<style>
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: 13px;
    color: var(--ink-2);
  }
  li {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  svg {
    flex: none;
  }
</style>
