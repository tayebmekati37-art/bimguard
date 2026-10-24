# Metrics - methodology and measured results

> **Update (M22):** The rule-accuracy benchmark now exists. See `docs/evaluation/methodology.md` for the methodology and `docs/evaluation/results.md` for the most recent measured numbers. This document is retained for its discussion of what is NOT measured (precision, recall on real projects, cross-machine consistency) and why.

**Nothing in this file is a claim about industry standards.** It reports
numbers observed on one machine with one synthetic dataset. It is a
snapshot, not a benchmark suite.

## What was measured

### Validation runtime

`scripts/benchmark.ps1` loads a fresh copy of the demo, uploads A-101 v13,
and runs `POST /projects/{id}/validate` 5 times back to back. It reports
wall time per call.

Measured on the demo dataset (5 documents, 5 dependencies, no spatial
conflicts loaded by default; element counts vary by revision).

**Reported as observed.** The benchmark prints the numbers; it does not
assert that any of them are "good" or "fast". A user running
`scripts/benchmark.ps1` on their own machine will see their own numbers;
the tool reports what happened without commenting.

### Determinism

`scripts/benchmark.ps1` also computes a signature of each run
(status + per-rule counts) and asserts all runs are identical. This IS
asserted, because determinism is a documented guarantee (see
`docs/architecture/pipeline.md`). If any run differs, the script exits
non-zero.

### Demo verification

`scripts/verify-demo.ps1` runs the full demo flow and asserts the specific
states from `docs/evaluation/demo-dataset.md`. It exits non-zero if any
mismatch occurs. This is a correctness gate, not a performance benchmark.

## What was NOT measured

### Precision and recall

Measuring whether the rules find "the right" issues would require a
labeled dataset: elements that a BIM engineer has manually classified as
"should trigger rule X" versus "should not". No such dataset exists in
this repository. Every element is synthetic. Reporting precision or
recall on synthetic data would be misleading.

**What a real evaluation would require:**

1. A real building model with a documented change log
2. An engineer-independent set of "this change should be flagged"
   annotations
3. A rule configuration agreed with domain experts
4. Reported precision, recall, and per-rule confusion matrices

None of that is here. Do not present the demo dataset as a validation
study.

### Throughput under load

The benchmark runs 5 sequential requests. It does not measure concurrent
throughput, request latency under load, or behavior when the database is
under pressure. Those would require a load generator like k6 or locust,
which is out of scope.

### Cross-machine consistency

The runtime numbers depend on the hardware, the disk, and the Python
process state. Running the same benchmark on a different machine will
produce different numbers. The benchmark reports what it observed; it
does not claim that those numbers transfer.

### Long-term stability

The benchmark does not run overnight. It does not measure memory growth,
disk growth, or behavior across schema migrations.

## How to run the measurements yourself

    # Full correctness gate (asserts specific states)
    powershell -ExecutionPolicy Bypass -File scripts\verify-demo.ps1

    # Runtime + determinism check
    powershell -ExecutionPolicy Bypass -File scripts\benchmark.ps1

    # Full backend test suite (functional coverage)
    cd apps\api
    .\.venv\Scripts\python.exe -m pytest -q

    # End-to-end browser tests
    powershell -ExecutionPolicy Bypass -File .\run_m11_e2e.ps1

Each of these runs on your machine, against your install. Any number they
report is yours, not mine.

## What the repository can honestly claim

- **The pipeline is deterministic** (asserted by the benchmark's signature check and by `test_validation_engine.py`).
- **The demo produces the documented state** (asserted by `verify-demo.ps1`).
- **The full test suite passes on a clean install** (asserted by CI or by running pytest).
- **The AI layer cannot invent identifiers** (asserted by `test_ai_grounding.py`).
- **Every route is authenticated or explicitly public** (asserted by `test_rbac_audit.py`).

## What the repository does NOT claim

- That the rules match any real engineering standard
- That the runtime is competitive with any other tool
- That the demo dataset represents a typical project
- That the software is production-ready as-is