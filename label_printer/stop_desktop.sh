#!/usr/bin/env bash
set -euo pipefail

PID_FILE="/tmp/fieldcollect_label_printer.pid"
PORT_FILE="/tmp/fieldcollect_label_printer.port"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "No PID file found. Is the label printer running?"
  exit 0
fi

PID="$(cat "${PID_FILE}")"
if kill -0 "${PID}" 2>/dev/null; then
  kill "${PID}"
  echo "Stopped label printer (pid ${PID})."
else
  echo "Process not running; removing stale PID file."
fi

rm -f "${PID_FILE}"
rm -f "${PORT_FILE}"
