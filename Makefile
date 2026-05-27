.PHONY: fmt lint test ci plan apply destroy

fmt:
	python -m black .
	python -m ruff check . --fix

lint:
	python -m ruff check .
	python -m black --check .

test:
	python -m pytest -q

ci: lint test

plan:
	@echo "TODO: add terraform plan"

apply:
	@echo "TODO: add terraform apply"

destroy:
	@echo "TODO: add terraform destroy"
