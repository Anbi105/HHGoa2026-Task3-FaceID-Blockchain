# FaceProof — every demo command is one target.
PY := .venv/bin/python
PIP := .venv/bin/pip
SUBJECT ?= alice
IMAGE ?= data/demo/synthetic_face.jpg

.PHONY: help venv install setup test cov fixtures demo-variants \
        consent-grant consent-list consent-revoke probe calibrate \
        config demo clean-runs \
        banner index-stats search anchor verify tamper abstain forget \
        deploy anvil forge-test stage3-test

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

# ── Stage 3 (blockchain attestation) ───────────────────────────────
# Added by Person 3.  These wrap faceproof.run / Foundry and do not change
# any Stage 1 target above.

banner: ## Stage 3: print the public pipeline configuration
	$(PY) -m faceproof.run banner

index-stats: ## Stage 3: print the index snapshot id / stats
	$(PY) -m faceproof.run index-stats

search: ## Stage 3: Stage 1 handoff -> Stage 2 -> 8-group evidence bundle
	$(PY) -m faceproof.run search --img $(IMAGE) --subject $(SUBJECT)

anchor: ## Stage 3: anchor the latest run's Merkle root on-chain
	$(PY) -m faceproof.run anchor

verify: ## Stage 3: independently re-verify the latest run (add CHAIN=1 for on-chain)
	$(PY) -m faceproof.run verify $(if $(CHAIN),--chain,)

tamper: ## Stage 3: single-character tamper demonstration on the latest run
	$(PY) -m faceproof.run tamper

abstain: ## Stage 3: show the abstain path (quality-gate rejection -> no bundle)
	$(PY) -m faceproof.run abstain --subject $(SUBJECT)

forget: ## Stage 3: revoke consent and destroy the erasure salt
	$(PY) -m faceproof.run forget --subject $(SUBJECT)

anvil: ## Stage 3: start a local Anvil node on :8545
	anvil

deploy: ## Stage 3: build + deploy EvidenceRegistry to local Anvil
	forge build --root contracts
	forge script contracts/script/Deploy.s.sol:DeployScript --root contracts \
	  --rpc-url http://127.0.0.1:8545 --broadcast \
	  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

forge-test: ## Stage 3: run the Foundry contract test suite
	forge test --root contracts -vv

stage3-test: ## Stage 3: run only the Stage 3 Python tests
	$(PY) -m pytest -q tests/test_canonical.py tests/test_merkle.py \
	  tests/test_bundle.py tests/test_stage2_adapter.py tests/test_verify.py \
	  tests/test_chain.py tests/test_run.py

