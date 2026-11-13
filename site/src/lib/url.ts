// SPDX-License-Identifier: AGPL-3.0-or-later
// Shareable URL state: ?service=CPT:70553&payer=...&state=TX&sort=cash&hospital=<id>

import type { SortKey } from './types';

export interface UrlState {
  service: string | null;
  payer: string | null;
  state: string | null;
  sort: SortKey | null;
  hospital: string | null;
}

const SORTS: SortKey[] = ['cash', 'payer', 'median', 'name'];

export function readUrl(search: string): UrlState {
  const p = new URLSearchParams(search);
  const sort = p.get('sort');
  const state = p.get('state');
  return {
    service: p.get('service'),
    payer: p.get('payer'),
    state: state && /^[A-Za-z]{2}$/.test(state) ? state.toUpperCase() : null,
    sort: sort && (SORTS as string[]).includes(sort) ? (sort as SortKey) : null,
    hospital: p.get('hospital'),
  };
}

export function writeUrl(state: UrlState): string {
  const p = new URLSearchParams();
  if (state.service) p.set('service', state.service);
  if (state.payer) p.set('payer', state.payer);
  if (state.state) p.set('state', state.state);
  if (state.sort && state.sort !== 'cash') p.set('sort', state.sort);
  if (state.hospital) p.set('hospital', state.hospital);
  const qs = p.toString();
  return qs ? `?${qs}` : '';
}
