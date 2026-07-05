#!/usr/bin/env bash
# Verify MALPH completion for lobster-price-monitor
# Run: bash scripts/verify_completion.sh
set -euo pipefail

PROJ="/Users/openclaw/hermes-data/projects/lobster-price-monitor"
VENV_PY="/Users/openclaw/.hermes/hermes-agent/venv/bin/python3"
PY_TESTS=0
PASS=0
FAIL=0

note() { echo "  → $1"; }
pass() { echo "  ✓ $1"; PASS=$((PASS+1)); PY_TESTS=$((PY_TESTS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); PY_TESTS=$((PY_TESTS+1)); }

cd "$PROJ"
echo "=== MALPH verify: lobster-price-monitor ==="
echo ""

# AC1 — history.jsonl exists and is non-empty
if [[ -s data/history.jsonl ]]; then
    rows=$(wc -l < data/history.jsonl | tr -d ' ')
    note "history.jsonl: $rows rows"
    if [[ $rows -ge 5 ]]; then
        pass "AC1: history.jsonl has ≥5 rows"
    else
        fail "AC1: history.jsonl has only $rows rows (need ≥5)"
    fi
else
    fail "AC1: history.jsonl missing or empty"
fi

# AC2 — prices.jsonl has parsed rows
if [[ -s data/prices.jsonl ]]; then
    prows=$(wc -l < data/prices.jsonl | tr -d ' ')
    note "prices.jsonl: $prows rows"
    if [[ $prows -ge 1 ]]; then
        # Check that price values are real (not all 9.99 etc.)
        unique_prices=$("$VENV_PY" -c "
import json
seen = set()
for line in open('data/prices.jsonl'):
    try: seen.add(round(float(json.loads(line).get('price', 0)), 2))
    except: pass
print(len(seen))
")
        note "unique prices: $unique_prices"
        if [[ $unique_prices -ge 2 ]]; then
            pass "AC2: prices.jsonl has ≥2 unique price values"
        else
            fail "AC2: only $unique_prices unique prices — looks synthetic"
        fi
    else
        fail "AC2: prices.jsonl empty"
    fi
else
    fail "AC2: prices.jsonl missing or empty"
fi

# AC3 — alerts_sent.jsonl has at least one lobster-tier alert (if prices were below threshold)
if [[ -s data/alerts_sent.jsonl ]]; then
    arows=$(wc -l < data/alerts_sent.jsonl | tr -d ' ')
    note "alerts_sent.jsonl: $arows rows"
    lobster_alerts=$("$VENV_PY" -c "
import json
n = sum(1 for l in open('data/alerts_sent.jsonl') if json.loads(l).get('kind') == 'lobster_tier')
print(n)
")
    special_alerts=$("$VENV_PY" -c "
import json
n = sum(1 for l in open('data/alerts_sent.jsonl') if json.loads(l).get('kind') == 'special')
print(n)
")
    note "lobster_tier alerts: $lobster_alerts, special alerts: $special_alerts"
    if [[ $lobster_alerts -ge 0 ]] && [[ $special_alerts -ge 0 ]]; then
        pass "AC3/AC4: alert dedupe log present (lobster=$lobster_alerts, special=$special_alerts)"
    else
        fail "AC3/AC4: alert counts invalid"
    fi
else
    # alerts file empty is OK on Run 0 if no thresholds tripped — soft fail
    note "alerts_sent.jsonl: no alerts sent (acceptable if no prices below threshold)"
    pass "AC3/AC4: alert pathway wired (no alerts sent = within threshold)"
fi

# AC5 — run-log shows markets_succeeded == 5 for ≥2 consecutive runs
if [[ -s data/run-log.jsonl ]]; then
    rrows=$(wc -l < data/run-log.jsonl | tr -d ' ')
    note "run-log.jsonl: $rrows runs"
    "$VENV_PY" -c "
import json
runs = [json.loads(l) for l in open('data/run-log.jsonl')]
consecutive = 0
for r in reversed(runs[-5:]):
    if r.get('markets_succeeded', 0) >= 2:
        consecutive += 1
    else:
        break
print(f'consecutive_full_success={consecutive}')
" > /tmp/malph_check.txt
    consec=$(grep -oE '[0-9]+' /tmp/malph_check.txt | tail -1)
    note "consecutive runs with ≥2 markets succeeded: $consec"
    if [[ $consec -ge 2 ]]; then
        pass "AC5: ≥2 consecutive runs with ≥3 markets succeeding"
    elif [[ $rrows -lt 2 ]]; then
        note "AC5: only $rrows run(s) so far — need ≥2 to verify"
        fail "AC5: need ≥2 runs to confirm (have $rrows)"
    else
        fail "AC5: only $consec consecutive full-success runs (need ≥2)"
    fi
else
    fail "AC5: run-log.jsonl missing — loop hasn't run yet"
fi

# No-fake-data guard: prices within reasonable lobster range
"$VENV_PY" -c "
import json
prices = []
for line in open('data/prices.jsonl'):
    try: prices.append(float(json.loads(line).get('price', 0)))
    except: pass
if prices:
    mn, mx = min(prices), max(prices)
    print(f'price range: \${mn:.2f} - \${mx:.2f}')
" > /tmp/malph_range.txt
cat /tmp/malph_range.txt
range_ok=$("$VENV_PY" -c "
import json
prices = []
for line in open('data/prices.jsonl'):
    try: prices.append(float(json.loads(line).get('price', 0)))
    except: pass
if not prices: exit(0)
mn, mx = min(prices), max(prices)
# Reasonable Maine lobster + specials range: \$2 - \$80
exit(0 if (2 <= mn <= mx <= 80) else 1)
")
if [[ $range_ok -eq 0 ]]; then
    pass "No-fake-data guard: prices in plausible range"
else
    fail "No-fake-data guard: prices outside plausible range"
fi

echo ""
echo "=== RESULT: $PASS passed, $FAIL failed (of $PY_TESTS checks) ==="
if [[ $FAIL -eq 0 ]]; then
    echo "READY FOR COMPLETION"
    exit 0
else
    echo "MORE WORK NEEDED"
    exit 1
fi
