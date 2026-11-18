# Medicine and medical knowledge reference

## What exists (18 Nov 2026)

- **Data file:** `app/data/medicine_reference.json`, version `2026-11-18.1`.
  - Each entry has a name, aliases, market, ingredients and strength, form, company, a one-line summary, sources (URL, the date it was read, the page date), a review status and a clinical review field.
- **Loader and matching:** `app/services/medicine_reference.py`.
  - It matches names people type as whole words, so "dolo650" matches "Dolo 650", and "testamolecule" does not match "testamol".
  - Only entries marked `source-verified` are ever used: they are sent to the model as context and returned as cited `sources`.
  - A file that marks an entry verified without sources and dates fails to load.
- **Answers:** the chat adds matching verified entries to the prompt and returns their sources. The website shows them under the answer.

## Coverage today: no entries verified yet

10 entries are listed with names only (no facts):
- generics: acetaminophen/paracetamol, ibuprofen, metformin, atorvastatin, levothyroxine;
- brands: Dolo 650, Crocin, Calpol, Panadol, Tylenol.

They are `pending-source-check` and are never used.

The source pages could not be read from this build environment. MedlinePlus, DailyMed, RxNav and the manufacturers' sites all failed at the network level on 18 Nov. Facts were not filled in from memory, because the owner's rule is to verify every fact against a reliable source.

Until entries are verified, the chat model answers "What is Dolo 650?" under the owner-approved medicine rule:
- it may say what a named medicine is;
- it must say when it is not sure;
- it never gives doses.

## Sources to use, in order

1. **US generics:** MedlinePlus drug pages (NLM) for the plain-language use, and DailyMed for the label.
2. **Brand to ingredient:** RxNav/RxNorm (NLM), for US and some international brands.
3. **Brands outside the US** (for example India: Dolo 650, Crocin):
   - the manufacturer's own product page;
   - the national regulator's listing where one is published (for India, CDSCO).
   - A commercial pharmacy site is not enough on its own.

## How an entry is verified

1. Read the source page. Record the URL, today's date as `checked`, and the page's own revision date.
2. Fill in only what the page states, word for word where possible, with no dose.
3. Set `review_status` to `source-verified`. A second person, or a later run, re-reads the page before merge.
4. `clinical_review` stays `none` until a qualified clinician signs it. The app never calls an entry clinician-reviewed otherwise.

## Keeping it fresh

These are proposals and need the owner's go-ahead:
- **Weekly:** re-read each source page and open a PR for any change.
- **Monthly:** list the medicine names people asked about that matched no entry. Only names are counted, never questions, and only if the owner approves logging that.

## Retraining

- **Knowledge updates (RAG):** this reference, refreshed by PRs. This is what "learning" means here.
- **Fine-tuning:** not planned. It would need a verified dataset and approvals.
- **Foundation-model training:** not applicable.
- Private reports and chats are never used to train anything.
