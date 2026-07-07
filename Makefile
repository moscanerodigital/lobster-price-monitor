# lobster-price-monitor — Mac mini / Chromebox deployment targets
PYTHON ?= .venv/bin/python
VENV   ?= .venv
PORT   ?= 8765
BIND   ?= 0.0.0.0

.PHONY: install scrape serve serve-tailnet health verify verify-core verify-visual test seed-ci-fixtures seed-ci-bplus-fixtures verify-ci verify-next-ci verify-production-ci verify-ops-ci verify-deploy-ci verify-deploy verify-ops promote-ops demote-ops install-scheduler uninstall-scheduler bootstrap-host deploy-host teardown-host upgrade-host redeploy-host rebuild-host reprovision-host status-host watchdog-host recover-host regen-bplus-fixtures import-five-islands sync-scrape-state archive-board mirror-host

install:
	python3 -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requirements.txt

scrape:
	$(PYTHON) scripts/scrape_markets.py --no-alerts

import-five-islands:
	$(PYTHON) scripts/manual_import.py --market "Five Islands Lobster Co." --tier soft_shell --price 14.99 --unit lb --kind lobster_tier
	$(PYTHON) scripts/manual_import.py --market "Five Islands Lobster Co." --tier hard_shell --price 15.99 --unit lb --kind lobster_tier

# Copy gated scrape state from dev workspace into LOBSTER_ROOT (local same-machine handoff).
LOBSTER_ROOT ?= $(HOME)/lobster-price-monitor
sync-scrape-state:
	@test -n "$(SOURCE_DATA)" || (echo "Usage: make sync-scrape-state SOURCE_DATA=/path/to/dev/data" && exit 1)
	cp "$(SOURCE_DATA)/prices.jsonl" "$(LOBSTER_ROOT)/data/prices.jsonl"
	cp "$(SOURCE_DATA)/run-log.jsonl" "$(LOBSTER_ROOT)/data/run-log.jsonl" 2>/dev/null || true
	cp "$(SOURCE_DATA)/market-coverage.json" "$(LOBSTER_ROOT)/data/market-coverage.json" 2>/dev/null || true
	$(MAKE) -C "$(LOBSTER_ROOT)" import-five-islands
	cd "$(LOBSTER_ROOT)" && $(MAKE) board-html PYTHON=$(LOBSTER_ROOT)/.venv/bin/python

board-html:
	BOARD_AUTO_REFRESH=0 $(PYTHON) scripts/board.py --html

archive-board:
	$(PYTHON) scripts/archive_board.py

mirror-host:
	@test -n "$(HOST)" || (echo "Usage: make mirror-host HOST=mac-mini" && exit 1)
	ssh $(HOST) 'cd ~/lobster-price-monitor && git pull --ff-only && make recover-host'

serve serve-tailnet:
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
	$(PYTHON) scripts/test_upgrade_host.py
	$(PYTHON) scripts/test_redeploy_host.py
	$(PYTHON) scripts/test_rebuild_host.py
	$(PYTHON) scripts/test_reprovision_host.py
	$(PYTHON) scripts/test_status_host.py
	$(PYTHON) scripts/test_watchdog_host.py
	$(PYTHON) scripts/test_recover_host.py
	$(PYTHON) scripts/test_host_health_state.py
	$(PYTHON) scripts/test_preflight_secrets.py
	$(PYTHON) scripts/test_secrets.py
	$(PYTHON) scripts/test_scrape_publish_gate.py
	$(PYTHON) scripts/test_board_lobster.py
	$(PYTHON) scripts/test_fb_curl_fetch.py
	$(PYTHON) scripts/test_board_meta.py
	$(PYTHON) scripts/test_serve_board.py
	$(PYTHON) scripts/test_archive_board.py

verify-visual:
	$(PYTHON) scripts/test_board_visual.py

verify: verify-core verify-visual
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
	bash scripts/teardown_host.sh $(TEARDOWN_FLAGS)

upgrade-host:
	bash scripts/upgrade_host.sh

redeploy-host:
	bash scripts/redeploy_host.sh

rebuild-host:
	bash scripts/rebuild_host.sh

reprovision-host:
	bash scripts/reprovision_host.sh

status-host:
	bash scripts/status_host.sh

watchdog-host:
	bash scripts/watchdog_host.sh

recover-host:
	bash scripts/recover_host.sh

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

verify-ci: seed-ci-fixtures verify verify-visual

verify-production-ci: seed-ci-bplus-fixtures verify
	$(PYTHON) scripts/verify_production_gate.py --skip-scheduling

verify-deploy-ci: seed-ci-bplus-fixtures verify-core
	$(PYTHON) scripts/board.py --html
	$(PYTHON) scripts/verify_deploy_gate.py --skip-scheduling --skip-verify-suite

verify-ops-ci: seed-ci-bplus-fixtures verify
	$(PYTHON) scripts/update_ralph_learnings.py
	$(PYTHON) scripts/verify_ops_gate.py --skip-scheduling --skip-alerts-check
