# Test-data generation spec

## Objective
Define reproducible generation rules for benchmark datasets.

## Problem slices and generation rules

### Fields to Cover

**Entities and their fields (clean baseline quality):**

Synthetic but **locale-aware** values per `country_iso` (see `country_profiles.yaml`; each profile includes `faker_locale` for generation and **`analyzer_language`** for NLP eval such as Presidio):

- **Names (person):** `Faker` first, optional middle, last name using the profile `faker_locale` (diacritics and multi-part names occur naturally per locale).
- **Organization names:** `Faker.company()` in the same locale (legal-form tokens may appear depending on locale).
- **Addresses:** `street_address`, optional `secondary_address` when supported, `city`, `postcode` from `Faker`; `state` filled from locale-appropriate attributes when `state_required` is true in the profile (full names or abbreviations depending on provider).
- **Email:** `Faker.email()` (or `company_email()` when available for organizations).
- **Phone:** national numbers generated in locale style, parsed and validated with **`phonenumbers`**, stored as **E.164** (`+…`).
- **Postal codes:** produced by the locale’s `postcode` provider (format varies by country).
- **Tax ID (organization):** `vat_id` / `ein` / `cnpj` / `rfc` when exposed by that locale’s Faker; EU profiles with `eu_vat: true` may fall back to **`python-stdnum` EU VAT** validation loop; otherwise a country-appropriate numeric or alphanumeric pattern.
- **Driver license (person):** country-specific synthetic patterns (not DMV-registered values).
- **DUNS:** nine decimal digits (synthetic; not looked up in Dun and Bradstreet).

All values remain **synthetic** (no scraped PII); goal is **format plausibility and cross-country variety**, not registry truth.

#### Person
- first_name
- middle_name
- last_name
- address_line_1
- address_line_2
- city
- postal_code
- country
- country_iso
- state
- email
- phone
- drivers_license_number

#### Organization
- organization_name
- address_line_1
- address_line_2
- city
- postal_code
- country
- country_iso
- state
- email
- phone
- tax_id
- duns_number

### Countries to Cover

| Priority | Country Name         | ISO Code | Region              | GDP (USD, Trillions) |
|----------|----------------------|----------|---------------------|----------------------|
| 1        | United States        | US       | North America       | 26.95                |
| 2        | Germany              | DE       | Western Europe      | 4.43                 |
| 3        | United Kingdom       | GB       | Western Europe      | 3.33                 |
| 4        | France               | FR       | Western Europe      | 2.78                 |
| 5        | Canada               | CA       | North America       | 2.12                 |
| 6        | Italy                | IT       | Southern Europe     | 2.01                 |
| 7        | Brazil               | BR       | South America       | 2.13                 |
| 8        | Spain                | ES       | Southern Europe     | 1.60                 |
| 9        | Mexico               | MX       | North America       | 1.47                 |
| 10       | Netherlands          | NL       | Western Europe      | 1.04                 |
| 11       | Switzerland          | CH       | Western Europe      | 0.92                 |
| 12       | Poland               | PL       | Eastern Europe      | 0.86                 |
| 13       | Sweden               | SE       | Northern Europe     | 0.63                 |
| 14       | Belgium              | BE       | Western Europe      | 0.59                 |
| 15       | Argentina            | AR       | South America       | 0.63                 |
| 16       | Austria              | AT       | Western Europe      | 0.52                 |
| 17       | Norway               | NO       | Western Europe      | 0.55                 |
| 18       | Ireland              | IE       | Western Europe      | 0.53                 |
| 19       | Czechia (Czech Rep.) | CZ       | Eastern Europe      | 0.32                 |
| 20       | Denmark              | DK       | Western Europe      | 0.44                 |
| 21       | Finland              | FI       | Northern Europe     | 0.31                 |
| 22       | Romania              | RO       | Eastern Europe      | 0.31                 |
| 23       | Chile                | CL       | South America       | 0.33                 |
| 24       | Colombia             | CO       | South America       | 0.32                 |
| 25       | Portugal             | PT       | Southern Europe     | 0.27                 |
| 26       | Hungary              | HU       | Eastern Europe      | 0.20                 |
| 27       | Slovakia             | SK       | Eastern Europe      | 0.13                 |
| 28       | Bulgaria             | BG       | Eastern Europe      | 0.09                 |
| 29       | Croatia              | HR       | Eastern Europe      | 0.07                 |
| 30       | Serbia               | RS       | Eastern Europe      | 0.07                 |
| 31       | Slovenia             | SI       | Eastern Europe      | 0.07                 |
| 32       | Lithuania            | LT       | Eastern Europe      | 0.07                 |
| 33       | Latvia               | LV       | Eastern Europe      | 0.04                 |
| 34       | Estonia              | EE       | Eastern Europe      | 0.04                 |
| 35       | Ukraine              | UA       | Eastern Europe      | 0.16                 |


