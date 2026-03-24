# CLAUDE.md

## Project: flaky-test-detector
Python CLI tool that parses CI test artifacts, fingerprints failures by stacktrace,
and detects flaky tests across runs.

## Tech Stack
- Python 3.11+, managed with uv
- CLI: click
- Storage: SQLite (via stdlib sqlite3)
- Testing: pytest + pytest-cov
- Linting: ruff
- Type checking: ty

## Architecture
- `src/flakydetector/` — main package
- `src/flakydetector/parsers/` — pluggable parsers (BaseParser interface)
- `src/flakydetector/reporters/` — output formatters
- `tests/` — pytest tests, fixtures in `tests/fixtures/`

## Development Commands
- `uv run pytest tests/ -v` — run tests
- `uv run ruff check .` — lint
- `uv run ruff format .` — format
- `uv run flaky-detect --help` — CLI

## Key Design Decisions
- Parsers auto-detect format via `can_parse()` method
- Fingerprinting normalizes line numbers, timestamps, UUIDs, memory addresses before hashing
- Flakiness = 1.0 - abs(pass_rate - 0.5) * 2 (closer to 0.5 pass rate = more flaky)
- SQLite for history (single file, no server, works in CI)

## Testing Philosophy
- Every parser gets: can_parse positive/negative, parse with count assertions, parse with content assertions
- Fingerprinting: same-root-cause produces same hash, different causes produce different hashes
- Analyzer: synthetic history data to test flakiness detection
- Integration tests: run CLI as subprocess, verify exit codes and output

## Rules
- Always write failing test first (TDD)
- New parsers must implement BaseParser interface
- Keep CLI thin — business logic in modules, not in click commands
- Fixtures go in tests/fixtures/ with realistic data
