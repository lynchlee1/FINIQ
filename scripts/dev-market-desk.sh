#!/usr/bin/env bash

set -euo pipefail
set -m

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_pid=""
frontend_pid=""

stop_process_group() {
  local pid="$1"

  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM -- "-$pid" 2>/dev/null || true
  fi
}

cleanup() {
  trap - EXIT INT TERM
  stop_process_group "$frontend_pid"
  stop_process_group "$backend_pid"
  [[ -z "$frontend_pid" ]] || wait "$frontend_pid" 2>/dev/null || true
  [[ -z "$backend_pid" ]] || wait "$backend_pid" 2>/dev/null || true
}

handle_exit() {
  local exit_code=$?
  cleanup
  exit "$exit_code"
}

handle_signal() {
  cleanup
  exit 130
}

trap handle_exit EXIT
trap handle_signal INT TERM

if curl --fail --silent --output /dev/null http://127.0.0.1:8765/api/config; then
  echo "MarketDesk backend가 이미 127.0.0.1:8765에서 실행 중입니다." >&2
  exit 1
fi

(
  cd "$repo_root"
  export PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}"
  exec "$repo_root/.venv/bin/python" -m finiq.market_desk.web.app
) &
backend_pid=$!

echo "Backend API가 준비될 때까지 기다리는 중..."
until curl --fail --silent --output /dev/null http://127.0.0.1:8765/api/config; do
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    wait "$backend_pid"
  fi
  sleep 0.2
done

(
  cd "$repo_root/frontend"
  exec npm run dev:market-desk
) &
frontend_pid=$!

echo "MarketDesk 실행 완료. 종료하려면 Ctrl+C를 누르세요."

while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 1
done

exit_code=0
if ! kill -0 "$backend_pid" 2>/dev/null; then
  wait "$backend_pid" || exit_code=$?
else
  wait "$frontend_pid" || exit_code=$?
fi
exit "$exit_code"
