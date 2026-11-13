# Data model

## Normalized charges (parser output)

One row per item/service × standard-charge entry × payer/plan. Rows that
carry only item-level prices have `payer_name = NULL`. Schema version: `1`
(`pricelight_parser.SCHEMA_VERSION`).

| Column | Type | Source (JSON / CSV) |
|---|---|---|
| `item_index` | int64 | position of the item in the JSON array / CSV line number |
| `description` | string | `description` |
| `code` | string | primary billing code (see priority below) |
| `code_type` | string | its code type, normalized to the CMS valid values |
| `codes` | list<struct<code, type>> | every `code_information` / `code\|i` pair |
| `setting` | string | `inpatient`, `outpatient`, `both` (abbreviations normalized) |
| `billing_class` | string | optional `billing_class` |
| `modifiers` | list<string> | `modifier_code` (v3), `modifiers` (v2 / CSV) |
| `drug_unit`, `drug_type` | float64, string | `drug_information` / `drug_*_of_measurement` |
| `gross_charge` | float64 | `gross_charge` / `standard_charge\|gross` |
| `discounted_cash` | float64 | `discounted_cash` / `standard_charge\|discounted_cash` |
| `min_negotiated`, `max_negotiated` | float64 | `minimum`/`maximum` / `standard_charge\|min`/`max` |
| `payer_name`, `plan_name` | string | payer columns or wide header placeholders |
| `negotiated_dollar` | float64 | `standard_charge_dollar` / `…\|negotiated_dollar` |
| `negotiated_percentage` | float64 | `standard_charge_percentage` / `…\|negotiated_percentage` |
| `negotiated_algorithm` | string | `standard_charge_algorithm` / `…\|negotiated_algorithm` |
| `methodology` | string | `case rate`, `fee schedule`, `percent of total billed charges`, `per diem`, `other` |
| `estimated_amount` | float64 | v2 `estimated_amount` |
| `median_amount`, `p10_amount`, `p90_amount` | float64 | v3 allowed amounts |
| `allowed_count` | string | v3 `count` (`"0"`, `"1 through 10"`, or a number) |
| `additional_generic_notes`, `additional_payer_notes` | string | notes columns |

**Primary code priority:** MS-DRG, APR-DRG, DRG, AP-DRG, APS-DRG, R-DRG,
S-DRG, TRIS-DRG, MS-LTC-DRG, CPT, HCPCS, CDT, NDC, APC, EAPG, HIPPS, CMG, ICD,
RC, CDM, LOCAL. Grouping codes beat procedure codes, which beat internal
chargemaster codes.

**Code normalization:** types are upper-cased and mapped from common variants
(`MSDRG`, `MS DRG` → `MS-DRG`; `REV CODE` → `RC`; `CPT4` → `CPT`). DRG codes
become three digits (`0470` → `470`), revenue codes four (`120` → `0120`).

The parse summary (header, stats, issues, parser version) is stored in the
Parquet key-value metadata under the key `pricelight`; read it with
`pricelight_parser.read_result_metadata(path)`.

## Issue codes

Errors make a file unusable for some purpose; warnings are repairs or
missing optional data. Examples:

| Code | Severity | Meaning |
|---|---|---|
| `missing-hospital-name`, `missing-last-updated`, `missing-version` | error | required header element absent |
| `missing-attestation` | error | no attestation / affirmation statement |
| `payer-without-charge` | error | payer entry with no dollar, percentage or algorithm |
| `no-charge-values` | error | item with no price of any kind |
| `invalid-json` | error | the JSON is malformed (rows read so far are kept) |
| `formatted-number` | warning | `$`, `,` or spaces inside a numeric field |
| `non-numeric-value` | warning | text such as `abc` in a numeric field |
| `nonstandard-code-type`, `unknown-code-type` | warning | code type normalized / not a CMS value |
| `nonstandard-setting`, `invalid-setting` | warning | setting abbreviated / not a CMS value |
| `missing-min-max` | warning | dollar rates without de-identified min/max |
| `other-methodology-without-notes` | warning | methodology "other" with no explanation |
| `missing-allowed-amounts`, `missing-allowed-count` | warning | v3 percentage/algorithm contract without allowed amounts |
| `missing-type-2-npi`, `missing-attester-name` | warning | v3 header elements absent |
| `no-discounted-cash` | warning | the whole file lists no cash prices |

## Site dataset (`pricelight build` output)

| File | Contents |
|---|---|
| `meta.json` | schema version, generation time, `demo` flag, pipeline/parser versions, counts, build info (version, build number, commit) |
| `hospitals.json` | id, name, address, lat/lon, links, file facts (format, template version, last updated, size, sha256), service/payer counts, quality summary |
| `services.json` | `id` (`CPT:70553`), type, code, label, category, keywords, hospitals offering it, cash-price stats, median insurer rate |
| `payers.json` | normalized payer names with hospital and plan counts |
| `prices.parquet` | see below; Snappy-compressed, sorted by `service`, 8,192-row groups |

`prices.parquet` has two kinds of rows per service × hospital:

| Column | Item row (`payer IS NULL`) | Payer row |
|---|---|---|
| `service`, `hospital`, `setting` | ✓ | ✓ |
| `payer`, `plan` | `NULL` | normalized payer, plan |
| `rate`, `rate_basis` | `NULL` | median negotiated dollar (`dollar`), else median/estimated allowed amount (`allowed`) |
| `pct`, `algorithm`, `methodology` | `NULL` | contract details |
| `gross`, `cash` | median gross / cash | `NULL` |
| `min`, `max` | reported min/max (else derived from dollar rates) | `NULL` |
| `description` | the hospital's own description | `NULL` |
