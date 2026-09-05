set dotenv-load := false
set positional-arguments := true

# List available commands.
default:
    @just --list

# Sync the project environment from uv.lock.
sync:
    uv sync --locked

# Run the MCP server.
run *args:
    uv run mint-computer-mcp "$@"

# Run the package directly.
run-module *args:
    uv run python -m mint_computer_mcp "$@"

# Format Python files.
fmt:
    uv run ruff format .

# Check formatting without modifying files.
fmt-check:
    uv run ruff format --check .

# Run Ruff.
lint:
    uv run ruff check .

# Apply safe Ruff fixes.
lint-fix:
    uv run ruff check . --fix

# Run static type checking.
type:
    uv run basedpyright

# Fast checks during implementation.
quick: lint type

# Run the standard local quality gate.
check: fmt-check lint type test

# Run the complete suite. Requires an explicitly authorized X11 test desktop.
check-all: fmt-check lint type test-all

# Apply safe fixes and formatting, then validate.
fix:
    uv run ruff check . --fix
    uv run ruff format .
    just check

# Run tests that do not require a real X11 desktop.
test:
    uv run pytest -m "not integration"

# Run all tests. Requires an explicitly authorized X11 test desktop.
test-all:
    uv run pytest

# Run integration tests on an explicitly authorized X11 test desktop.
test-integration:
    uv run pytest -m integration

# Run slow tests that do not require a real X11 desktop.
test-slow:
    uv run pytest -m "slow and not integration"

# Run a specific pytest path or node ID.
test-one target:
    uv run pytest "$1"

# Pass arbitrary arguments to pytest.
pytest *args:
    uv run pytest "$@"

# Run non-integration tests with branch coverage.
coverage:
    uv run pytest -m "not integration" --cov=mint_computer_mcp --cov-branch --cov-report=term-missing

# Install Git hooks.
hooks:
    uv run prek install

# Run Git hooks against all tracked files.
hooks-all:
    uv run prek run --all-files

# Update locked dependencies within declared constraints.
update:
    uv lock --upgrade
    uv sync --locked

# Show outdated packages.
outdated:
    uv tree --outdated

# List reference repositories, or populate/update selected names.
agent-docs *names:
    ./scripts/sync-agent-docs "$@"

# Remove project caches and coverage files.
clean:
    rm -rf .coverage htmlcov .pytest_cache .ruff_cache .mypy_cache .hypothesis .basedpyright
    find src tests -type d -name __pycache__ -prune -exec rm -rf {} +

probe:
    uv run python -m mint_computer_mcp.native.x11.probe

bench name *args:
    shift; uv run python "scripts/benchmarks/{{name}}.py" "$@"
