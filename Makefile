# lobster-price-monitor — Mac mini / Chromebox deployment targets
PYTHON ?= .venv/bin/python
VENV   ?= .venv
PORT   ?= 8765
BIND   ?= 0.0.0.0

.PHONY: install scrape serve health verify verify-core test seed-ci-fixtures seed-ci-bplus-fixtures verify-ci verify-next-ci verify-production-ci verify-ops-ci verify-deploy-ci verify-deploy verify-ops promote-ops demote-ops install-scheduler uninstall-scheduler bootstrap-host deploy-host teardown-host regen-bplus-fixtures

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

seed-ci-bplus-fixtures:
	mkdir -p data
	$(PYTHON) scripts/refresh_ci_fixture_dates.py
	$(PYTHON) scripts/board.py --html

verify-core:
	@test -f data/prices.jsonl || $(MAKE) seed-ci-fixtures
	$(PYTHON) scripts/test_parse.py
	$(PYTHON) scripts/test_parse_web.py
	$(PYTHON) scripts/test_quality_gate.py
	$(PYTHON) scripts/test_specials.py
	$(PYTHON) scripts/test_aaa_gate.py
	$(PYTHON) scripts/test_verify_next_ci.py
	$(PYTHON) scripts/test_verify_production_ci.py
	$(PYTHON) scripts/test_update_ralph_learnings.py
	$(PYTHON) scripts/test_verify_ops_ci.py
	$(PYTHON) scripts/test_deploy_units.py
	$(PYTHON) scripts/test_scheduling_gates.py
	$(PYTHON) scripts/test_bootstrap_host.py
	$(PYTHON) scripts/test_deploy_host.py
	$(PYTHON) scripts/test_demote_ops.py
	$(PYTHON) scripts/test_uninstall_scheduler.py
	$(PYTHON) scripts/test_teardown_host.py
	$(PYTHON) scripts/test_preflight_secrets.py

verify: verify-core
	$(PYTHON) scripts/test_verify_deploy_ci.py
	$(PYTHON) scripts/verify_aaa_gate.py

verify-next: verify
	$(PYTHON) scripts/verify_next_gate.py

verify-production: verify-next
	$(PYTHON) scripts/verify_production_gate.py

verify-deploy: verify-core
	$(PYTHON) scripts/verify_deploy_gate.py

verify-ops: verify-production
	$(PYTHON) scripts/verify_ops_gate.py

install-scheduler:
	bash scripts/install_scheduler.sh

uninstall-scheduler:
	bash scripts/uninstall_scheduler.sh

teardown-host:
	bash scripts/teardown_host.sh

promote-ops:
	bash scripts/promote_ops.sh

demote-ops:
	bash scripts/demote_ops.sh

bootstrap-host:
	bash scripts/bootstrap_host.sh

deploy-host:
	bash scripts/deploy_host.sh

regen-bplus-fixtures:
	$(PYTHON) scripts/generate_ci_bplus_fixtures.py

test: verify

verify-next-ci: seed-ci-bplus-fixtures verify
	$(PYTHON) scripts/verify_next_gate.py --min-lobster-markets 7

verify-ci: seed-ci-fixtures verify

verify-production-ci: seed-ci-bplus-fixtures verify
	$(PYTHON) scripts/verify_production_gate.py --skip-scheduling

verify-deploy-ci: seed-ci-bplus-fixtures verify-core
	$(PYTHON) scripts/verify_deploy_gate.py --skip-scheduling --skip-verify-suite

verify-ops-ci: seed-ci-bplus-fixtures verify
	$(PYTHON) scripts/update_ralph_learnings.py
	$(PYTHON) scripts/verify_ops_gate.py --skip-scheduling --skip-alerts-check
