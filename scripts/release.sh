#!/usr/bin/env bash
set -euo pipefail

echo "========================================="
echo "  Synapse Production Release Hardening  "
echo "========================================="

# 1. Run static checks
echo "-> Running Ruff linter..."
uv run ruff check .

echo "-> Running Ruff formatting check..."
uv run ruff format --check .

echo "-> Running MyPy strict type checker..."
uv run mypy src tests

echo "-> Running Bandit security scanner..."
uv run bandit -r src/ -ll

# 2. Run test suites
echo "-> Running PyTest unit and integration tests..."
uv run pytest -m "not benchmark" -q

echo "-> Running PyTest monorepo stress benchmarks..."
SYNAPSE_SKIP_STRESS="" uv run pytest -m "benchmark" -v --tb=short

# 3. Packaging & Build validation
echo "-> Cleaning old builds..."
rm -rf dist/ build/ *.egg-info

echo "-> Building wheel and source distribution..."
uv build

echo "-> Setting up fresh temporary virtual environment to validate package..."
rm -rf test_release_env
uv venv test_release_env

# Activate test environment
# shellcheck disable=SC1091
source test_release_env/bin/activate

echo "-> Installing built wheel..."
uv pip install dist/*.whl

echo "-> Validating CLI execution and doctor checks..."
git config --global user.email "release@synapse.local" || true
git config --global user.name "Release Builder" || true

# Initialize synapse in a temporary folder
rm -rf tmp_release_test
mkdir tmp_release_test
cd tmp_release_test
git init
git config user.email "release@synapse.local"
git config user.name "Release Builder"
echo "def test(): pass" > test.py
git add .
git commit -m "initial"

# Verify CLI commands
synapse init . --skip-llm --quiet
synapse doctor .
synapse mcp verify .
synapse checkpoint create . --doing "Verifying release wheel" --files "test.py" --next-step "done" --blockers "None"
synapse checkpoint list .
synapse checkpoint restore latest .

# Cleanup
cd ..
rm -rf tmp_release_test
deactivate
rm -rf test_release_env

echo "========================================="
echo "✓ SUCCESS: Synapse Release Candidate Hardening passed!"
echo "========================================="
