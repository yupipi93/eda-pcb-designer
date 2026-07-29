# eda-pcb-designer — self-documenting Makefile (`make help`)
.DEFAULT_GOAL := help
PY ?= python3

help:  ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## Install the package
	$(PY) -m pip install .

dev:  ## Editable install with dev + all optional extras
	$(PY) -m pip install -e '.[dev,schematic,render,verify]'

test:  ## Run the test suite
	$(PY) -m pytest -q

lint:  ## Ruff lint (src + tests)
	$(PY) -m ruff check src tests

fmt:  ## Ruff lint with autofix
	$(PY) -m ruff check --fix src tests

freerouting:  ## Fetch the pinned freerouting JAR into vendor/ (checksum-verified)
	./vendor/fetch-freerouting.sh

validate-examples:  ## Validate every example config
	pcb-designer validate --config examples/mt1.yaml
	pcb-designer validate --config examples/blank-board/blank.yaml

mt1-pipeline:  ## Run the MT1 worked example: schematic → place → render (needs KiCad 9)
	pcb-designer pipeline --config examples/mt1.yaml --stages schematic,place,render

api:  ## Run the HTTP API locally (dev server on :8080)
	$(PY) -m pcb_designer.api

docker:  ## Build the pipeline-in-a-box image (KiCad 9 + Java 21 + freerouting)
	docker build -t eda-pcb-designer .

docker-api:  ## Build + run the HTTP API image (Cloud Run image) on :8080
	docker build -f deploy/Dockerfile -t pcb-designer-api .
	docker run --rm -p 8080:8080 pcb-designer-api

docker-smoke:  ## Run the containerised MT1 smoke test (validate + place + render)
	docker run --rm -w /app eda-pcb-designer validate --config examples/mt1.yaml
	docker run --rm -w /app eda-pcb-designer pipeline --config examples/mt1.yaml --stages place,render

clean:  ## Remove caches and build artefacts
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

.PHONY: help install dev test lint fmt freerouting validate-examples mt1-pipeline api docker docker-api docker-smoke clean
