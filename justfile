# Agent CLI Development Commands
# Run `just` to see available commands

# Default: list available commands
default:
    @just --list

# Install development dependencies
install:
    uv sync --all-extras

# Run all tests
test:
    uv run pytest tests

# Lint and format
lint:
    uv run ruff check --fix .
    uv run ruff format .

# Run pre-commit on all files
pre-commit:
    uv run pre-commit run --all-files

# Build docs
doc-build:
    uv run zensical build

# Serve docs locally
doc-serve:
    uv run zensical serve

# Update auto-generated docs
doc-update:
    uv run python docs/run_markdown_code_runner.py

# Clean up build artifacts and caches
clean:
    rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build site
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
