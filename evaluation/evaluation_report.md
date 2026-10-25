# Evaluation Report

## Supplied labeled cases

Command:

```bash
python3 code/evaluation/main.py
```

The production engine is evaluated on `sample_deletion_requests.csv` only; the
unlabeled 518-case file is never assigned fabricated ground truth.

| Metric | Result |
| --- | ---: |
| Cases | 32 |
| Deletion-status accuracy | 100.00% (32/32) |
| Exact ordered step-array accuracy | 43.75% (14/32) |
| Step precision | 98.18% |
| Step recall | 83.94% |
| Step F1 | 90.50% |
| Key-aligned step-field accuracy | 82.65% |
| Exact sequence accuracy | 43.75% (14/32) |

Steps are compared as sets for precision/recall using phase, system, resource,
operation, state, and evidence ID. Field scoring aligns steps by phase, system,
resource, and operation before comparing all six fields; missing and extra steps
count as incorrect. This avoids the misleading positional metric where removing
one incorrect early step made every later field appear wrong.

These 32 public labels are a **development benchmark**, not a held-out test set:
they were used while improving the deterministic engine. The unlabeled 518-case
submission set is checked only for structural validity and coverage.

## Mismatch analysis and improvements

Initial evaluation produced 65.63% status accuracy and 36.43% positional field
accuracy. The following changes raised status accuracy to 100% and final
key-aligned field accuracy to 82.65%:

- expanded deterministic multilingual deletion-intent handling;
- added pipe-delimited, structured JSON log, escaped runtime-log, syslog, SQL,
  PDF, and screenshot OCR adapters;
- propagated trace-scoped identifiers to completed readback events;
- parsed handover state declarations instead of inferring from prose;
- filtered stale pre-request evidence and enforced the audit cutoff; and
- linked identifier-free compliant records through a narrow report-time workflow
  window while requiring separate state evidence; and
- added a subject-conflict guard after independent review found report-time
  resources from other users in 92 evaluation cases.

The remaining 18 exact-step mismatches are mainly missing verification
steps for records whose compliant final form contains no subject identifier.
There are also scoped-absence cases where a snapshot proves no matching row but
does not directly repeat the deleted resource-to-subject link. These are kept as
known recall limits instead of being solved with sample-case branches or expected
answers.

## Additional synthetic evaluation cases

Command:

```bash
PYTHONPATH=code python3 -m unittest discover -s code/tests -v
```

All twelve tests pass. They include:

1. two people sharing a phone number do not merge;
2. a historical email resolves to the stable current user;
3. an active recreation flow is disabled before record deletion;
4. a mandatory retained security record is verified present;
5. a later absence observation supersedes an earlier present observation;
6. non-deletion intent fails closed while explicit deletion is accepted; and
7. an unavailable media extractor creates a coverage gap rather than proof of
   absence;
8. a missing required retained record cannot be marked complete;
9. a noncanonical flow state cannot crash output validation;
10. multilingual deletion and scoped negation cases;
11. a report-time resource owned by another subject is rejected; and
12. unknown process state and residual name fields are not treated as safe.

## Full-dataset validation

The final full run produces 518 rows sorted by numeric `case_id`. Validation
checks the exact header and row coverage, JSON arrays, consecutive step numbers,
allowed phase/operation/state triples, evidence IDs for findings and complete
verification, and empty evidence IDs for future remediation/verification.

