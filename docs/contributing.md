# Contributing

Thank you for your interest in improving Synap!

## Development Setup

1.  **Install `uv`:**
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```
2.  **Clone and Install:**
    ```bash
    git clone https://github.com/saahilpal/synap-git.git
    cd synapse
    uv sync --all-extras
    ```
3.  **Run Tests:**
    ```bash
    uv run pytest
    ```

## Quality Gates

Synap has strict quality requirements. All PRs must pass:
- `ruff check .` (linting)
- `ruff format .` (formatting)
- `mypy src tests` (type checking)
- `pytest` (functional tests)

## Code Standards

1.  **Determinism:** Every component must be a pure function of its inputs (Git state + config).
2.  **No Silence:** Failures in configuration or connectivity must be loud and actionable.
3.  **Minimalism:** Avoid adding new dependencies unless absolutely necessary.
