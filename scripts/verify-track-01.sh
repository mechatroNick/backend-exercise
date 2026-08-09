#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd "${script_dir}/.." && pwd)"
report_helper="${script_dir}/verification-report.sh"
[[ -r "${report_helper}" ]] || { printf 'FAIL: missing verification report helper\n' >&2; exit 1; }
# shellcheck source=verification-report.sh
source "${report_helper}"
verification_report_start 'scripts/verify-track-01.sh' 'Track 01 foundation real-process verification'
verification_report_gate 'isolated migration and factory bootstrap'
verification_report_gate 'OpenAPI, JSON Lines lifecycle, and owning fault boundary'
verification_report_gate 'verified disposable-process cleanup'
uv_command="${UV:-uv}"
debug="${TRACK01_DEBUG:-0}"
temporary_base="${TMPDIR:-/tmp}"
work_dir_prefix="${temporary_base%/}/backend-sample-track01."
work_dir=""
database_path=""
log_path=""
process_output_path=""
port=""
child_pid=""

cleanup() {
  local original_status=$?
  local cleanup_status=0
  local wait_status=0
  trap - EXIT
  if [[ -n "${child_pid}" ]] && kill -0 "${child_pid}" 2>/dev/null; then
    kill "${child_pid}" 2>/dev/null || cleanup_status=1
    for _ in {1..30}; do
      kill -0 "${child_pid}" 2>/dev/null || break
      sleep 0.1
    done
    if kill -0 "${child_pid}" 2>/dev/null; then
      kill -TERM "${child_pid}" 2>/dev/null || cleanup_status=1
      sleep 0.2
    fi
    if kill -0 "${child_pid}" 2>/dev/null; then
      kill -KILL "${child_pid}" 2>/dev/null || cleanup_status=1
    fi
    wait "${child_pid}" 2>/dev/null || wait_status=$?
    if [[ "${wait_status}" -ne 0 && "${wait_status}" -ne 143 ]]; then
      cleanup_status=1
    fi
  fi
  if [[ "${debug}" == "1" ]]; then
    printf 'Track 01 harness debug artifacts retained at %s\n' "${work_dir}"
  else
    if [[ ! -d "${work_dir}" || "${work_dir}" != "${work_dir_prefix}"* ]]; then
      printf 'refusing to remove an unverified harness path\n' >&2
      cleanup_status=1
    else
      rm -rf -- "${work_dir}" || cleanup_status=1
    fi
    [[ ! -e "${work_dir}" ]] || cleanup_status=1
    [[ "${cleanup_status}" -eq 0 ]] && printf 'Track 01 harness cleanup: removed verified disposable resources\n'
  fi
  verification_report_cleanup "${cleanup_status}" 'verified disposable process and workspace removal'
  if [[ "${original_status}" -ne 0 ]]; then
    verification_report_finish "${original_status}" "${cleanup_status}"
    exit "${original_status}"
  fi
  verification_report_finish 0 "${cleanup_status}"
  exit "${cleanup_status}"
}
trap cleanup EXIT

work_dir="$(mktemp -d "${work_dir_prefix}XXXXXX")"
database_path="${work_dir}/track01.sqlite3"
log_path="${work_dir}/application.jsonl"
process_output_path="${work_dir}/bootstrap-output.log"

cd "${repository_root}"
export DATABASE_URL="sqlite:///${database_path}"
export APP_ENV=test
export JWT_SECRET="track01-secret-sentinel-do-not-emit"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/backend-sample-uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/private/tmp/backend-sample-python}"

port="$(${uv_command} run python - <<'PY'
import socket
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"

if ${uv_command} run python -c 'import app.main; import app.db.models' && [[ -e "${database_path}" ]]; then
  printf 'unmigrated import unexpectedly created a database\n' >&2
  exit 1
fi

make bootstrap HOST=127.0.0.1 PORT="${port}" >"${process_output_path}" 2>&1 &
child_pid="$!"

ready=0
for _ in {1..100}; do
  if curl --fail --silent "http://127.0.0.1:${port}/openapi.json" >"${work_dir}/openapi.json" 2>/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "${child_pid}" 2>/dev/null; then
    wait "${child_pid}" || true
    printf 'bootstrap process exited before readiness\n' >&2
    exit 1
  fi
  sleep 0.1
