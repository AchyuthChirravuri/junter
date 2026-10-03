#!/usr/bin/env bash
# Junter verification runner. Default is strictly offline PRE-DEPLOY.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PHASE="${1:-pre-deploy}"
PYTHON="${PYTHON:-python3}"
FAIL=0

run_gate() {
  local label="$1" module="$2" started ended elapsed
  started=$(date +%s)
  if "$PYTHON" -m unittest "$module" -v; then
    ended=$(date +%s); elapsed=$((ended - started)); printf 'PASS %-28s %ss\n' "$label" "$elapsed"
  else
    ended=$(date +%s); elapsed=$((ended - started)); printf 'FAIL %-28s %ss\n' "$label" "$elapsed" >&2; FAIL=1
  fi
}

if [ "$PHASE" = "pre-deploy" ]; then
  printf 'PHASE=PRE_DEPLOY (offline; no network and no remote writes)\n'
  run_gate 'Figma parity' tests.verify.test_figma_parity
  run_gate 'Design tokens' tests.verify.test_design_tokens
  run_gate 'PII guard' tests.verify.test_pii_guard
  run_gate 'Action surface' tests.verify.test_action_surface
  run_gate 'Mechanism strengths' tests.verify.test_strong_surface
  run_gate 'Live probe logic (offline)' tests.verify.test_live_deploy
  run_gate 'Visual regression' tests.verify.test_visual_regression
  if [ "$FAIL" -eq 0 ]; then
    printf 'PRE_DEPLOY=PASS\nREADY FOR AUTHORIZED DEPLOY=yes\nLIVE_ACCEPTANCE=PENDING (run: LIVE_URL=https://new-deployment INTENDED_SOURCE_SHA=<sha> LIVE_SOURCE_SHA=<sha> bash tests/verify/run_all.sh live)\n'
    exit 0
  fi
  printf 'PRE_DEPLOY=FAIL\nREADY FOR AUTHORIZED DEPLOY=no\nLIVE_ACCEPTANCE=PENDING\n' >&2
  exit 1
fi

if [ "$PHASE" = "live" ]; then
  if [ -z "${LIVE_URL:-}" ] || [ -z "${INTENDED_SOURCE_SHA:-}" ] || [ -z "${LIVE_SOURCE_SHA:-}" ]; then
    printf 'LIVE_ACCEPTANCE=FAIL\nfix: supply LIVE_URL, INTENDED_SOURCE_SHA, and LIVE_SOURCE_SHA for an authorized deployment\n' >&2
    exit 2
  fi
  printf 'PHASE=LIVE (explicit remote read-only probes)\n'
  RUN_LIVE=1 LIVE_URL="$LIVE_URL" INTENDED_SOURCE_SHA="$INTENDED_SOURCE_SHA" LIVE_SOURCE_SHA="$LIVE_SOURCE_SHA" "$PYTHON" tests/verify/test_live_deploy.py
  exit $?
fi

printf 'Unknown phase: %s\nusage: bash tests/verify/run_all.sh [pre-deploy|live]\n' "$PHASE" >&2
exit 2
