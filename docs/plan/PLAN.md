## Create Planned Repository Scaffold (Decision-Complete)

### Summary
Create the project structure exactly as defined in `docs/plan/music_streaming_pipeline_implementation_plan_guide.md`, using a **folders + placeholders** scaffold so the repo is immediately ready for implementation. Keep all existing files/data intact, and only add missing structure.

### Implementation Changes
1. Establish the root layout under the current repo:
   - `.github/workflows/`
   - `infra/envs/dev`
   - `infra/modules/{s3,kms,iam,dynamodb,glue,lambda,step_functions,eventbridge,monitoring}`
   - `state_machine/`
   - `glue_jobs/common/`
   - `lambda/archive_success`, `lambda/archive_failure`
   - `sample_data/{users,songs,streams}`
   - `tests/{unit,fixtures}`
   - `scripts/`
   - `docs/architecture` and `docs/plan` remain as-is (already present)

2. Add placeholder files for implementation entrypoints:
   - Root: `README.md`, `pyproject.toml`, `Makefile`, `requirements-dev.txt`
   - CI/CD: `.github/workflows/ci.yml`, `.github/workflows/cd.yml`
   - Step Functions: `state_machine/pipeline.asl.json`
   - Glue jobs: `glue_jobs/validate_inputs.py`, `glue_jobs/compute_kpis.py`, `glue_jobs/load_dynamodb.py`, `glue_jobs/common/logging_utils.py`
   - Lambda: `lambda/archive_success/handler.py`, `lambda/archive_success/requirements.txt`, `lambda/archive_failure/handler.py`, `lambda/archive_failure/requirements.txt`
   - Tests: `tests/unit/test_validation.py`, `tests/unit/test_kpi_logic.py`, `tests/unit/test_dynamodb_items.py`, `tests/conftest.py`
   - Docs: `docs/runbook.md`, `docs/dynamodb_queries.md`
   - Scripts: `scripts/upload_sample.sh`, `scripts/trigger_manual.sh`, `scripts/invoke_failure_test.sh`

3. Add Terraform module/env placeholders:
   - `infra/envs/dev/{main.tf,variables.tf,terraform.tfvars,outputs.tf,backend.tf}`
   - For each module in `infra/modules/*`: `main.tf`, `variables.tf`, `outputs.tf`
   - IAM module additional policy directory: `infra/modules/iam/policies/` with placeholder policy JSON files.

4. Seed `sample_data/` as a mirror pointer target for current `data/`:
   - Create README-style note in `sample_data/` that it mirrors `data/` (copy/symlink decision deferred to implementation step by environment capability).
   - Do not move or alter `data/`.

### Test Plan
1. Tree validation:
   - Verify all planned directories exist.
   - Verify all required placeholder files exist and are non-destructive.
2. Safety validation:
   - Confirm existing files remain untouched (`data/*`, current docs, `project_docs.docx`).
3. Scaffold readiness:
   - Confirm top-level structure matches plan’s “Repository Structure” section.
   - Confirm no implementation logic is introduced beyond placeholders.

### Assumptions and Defaults
- Default chosen: **Folders + placeholders** (as confirmed).
- Existing repo contents are preserved; this is additive scaffolding only.
- Placeholder files will contain minimal headers/TODO comments only, not full implementation.
- `sample_data` initially created as structure + guidance; actual copy/symlink population happens during implementation phase based on OS/tooling constraints.