done
if [[ "${ready}" != "1" ]]; then
  curl --fail --silent --show-error "http://127.0.0.1:${port}/openapi.json" >/dev/null || true
  printf 'timed out waiting for application readiness\n' >&2
  exit 1
fi

fault_status="$(curl --silent --show-error --output "${work_dir}/fault-response.txt" --write-out '%{http_code}' --header 'X-Track01-Harness-Fault: 1' "http://127.0.0.1:${port}/openapi.json")"
[[ "${fault_status}" == "500" ]] || { printf 'test fault returned HTTP %s, expected 500\n' "${fault_status}" >&2; exit 1; }
kill -0 "${child_pid}" 2>/dev/null || { printf 'bootstrap process exited after test fault\n' >&2; exit 1; }

awk '/^\{/{print}' "${process_output_path}" >"${log_path}"

${uv_command} run python - "${work_dir}/openapi.json" "${log_path}" "${process_output_path}" "${database_path}" <<'PY'
import json
import sqlite3
import sys

openapi_path, log_path, process_output_path, database_path = sys.argv[1:]
with open(openapi_path, encoding="utf-8") as handle:
    document = json.load(handle)
assert document["info"]["title"] == "Bookmarks API"
assert document["info"]["version"] == "0.1.0"
assert document["info"]["description"] == "Foundation runtime for the Bookmarks API."
with open(log_path, encoding="utf-8") as handle:
    records = [json.loads(line) for line in handle if line.strip()]
assert records
with open(process_output_path, encoding="utf-8") as handle:
    non_application_lines = [line for line in handle if line.strip() and not line.startswith("{")]
assert all("alembic" in line.lower() for line in non_application_lines), non_application_lines
for record in records:
    assert {"source", "service", "component", "event", "level", "timestamp", "logger", "process_id", "thread_id"} <= record.keys()
    assert record["timestamp"].endswith("Z")
    assert record["source"]["pathname"].startswith("/")
    assert record["source"]["lineno"] > 0
assert [record["event"] for record in records].count("application.starting") == 1
assert [record["event"] for record in records].count("application.started") == 1
application_records = [record for record in records if record["event"].startswith("application.")]
assert len({record["process_id"] for record in application_records}) == 1
unexpected = [record for record in records if record["event"] == "http.request.unexpected_exception"]
assert len(unexpected) == 1
assert unexpected[0]["process_id"] == application_records[0]["process_id"]
assert unexpected[0]["exception"]["type"] == "RuntimeError"
assert unexpected[0]["exception"]["frames"]
with sqlite3.connect(database_path) as connection:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
assert {"alembic_version", "users", "bookmarks", "tags", "bookmark_tags"} <= tables
assert "track01-secret-sentinel-do-not-emit" not in open(log_path, encoding="utf-8").read()
assert "track01-submitted-bookmark-sentinel-do-not-emit" not in open(log_path, encoding="utf-8").read()
PY

kill "${child_pid}"
wait_status=0
wait "${child_pid}" 2>/dev/null || wait_status=$?
if [[ "${wait_status}" -ne 0 && "${wait_status}" -ne 143 ]]; then
  printf 'bootstrap process exited with unexpected status %s during shutdown\n' "${wait_status}" >&2
  exit "${wait_status}"
fi
child_pid=""

awk '/^\{/{print}' "${process_output_path}" >"${log_path}"

${uv_command} run python - "${log_path}" <<'PY'
import json
import sys

log_path = sys.argv[1]
raw = open(log_path, encoding="utf-8").read()
records = [json.loads(line) for line in raw.splitlines() if line]
events = [record["event"] for record in records]
assert events.count("application.stopping") == 1
assert events.count("application.stopped") == 1
assert "track01-secret-sentinel-do-not-emit" not in raw
assert "track01-submitted-bookmark-sentinel-do-not-emit" not in raw
print("Track 01 process evidence: factory bootstrap, one worker, OpenAPI, JSON lifecycle, request exception boundary")
PY
verification_report_summary 'foundation bootstrap, lifecycle, fault-boundary, and redaction evidence completed'
