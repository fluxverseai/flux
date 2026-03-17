# Contributing to Flux

## Development Setup

```bash
git clone https://github.com/fluxverseai/flux
cd flux
uv pip install -e ".[dev]"
```

## Running Tests

```bash
uv run pytest tests/ -v --cov=lib          # Full suite with coverage
uv run pytest tests/unit/ -v               # Unit tests only
uv run pytest tests/integration/ -v        # Integration tests only
```

Tests use `FLUX_TEST_ROOT` to isolate all file operations in temp directories — they never touch your real `~/.flux/`.

## Linting

```bash
uv run ruff check lib/ flux_cli/ tests/
```

Ruff rules: E/F/W (pyflakes), I (isort), UP (pyupgrade), B (bugbear), SIM (simplify), S (bandit security).

## Code Style

- Python 3.11+, modern syntax (`list[str]`, `str | None`)
- Type annotations on all public functions
- Concise docstrings — one-line for simple functions, multi-line only for non-obvious behavior
- Line length: 120 characters
- Atomic file writes (temp file + rename) for all JSON/TOML saves

## Coverage Requirement

PRs must maintain **>90% test coverage**. Run `pytest --cov=lib --cov-report=term-missing` to check.

## Pull Request Process

1. Create a branch: `feature/description`, `fix/description`, or `chore/description`
2. Write tests alongside code
3. Ensure `ruff check` passes with zero errors
4. Ensure all tests pass
5. Open PR against `main`

## Security

If you find a security vulnerability, please report it via GitHub Security Advisories rather than opening a public issue.
