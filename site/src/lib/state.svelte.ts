// SPDX-License-Identifier: AGPL-3.0-or-later
// Application state (Svelte 5 runes). One instance, created in App.svelte.

import { filterResults, groupByHospital, sortResults } from './aggregate';
import { PriceEngine } from './engine';
import { mapColorScale, priceAxis } from './scale';
import { ServiceIndex } from './search';
import type { Hospital, HospitalPrices, MapMetric, Meta, Payer, Service, SortKey } from './types';
import { readUrl, writeUrl } from './url';

export type Theme = 'auto' | 'light' | 'dark';

function dataUrl(name: string): string {
  return new URL(`data/${name}`, document.baseURI).href;
}

async function getJson<T>(name: string): Promise<T> {
  const res = await fetch(dataUrl(name));
  if (!res.ok) throw new Error(`Could not load ${name} (HTTP ${res.status})`);
  return (await res.json()) as T;
}

export class AppState {
  // dataset ----------------------------------------------------------------
  meta = $state.raw<Meta | null>(null);
  hospitals = $state.raw<Hospital[]>([]);
  services = $state.raw<Service[]>([]);
  payers = $state.raw<Payer[]>([]);
  status = $state<'loading' | 'ready' | 'error'>('loading');
  error = $state<string | null>(null);

  hospitalsById = $derived(new Map(this.hospitals.map((h) => [h.id, h])));
  index = $derived(new ServiceIndex(this.services));
  states = $derived([...new Set(this.hospitals.map((h) => h.state).filter(Boolean))].sort());

  // query engine -----------------------------------------------------------
  engine: PriceEngine | null = null;
  engineStatus = $state<'idle' | 'starting' | 'ready' | 'error'>('idle');
  engineError = $state<string | null>(null);
  querying = $state(false);

  // user selections --------------------------------------------------------
  serviceId = $state<string | null>(null);
  payer = $state<string | null>(null);
  stateFilter = $state<string | null>(null);
  sort = $state<SortKey>('cash');
  selectedId = $state<string | null>(null);
  hoveredId = $state<string | null>(null);
  theme = $state<Theme>('auto');
  systemDark = $state(false);

  /** Every hospital offering the selected service (unfiltered). */
  results = $state.raw<HospitalPrices[]>([]);

  service = $derived(this.services.find((s) => s.id === this.serviceId) ?? null);
  dark = $derived(this.theme === 'dark' || (this.theme === 'auto' && this.systemDark));
  mapMetric = $derived<MapMetric>(this.payer ? 'payer' : 'cash');
  visible = $derived(
    sortResults(
      filterResults(this.results, { state: this.stateFilter, payer: this.payer, within: null }),
      this.sort,
    ),
  );
  axis = $derived(priceAxis(this.visible.length ? this.visible : this.results));
  colorScale = $derived(mapColorScale(this.visible, this.mapMetric, this.dark));
  selected = $derived(
    this.selectedId ? (this.results.find((r) => r.hospital.id === this.selectedId) ?? null) : null,
  );
  selectedHospital = $derived(
    this.selectedId ? (this.hospitalsById.get(this.selectedId) ?? null) : null,
  );

  private queryToken = 0;

  async load(): Promise<void> {
    try {
      const [meta, hospitals, services, payers] = await Promise.all([
        getJson<Meta>('meta.json'),
        getJson<Hospital[]>('hospitals.json'),
        getJson<Service[]>('services.json'),
        getJson<Payer[]>('payers.json'),
      ]);
      this.meta = meta;
      this.hospitals = hospitals;
      this.services = services;
      this.payers = payers;
      this.status = 'ready';
    } catch (err) {
      this.status = 'error';
      this.error = err instanceof Error ? err.message : String(err);
      return;
    }
    this.engine = new PriceEngine(dataUrl('prices.parquet'));
    this.applyUrl(location.search, false);
    // Read the Parquet footer after first paint so the first search is instant.
    if (!this.serviceId) setTimeout(() => void this.startEngine(), 300);
  }

