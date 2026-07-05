# lobster-price-monitor — Mac mini / Chromebox deployment targets
PYTHON ?= .venv/bin/python
VENV   ?= .venv
PORT   ?= 8765
BIND   ?= 0.0.0.0

.PHONY: install scrape serve health verify test seed-ci-fixtures verify-ci

install:
	python3 -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requirements.txt

scrape:
	$(PYTHON) scripts/scrape_markets.py --no-alerts

serve:
	$(PYTHON) scripts/serve_board.py --port $(PORT) --host $(BIND)

health:
	$(PYTHON) scripts/health_check.py

seed-ci-fixtures:
	mkdir -p data
	cp fixtures/ci_gate/* data/
	$(PYTHON) scripts/board.py --html

verify:
	@test -f data/prices.jsonl || $(MAKE) seed-ci-fixtures
	$(PYTHON) scripts/test_parse.py
	$(PYTHON) scripts/test_parse_web.py
	$(PYTHON) scripts/test_quality_gate.py
	$(PYTHON) scripts/test_specials.py
	$(PYTHON) scripts/test_aaa_gate.py
	$(PYTHON) scripts/verify_aaa_gate.py

verify-next: verify
	$(PYTHON) scripts/verify_next_gate.py

verify-production: verify-next
	$(PYTHON) scripts/verify_production_gate.py

test: verify

verify-ci: seed-ci-fixtures verify
