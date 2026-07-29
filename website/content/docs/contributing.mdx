# Contributing to Synapse

This guide details developer environment setup, running tests, checking code standards, and submitting pull requests.

---

## 1. Environment Setup

Synap uses `hatchling` as its build backend and `uv` for python dependencies.

Clone the repository and install dependencies in editable mode:
```bash
git clone https://github.com/saahilpal/synap-git.git
cd synap-git
uv sync --all-extras
```

---

## 2. Running Tests

Synap uses `pytest` for unit and integration tests.

Run the unit test suite:
```bash
uv run pytest tests/ -x --tb=short
```

### Skip Performance Benchmarks
Monorepo stress and latency tests can be slow or non-deterministic depending on model availability and CPU load. Skip them by setting the `SYNAP_SKIP_STRESS` variable:
```bash
SYNAP_SKIP_STRESS=1 uv run pytest tests/ -x --tb=short
```

---

## 3. Formatting & Linting

Before pushing changes, ensure code complies with code style and type safety standards.

### Code Formatting
Synap uses `ruff` to format Python source files:
```bash
uv run ruff format src/ tests/
```
Verify formatting compliance:
```bash
uv run ruff format --check src/ tests/
```

### Code Linting
Synap uses `ruff` for static analysis checks:
```bash
uv run ruff check src/ tests/
```

### Static Type Safety
Synap uses `mypy` for strict type safety verification:
```bash
uv run mypy src/
```

---

## 4. Pull Request Guidelines

* **Deterministic Focus:** Do not introduce non-deterministic retrieval components or implicit heuristic overlays to L1 or L3 layers.
* **Keep AST Parsers Complete:** If modifying language parsers under `parser/registry.py`, ensure new AST node types are mapped explicitly and that test coverage verifies symbol extraction.
* **Database Migration Integrity:** Schema updates require incrementing the `user_version` pragma in `storage/sqlite.py` and writing transition steps inside the `initialize` method.
* **Pre-commit Hooks:** Install pre-commit hooks locally to prevent whitespace and format warnings:
  ```bash
  uv run pre-commit install
  ```