### 1) Misplaced attribute values

#### a) Common Problems: **Person Records**
- **Misplaced personal name components**
  - First, middle, and last names swapped or concatenated in incorrect fields (e.g., last name in given name, given name in family name, middle name combined with first or last name, or all names merged into one field)
  - Variations such as:
    - First and last name reversed
    - Middle name omitted or misplaced
    - All components in the full name field with others blank
    - Parts split across fields incorrectly (e.g., first part of last name in given name field)
    - Double-barreled or multi-part names distributed inconsistently  
- **Contact info in name fields**  
  - Email address in given/family/full name
  - Phone number in first/last/full name
  - Street address or postal code in name fields
- **Demographics in wrong fields**
  - Gender, marital status, or titles (e.g., "Mr.", "Married", "Single") in name fields
  - Date of birth in address fields or company fields
- **Role/occupation confusion**
  - Job titles or roles (e.g., "CEO", "Doctor") in name or address fields
- **Status labels as names or IDs**
  - "Inactive", "Active", "Prospect", "Customer" in person name or ID fields
- **Social handles or URLs in PII fields**
  - Twitter handles in name, email, or address fields
  - LinkedIn URLs in phone or name fields
- **Numeric values in text-only fields**
  - Numbers or codes in name fields (e.g., "123" as a first name)
- **Fake or clearly invalid phone numbers in name or phone fields**
  - Obvious non-phone patterns: "12345678", "123", "99999999", "11111111", "00000000", repetitive digits, "55555555"
  - Sequential or placeholder patterns: "123456789", "987654321", "00012345", "11223344"
  - Non-numeric or partial strings: "abcdefg", "phone", "notaphone", just special characters (e.g., "---------")
  - Numbers too short or too long for actual phone formats (e.g., 1-3 digits, 20+ digits)
  - Country-specific unlikely phone formats (e.g., "00000000" in countries with strict number assignments)
**Geographic info in contact/ID fields**  
  - Country, city, or state names/abbreviations in phone or ID fields
- **Cross-field bleeding**
  - Organization name in individual’s name fields (e.g., "John Google" as full name)

#### b) Common Problems: **Organization Records**
- **Contact info in org name/address fields**
  - Email addresses or phone numbers as organization name or address line
  - Contact person name ("Jane Doe") as organization name
- **Registration/ID confusion**
  - Tax ID, DUNS, or VAT numbers in name or address
- **Address or location in wrong fields**
  - Country/state/city/postal code in organization name or ID fields
  - Building/room numbers in wrong segments
- **Business type/status in name fields**
  - "LLC", "Inc.", "GmbH", or status like "Closed" or "Pending" in main org name instead of dedicated type/status attribute
- **Website or social handles in address or name**
  - Organization website entered as address or name
- **Department/division in address field**
  - Specific department or business unit placed in address rather than in separate division attribute
- **Ambiguous org/person blending**
  - Team or group name where only a legal entity is expected
  - "HR Department" or "Sales Director" in company name field

#### c) Shared / Mixed Issues
- **Free-text notes in structured fields**
  - Notes or explanations in name/address/ID ("Moved office 2022", "Pending verification")
- **Ambiguous or composite values**
  - Multiple distinct items packed into one field with delimiters:  
    - "John/Mary Smith", "ACME Corp. / ABC Inc."
- **Encoding errors or language mismatches**
  - Non-ASCII or non-local script in fields with strict format requirements
- **Blank, null, or default values placed incorrectly**
  - Empty strings, "N/A", or system defaults substituting for real attributes
- **Missing premise / house number on an otherwise real street line**
  - Strip a house or block number from `address_line_1` and/or `address_line_2` when one is present (`MIS_ADDR_STRIP_PREMISE`). Street-only Faker lines (no number to remove) stay clean-shaped and do not receive this label.
