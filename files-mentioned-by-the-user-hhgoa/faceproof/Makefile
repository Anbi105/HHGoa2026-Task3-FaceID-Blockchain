PYTHON ?= python
IMG ?= fixtures/subject_a.jpg
RUN ?=
.PHONY: setup test calibrate ingest index probe search anchor verify tamper abstain forget run
setup:
	$(PYTHON) -m pip install -r requirements.txt
test:
	$(PYTHON) -m pytest -q
calibrate:
	$(PYTHON) -m faceproof.calibrate
ingest:
	@echo "Use: python -m faceproof.ingest_bsky --handles consenting.handle.bsky.social"
index:
	@echo "Build via faceproof.index.build(records, config); records require locally re-fetched images."
probe:
	$(PYTHON) -m faceproof.run --img $(IMG)
search: probe
run: probe
verify:
	$(PYTHON) -c "from faceproof.verify import main; main('$(RUN)')"
tamper:
	$(PYTHON) -c "import json; from pathlib import Path; p=Path('$(RUN)')/'bundle.json'; x=json.loads(p.read_text()); x['fields']['match_location']['post_url'] += 'x'; p.write_text(json.dumps(x)); from faceproof.verify import main; main('$(RUN)')"
abstain:
	$(PYTHON) -m faceproof.run --img $(IMG)
forget:
	$(PYTHON) -c "from faceproof.forget import forget; forget('$(RUN)')"
