<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
  import AboutDialog from './components/AboutDialog.svelte';
  import HospitalDetail from './components/HospitalDetail.svelte';
  import Landing from './components/Landing.svelte';
  import MapView from './components/MapView.svelte';
  import ResultsPanel from './components/ResultsPanel.svelte';
  import SearchBox from './components/SearchBox.svelte';
  import SqlExplorer from './components/SqlExplorer.svelte';
  import { AppState, type Theme } from './lib/state.svelte';

  const app = new AppState();
  let aboutOpen = $state(false);
  let sqlOpen = $state(false);
  let panel: HTMLElement | undefined = $state();
  const build = __BUILD__;

  $effect(() => {
    void app.load();
    const media = matchMedia('(prefers-color-scheme: dark)');
    app.systemDark = media.matches;
    const onMedia = (e: MediaQueryListEvent) => (app.systemDark = e.matches);
    media.addEventListener('change', onMedia);
    const saved = localStorage.getItem('pricelight-theme');
    if (saved === 'light' || saved === 'dark') app.theme = saved;
    const onPop = () => app.applyUrl(location.search);
    window.addEventListener('popstate', onPop);
    return () => {
      media.removeEventListener('change', onMedia);
      window.removeEventListener('popstate', onPop);
    };
  });

  // Scroll the side panel to the top when its content changes.
  $effect(() => {
    void app.selectedId;
    void app.serviceId;
    panel?.scrollTo({ top: 0 });
  });

  function cycleTheme() {
    const order: Theme[] = ['auto', 'light', 'dark'];
    const next = order[(order.indexOf(app.theme) + 1) % order.length]!;
    app.theme = next;
    if (next === 'auto') {
      delete document.documentElement.dataset.theme;
      localStorage.removeItem('pricelight-theme');
    } else {
      document.documentElement.dataset.theme = next;
      localStorage.setItem('pricelight-theme', next);
    }
  }

  const themeLabel = $derived(
    app.theme === 'auto'
      ? 'Theme: match system'
      : app.theme === 'light'
        ? 'Theme: light'
        : 'Theme: dark',
  );
</script>