- Inject values into wrong attributes by controlled patterns.

#### Dirt labels (machine-readable)

Stable IDs for validation and for `dirt_label_ids` / `dirt_distribution.csv`. `maps_to` uses headings in this section (1a Person, 1b Organization, 1c Shared).

| dirt_label_id | maps_to | entity_scope | notes |
| --- | --- | --- | --- |
| MIS_NAME_SWAP_FL | 1a / Misplaced personal / First and last reversed | person | Swap `first_name` and `last_name`. |
| MIS_NAME_MIDDLE_TO_FIRST | 1a / Middle misplaced | person | Move `middle_name` into `first_name`; clear `middle_name`. |
| MIS_NAME_MERGE_ALL_FIRST | 1a / All components in one field | person | Set `first_name` to concatenation of names; clear `middle_name`, `last_name`. |
| MIS_NAME_SPLIT_WRONG | 1a / Parts split incorrectly | person | Put part of `last_name` into `first_name`. |
| MIS_NAME_HYPHEN_INCONSISTENT | 1a / Double-barreled inconsistent | person | Split hyphenated last across `first_name` and `last_name` incorrectly. |
| MIS_EMAIL_IN_FIRST | 1a / Contact / Email in given | person | Copy `email` into `first_name`. |
| MIS_EMAIL_IN_LAST | 1a / Contact / Email in family | person | Copy `email` into `last_name`. |
| MIS_PHONE_IN_FIRST | 1a / Contact / Phone in first | person | Copy `phone` into `first_name`. |
| MIS_ADDR_LINE_IN_FIRST | 1a / Street in name | person | Copy `address_line_1` into `first_name`. |
| MIS_POSTAL_IN_FIRST | 1a / Postal in name | person | Copy `postal_code` into `first_name`. |
| MIS_TITLE_IN_FIRST | 1a / Demographics / title in name | person | Set `first_name` to a locale honorific (`Mr.` / `Herr` / …). |
| MIS_DOB_IN_ADDRESS2 | 1a / DOB in address | person | Set `address_line_2` to a random date-like string. |
| MIS_JOB_IN_FIRST | 1a / Role in person name | person | Set `first_name` to a locale job title. |
| MIS_STATUS_IN_FIRST | 1a / Status label in name | person | Set `first_name` to a locale status token (Active / Inactive / …). |
| MIS_TWITTER_IN_FIRST | 1a / Social handle in name | person | Set `first_name` to a generated `@handle`. |
| MIS_LINKEDIN_IN_PHONE | 1a / LinkedIn in phone | person | Set `phone` to a generated LinkedIn URL. |
| MIS_NUMERIC_FIRST | 1a / Numeric in name | person | Set `first_name` to a numeric token from a small pool. |
| MIS_FAKE_PHONE_SHORT | 1a / Fake phone | person | Set `phone` to a short fake digit string from a pool. |
| MIS_FAKE_PHONE_REPEAT | 1a / Fake phone repeat | person | Set `phone` to a repeating fake digit string from a pool. |
| MIS_PHONE_NONNUMERIC | 1a / Non-numeric phone | person | Set `phone` to a locale “not a phone/email” phrase. |
| MIS_CITY_IN_PHONE | 1a / Geo in phone | person | Set `phone` to `city:` + `city`. |
| MIS_STATE_IN_DL | 1a / Geo in ID | person | Replace `drivers_license_number` with `{state}-{drivers_license_number}`. |
| MIS_ORG_TOKEN_IN_FIRST | 1a / Company in given name | person | Set `first_name` to a locale `company()` name (CRM paste). |
| MIS_ORG_EMAIL_AS_NAME | 1b / Email as org name | organization | Set `organization_name` to `email`. |
| MIS_ORG_PHONE_AS_NAME | 1b / Phone as org name | organization | Set `organization_name` to `phone`. |
| MIS_ORG_CONTACT_AS_NAME | 1b / Contact person as org name | organization | Set `organization_name` to a locale person name from Faker. |
| MIS_ORG_TAX_IN_ADDRESS1 | 1b / Tax ID in address | organization | Copy `tax_id` into `address_line_1`. |
| MIS_ORG_DUNS_IN_CITY | 1b / DUNS in city | organization | Copy `duns_number` into `city`. |
| MIS_ORG_COUNTRY_IN_NAME | 1b / Location in name | organization | Replace `organization_name` with `country`. |
| MIS_ORG_POSTAL_IN_NAME | 1b / Postal in name | organization | Replace `organization_name` with `postal_code`. |
| MIS_ORG_WEBSITE_AS_ADDRESS | 1b / Website as address | organization | Set `address_line_1` to a URL from a pool. |
| MIS_ORG_DEPT_IN_ADDRESS2 | 1b / Department in address | organization | Set `address_line_2` to a locale department phrase. |
| MIS_ORG_TEAM_AS_NAME | 1b / Team as legal name | organization | Set `organization_name` to a locale team phrase. |
| MIS_ORG_STATUS_IN_NAME | 1b / Status in name | organization | Replace `organization_name` with a locale status token. |
| MIS_JOB_IN_ORG_NAME | 1b / Role as org name | organization | Set `organization_name` to a locale job title. |
| MIS_NOTE_IN_ADDRESS1 | 1c / Free-text notes | both | Replace `address_line_1` with a locale note template. |
| MIS_ADDR_STRIP_PREMISE | 1c / Missing premise number | both | Strip house/premise tokens from `address_line_1` and `address_line_2` when present; `fields_affected` lists only lines that changed. |
| MIS_COMPOSITE_FIRST | 1c / Composite delimiter | person | Set `first_name` to a slash-joined name pair. |
| MIS_COMPOSITE_ORG_NAME | 1c / Composite delimiter | organization | Set `organization_name` to a slash-joined org pair. |
| MIS_NA_IN_CITY | 1c / N/A in structured field | both | Set `city` to a locale/global N/A token. |
| MIS_INVALID_EMAIL_NO_AT | 1c / Invalid email | both | Set `email` to a non-address phrase (`not_email` pool). |
| MIS_INVALID_EMAIL_MALFORMED | 1c / Malformed email | both | Set `email` to a syntactically invalid mailbox. |
| MIS_INVALID_TAX_NOT_ID | 1c / Not a tax id | organization | Set `tax_id` to a `not_tax` phrase. |
| MIS_INVALID_TAX_MALFORMED | 1c / Malformed tax | organization | Set `tax_id` to a malformed identifier. |


