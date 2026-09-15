# Contributing to Synapse

This guide details developer environment setup, running tests, code standards, type checking, and pull request guidelines for the Synapse codebase.

---

## 1. Environment Setup

Synapse targets **Python 3.12+** and uses `uv` for fast dependency management and virtual environments.

Clone the repository and install all dependencies in editable mode:
```bash
git clone https://github.com/saahilpal/synapse.git
cd synapse
uv sync --all-extras
```

Activate the virtual environment:
```bash
source .venv/bin/activate
```

---

## 2. Running Tests

Synap uses `pytest` with `pytest-asyncio`, `pytest-cov`, and `pytest-timeout`.

Run the entire test suite:
```bash
uv run pytest -v
```

### Skipping Heavy Stress Benchmarks
To run tests quickly without long monorepo stress benchmarks, set the `SYNAP_SKIP_STRESS` flag:
```bash
SYNAP_SKIP_STRESS=1 uv run pytest tests/ -x --tb=short
```

---

## 3. Formatting, Linting & Type Safety

All contributions must pass strict static analysis before merging.

### Code Formatting (`ruff`)
Synap uses `ruff` with a line length of 100 and double quotes:
```bash
uv run ruff format .
```
Verify formatting compliance:
```bash
uv run ruff format --check .
```

### Code Linting (`ruff`)
Run static analysis rules:
```bash
uv run ruff check .
```

### Static Type Safety (`mypy`)
Synapse enforces strict type checking (`strict = true` in `pyproject.toml`). All function arguments and return values must have explicit type annotations:
```bash
uv run mypy src/
```

---

## 4. Engineering Standards

Contributors and automated agents must adhere to the following architecture rules:

* **Structured Logging:** Always use `structlog` (`structlog.get_logger()`). Include key-value contextual parameters (e.g., `path`, `commit`, `error`). Never use standard `print()` in library code.
* **No Swallowed Exceptions:** Never write silent `try-except-pass` blocks without structured logging.
* **Async I/O Safety:** Never block the asyncio event loop. Wrap heavy synchronous filesystem reads, Git executions, and Tree-sitter AST parses in `asyncio.to_thread()`.
* **Database & Storage:**
  - SQLite databases must maintain Write-Ahead Logging (`WAL` mode) and `PRAGMA synchronous = NORMAL`.
  - Schema updates require incrementing the `user_version` pragma in `storage/sqlite.py` with idempotent migration blocks.
* **Deterministic Focus:** Keep L1 structural graphs and L3 memory strictly deterministic. Do not inject fuzzy heuristics into the core graph database.
* **Pre-commit Hooks:** Install git pre-commit hooks to ensure clean commits:
  ```bash
  uv run pre-commit install
  ```