<div class="shell">
  {#if app.meta?.demo}
    <div class="banner" role="note">
      <strong>Demo data.</strong> Hospitals, insurers and prices shown here are synthetic and not
      real.
      <button type="button" class="banner-link" onclick={() => (aboutOpen = true)}
        >Learn more</button
      >
    </div>
  {/if}

  <header class="top">
    <button type="button" class="brand" onclick={() => app.goHome()} aria-label="Pricelight home">
      <img src="./favicon.svg" alt="" width="28" height="28" />
      <span>Pricelight</span>
    </button>
    {#if app.serviceId || app.selectedId}
      <div class="top-search">
        <SearchBox {app} />
      </div>
    {:else}
      <div class="spacer"></div>
    {/if}
    <nav class="actions" aria-label="Site">
      <button type="button" class="btn ghost" onclick={() => (aboutOpen = true)}>About</button>
      <button type="button" class="btn ghost hide-sm" onclick={() => (sqlOpen = true)}>SQL</button>
      <button
        type="button"
        class="btn ghost icon"
        onclick={cycleTheme}
        aria-label={themeLabel}
        title={themeLabel}
      >
        {#if app.theme === 'dark'}
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"
            ><path
              d="M14.5 11.5A6.5 6.5 0 0 1 6.5 3.5a6.5 6.5 0 1 0 8 8Z"
              fill="currentColor"
            /></svg
          >
        {:else if app.theme === 'light'}
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"
            ><circle cx="9" cy="9" r="3.5" fill="currentColor" /><g
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              ><path
                d="M9 1.5v2M9 14.5v2M1.5 9h2M14.5 9h2M3.7 3.7l1.4 1.4M12.9 12.9l1.4 1.4M3.7 14.3l1.4-1.4M12.9 5.1l1.4-1.4"
              /></g
            ></svg
          >
        {:else}
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"
            ><circle
              cx="9"
              cy="9"
              r="6.5"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            /><path d="M9 2.5a6.5 6.5 0 0 1 0 13Z" fill="currentColor" /></svg
          >
        {/if}
      </button>
      <a
        class="btn ghost icon"
        href="https://github.com/lobojoel2003/Pricelight"
        rel="noopener noreferrer"
        target="_blank"
        aria-label="Source code on GitHub"
      >
        <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true"
          ><path
            fill="currentColor"
            d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
          /></svg
        >
      </a>
    </nav>
  </header>

  {#if app.status === 'error'}
    <main class="fatal">
      <h1>Pricelight couldn't load its data</h1>
      <p>{app.error}</p>
      <p class="muted">
        If you are running the site locally, build the dataset first: <code>make demo</code> (see the
        README).
      </p>
    </main>
  {:else}
    <main class="main">
      <aside class="panel" bind:this={panel} aria-busy={app.status === 'loading'}>
        {#if app.status === 'loading'}
          <div class="loading">Loading hospitals…</div>
        {:else if app.selectedHospital}
          <HospitalDetail {app} />
        {:else if app.service}
          <ResultsPanel {app} />
        {:else}
          <Landing {app} />
        {/if}
        <footer class="foot">
          <span>v{build.version} · build {build.buildNumber}</span>
          <span>Prices from hospitals' public files. Not medical or financial advice.</span>
        </footer>
      </aside>
      <section class="map-wrap" aria-label="Map">
        <MapView {app} />
        {#if app.serviceId && app.querying}
          <div class="map-status" role="status">Loading prices…</div>
        {/if}
      </section>
    </main>
  {/if}
</div>

<AboutDialog {app} bind:open={aboutOpen} />
<SqlExplorer {app} bind:open={sqlOpen} />

<style>
  .shell {
    height: 100%;
    display: flex;
    flex-direction: column;
  }
  .banner {
    background: var(--banner);
    color: var(--banner-ink);
    font-size: 13px;
    padding: 6px 16px;
    text-align: center;
  }
  .banner-link {
    border: 0;
    background: none;
    padding: 0;
    color: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;
    font-size: inherit;
  }
  .top {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 16px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    z-index: 10;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    border: 0;
    background: none;
    padding: 0;
    font-weight: 700;
    font-size: 18px;
    letter-spacing: -0.01em;
  }
  .brand img {
    border-radius: 7px;
  }
  .top-search {
    flex: 1;
    max-width: 560px;
  }
  .spacer {
    flex: 1;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 2px;
    margin-left: auto;
  }
  .icon {
    padding: 7px;
  }
  .main {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(380px, 480px) 1fr;
  }
  .panel {
    background: var(--surface);
    border-right: 1px solid var(--border);
    overflow-y: auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .panel > :global(:first-child) {
    flex: 1 0 auto;
  }
  .map-wrap {
    position: relative;
    min-height: 0;
  }
  .map-status {
    position: absolute;
    top: 12px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 13px;
    box-shadow: var(--shadow);
  }
  .loading {
    padding: 32px 20px;
    color: var(--ink-3);
  }
  .foot {
    display: grid;
    gap: 2px;
    padding: 14px 16px 18px;
    font-size: 12px;
    color: var(--muted);
    border-top: 1px solid var(--border);
  }
  .fatal {
    padding: 48px 24px;
    max-width: 640px;
    margin: 0 auto;
  }
  @media (max-width: 900px) {
    .main {
      grid-template-columns: 1fr;
      grid-template-rows: minmax(240px, 42vh) auto;
      overflow-y: auto;
    }
    .map-wrap {
      order: -1;
      border-bottom: 1px solid var(--border);
    }
    .panel {
      overflow: visible;
      border-right: 0;
    }
    .hide-sm {
      display: none;
    }
    .top {
      flex-wrap: wrap;
      gap: 8px 12px;
    }
    .top-search {
      order: 3;
      flex-basis: 100%;
      max-width: none;
    }
  }
</style>
