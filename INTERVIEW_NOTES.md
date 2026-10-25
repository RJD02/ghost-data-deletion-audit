# Interview Notes

## Architecture in one minute

The solution is a deterministic evidence compiler. Typed adapters normalize the
participant CSVs and heterogeneous evidence into provenance-bearing resource
observations. Exact current/historical identity resolution connects observations
to a stable `user_id`; temporal reconstruction selects evidence available at the
case cutoff; policy evaluation determines compliance; a planner emits findings,
risk-first recreation prevention, cleanup, and verification in the contract's
canonical order; a final
validator rejects malformed or incomplete output coverage.

AI was deliberately excluded from the production path because structured parsing
and local OCR cover the supplied corpus. A future vision/LLM adapter would be
schema-constrained and could propose observations only; it could not decide
policy or bypass provenance and output validation.

## Key tradeoffs

- Exact email/hash/stable-ID links have high precision. Names and shared phone
  numbers never merge people, sacrificing some recall to prevent cross-subject
  deletion.
- Workflow events link identifier-free final records to a request only within a
  narrow report-time window. The event does not prove state; separate evidence
  must establish the state.
- Evidence is bounded by request and audit time. Old snapshots are not treated as
  indefinitely current, which prevents stale failures from overriding later
  remediation.
- Active data flows and restore permissions are resources in their own right and
  are remediated before records.
- Extraction failures are diagnostics, not proof of absence.

## Known limitations

- Irreversibly anonymized records intentionally contain no subject identifier.
  When no workflow-time link exists, the engine can prove the record is
  anonymized but cannot always attribute it to the exact subject. This primarily
  lowers exact step recall rather than case-status accuracy.
- Some snapshots prove absence through query/table scope rather than an explicit
  row. The current implementation handles the supplied account failover scope,
  but a richer source-specific scope model would improve generality.
- OCR is deterministic but depends on `rapidocr_onnxruntime`; missing OCR produces
  coverage gaps and lower evidence recall.
- The request-intent classifier is deterministic and multilingual for the
  languages observed in the corpus. Unseen or genuinely ambiguous language
  should be routed to a constrained classifier rather than guessed.

## Evaluation summary

On the 32 supplied labeled development cases, the corrected baseline achieves
100% status accuracy, 98.18% step precision, 83.94% recall, 90.50% step F1,
82.65% key-aligned field accuracy, and 43.75% exact step/sequence accuracy.
Twelve synthetic tests cover identity collision safety, historical aliases,
active recreation paths, retained records, temporal conflicts, multilingual and
negated intent, cross-subject report windows, uncertain process states, and
media-extraction failure.
