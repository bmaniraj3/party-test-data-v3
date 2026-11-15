# Student questions (stable IDs)

Answers for the party-data classification practicum. Dataset changelog: [../self-research/test-data/CHANGELOG.md](../self-research/test-data/CHANGELOG.md).

## GT-01 — Non-ASCII email in dirt vs gold

**Original Q:** EMAILS --> There is one place where the two label sources disagree, and it affects how we should score email detectors. The dirt type MIS_NONASCII_IN_EMAIL_LOCAL (e.g. record AR-014550: "vargasjuan-ignacioé@ojeda.com.ar") is recorded as applied dirt in dirt_label_ids in the dirty files, but in eval_gold.csv those same emails have empty contaminant_types, meaning they are labeled clean. Is that intentional (internationalized emails being technically valid)?

**Q:** Why did some dirty emails with non-ASCII local-parts have empty `contaminant_types` in gold?

**A:** In v1 that pattern (`MIS_NONASCII_IN_EMAIL_LOCAL`) was generated as “dirt” but gold treated EAI/UTF-8 local-parts as still `email` (empty extra types). That was a trap: **dirt must be something a detector should flag**. Internationalized email is still email, not junk. **v2 removes that dirt ID.** We do not add EAI as a clean pattern either (rare in this MDM slice). Not junk; not in the corpus.

## GT-02 — Plus-addressing / unusual valid email

**Original Q:** EMAILS --> What is the product's ruling on emails that are syntactically unusual but technically valid, like non-ASCII local parts or plus-addressing (test+something@something.com)? We want to make sure our detectors and metrics reflect what you would actually consider junk.

**Q:** Are plus-addressed or unusual-but-valid emails junk?

**A:** **No.** Plus-addressing (`user+tag@domain`) is valid and appears on a hashed **clean** subset in v2. Shared `info@` mailboxes are still email (matching trust), not dirt. Non-ASCII local-parts are valid in principle (EAI) but are **not** in this corpus and are **not** dirt.

| Pattern | Junk? | In v2? |
| --- | --- | --- |
| Plus-addressing | No | Clean subset |
| Non-ASCII local-part | No | Not in corpus; not dirt |
| Placeholders / invalid syntax | Yes | Dirt |
| Shared `info@` | No | Not dirt |

## GT-03 — Identical phones for AR / EE / IE

**Original Q:** PHONES --> All 500 Argentine person phones (and all 500 organization phones) are the identical number +5491123456789 - which also contains the sequential run "123456789" that the generation spec itself lists as a fake-phone pattern. Estonia has only 12 unique phone numbers per file, Ireland 360 of 500. Should we exclude AR, EE and IE from phone-field metrics?

**Q:** Should we drop Argentina, Estonia, and Ireland from phone metrics?

**A:** **Not as product policy.** Those slices were broken in **v1 generation**, not as markets. Faker often failed regional validation, then every row used libphonenumber’s **single** example mobile number. AR’s example contains sequential `123456789`; the clean validator only rejected **exact** equality to a fake list, so it passed. EE/IE had a small surviving Faker pool (low uniqueness).

On **v1 only**, phone-field metrics for AR (and low-uniqueness EE/IE) are not meaningful; you may omit those country slices for v1 with that caveat.

**v2** samples random valid national numbers after Faker fails, never emits a lone example as the value, rejects fake digit **substrings**, and requires **500 unique** phones per `country_iso` in each phone file (all 35 countries).

## GT-04 — Fixed dirt strings

**Original Q:** DIRT PATTERNS --> A lot of the dirt uses the same fixed string every time - for example, MIS_STATUS_IN_FIRST is always "Active", MIS_ORG_CONTACT_AS_NAME is always "Jane Doe". A detector could just hardcode these exact strings and get a perfect score, but it would miss "Inactive" or any other name in real data. Is catching the exact v1 strings good enough for this project, or do you want us to also test whether detectors catch variations?

**Q:** Is catching only v1 literals (`Active`, `Jane Doe`, …) good enough?

**A:** **No.** A detector that memorizes v1 constants would fail on real MDM. Gold stays on `dirt_label_id` → contaminant type (`status_token`, `given_name`+`family_name` in org name, etc.). **v2 varies the surface string** from locale pools and Faker (several tokens per ID; tiny closed sets only for punctuation placeholders).

## GT-05 — Serbia names and addresses look American (v1) / Croatian (v2)

**Original Q:** SERBIAN RECORDS --> We noticed Serbia is generated with the en_US Faker locale - Serbian records have American names and addresses (e.g. "Zachary Johnson", state "Arizona") combined with RS country code and Serbian phone numbers. We assume Faker has no Serbian locale. Is it OK if we leave Serbia out of per-country and locale-based analysis and note it as a data limitation?

**Q:** Why aren’t Serbian names and addresses authentic?

