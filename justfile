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
    uv run pytest {{args}}

# Run tests with coverage report.
coverage:
    uv run pytest --cov=tsujikiri --cov-report=term-missing -vv

# Remove build artifacts.
clean:
    rm -rf dist build src/*.egg-info src/**/.pytest_cache .pytest_cache .coverage htmlcov