  async startEngine(): Promise<boolean> {
    if (!this.engine) return false;
    if (this.engineStatus === 'ready') return true;
    this.engineStatus = 'starting';
    try {
      await this.engine.init();
      this.engineStatus = 'ready';
      this.engineError = null;
      return true;
    } catch (err) {
      this.engineStatus = 'error';
      this.engineError = err instanceof Error ? err.message : String(err);
      return false;
    }
  }

  /** Select a service and load its prices. */
  async selectService(id: string | null, opts: { push?: boolean } = {}): Promise<void> {
    if (id === this.serviceId && this.results.length) return;
    this.serviceId = id;
    this.selectedId = null;
    this.hoveredId = null;
    this.syncUrl(opts.push ?? true);
    if (!id) {
      this.results = [];
      return;
    }
    const token = ++this.queryToken;
    this.querying = true;
    try {
      if (!(await this.startEngine())) return;
      const rows = await this.engine!.pricesFor(id);
      if (token !== this.queryToken) return;
      this.results = groupByHospital(rows, this.hospitalsById, this.payer);
    } catch (err) {
      if (token === this.queryToken) {
        this.engineError = err instanceof Error ? err.message : String(err);
        this.engineStatus = 'error';
      }
    } finally {
      if (token === this.queryToken) this.querying = false;
    }
  }

  setPayer(payer: string | null): void {
    this.payer = payer;
    if (payer && this.sort === 'cash') this.sort = 'payer';
    if (!payer && this.sort === 'payer') this.sort = 'cash';
    this.recomputePayerRates();
    this.syncUrl(false);
  }

  /** Refresh each hospital's rate for the selected insurer without re-querying. */
  private recomputePayerRates(): void {
    const payer = this.payer;
    this.results = this.results.map((r) => {
      const mine = payer
        ? r.rates.filter((x) => x.payer === payer && x.rate !== null).map((x) => x.rate!)
        : [];
      return { ...r, payerRate: mine.length ? Math.min(...mine) : null };
    });
  }

  setState(state: string | null): void {
    this.stateFilter = state;
    this.syncUrl(false);
  }

  setSort(sort: SortKey): void {
    this.sort = sort;
    this.syncUrl(false);
  }

  selectHospital(id: string | null, opts: { push?: boolean } = {}): void {
    if (id === this.selectedId) return;
    this.selectedId = id;
    this.syncUrl(opts.push ?? true);
  }

  /** Close the hospital detail, preferring the browser's history entry we created. */
  closeHospital(): void {
    if ((history.state as { pricelight?: boolean } | null)?.pricelight) history.back();
    else this.selectHospital(null, { push: false });
  }

  goHome(): void {
    this.payer = null;
    this.stateFilter = null;
    this.sort = 'cash';
    void this.selectService(null);
  }

  // URL <-> state ------------------------------------------------------------

  applyUrl(search: string, fromPop = true): void {
    const url = readUrl(search);
    const payer = url.payer && this.payers.some((p) => p.name === url.payer) ? url.payer : null;
    if (payer !== this.payer) {
      this.payer = payer;
      this.recomputePayerRates();
    }
    this.stateFilter = url.state && this.states.includes(url.state) ? url.state : null;
    this.sort = url.sort ?? (this.payer ? 'payer' : 'cash');
    const service =
      url.service && this.services.some((s) => s.id === url.service) ? url.service : null;
    const hospital = url.hospital && this.hospitalsById.has(url.hospital) ? url.hospital : null;
    if (service !== this.serviceId || !fromPop) {
      void this.selectService(service, { push: false }).then(() => {
        this.selectedId = hospital;
        this.syncUrl(false);
      });
    } else {
      this.selectedId = hospital;
    }
  }

  private syncUrl(push: boolean): void {
    const next =
      writeUrl({
        service: this.serviceId,
        payer: this.payer,
        state: this.stateFilter,
        sort: this.sort,
        hospital: this.selectedId,
      }) || location.pathname;
    if (next === location.search || (next === location.pathname && !location.search)) return;
    if (push) history.pushState({ pricelight: true }, '', next);
    else history.replaceState(history.state, '', next);
  }
}