### 2) Anonymous and placeholder values
- Inject placeholder variants:
  - unknown,
  - tba,
  - no name,
  - test,
  - no address.
- Include spelling and formatting variants and translations for each conutry. 
- single character or special character.

#### Dirt labels (machine-readable)

| dirt_label_id | maps_to | entity_scope | application_mode | notes |
| --- | --- | --- | --- | --- |
| PH_UNKNOWN_REPLACE_FIRST | 2 / unknown variant | person | replace | Locale/global unknown token in `first_name`. |
| PH_TBA_SUFFIX_LAST | 2 / tba | person | replace | Locale TBA/TBD token in `last_name`. |
| PH_NO_NAME_REPLACE_FIRST | 2 / no name | person | replace | Locale “no name” token in `first_name`. |
| PH_TEST_PREFIX_EMAIL | 2 / test | both | replace | Test mailbox from a `*.invalid` pool. |
| PH_NO_ADDRESS_REPLACE_LINE1 | 2 / no address | person | replace | Locale “no address” in `address_line_1`. |
| PH_NULL_STRING_FIRST | 2 / system token | person | replace | Set `first_name` to `NULL`. |
| PH_DASH_REPLACE_FIRST | 2 / dash token | person | replace | Set `first_name` to `-`. |
| PH_DOT_REPLACE_FIRST | 2 / dot token | person | replace | Set `first_name` to `.`. |
| PH_SINGLE_CHAR_FIRST | 2 / single character | person | replace | Set `first_name` to `?`. |
| PH_SPACE_ONLY_FIRST | 2 / whitespace | person | replace | Set `first_name` to one space. |
| PH_NA_REPLACE_EMAIL | 2 / N/A email | both | replace | Locale/global N/A in `email`. |
| PH_NULL_REPLACE_EMAIL | 2 / NULL email | both | replace | `NULL` in `email`. |
| PH_UNKNOWN_REPLACE_EMAIL | 2 / unknown email | both | replace | Locale unknown token in `email`. |
| PH_UNKNOWN_REPLACE_ORG | 2 / unknown in org name | organization | replace | Locale/global unknown in `organization_name`. |
| PH_TBD_REPLACE_ORG | 2 / tbd | organization | replace | Locale TBD in `organization_name`. |
| PH_NA_REPLACE_CITY | 2 / na in city | organization | replace | Locale/global N/A in `city`. |
| PH_TEST_REPLACE_PHONE | 2 / test in phone | organization | replace | Set `phone` to `test`. |
| PH_DOT_REPLACE_TAX | 2 / dot in tax | organization | replace | Set `tax_id` to `.`. |
| PH_SINGLE_CHAR_DUNS | 2 / single char in duns | organization | replace | Set `duns_number` to `0`. |
| PH_NA_REPLACE_TAX | 2 / N/A tax | organization | replace | Locale/global N/A in `tax_id`. |
| PH_NULL_REPLACE_TAX | 2 / NULL tax | organization | replace | `NULL` in `tax_id`. |
| PH_NOVAT_REPLACE_TAX | 2 / no VAT | organization | replace | Locale “no VAT” phrase in `tax_id`. |

