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
    uv run pytest --cov=tsujikiri --cov-report=term-missing

# Generate binding files for CMake compilation tests.
gen-test-bindings:
    uv run tsujikiri -i tests/test_compilation/combined.input.yml -o pybind11 -O tests/test_compilation/pybind11_bindings.cpp
    uv run tsujikiri -i tests/test_compilation/combined.input.yml -o luabridge3 -O tests/test_compilation/luabridge3_bindings.cpp
    uv run tsujikiri -i tests/test_compilation/combined.input.yml -o c_api -O tests/test_compilation/c_api_bindings.h

# Configure and build CMake compilation tests (requires cmake).
cmake-test: gen-test-bindings
    cmake -S tests -B build/cmake-tests -DCMAKE_BUILD_TYPE=Release
    cmake --build build/cmake-tests --parallel

# Remove build artifacts.
clean:
    rm -rf dist build src/*.egg-info src/**/.pytest_cache .pytest_cache .coverage htmlcov
