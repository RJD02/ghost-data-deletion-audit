# HackerRank Orchestrate - October 2026

## Ghost Data Still Exists

Build an AI agent that audits whether a user's personal data was actually deleted.

## Implemented Solution

This repository now contains a deterministic Python deletion-audit engine. It
resolves current and historical identifiers, normalizes JSON/SQL/log/text/PDF
and screenshot evidence, reconstructs resource state at each audit cutoff,
applies the supplied policy, orders remediation by dependency, and validates the
exact output contract. AI is not used in the production path.

### Setup and run

Python 3.10 or newer is recommended. Local screenshot OCR is required whenever
the evidence manifest contains images; the pinned dependency provides it.
PDF extraction also requires Poppler's `pdftotext`. Production runs fail fast
when any evidence file cannot be extracted, so machine-dependent gaps cannot be
silently converted into deletion conclusions.

```bash
python3 -m pip install -r code/requirements.txt
# Debian/Ubuntu: sudo apt-get install poppler-utils
# macOS: brew install poppler
python3 code/main.py
```

The run reads only `dataset/` and writes the final `output.csv` at repository
root. To retain machine-readable extraction diagnostics during development:

```bash
python3 code/main.py --diagnostics run_diagnostics.json
```

Run tests and labeled evaluation separately:

```bash
PYTHONPATH=code python3 -m unittest discover -s code/tests -v
python3 code/evaluation/main.py
```

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the flow, deterministic/AI
boundary, provenance design, and failure handling. See
[`INTERVIEW_NOTES.md`](./INTERVIEW_NOTES.md) for tradeoffs and known limits.

A deletion workflow may report **Complete** while data still exists in databases, logs, support attachments, exports, search indexes, archives, or backups. Sync and restore processes may also bring deleted data back.

For each request, the agent must first determine whether deletion was actually requested. It then returns `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`, reports any remaining data or recreation risk, and produces the ordered remediation and verification steps required to finish an authorized deletion safely.

The original challenge contract is available on the
[HackerRank challenge page](https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists).

---

## Quick Start

Clone the repository and move into the project directory:

```bash
git clone https://github.com/RJD02/ghost-data-deletion-audit.git
cd ghost-data-deletion-audit
```

Place the participant-facing `dataset/` directory from the challenge at the
repository root before running the solution. The dataset and generated
submission artifacts are intentionally excluded from this public source repository.

Build your solution in `code/main.py`, or use another language and document its setup and run command clearly in your README.

Your solution must:

- Read the input files from `dataset/`
- Generate one prediction row for every request in `dataset/deletion_requests.csv`
- Write the final predictions to `output.csv` in the repository root

Run the starter Python entry point with:

```bash
python3 code/main.py
```

The blank template at `dataset/output.csv` is provided as a reference. Your final generated file for submission must be the root-level `output.csv`.


## Dataset

All participant-facing files are in `dataset/`:

| File | Contents |
| --- | --- |
| `deletion_requests.csv` | 518 requests |
| `sample_deletion_requests.csv` | 32 sample requests |
| `sample_output.csv` | Correct sample answers |
| `user_identities.csv` | Current user identities |
| `user_audit_log.csv` | Historical identity changes |
| `system_activity.csv` | Activity across services and data processes |
| `deletion_rules.csv` | Required treatment for each data category |
| `evidence_files.csv` | Manifest of supplied evidence files |
| `output.csv` | Blank output template |

Evidence is stored under `dataset/evidence/` and may include PDFs, images, logs, JSON, plain text, or SQL snapshot exports. SQL captures may contain a primary database, regional replicas, a reporting replica, or a failover replica so replication drift can be investigated directly. The `.sql` files are readable as text and executable with SQLite.

Only `deletion_requests.csv` requires answers. The other files provide evidence and context.

---

## Output

Create `output.csv` with these columns in this exact order:

```text
case_id,deletion_status,steps_json
```

Produce exactly one row per request. `deletion_status` is `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`. `steps_json` is an ordered JSON array containing findings, remediation actions, and verification checks. Use an empty array (`[]`) for `NOT_APPLICABLE`. Evidence references may be a `file_id`, `activity_id`, or `audit_id`. Determine the resource state at `audit_at` from the available evidence; reported workflow statuses and operation results are claims. Use `dataset/sample_output.csv` as the format reference.