### 3) Person vs organization confusion
- Mix person-like tokens and organization-like names.
- Include ambiguous edge cases and abbreviations.

## Label schema
- `semantic_class_expected`
- `attribute_intent`
- `is_mismatch_expected` (true/false)
- `is_placeholder_expected` (true/false)
- `confidence_note` (optional reviewer note)

## Split policy
- Keep class distribution stable across train, validation, and test.
- Keep hard edge cases in validation and test.

## Reproducibility
- Record seed values and generation parameters for each dataset version.

## Clean golden dataset

### Purpose
Provide a clean-only baseline dataset package for all listed countries, with no injected mismatches or placeholder values.

### Artifacts
- Specification: `clean_dataset_spec.md`
- Country profiles: `country_profiles.yaml` (quoted ISO keys); dependencies: `requirements-test-data.txt`
- Token pools: `placeholder_lexicon.yaml` (used by dirt generation)
- Generator script: `scripts/generate_clean_country_party_data.py`
- Output files (folder is the version; names are unversioned):
  - `clean_person_name.csv`
  - `clean_organization_name.csv`
  - `clean_person_address.csv`
  - `clean_organization_address.csv`
  - `clean_person_email.csv`
  - `clean_organization_email.csv`
  - `clean_person_phone.csv`
  - `clean_organization_phone.csv`
  - `clean_drivers_license_number.csv`
  - `clean_tax_id.csv`
  - `clean_duns_number.csv`

### Contract summary
- Join keys: `record_id`, `country_iso`
- Address files include `country` as a data column.
- **Entity-scoped splits**: person-only CSVs have 500 rows per `country_iso` (17,500 total); organization-only CSVs have 500 rows per `country_iso` (17,500 total). Merge consumers load person vs organization email/phone separately and join on keys.
- **Phones:** unique valid E.164 per `country_iso` in each phone file (500 uniques); no lone libphonenumber example fallback; digit strings must not contain spec fake runs.
- **Email:** a hashed subset uses plus-addressing (`local+tag@domain`). Non-ASCII (EAI) local-parts are not in this corpus.
- **Tax:** valid format aliases (spaces/dashes/compact) stay **clean**. Placeholders and malformed values are dirt only.
- **Serbia (RS):** Faker has no `sr_RS`. Names/addresses use Croatian `hr_HR` as a documented South-Slavic Latin-script **proxy** (not Serbian). Omit RS from locale name/address eval if the proxy would corrupt metrics. `phone_region` remains RS.

## Dirty synthetic dataset