**A:** Faker has **no `sr_RS`**. v1 set `faker_locale: en_US` while `phone_region` stayed RS. v2 uses Croatian **`hr_HR`**: closest built-in South Slavic, Latin-script locale (regionally adjacent). It is a **proxy**, not Serbian language, not Cyrillic, not Serbian toponyms.

If that mix **corrupts** locale/name/address evaluation, **leave Serbia out of those slices**. We cannot generate authentic Serbian party data with the current generators. Phone/tax/DL may still be RS-specific.

## GT-06 — Is v1 frozen for the semester?

**Original Q:** GENERAL --> Should we treat the v1 dataset you provided as frozen for the whole semester, or might the dataset get updates along the way?

**Q:** Is v1 frozen for the whole semester?

**A:** **No full freeze of “the only data for 14 weeks.”** v1 is frozen **as a folder** so the first drop stays available. Stibo wants student feedback to improve synthetic generation (that helps later productization). We will keep students in the loop and ship new version folders (`v2`, `v3`, …) when we can. Some gaps cannot be fixed ideally (GT-05). Use the changelog plus this Q&A when a new drop lands.

## GT-07 — Street-only address line 1 (no house number)

**Original Q:** for address line 1. An address value with only a street name (ex. Evergreen Terrace), without a specific house number or building number (ex. Evergreen Terrace 152), would you consider that a clean value? The clean synthetic data considers just the street name a clean value, but I want to know whether that is acceptable under Stibo guidelines or if it would be considered a noisy/missing value. I will add that the clean data considers address line 1, just the street name, a clean value, even if address line 2 has no value in the record (ex., Address line 1 = Evergreen Terrace, Address line 2 = NaN). Would Stibo consider that clean, or something to go into "manual review"?

**Q:** Is a street name without a house number (and empty address line 2) clean, or dirt / manual review?

**A:** This is obviously a complexity and a dilemma. So the question is how to solve it.

You suggest to penalize the data, when there is no premise identifier, possibly leading to a manual review.

The relevance of manual review is very use case specific for our customers. It depends if it is 'worth it' from a cost/benefit point of view. For B2C use cases, it is less relevant than for B2B cases, where each customer often has a higher value to the business.

In the following record matching (entity resolution) process, it is generally so that false positives are highly unwanted, whereas occasional false negatives is less of a problem.

This means that cases of doubt should in some cases leads to manual review, in other cases false negatives. Our customers decides this, when they 'tune' their matching algorithms.

Regardless, the goal should be to reduce the set of cases with doubt as much as possible.

I think the proportionality of clean addresses without premise identifiers is somewhat correct in the clean data (2.3% across all countries).

I don't think that addresses with missing identifiers is accurately represented in the v2 dirty data.

I have created a v3 of the dataset and made it available here

v3 folder: [self-research/test-data/v3](../self-research/test-data/v3). Student zip: [party-test-data-v3-20260914T085858Z.zip](party-test-data-v3-20260914T085858Z.zip). Dirt ID `MIS_ADDR_STRIP_PREMISE` strips a house/premise token from `address_line_1` and/or `address_line_2` only when one is present (gold `incomplete_premise` on changed lines). Street-only clean lines stay `street_address`. Empty / pandas `NaN` line 2 is an optional blank, not a quality flag.

## GT-08 — Gold contaminants where raw_value equals clean_value (v2)

**Original Q:** In the V2 dataset we are seeing situations where eval_gold is flagging fields as dirty but the raw_value and clean_value are precisely the same. There are just over 900 contaminates similar to the below. Here is an example from eval_gold (v2) where you see first_name and middle_name are both flagged as contaminated, but the raw and clean appear the same with the implication that Valentina should have moved to middle. These are the only issues flagged for this particular record. How should we interpret such situations? Can we exclude these contaminants from our recall and precision measurements?

**Q:** If `raw_value` equals `clean_value` but gold has contaminants, should we score those cells?

**A:** This record is a no-op dirt label, not a real misplacement.

`AR-014108` already had an empty middle name in clean data. `MIS_NAME_MIDDLE_TO_FIRST` is supposed to copy middle into first and clear middle. With middle empty, first stays `Valentina` and middle stays empty. Gold still attaches `additional_given_name` / `unknown_content` because it keys off the dirt ID, not off whether the string changed.

A detector should not be required to flag those cells. On **v2**, exclude from precision/recall any gold contaminant cell where `raw_value` equals `clean_value` for that field (the ~900 you found). Do not exclude other contaminants.

**v3** keeps a dirt event only if the row actually changes, so this pattern should not appear there. `AR-014108` in v3 is a real placeholder on first name (`-`), not a silent middle-name fold.

Also: if phone looks like `5.49112E+12`, that is Excel scientific notation. Use the CSV value (`+5491120851890`).


