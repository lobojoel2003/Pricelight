<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
  import { money } from '../lib/format';
  import type { AppState } from '../lib/state.svelte';
  import type { Service } from '../lib/types';
  import SearchBox from './SearchBox.svelte';

  let { app }: { app: AppState } = $props();

  const POPULAR = [
    'CPT:70553',
    'CPT:45378',
    'MS-DRG:470',
    'MS-DRG:807',
    'CPT:74177',
    'CPT:80053',
    'CPT:77067',
    'CPT:99285',
  ];

  const popular = $derived(
    POPULAR.map((id) => app.services.find((s) => s.id === id)).filter((s): s is Service => !!s),
  );

  const categories = $derived.by(() => {
    const groups = new Map<string, Service[]>();
    for (const s of app.services) {
      if (!s.curated) continue;
      const list = groups.get(s.category) ?? [];
      list.push(s);
      groups.set(s.category, list);
    }
    return [...groups.entries()].map(([name, list]) => ({ name, list: list.slice(0, 6) }));
  });

  const counts = $derived(app.meta?.counts);
</script>

<section class="landing">
  <h1>Know what a hospital will charge <span>before you go.</span></h1>
  <p class="lede">
    Hospitals must publish their prices, but in files too big and technical to read. Pricelight
    turns them into a map you can search: the cash price and every insurer's negotiated rate, side
    by side.
  </p>

  <SearchBox {app} size="lg" autofocus />

  {#if popular.length}
    <div class="popular" aria-label="Popular searches">
      {#each popular as s (s.id)}
        <button type="button" class="chip" onclick={() => app.selectService(s.id)}>
          {s.label.split(',')[0]}
          {#if s.cash}<span class="price tabular">{money(s.cash.median)}</span>{/if}
        </button>
      {/each}
    </div>
  {/if}

  {#if counts}
    <dl class="stats">
      <div>
        <dt>Hospitals</dt>
        <dd>{counts.hospitals.toLocaleString()}</dd>
      </div>
      <div>
        <dt>Services</dt>
        <dd>{counts.services.toLocaleString()}</dd>
      </div>
      <div>
        <dt>Insurers</dt>
        <dd>{counts.payers.toLocaleString()}</dd>
      </div>
      <div>
        <dt>States</dt>
        <dd>{counts.states.toLocaleString()}</dd>
      </div>
    </dl>
  {/if}

  <div class="browse">
    {#each categories as group (group.name)}
      <section>
        <h2>{group.name}</h2>
        <ul>
          {#each group.list as s (s.id)}
            <li>
              <button type="button" class="link" onclick={() => app.selectService(s.id)}>
                <span>{s.label}</span>
                {#if s.cash}<span class="price tabular">from {money(s.cash.min)}</span>{/if}
              </button>
            </li>
          {/each}
        </ul>
      </section>
    {/each}
  </div>

  <ol class="how">
    <li><strong>Search</strong> a procedure, test or stay, in plain words or by billing code.</li>
    <li><strong>Compare</strong> each hospital's cash price with what every insurer negotiated.</li>
    <li>
      <strong>Check</strong> the hospital's own file: when it was updated and how complete it is.
    </li>
  </ol>
</section>

<style>
  .landing {
    padding: 28px 20px 40px;
    display: grid;
    gap: 18px;
  }
  h1 {
    font-size: clamp(26px, 3.2vw, 34px);
    line-height: 1.12;
    letter-spacing: -0.02em;
    margin: 0;
  }
  h1 span {
    color: var(--ink-3);
  }
  .lede {
    margin: 0;
    color: var(--ink-2);
    font-size: 16px;
    max-width: 52ch;
  }
  .popular {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .price {
    color: var(--ink-3);
    font-size: 13px;
  }
  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin: 4px 0 0;
  }
  .stats div {
    background: var(--surface-2);
    border-radius: var(--radius);
    padding: 10px 12px;
  }
  dt {
    font-size: 12px;
    color: var(--ink-3);
  }
  dd {
    margin: 0;
    font-size: 22px;
    font-weight: 650;
  }
  .browse {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 14px 22px;
    margin-top: 6px;
  }
  h2 {
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--ink-3);
    margin: 0 0 6px;
  }
  .browse ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 2px;
  }
  .link {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    width: 100%;
    text-align: left;
    border: 0;
    background: none;
    padding: 5px 6px;
    margin: 0 -6px;
    border-radius: 6px;
    font-size: 14px;
  }
  .link:hover {
    background: var(--surface-2);
  }
  .link .price {
    flex: none;
  }
  .how {
    margin: 8px 0 0;
    padding: 14px 16px 14px 34px;
    background: var(--surface-2);
    border-radius: var(--radius);
    display: grid;
    gap: 6px;
    font-size: 14px;
    color: var(--ink-2);
  }
  @media (max-width: 520px) {
    .stats {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
