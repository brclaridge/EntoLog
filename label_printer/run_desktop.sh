#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="/tmp/fieldcollect_label_printer.pid"
PORT_FILE="/tmp/fieldcollect_label_printer.port"
LOG_FILE="/tmp/fieldcollect_label_printer.log"
DEFAULT_PORT="${FIELDCOLLECT_PORT:-5000}"
PORT="${DEFAULT_PORT}"

open_url() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${url}" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "${url}" >/dev/null 2>&1 || true
  else
    echo "Open your browser to: ${url}"
  fi
}

is_our_process() {
  local pid="$1"
  local cmdline
  if [[ ! -r "/proc/${pid}/cmdline" ]]; then
    return 1
  fi
  cmdline="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
  [[ "${cmdline}" == *"${ROOT_DIR}/app.py"* ]]
}

port_in_use() {
  local p="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "( sport = :${p} )" 2>/dev/null | tail -n +2 | grep -q .
    return $?
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"${p}" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  return 1
}

find_open_port() {
  local start="$1"
  local end=$((start + 30))
  local p
  for ((p=start; p<=end; p++)); do
    if ! port_in_use "${p}"; then
      echo "${p}"
      return 0
    fi
  done
  return 1
}

if [[ -f "${PID_FILE}" ]]; then
  RUNNING_PID="$(cat "${PID_FILE}")"
  if kill -0 "${RUNNING_PID}" 2>/dev/null && is_our_process "${RUNNING_PID}"; then
    RUNNING_PORT="${PORT}"
    if [[ -f "${PORT_FILE}" ]]; then
      RUNNING_PORT="$(cat "${PORT_FILE}")"
    fi
    URL="http://localhost:${RUNNING_PORT}"
    echo "Label printer already running (pid ${RUNNING_PID})."
    echo "Open: ${URL}"
    open_url "${URL}"
    exit 0
  fi
  echo "Removing stale PID file."
  rm -f "${PID_FILE}"
  rm -f "${PORT_FILE}"
fi

if port_in_use "${PORT}"; then
  NEW_PORT="$(find_open_port "$((PORT + 1))" || true)"
  if [[ -z "${NEW_PORT}" ]]; then
    echo "Port ${PORT} is in use and no free port was found in the next 30 ports."
    exit 1
  fi
  echo "Port ${PORT} is in use. Using ${NEW_PORT} instead."
  PORT="${NEW_PORT}"
fi

URL="http://localhost:${PORT}"
echo "${PORT}" > "${PORT_FILE}"

FIELDCOLLECT_PORT="${PORT}" nohup python3 "${ROOT_DIR}/app.py" > "${LOG_FILE}" 2>&1 &
PID=$!
echo "${PID}" > "${PID_FILE}"

# Give Flask a moment to start and fail fast if it crashes.
for _ in 1 2 3; do
  sleep 1
  if ! kill -0 "${PID}" 2>/dev/null; then
    echo "Label printer failed to start."
    echo "Last log lines:"
    tail -n 60 "${LOG_FILE}" || true
    rm -f "${PID_FILE}"
    rm -f "${PORT_FILE}"
    exit 1
  fi
done

open_url "${URL}"

echo "Label printer started in background (pid ${PID})."
echo "Open: ${URL}"
echo "Logs: ${LOG_FILE}"
