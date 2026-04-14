default:
    @just --list

# Create/update a local virtual environment from pyproject metadata including dev dependencies.
sync:
    uv sync --extra dev

# Build wheel and source distribution.
wheel:
    @just sync
    uv build

# Run test suite.
test *args:
    @just sync
    uv run pytest -n auto {{args}}

# Regenerate inline stubs (src/tsujikiri/**/*.pyi) via stubgen.
stubs:
    @just sync
    uv run stubgen -p tsujikiri -o src

# Run mypy type checking.
typecheck:
    @just sync
    uv run mypy

# Run tests with coverage report.
coverage *args:
    @just sync
    uv run pytest -n auto --cov=tsujikiri --cov-branch --cov-report=term-missing {{args}}

# Publish a release (build + PyPI publish handled by .github/workflows/release.yml on tag push)
publish version:
    echo "__version__ = \"{{version}}\"" > src/tsujikiri/__init__.py
    perl -0pi -e 's/x=(\d+)/"x=" . ($1 + 1)/ge' README.md

# Remove build artifacts.
clean:
    rm -rf dist build .venv src/*.egg-info
    rm -rf src/**/.pytest_cache .pytest_cache .mypy_cache .coverage htmlcov
    rm -rf tests/test_compilation/build/ tests/test_compilation/.cmake_*.lock
