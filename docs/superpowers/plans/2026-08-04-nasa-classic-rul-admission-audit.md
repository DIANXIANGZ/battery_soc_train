# NASA Classic RUL Admission Audit Implementation Plan

> **For agentic workers:** Execute inline with strict RED→GREEN checkpoints; do not dispatch training work.

**Goal:** Fail-closed adjudication of NASA classic-aging license and, only if licensed, exact per-cell physical EOL evidence for 15 candidates.

**Architecture:** A standalone research audit validates immutable official-source evidence before any cell protocol. License failure terminates the source. Protocol validation is pure and cannot connect to adapters, schemas, datasets, or trainers.

**Tech Stack:** Python 3.12, pytest, scipy for read-only MATLAB parsing, CSV/JSON audit artifacts.

## Global Constraints

- Do not create v12 or modify v11, adapters, schemas, labels, provenance, thresholds, training settings, or historical results.
- Do not run smoke tests, model fitting, downloads, XGBoost, or Torch.
- Official NASA domains/APIs only; no mirrors, redirects, retries, or inferred license.
- Any non-2xx, parse failure, or uncertain license stops the NASA source.

---

### Task 1: Official license adjudication

**Files:**
- Create only if evidence is complete: `docs/audits/2026-08-04-nasa-classic-license-snapshot.json`
- Update final decision only: `docs/audits/2026-08-04-nasa-classic-rul-admission-final.md`

**Interfaces:**
- Consumes official NASA directory, dataset metadata/API, and official terms.
- Produces a fingerprinted `license_admitted: bool` decision with blockers.

- [ ] Record exact official URLs, UTC, HTTP/content type, response fingerprint, license field, and applicability text.
- [ ] Reject `License not specified`, generic public access, or unrelated government terms as insufficient.
- [ ] Stop the source immediately on any non-2xx, parse error, or applicability ambiguity.
- [ ] If rejected, write the final one-page NOT_ADMITTED decision and skip Tasks 2–3.

### Task 2: Protocol validator TDD (conditional on Task 1 PASS)

**Files:**
- Create: `tests/research/test_nasa_classic_rul_audit.py`
- Create after RED: `src/research/nasa_classic_rul_audit.py`

**Interfaces:**
- `validate_license_snapshot(snapshot: dict) -> list[str]`
- `validate_cell_protocol(record: dict) -> list[str]`
- `audit_cell(record: dict) -> dict`

- [ ] Write RED tests proving missing/unspecified license, non-official URL, incomplete hash, non-contiguous cycles, non-discharge records, unit mismatch, protocol mismatch, anomalous capacity, and non-adjacent crossing are blocked.
- [ ] Run the focused test file and record expected failures caused only by missing validator behavior.
- [ ] Implement the minimal pure validator without imports from `src.training`, adapters, or corpus builders.
- [ ] Run focused tests to GREEN, then run the freeze-safe research/data-quality test subset.

### Task 3: Fifteen-cell audit outputs (conditional on Tasks 1–2 PASS)

**Files:**
- Create: `docs/audits/2026-08-04-nasa-classic-rul-cell-matrix.csv`
- Create: `docs/audits/2026-08-04-nasa-classic-rul-cell-audit.json`

**Interfaces:**
- Consumes the 15 fixed candidate IDs and local official archive/README groups.
- Produces one row per cell with source mapping, threshold, crossing bounds, protocol fields, blockers, and exact-RUL eligibility.

- [ ] Parse only local `.mat` and README files; never mutate them.
- [ ] Require a single adjacent above→below crossing under identical verified protocol.
- [ ] Mark every ambiguous cell censored; never select a convenient crossing by smoothing or future tail.
- [ ] Recompute candidate/pass/fail totals independently and reconcile them with JSON/CSV.

### Task 4: Final ruling and freeze verification

**Files:**
- Create: `docs/audits/2026-08-04-nasa-classic-rul-admission-final.md`

- [ ] State official license decision, per-cell results or the license-stop boundary, risks, and next permitted action.
- [ ] Recheck v11 frozen flags and SHA-256 for manifest/cycles.
- [ ] Verify zero new training artifacts since the stage start using Asia/Shanghai timestamps.
- [ ] Search new audit code for training/adapter/schema imports and forbidden writes.
- [ ] Submit the report to thread `019fc71f-f3d0-7373-8669-8ed00eb533de`; do not request v12 unless every prior gate passed.

