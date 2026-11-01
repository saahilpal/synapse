# Synapse Monorepo Stress & Reliability Methodology

**Document Version:** 2.5.0
**Test Harness:** `tests/test_monorepo_stress.py` & `tests/test_real_world_stress_matrix.py`
**Scale Target:** 1,000 to 10,000 files / 100,000+ symbols

---

## 1. Test Methodology

Synapse is validated under synthetic stress workloads designed to simulate large enterprise repositories and monorepos:

### 1.1 Synthetic Generation Harness
- Generates 1,000 to 10,000 realistic Python, TypeScript, and Rust files.
- Simulates realistic dependency structures:
  - Deep class inheritance trees (depth 3–5).
  - Cross-file imports (fan-in / fan-out ratio of 4:1).
  - Cyclic imports and mutual references.
  - Large single files (> 1MB) and deeply nested closures.

### 1.2 Concurrency & Stress Load
- **Concurrent Readers:** 4–8 worker threads executing continuous hybrid retrieval queries (`query_hybrid`).
- **Concurrent Writers:** Dedicated thread executing continuous checkpoints, decisions, and memory insertions (`put_checkpoint`, `remember`).
- **Concurrent Background Worker:** Queue processor draining `wiki_queue` via atomic `dequeue_wiki()` calls.
- **Git State Shifts:** Periodic simulated commit checkouts, branch switches, and dirty working tree edits.

---

## 2. Acceptance Criteria & Latency Bounds

| Metric | Target SLA | Measured Result | Status |
| :--- | :---: | :---: | :---: |
| **Incremental Indexing (1 file change)** | $< 250\text{ms}$ | **84ms** | PASS |
| **Incremental Indexing (0 file change)** | $< 50\text{ms}$ | **14ms** | PASS |
| **P95 Symbol Lookup (`search`)** | $< 10\text{ms}$ | **2.1ms** | PASS |
| **P95 Graph Neighborhood (`get_neighborhood`)** | $< 5\text{ms}$ | **0.8ms** | PASS |
| **P95 Preamble Generation (`get_session_preamble`)** | $< 50\text{ms}$ | **12ms** | PASS |
| **Memory Resident Set Size (RSS)** | $< 200\text{MB}$ | **128MB** | PASS |
| **SQLite Lock Timeout Errors** | **0 errors** | **0 errors** | PASS |

---

## 3. Running Stress Tests Locally

Stress tests are included in the test suite and can be executed via pytest:

```bash
# Run real-world stress matrix
.venv/bin/pytest tests/test_real_world_stress_matrix.py -v

# Run full monorepo stress benchmarks (requires ~30-60s)
.venv/bin/pytest tests/test_monorepo_stress.py -v
```
