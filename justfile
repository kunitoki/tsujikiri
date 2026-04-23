default:
    @just --list

# Create/update a local virtual environment from pyproject metadata including dev dependencies.
sync extras="clang22":
    uv sync --extra dev --extra {{extras}}

# Run test suite.
test extras="clang22" *args:
    @just sync {{extras}}
    uv run pytest -n auto {{args}}

# Run test suite.
tests *args:
    @just test clang19 {{args}}
    @just test clang20 {{args}}
    @just test clang21 {{args}}
    @just test clang22 {{args}}

# Run tests with coverage report.
coverage *args: sync
    uv run pytest -n auto --cov=tsujikiri --cov-branch --cov-report=term-missing {{args}}

# Regenerate inline stubs (src/tsujikiri/**/*.pyi) via stubgen.
stubs: sync
    uv run stubgen -p tsujikiri -o src

# Run code formatters (ruff).
format: sync
    uv run ruff format src/tsujikiri/*.py* tests/**/*.py

# Run mypy type checking.
check: sync format
    uv run mypy
    uv run ruff check src tests

# Build wheel and source distribution.
wheel: sync stubs format check
    uv build

# Publish a release (build + PyPI publish handled by .github/workflows/release.yml on tag push)
publish version: stubs check
    echo "__version__ = \"{{version}}\"" > src/tsujikiri/__init__.py
    perl -0pi -e 's/x=(\d+)/"x=" . ($1 + 1)/ge' README.md

# Remove build artifacts.
clean:
    rm -rf dist build .venv src/*.egg-info src/**/__pycache__ tests/**/__pycache__
    rm -rf src/**/.pytest_cache .pytest_cache .mypy_cache .coverage htmlcov
    rm -rf tests/test_compilation/_deps tests/test_compilation/**/build
