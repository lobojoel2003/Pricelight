// SPDX-License-Identifier: AGPL-3.0-or-later
// Client-side service search: plain words ("knee mri"), codes ("70553",
// "drg 470") and common synonyms. Runs on every keystroke, so it is a
// simple token scorer over a few thousand services, not a full-text index.

import type { Service } from './types';

const SYNONYMS: Record<string, string[]> = {
  xray: ['x-ray'],
  'x-ray': ['xray'],
  cat: ['ct'],
  scan: ['ct', 'mri', 'ultrasound'],
  csection: ['c-section', 'cesarean'],
  'c-section': ['cesarean'],
  cesarean: ['c-section'],
  birth: ['childbirth', 'delivery'],
  labor: ['delivery', 'childbirth'],
  baby: ['delivery', 'pregnancy'],
  ekg: ['ecg'],
  ecg: ['ekg'],
  blood: ['blood test', 'panel'],
  cholesterol: ['lipid'],
  er: ['emergency'],
  colon: ['colonoscopy'],
  knee: ['knee'],
  hip: ['hip'],
  heart: ['cardiac', 'ecg'],
  mammo: ['mammogram'],
  pt: ['physical therapy'],
};

const STOP = new Set([
  'a',
  'an',
  'the',
  'of',
  'for',
  'and',
  'with',
  'my',
  'cost',
  'price',
  'how',
  'much',
]);

export function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[(),./]/g, ' ')
    .split(/\s+/)
    .map((t) => t.replace(/^[^a-z0-9]+|[^a-z0-9-]+$/g, ''))
    .filter((t) => t.length > 0 && !STOP.has(t));
}

interface Indexed {
  service: Service;
  words: string[];
  haystack: string;
  boost: number;
}

export class ServiceIndex {
  private items: Indexed[];

  constructor(services: Service[]) {
    const maxHospitals = Math.max(1, ...services.map((s) => s.hospitals));
    this.items = services.map((service) => {
      const text = [service.label, service.category, service.type, ...service.keywords].join(' ');
      return {
        service,
        words: tokenize(text),
        haystack: text.toLowerCase(),
        boost:
          (service.curated ? 0.6 : 0) + Math.log1p(service.hospitals) / Math.log1p(maxHospitals),
      };
    });
  }

  get size(): number {
    return this.items.length;
  }

  search(query: string, limit = 8): Service[] {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const code = parseCode(q);
    const tokens = tokenize(q);
    const scored: { s: Service; score: number }[] = [];
    for (const item of this.items) {
      let score = 0;
      if (code) {
        if (
          item.service.code.toLowerCase() === code.code &&
          (!code.type || typeMatches(item.service.type, code.type))
        ) {
          score += 100;
        } else if (item.service.code.toLowerCase().startsWith(code.code) && !code.type) {
          score += 20;
        }
      }
      if (score === 0) {
        const tokenScore = scoreTokens(tokens, item);
        if (tokenScore === 0) continue;
        score = tokenScore;
      }
      scored.push({ s: item.service, score: score + item.boost });
    }
    scored.sort((a, b) => b.score - a.score || b.s.hospitals - a.s.hospitals);
    return scored.slice(0, limit).map((x) => x.s);
  }
}

function typeMatches(type: string, wanted: string): boolean {
  const t = type.toLowerCase();
  return t === wanted || (wanted === 'drg' && t.endsWith('drg'));
}

/** "70553", "cpt 70553", "drg 470", "ms-drg 470", "G0121". */
export function parseCode(q: string): { type: string | null; code: string } | null {
  const m = q.match(/^(cpt|hcpcs|drg|ms-drg|msdrg|apr-drg)?[\s:#-]*([a-z]?\d{3,5}[a-z]?)$/i);
  if (!m) return null;
  const rawType = m[1]?.toLowerCase() ?? null;
  const type = rawType === 'msdrg' ? 'ms-drg' : rawType;
  let code = m[2]!.toLowerCase();
  if (type && type.endsWith('drg')) code = code.replace(/^0+/, '').padStart(3, '0');
  return { type, code };
}

function scoreTokens(tokens: string[], item: Indexed): number {
  if (tokens.length === 0) return 0;
  let total = 0;
  for (const token of tokens) {
    const options = [token, ...(SYNONYMS[token] ?? [])];
    if (token.endsWith('s') && token.length > 3) options.push(token.slice(0, -1));
    let best = 0;
    for (const option of options) {
      if (option.includes(' ') || option.includes('-')) {
        if (item.haystack.includes(option)) best = Math.max(best, 3);
        continue;
      }
      for (const word of item.words) {
        if (word === option) best = Math.max(best, 3);
        else if (word.startsWith(option) && option.length >= 2) best = Math.max(best, 2);
        else if (option.length >= 4 && word.includes(option)) best = Math.max(best, 1);
      }
    }
    if (best === 0) return 0; // every token must match something
    total += best;
  }
  return total;
}

/** Wrap matched query words in the label with <mark> segments for display. */
export function highlight(label: string, query: string): { text: string; match: boolean }[] {
  const tokens = tokenize(query).filter((t) => t.length >= 2);
  if (tokens.length === 0) return [{ text: label, match: false }];
  const escaped = tokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const re = new RegExp(`(${escaped.join('|')})`, 'gi');
  return label
    .split(re)
    .filter((part) => part.length > 0)
    .map((part) => ({ text: part, match: tokens.some((t) => part.toLowerCase() === t) }));
}
