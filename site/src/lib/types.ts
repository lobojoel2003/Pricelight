// SPDX-License-Identifier: AGPL-3.0-or-later
// Shapes of the dataset files written by `pricelight build`.

export interface BuildInfo {
  version?: string;
  build_number?: string;
  commit?: string;
}

export interface Meta {
  name: string;
  schema_version: number;
  generated_at: string;
  demo: boolean;
  pipeline_version: string;
  parser_version: string;
  counts: {
    hospitals: number;
    services: number;
    payers: number;
    price_rows: number;
    states: number;
  };
  build: BuildInfo;
}

export interface QualityIssue {
  code: string;
  severity: 'error' | 'warning';
  message: string;
  count: number;
}

export interface Hospital {
  id: string;
  name: string;
  address: string;
  city: string;
  state: string;
  zip: string;
  lat: number | null;
  lon: number | null;
  website: string | null;
  source_page_url: string | null;
  mrf_url: string | null;
  file: {
    name: string;
    format: 'json' | 'csv-tall' | 'csv-wide';
    compression: string | null;
    bytes: number;
    template_version: string | null;
    last_updated: string | null;
    sha256: string;
  };
  services: number;
  services_with_cash: number;
  payers: number;
  quality: {
    attestation: boolean | null;
    errors: number;
    warnings: number;
    issues: QualityIssue[];
  };
}

export interface PriceStats {
  median: number;
  min: number;
  max: number;
}

export interface Service {
  id: string; // "CPT:70553"
  type: string;
  code: string;
  label: string;
  category: string;
  keywords: string[];
  curated: boolean;
  hospitals: number;
  with_cash: number;
  cash: PriceStats | null;
  rate_median: number | null;
}

export interface Payer {
  name: string;
  hospitals: number;
  plans: number;
}

/** One row of prices.parquet. */
export interface PriceRow {
  service: string;
  hospital: string;
  setting: string | null;
  payer: string | null;
  plan: string | null;
  rate: number | null;
  rate_basis: 'dollar' | 'allowed' | null;
  pct: number | null;
  algorithm: string | null;
  methodology: string | null;
  gross: number | null;
  cash: number | null;
  min: number | null;
  max: number | null;
  description: string | null;
}

export interface PayerRate {
  payer: string;
  plan: string | null;
  rate: number | null;
  basis: 'dollar' | 'allowed' | null;
  pct: number | null;
  algorithm: string | null;
  methodology: string | null;
}

/** All prices one hospital lists for the selected service. */
export interface HospitalPrices {
  hospital: Hospital;
  setting: string | null;
  description: string | null;
  gross: number | null;
  cash: number | null;
  /** De-identified minimum / maximum negotiated charge (file-reported or derived). */
  min: number | null;
  max: number | null;
  rates: PayerRate[];
  rateMedian: number | null;
  /** Lowest rate across the selected insurer's plans, if an insurer is selected. */
  payerRate: number | null;
}

export type SortKey = 'cash' | 'payer' | 'median' | 'name';
export type MapMetric = 'cash' | 'payer' | 'median';
