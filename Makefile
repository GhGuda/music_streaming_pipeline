.PHONY: fmt lint test ci tf-init tf-validate plan apply empty-buckets destroy destroy-all

TF_DIR := infra/envs/dev

fmt:
	python -m black .
	python -m ruff check . --fix

lint:
	python -m ruff check .
	python -m black --check .

test:
	python -m pytest -q

ci: lint test

tf-init:
	terraform -chdir=$(TF_DIR) init

tf-validate:
	terraform -chdir=$(TF_DIR) validate

plan:
	terraform -chdir=$(TF_DIR) plan -out plan.tfplan

apply:
	terraform -chdir=$(TF_DIR) apply plan.tfplan

empty-buckets:
	@RAW=$$(terraform -chdir=$(TF_DIR) output -raw raw_bucket_name); \
	PROC=$$(terraform -chdir=$(TF_DIR) output -raw processed_bucket_name); \
	ARCH=$$(terraform -chdir=$(TF_DIR) output -raw archive_bucket_name); \
	SCR=$$(terraform -chdir=$(TF_DIR) output -raw scripts_bucket_name); \
	aws s3 rm s3://$$RAW --recursive || true; \
	aws s3 rm s3://$$PROC --recursive || true; \
	aws s3 rm s3://$$ARCH --recursive || true; \
	aws s3 rm s3://$$SCR --recursive || true

destroy:
	terraform -chdir=$(TF_DIR) destroy

destroy-all: empty-buckets destroy