### Purpose
Provide **misplaced-value** and **placeholder** dirt on top of the clean golden package for model training and evaluation. Rows are **derived from clean CSVs** (same `record_id` and `country_iso`). Labels are **traceable** to `dirt_label_id` values listed under [Misplaced attribute values](#1-misplaced-attribute-values) and [Anonymous and placeholder values](#2-anonymous-and-placeholder-values).

Surface strings vary via `placeholder_lexicon.yaml` and Faker; gold maps `dirt_label_id` → contaminant types (never an empty list). `MIS_NONASCII_IN_EMAIL_LOCAL` is **not** in this version.

**Replace-only** application (see below).

### Application modes

| Mode | v2 |
| --- | --- |
| `replace` | **Allowed** — entire field value after the event is the dirty literal (cross-field copy, full placeholder, name rearrangements, composite delimiters) |
| `prefix`, `suffix`, `append` | **Not allowed** — no preserving prior cell text and prepending/appending |

A replace may construct a new string from multiple source fields (e.g. swapped names); it must not leave the original cell content intact as a separate segment (e.g. no `street; note` suffix patterns).

**Secondary events:** with probability **0.25** a second independent event may fire; if both touch the same field, the later event wins (last-writer-wins).

### Artifacts
- `dirty_person.csv` — 17,500 person rows (500 per country; half of the 1,000 clean rows per country are persons).
- `dirty_organization.csv` — 17,500 organization rows (500 per country).
- `dirt_distribution.csv` — planned sampling weights and post-generation `actual_count` per label (`dataset_version=v2`).
- `taxonomy/` — `semantic_types.yaml`, `field_intent.yaml`, `dirt_label_to_types.yaml`
- `eval_gold.csv` — rebuilt by `scripts/build_eval_gold.py` (gitignored)
- Generator script: `scripts/generate_dirty_party_data.py` (Python 3.12+).

### Row construction
1. Load clean split files (`clean_*.csv`) and merge on `record_id`, `country_iso`.
2. **Person** file: rows where `first_name` is non-empty in `clean_person_name.csv`. **Organization** file: rows where `organization_name` is non-empty in `clean_organization_name.csv`.
3. For each row, sample one **primary** dirt event, then with probability **0.25** a **secondary** independent event (same sampling rules). With probability **0.95** at least one event fires; if no event sampled, apply one fallback placeholder label so labels are dense for benchmarking.
4. **Family mix**: before each event, choose `misplacement` with probability **0.6** and `placeholder` with probability **0.4**. Within the family, choose `dirt_label_id` proportional to `sampling_weight` in `dirt_distribution.csv` for that `entity_type` and `country_iso` stratum (`ALL` = global).
5. Apply transforms and append label metadata.

### File schemas

#### `dirty_person.csv` and `dirty_organization.csv`
- **Identity**: `record_id`, `country_iso`, `country`
- **Entity fields**: full set from [Fields to Cover](#fields-to-cover) for that entity (blank where not applicable, same as clean).
- **Labels**:
  - `dirt_label_ids` — semicolon-separated list of `dirt_label_id` applied on the row (order matches application order).
  - `dirt_events_json` — JSON array of objects: `dirt_label_id`, `dirt_family`, `fields_affected`, `application_mode`, `detail` (short string; no full clean-value dump).

#### `dirt_distribution.csv`
| column | description |
| --- | --- |
| `dataset_version` | e.g. `dirty_v2` |
| `entity_type` | `person` or `organization` |
| `dirt_family` | `misplacement` or `placeholder` |
| `dirt_label_id` | must match registry in this document |
| `target_scope` | `field` or `record` |
| `fields_affected_pattern` | semicolon list or `ALL` |
| `country_iso` | `ALL` or specific ISO (stratum) |
| `sampling_weight` | relative weight within (`entity_type`, `dirt_family`, `country_iso`) |
| `planned_primary_rate` | optional; intended fraction of rows with this label as primary event |
| `actual_count` | filled by generator after run |
| `notes` | maps_to / heading reference |

**Normalization**: within each stratum (`entity_type`, `dirt_family`, `country_iso`), weights are normalized to sum to 1 before sampling.

### Validation gates
- Row counts: 17,500 per dirty file; 500 per `country_iso` in each file.
- Every row has non-empty `dirt_label_ids` and parseable `dirt_events_json`.
- Every `dirt_events_json` event has `application_mode` = `replace`.
- A dirt event is kept only if at least one field value changed (no-op transforms are resampled, then fallback).
- Every `dirt_label_id` in outputs appears in the registries above.
- `actual_count` in `dirt_distribution.csv` matches row-level counts (per stratum) within integer tolerance 0.

### Reproducibility
- Generator uses a fixed seed (`SEED = 481` in `generate_dirty_party_data.py`) unless overridden.
- Document seed and `dataset_version` when freezing a benchmark.
