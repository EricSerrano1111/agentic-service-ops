# QA fault injection, measurement 2, 2026-10-10 (ADR-092)

The same frozen catalogue and seed as measurement 1 (`../2026-10-10/`), run against QA after the
fixes of ADR-092. Both measurements are kept; this one does not replace the first.

- `base_answers.json` is byte-identical to measurement 1's. The same 390 cases ran.
- `results.json` records the SHA-256 of the four frozen files over this checkout's working-tree bytes.
  Two of them (`generate.py`, `report_format.md`) differ from measurement 1's only because git's
  line-ending conversion wrote them as CRLF here; the committed blobs are byte-identical to the freeze
  commit `b5ad1f4`, whose blob hashes equal measurement 1's recorded values for those two.
- `report.md` is the frozen format followed by the side-by-side comparison with measurement 1.
- **The fixes were designed after seeing measurement 1's misses.** This measurement shows they work on
  those cases. It is not new evidence that QA catches faults it has not seen.
- No model was called. The interpretation client was a fake that always says `faithful`.
