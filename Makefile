# FaceProof — every demo command is one target.
PY := .venv/bin/python
PIP := .venv/bin/pip
SUBJECT ?= alice
IMAGE ?= data/demo/synthetic_face.jpg

.PHONY: help venv install setup test cov fixtures demo-variants \
        consent-grant consent-list consent-revoke probe calibrate \
        config demo clean-runs

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

venv: ## create the virtualenv
	python3 -m venv .venv

install: ## install the package and dev dependencies
	$(PIP) install -e ".[dev]"

setup: ## pre-download model weights (run BEFORE the recording)
	$(PY) -m faceproof.cli setup

test: ## run the test suite (no model, no network)
	$(PY) -m pytest tests/

cov: ## run tests with a coverage report
	$(PY) -m pytest tests/ --cov=faceproof --cov-report=term-missing

config: ## print the configuration in force
	$(PY) -m faceproof.cli config

fixtures: ## regenerate + verify the synthetic demo fixtures
	$(PY) scripts/gen_fixtures.py

demo-variants: ## derive gate demos from a real photo: make demo-variants SRC=photo.jpg
	@test -n "$(SRC)" || (echo "usage: make demo-variants SRC=path/to/photo.jpg"; exit 2)
	$(PY) scripts/make_demo_variants.py "$(SRC)" --subject $(SUBJECT)

consent-grant: ## grant consent: make consent-grant SUBJECT=alice
	$(PY) -m faceproof.cli consent grant $(SUBJECT)

consent-list: ## list consent records and their status
	$(PY) -m faceproof.cli consent list

consent-revoke: ## revoke consent and destroy the salt (erasure demo)
	$(PY) -m faceproof.cli consent revoke $(SUBJECT)

probe: ## run a probe: make probe IMAGE=... SUBJECT=alice
	$(PY) -m faceproof.cli probe $(IMAGE) --subject $(SUBJECT)

calibrate: ## measure the acceptance threshold from data/calib
	$(PY) -m faceproof.calibrate data/calib

demo: ## the full recorded sequence, in order
	@echo "── 1. configuration in force ─────────────────────────────"
	@$(PY) -m faceproof.cli config
	@echo "\n── 2. probe with no consent on record → REFUSED ──────────"
	-@$(PY) -m faceproof.cli probe $(IMAGE) --subject $(SUBJECT) 2>/dev/null
	@echo "\n── 3. subject grants consent ─────────────────────────────"
	@$(PY) -m faceproof.cli consent grant $(SUBJECT)
	@echo "\n── 4. probe accepted → handoff written ───────────────────"
	@$(PY) -m faceproof.cli probe $(IMAGE) --subject $(SUBJECT) 2>/dev/null
	@echo "\n── 5. a face the gate rejects → ABSTAIN ──────────────────"
	-@$(PY) -m faceproof.cli probe data/demo/noface.jpg --subject $(SUBJECT) 2>/dev/null
	@echo "\n── 6. subject withdraws consent → salt destroyed ─────────"
	@$(PY) -m faceproof.cli consent revoke $(SUBJECT)
	@echo "\n── 7. the same probe is now refused ──────────────────────"
	-@$(PY) -m faceproof.cli probe $(IMAGE) --subject $(SUBJECT) 2>/dev/null

clean-runs: ## delete out/ (run artifacts, including raw embeddings)
	rm -rf out
