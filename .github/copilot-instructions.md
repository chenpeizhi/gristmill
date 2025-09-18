# Copilot Instructions for Gristmill

Gristmill is a tensor contraction optimizer and code generator built on top of the [drudge](https://github.com/DrudgeCAS/drudge) computer algebra system. It's designed for quantum chemistry and many-body theory computations but is suitable for any scientific computing problem involving tensors.

## Repository Overview

**Project Type**: Python package with C++ extensions  
**Size**: ~7k lines of Python code in main package  
**Languages**: Python 3.12+, C++17  
**Main Components**:
- `gristmill/optimize.py` (2967 lines) - Core optimization algorithms  
- `gristmill/generate.py` (1557 lines) - Code generation and printers  
- `gristmill/utils.py` (612 lines) - Utility functions including FLOP counting  

**Key Dependencies**: drudge, sympy, numpy, networkx, jinja2  
**Build Dependencies**: C++ compiler with C++17 support, Python setuptools

## Critical Setup Instructions

### 1. Environment Setup (ALWAYS REQUIRED)

**ALWAYS install uv before building**:
```bash
pip install uv
```

**ALWAYS initialize submodules before building** (contains C++ dependencies):
```bash
git submodule update --init --recursive
```

**ALWAYS set up the environment with uv** (handles all dependencies automatically):
```bash
uv sync --locked --extra dev
```

**ALWAYS set DUMMY_SPARK=1 environment variable before running tests**:
```bash
export DUMMY_SPARK=1
```

This is critical - the project is migrating from pyspark to dask, and all tests must use dummy_spark instead of pyspark to avoid conflicts.

### 2. Build and Installation

The project uses both `setup.py` and `pyproject.toml`. The C++ extension requires compilation:

```bash
# After environment setup, the package is built automatically by uv
# To test the installation works:
uv run python -c "import gristmill; print('gristmill imported successfully')"
```

**Build time**: ~1-2 minutes depending on C++ compilation

### 3. Running Tests

**Essential**: ALWAYS set the DUMMY_SPARK environment variable:
```bash
export DUMMY_SPARK=1
uv run pytest tests -v
```

**Test execution time**: ~30 seconds  
**Expected results**: 30 passed, 2 xfailed

Tests require the virtual environment created by uv. Running tests outside the uv environment will fail with import errors.

### 4. Coverage Testing (as used in CI)

```bash
uv pip install coverage
export DUMMY_SPARK=1
uv run coverage run --source=gristmill --omit="*/templates/*" -m pytest tests
```

### 5. Documentation Building

Requires sphinx and the uv environment:
```bash
uv pip install sphinx
cd docs
export DUMMY_SPARK=1
uv run make html
```

**Build time**: ~10 seconds  
**Output**: `docs/_build/html/`

## Project Architecture

### Key Configuration Files
- `pyproject.toml` - Modern Python project metadata and dependencies
- `setup.py` - Package setup with C++ extension configuration  
- `MANIFEST.in` - Package data inclusion rules (C++ headers, templates)
- `uv.lock` - Exact dependency versions for reproducible builds

### Source Layout
```
gristmill/
├── __init__.py          # Main exports (27 lines)
├── generate.py          # Code generation framework (1557 lines)
├── optimize.py          # Tensor optimization algorithms (2967 lines)
├── utils.py             # Utilities and FLOP counting (612 lines)
├── _parenth.cpp         # C++ extension for parenthesization (368 lines)
└── templates/           # Code generation templates
    ├── einsum           # NumPy einsum template
    ├── naiveterm        # Naive term evaluation template  
    └── naivezero        # Zero initialization template
```

### Test Layout
```
tests/
├── conftest.py          # Pytest configuration with Spark context setup
├── opt_cc_test.py       # Coupled cluster optimization tests (268 lines)
├── opt_matrix_test.py   # Matrix optimization tests (570 lines)
├── opt_misc_test.py     # Miscellaneous optimization tests (230 lines)
└── printers_test.py     # Code generation printer tests (491 lines)
```

### C++ Dependencies (in deps/ subdirectory)
- `cpypp/` - C++ Python bindings utilities
- `fbitset/` - Fast bitset implementation  
- `libparenth/` - Parenthesization algorithms

### CI/CD Workflows
- `.github/workflows/ci.yml` - Main CI pipeline (Ubuntu/macOS, Python 3.12)
- `.github/workflows/copilot-setup-steps.yml` - Reference setup steps

## Common Issues and Solutions

### Import Errors
**Problem**: `ModuleNotFoundError: No module named 'drudge'`  
**Solution**: Always use `uv run python` instead of bare `python` to access the virtual environment.

### Test Failures Related to Spark
**Problem**: Tests fail with pyspark-related errors  
**Solution**: Ensure `export DUMMY_SPARK=1` is set before running any tests or imports.

### C++ Compilation Errors
**Problem**: Extension build fails  
**Solution**: Ensure C++ compiler supports C++17 and submodules are initialized.

### Documentation Build Errors  
**Problem**: sphinx cannot import gristmill  
**Solution**: Use `uv run make html` from docs directory, not bare `make html`.

## Key Facts for Code Changes

### Main Public API (from `__init__.py`)
- `optimize()` - Main optimization function
- `verify_eval_seq()` - Sequence verification
- `get_flop_cost()` - FLOP cost calculation
- Printer classes: `BasePrinter`, `FortranPrinter`, `EinsumPrinter`, etc.

### Critical Test Requirements
- Tests expect `DUMMY_SPARK=1` environment variable
- All tests run through pytest framework
- Some tests are marked as `xfail` (expected failures) - don't try to fix them
- Tests validate mathematical correctness of optimizations

### Code Generation
- Uses Jinja2 templates in `gristmill/templates/`
- Supports Fortran, C, and Python (NumPy einsum) backends
- Templates are included via `MANIFEST.in`

## Validation Steps

After making changes, always run in this order:
1. `export DUMMY_SPARK=1`
2. `uv run pytest tests` (expect: 30 passed, 2 xfailed)
3. `uv run python -c "import gristmill; print('OK')"`
4. For documentation changes: `cd docs && uv run make html`

**Trust these instructions** - they are based on validated testing of the repository's build system. Only search for additional information if these instructions are incomplete or incorrect for your specific task.