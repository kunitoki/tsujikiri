default:
    @just --list

# Create/update a local virtual environment from pyproject metadata.
sync:
    uv sync

# Build both source distribution and wheel.
build:
    uv build

# Build wheel only.
wheel:
    uv build --wheel

# Build source distribution only.
sdist:
    uv build --sdist

# Run test suite.
test *args:
    uv run pytest -n auto {{args}}

# Run tests with coverage report.
coverage *args:
    uv run pytest -n auto --cov=tsujikiri --cov-branch --cov-report=term-missing {{args}}

# Remove build artifacts.
clean:
    rm -rf dist build src/*.egg-info src/**/.pytest_cache .pytest_cache .coverage htmlcov
