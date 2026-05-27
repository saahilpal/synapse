# Contributing to Synap

Welcome to the Synap project. We are building the **infrastructure for persistent structural context** for AI coding agents.

Because Synap is infrastructure, we hold ourselves to rigorous standards. The codebase must remain deterministic, bounded, and highly resilient. We prioritize structural truth over AI abstraction, and stability over hype.

If you share this vision, we’d love your help.

---

## 1. Architectural Philosophy

Before contributing, please read our [Architecture Documentation](ARCHITECTURE.md).

When adding features or fixing bugs, adhere strictly to these invariants:
- **Structural Truth is Deterministic**: AI models *never* define structural truth in Synap. Structure is derived exclusively via AST parsers, Git state, and file hashes.
- **Append-Only History**: The SQLite event store is append-only. We do not patch nodes in place. We invalidate them and append deltas.
- **Strict Boundaries**: Keep provider-specific LLM logic (e.g., OpenAI, Anthropic) out of the structural extraction and storage layers. LLMs belong in the retrieval synthesis and overlay generation phases.
- **Bounded Retrieval**: Protect context limits. Every structural traversal must respect hard node limits and token budgets to prevent agent overflow.

## 2. Development Setup

Synap relies on `uv` for ultra-fast, deterministic dependency resolution.

### Prerequisites
- Python 3.10+
- `uv` installed (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Environment Setup

Clone the repository and bootstrap your environment:

```bash
git clone https://github.com/saahilpal/synap-git.git
cd synapse

# Sync dependencies and install the package in editable mode
uv sync --all-extras --dev

# Install pre-commit hooks
uv run pre-commit install
```

## 3. Development Workflow

We enforce strict linting, type-checking, and formatting. Ensure these pass locally before pushing.

```bash
# Format code
uv run ruff format .

# Check linting
uv run ruff check .

# Run static type checks
uv run mypy src tests

# Run test suite
uv run pytest
```

### Writing Tests
- All bug fixes must include a regression test.
- All new parsers, transaction pathways, or API endpoints must be accompanied by comprehensive tests in the `tests/` directory.
- Test failure paths, invalid object states, and schema corruption handling.

## 4. Pull Request Process

1. **Open an Issue First**: If you intend to make a significant architectural change or feature addition, please open an issue to discuss it first. This saves time and ensures alignment.
2. **Branch Naming**: Use descriptive branch names: `feature/mcp-tools`, `fix/sqlite-wal-lock`, `docs/architecture`.
3. **Use the Template**: When opening a PR, fill out the provided `PULL_REQUEST_TEMPLATE.md`.
4. **Pass CI/CD**: GitHub Actions will run formatting, type checks, and pytest. Your PR cannot be merged if these fail.
5. **Code Review**: A maintainer will review your code. We look for deterministic logic, proper state invalidation, and adherence to infrastructure-grade quality.

## 5. Adding New Parsers / Languages

Synap’s strength lies in its AST extraction. If you are adding support for a new language:
- Implement it within `src/synap_git/context/parsers.py` (or a dedicated language submodule).
- Only extract bounded structure: functions, classes, imports, packages. Do *not* extract block-level logic or variable assignments.
- You must add a corresponding test file validating the parser against standard structural boundaries.

## 6. Packaging & Release Workflow

### Local Packaging Build
We use `hatchling` as our build backend. To build the wheels and source distributions locally:
```bash
uv build
```
This compiles the output to the `dist/` directory. You can verify it by installing it in a clean virtual environment:
```bash
python -m venv test_env
source test_env/bin/activate
pip install dist/*.whl
synap --help
```

### Semantic Versioning & Release Strategy
We follow semantic versioning (`major.minor.patch`). When releasing:
1. Increment the version in `pyproject.toml` and in `src/synap_git/__init__.py`'s `__version__`.
2. Commit the changes and tag it with `v<version>`, for example `v0.2.0`:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
3. GitHub Actions will trigger `.github/workflows/release.yml` on tag creation, run tests, and automatically build and upload the package to PyPI using OIDC trusted publishing.

---

Thank you for helping us build the foundational context layer for the next generation of AI coding agents!
