# Music Streaming Data Pipeline

Event-driven AWS ETL pipeline for music streaming analytics.

## Project Status

This repository is organized by implementation phases.

- Phase 1: bootstrap structure, Python tooling, CI baseline.
- Later phases: Terraform infrastructure, Glue jobs, Step Functions, Lambda archive handlers, and end-to-end tests.

Reference plan: `docs/plan/music_streaming_pipeline_implementation_plan_guide.md`

## Repository Layout

- `infra/`: Terraform environments and reusable modules.
- `glue_jobs/`: AWS Glue scripts for validation, KPI compute, and DynamoDB load.
- `lambda/`: archive success/failure Lambda handlers.
- `state_machine/`: Step Functions ASL definition.
- `tests/`: unit tests and fixtures.
- `docs/`: architecture, runbook, and query references.

## Local Setup

1. Create and activate a Python 3.10+ virtual environment.
2. Install dev dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

3. Run checks:

```bash
python -m pytest -q
python -m ruff check .
python -m black --check .
```

## Make Targets

- `make fmt` or `mingw32-make fmt`: auto-format Python files.
- `make lint`: run ruff + black check.
- `make test`: run unit tests.
- `make ci`: run full local CI sequence.

## Notes

- `sample_data/` is a mirror-oriented scaffold target for `data/`.
- Existing sample CSV data lives under `data/`.
