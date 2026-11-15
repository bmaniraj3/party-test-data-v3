# Clean dataset specification (v2)

## Purpose and scope
This specification defines the clean golden dataset package for Party Data Classification test data.
The package contains clean-only synthetic records for all countries listed in `countries.csv`, with no injected mismatches or placeholder values.

## Inputs
- `countries.csv` in the same folder
- `country_profiles.yaml` in the same folder (per-ISO Faker locale, phone region, `state_required`, `eu_vat` flag)
- Field definitions in `generation-spec.md` (`Fields to Cover`)

## Output files
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

## Join keys
Shared join keys in every file:
- `record_id`
- `country_iso`

## Row volume
- 1,000 synthetic records per country in the unified generator (500 person + 500 organization per `country_iso`).
- 35 countries.
- **Entity-scoped files**: each CSV contains rows **only** for that entity type. Person-only files have **17,500** rows total (500 × 35 countries); organization-only files have **17,500** rows total (500 × 35 countries). There is no cross-entity padding with empty rows.

## Entity distribution
- 50% person records and 50% organization records in the overall population (per country).
- Each output file holds exclusively person rows or exclusively organization rows (for example, `clean_tax_id.csv` has only organization records; `clean_drivers_license_number.csv` has only person records).

## Per-file schemas

### `clean_person_name.csv`
- `record_id`
- `country_iso`
- `first_name`
- `middle_name`
- `last_name`

### `clean_organization_name.csv`
- `record_id`
- `country_iso`
- `organization_name`

### `clean_person_address.csv`
- `record_id`
- `country_iso`
- `country`
- `address_line_1`
- `address_line_2`
- `city`
- `postal_code`
- `state`

### `clean_organization_address.csv`
- `record_id`
- `country_iso`
- `country`
- `address_line_1`
- `address_line_2`
- `city`
- `postal_code`
- `state`

### `clean_person_email.csv`
- `record_id`
- `country_iso`
- `email` — ASCII mailbox; a hashed subset uses plus-addressing (`local+tag@domain`). Not junk.

### `clean_organization_email.csv`
- `record_id`
- `country_iso`
- `email` — same rules as person email

### `clean_person_phone.csv`
- `record_id`
- `country_iso`
- `phone` — **E.164** string (leading `+`), validated with `phonenumbers` as a plausible national number for the profile `phone_region`. **500 unique values per `country_iso`**. Digit strings must not contain spec fake runs (`123456789`, `11111111`, …). Generation must not emit a lone libphonenumber example number as the fallback value.

### `clean_organization_phone.csv`
- `record_id`
- `country_iso`
- `phone` — same validation and uniqueness rules as person phone (500 uniques per ISO in this file)

### `clean_drivers_license_number.csv`
- `record_id`
- `country_iso`
- `drivers_license_number` — **country-specific** synthetic value per `country_iso` (see `scripts/drivers_license_formats.py`). Generator asserts each value passes the module’s per-country validator; values are **not** issued by any authority.

### `clean_tax_id.csv`
- `record_id`
- `country_iso`
- `tax_id` — valid identifier with **format variants** (compact, hyphen, spaced groups). Aliases remain clean `identifier_tax`. Placeholders and malformed strings are dirt, not clean.

### `clean_duns_number.csv`
- `record_id`
- `country_iso`
- `duns_number` — exactly **9 decimal digits** (synthetic identifier; not a D&B registry lookup)

## Serbia (RS)
Faker has no `sr_RS`. v2 uses Croatian `hr_HR` for names and addresses: nearest built-in South Slavic Latin-script locale. That is a **proxy**, not Serbian (different standard language, typically no Cyrillic, Croatian place names). If that mix corrupts per-country name/address evaluation, omit Serbia from those slices. Phone/tax/DL may still be RS-specific (`phone_region: RS`).

## Validation and acceptance criteria
- Exactly **17,500** rows in each person-only file; exactly **17,500** rows in each organization-only file
- Exactly **500** rows per `country_iso` in person-only files; exactly **500** rows per `country_iso` in organization-only files
- No blank values in required join keys (`record_id`, `country_iso`)
- No blank values in `email` for `clean_person_email.csv` and `clean_organization_email.csv`
- No blank values in `phone` for `clean_person_phone.csv` and `clean_organization_phone.csv`; each value must be valid **E.164** (`+` prefix) and pass `phonenumbers` validation
- **500 unique phones per `country_iso` in each phone file** (all 35 countries)
- No blank values in `address_line_1`, `city`, `postal_code` for populated address rows
- Where `country_profiles.yaml` sets `state_required: true` for an ISO, populated person and organization address rows for that ISO must have a **non-blank** `state`
- `country` and `country_iso` combinations must match `countries.csv`
- No placeholder tokens: `unknown`, `tba`, `no name`, `test`, `no address`, `n/a`
- `drivers_license_number` in `clean_drivers_license_number.csv` must pass `drivers_license_formats.is_valid_drivers_license(country_iso, value)` (checksums / regexes per country)

## Versioning and reproducibility
- Dataset version: `v2` (this folder)
- Generation script uses a fixed random seed (`SEED` in `scripts/generate_clean_country_party_data.py`) combined with a **SHA-256** per-country seed mix (not Python `hash()`, which is randomized on Windows)
- Python dependencies for generation: see `requirements-test-data.txt` (`faker`, `phonenumbers`, `python-stdnum`, `PyYAML`)
- Script records output counts and validation summaries to stdout
