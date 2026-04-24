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
    uv run ruff format src/tsujikiri/*.py tests/**/*.py

# Run mypy type checking.
check: sync format
    uv run mypy
    uv run ruff check src/tsujikiri/*.py tests/**/*.py

# Build HTML documentation locally (mirrors ReadTheDocs build).
docs:
    uv sync --extra dev --group docs
    uv run sphinx-build -T -W --keep-going -j auto -b html -d docs/_build/doctrees -D language=en docs docs/_build/html
    @echo "Docs built at docs/_build/html/index.html"

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
    rm -rf docs/_build
