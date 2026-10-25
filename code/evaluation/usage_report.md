# Usage Report

## Final full-dataset run

The production solution uses deterministic local Python parsing and local
RapidOCR. It makes no hosted model or LLM calls.

| Provider / model | Calls | Input tokens | Output tokens | Estimated cost |
| --- | ---: | ---: | ---: | ---: |
| None (deterministic local execution) | 0 | 0 | 0 | $0.00 |
| **Overall** | **0** | **0** | **0** | **$0.00** |

| Measure | Result |
| --- | ---: |
| Requests processed | 518 |
| Total tokens | 0 |
| Average tokens per request | 0 |
| Total estimated model cost | $0.00 |
| Average estimated model cost per request | $0.00 |

OCR is executed locally and has no token usage or per-call model charge. This
report covers the final run that generated the submitted root `output.csv`.
