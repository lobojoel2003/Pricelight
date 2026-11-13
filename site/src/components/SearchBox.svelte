<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Accessible combobox (WAI-ARIA 1.2 pattern) over the service index. -->
<script lang="ts">
  import { highlight } from '../lib/search';
  import type { AppState } from '../lib/state.svelte';
  import type { Service } from '../lib/types';

  let {
    app,
    size = 'md',
    autofocus = false,
  }: { app: AppState; size?: 'md' | 'lg'; autofocus?: boolean } = $props();

  const id = `search-${Math.random().toString(36).slice(2, 8)}`;
  let query = $state('');
  let open = $state(false);
  let active = $state(0);
  let input: HTMLInputElement | undefined = $state();

  const matches = $derived(app.index.search(query, 8));

  $effect(() => {
    if (autofocus && input && matchMedia('(min-width: 900px)').matches) input.focus();
  });

  function choose(service: Service) {
    query = '';
    open = false;
    input?.blur();
    void app.selectService(service.id);
  }

  function onkeydown(event: KeyboardEvent) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      open = true;
      active = Math.min(active + 1, matches.length - 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      active = Math.max(active - 1, 0);
    } else if (event.key === 'Enter') {
      const pick = matches[active];
      if (pick) {
        event.preventDefault();
        choose(pick);
      }
    } else if (event.key === 'Escape') {
      if (open) {
        event.preventDefault();
        open = false;
      } else {
        query = '';
      }
    }
  }
</script>

<div class="search {size}">
  <label for={id} class="visually-hidden">Search for a service, procedure or billing code</label>
  <svg class="icon" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
    <circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.7" />
    <path d="m12.2 12.2 3.6 3.6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
  </svg>
  <input
    bind:this={input}
    {id}
    type="search"
    role="combobox"
    autocomplete="off"
    spellcheck="false"
    aria-expanded={open && matches.length > 0}
    aria-controls="{id}-list"
    aria-autocomplete="list"
    aria-activedescendant={open && matches[active] ? `${id}-opt-${active}` : undefined}
    placeholder={size === 'lg'
      ? 'Try “MRI brain”, “colonoscopy” or 70553'
      : 'Search a service or code'}
    bind:value={query}
    oninput={() => {
      open = true;
      active = 0;
    }}
    onfocus={() => (open = query.length > 0)}
    onblur={() => setTimeout(() => (open = false), 120)}
    {onkeydown}
  />
  {#if open && query.trim()}
    <ul id="{id}-list" role="listbox" class="list" aria-label="Matching services">
      {#each matches as s, i (s.id)}
        <li
          id="{id}-opt-{i}"
          role="option"
          aria-selected={i === active}
          class:active={i === active}
          onpointerdown={(e) => {
            e.preventDefault();
            choose(s);
          }}
          onpointerenter={() => (active = i)}
        >
          <span class="label">
            {#each highlight(s.label, query) as part, j (j)}{#if part.match}<mark>{part.text}</mark
                >{:else}{part.text}{/if}{/each}
          </span>
          <span class="meta">
            <span class="code">{s.type} {s.code}</span>
            <span>{s.category}</span>
            <span>{s.hospitals} hospital{s.hospitals === 1 ? '' : 's'}</span>
          </span>
        </li>
      {:else}
        <li class="empty" role="option" aria-selected="false" aria-disabled="true">
          No services match “{query}”. Try a simpler word, like “mri” or “knee”.
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .search {
    position: relative;
    width: 100%;
  }
  .icon {
    position: absolute;
    left: 14px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
    pointer-events: none;
  }
  input {
    width: 100%;
    border: 1px solid var(--border-strong);
    background: var(--surface);
    border-radius: 999px;
    padding: 9px 16px 9px 42px;
    font-size: 15px;
    outline: none;
    transition:
      border-color 120ms,
      box-shadow 120ms;
  }
  .lg input {
    padding: 15px 20px 15px 46px;
    font-size: 17px;
    box-shadow: var(--shadow);
  }
  .lg .icon {
    left: 17px;
  }
  input:focus {
    border-color: var(--focus);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--focus) 22%, transparent);
  }
  input::-webkit-search-cancel-button {
    cursor: pointer;
  }
  .list {
    position: absolute;
    left: 0;
    right: 0;
    top: calc(100% + 6px);
    z-index: 30;
    margin: 0;
    padding: 6px;
    list-style: none;
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: 14px;
    box-shadow: var(--shadow-lg);
    max-height: min(420px, 70vh);
    overflow: auto;
  }
  li {
    display: grid;
    gap: 2px;
    padding: 8px 12px;
    border-radius: 9px;
    cursor: pointer;
  }
  li.active {
    background: var(--surface-2);
  }
  .label {
    font-weight: 550;
  }
  mark {
    background: none;
    color: inherit;
    font-weight: 750;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 2px 10px;
    font-size: 12px;
    color: var(--ink-3);
  }
  .code {
    font-family: var(--mono);
  }
  .empty {
    cursor: default;
    color: var(--ink-3);
    font-size: 14px;
  }
</style>