The final file must contain 518 data rows sorted by `case_id` (plus the header row). The grader parses `steps_json` as JSON, so object-key order and whitespace do not matter; array order does. Order findings, remediation, and verification in that phase order. Within a phase, follow the operation order in the problem statement, then sort by `system_id` and `resource_id`.

---

## Evaluation

`output.csv` will be compared with hidden canonical answers. Scoring considers:

- deletion assessment accuracy;
- current and historical identity resolution;
- discovery of remaining data and recreation risks;
- correct policy application and evidence references; and
- completeness and ordering of remediation and verification steps.

Your `code.zip` includes the required reports at the archive-root paths:

```text
evaluation/evaluation_report.md
evaluation/usage_report.md
```

The same reports remain beside the evaluator in `code/evaluation/` for local
development compatibility.

- `evaluation_report.md` must cover case, row, field, and sequence accuracy, at least three additional evaluation cases created by you, failures found, and improvements made.
- `usage_report.md` must cover the final full-dataset run, including model providers and names, model calls, input and output tokens, total and average tokens per request, and estimated total and per-request cost. Include per-model and overall totals when using multiple models.

Write the complete evaluation metrics, custom cases, and usage details directly
in these Markdown files. Automated code evaluation ignores raw data files
(`.csv`, `.tsv`, `.json`, `.jsonl`, `.sql`, `.log`), so required explanation
must not exist only in those formats.

---

## Chat Transcript

The competition workspace used an `AGENTS.md` instruction file to append
conversation summaries to `log.txt` in the repository root. The transcript is
not included in this public solution-only repository.

| Platform | Path |
| --- | --- |
| macOS / Linux | `<repo root>/log.txt` |
| Windows | `<repo root>\log.txt` |

- For a competition submission, follow the current challenge's transcript
  instructions and preserve every required turn in the requested format.
- Upload `log.txt` directly as your `chat_transcript` submission on HackerRank.
- Do not include API keys, tokens, credentials, or secrets in prompts, code, configuration, or `log.txt`.

---

## Packaging `code.zip` and Submission

| Item | Description |
| --- | --- |
| `code.zip` | Runnable solution, prompts, configuration, `README.md`, and `evaluation/` reports |
| `output.csv` | One answer row for each of the 518 requests in `dataset/deletion_requests.csv` |
| `chat_transcript` | The root `log.txt` file generated by your coding agent |
| AI interview | Live explanation of your architecture, approach, and evaluation |

You may use any programming language, model, framework, or retrieval approach. Include clear setup and execution instructions in `README.md` inside `code.zip`.

To package `code.zip` from the repository root without bundling the dataset:

**macOS / Linux:**

```bash
zip -r code.zip README.md ARCHITECTURE.md INTERVIEW_NOTES.md code evaluation -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"
```

**Windows (PowerShell):**

```powershell
Compress-Archive -Path README.md, ARCHITECTURE.md, INTERVIEW_NOTES.md, code, evaluation -DestinationPath code.zip -Force
```

When packaging `code.zip`:

- Keep the required evaluation reports in the top-level `evaluation/` directory.
- Do **not** include `dataset/`, virtual environments (`.venv`, `venv`, `node_modules`), or build caches (`__pycache__`). On Windows, keep `.venv` at the repository root (outside `code/`) and remove any `code/__pycache__` folders before running `Compress-Archive`.
- Do **not** include nested archives (`.zip`, `.tar`, `.gz`, `.tgz`, `.7z`, `.rar`) inside `code.zip` — submissions containing nested archive files will be rejected.

Before submitting, confirm that:

- `output.csv` has the exact header `case_id,deletion_status,steps_json` and contains all 518 data rows sorted by `case_id`;
- every `steps_json` value is a valid JSON array with consecutive step numbers starting at `1`;
- findings cite valid evidence IDs, and `COMPLETE` verification steps cite evidence proving the current state;
- proposed remediation and future verification steps use an empty `evidence_id` (`""`);
- `code.zip` includes runnable code, `README.md`, and the two reports under `evaluation/`;
- `log.txt` follows the `AGENTS.md` turn format and is uploaded to the `chat_transcript` slot; and
- no API keys, credentials, real personal data, or sensitive configuration values are included.
