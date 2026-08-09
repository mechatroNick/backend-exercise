#!/usr/bin/env bash
# Track 06 closure: deterministic gates plus real worker, overflow, and restart evidence.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
report_helper="${root}/scripts/verification-report.sh"
[[ -r "${report_helper}" ]] || { printf 'FAIL: missing verification report helper\n' >&2; exit 1; }
# shellcheck source=verification-report.sh
source "${report_helper}"
verification_report_start 'scripts/verify-track-06.sh' 'Track 06 event-driven statistics verification'
verification_report_gate 'exact inherited Track 05 quality gate'
verification_report_gate 'deterministic worker, overflow, and restart edge selectors'
verification_report_gate 'live lifecycle, readiness, JSON Lines, and cleanup evidence'
uv="${UV:-uv}"
prefix="${TMPDIR:-/tmp}/backend-sample-track06."
work=""
pid=""
port=""

fail() {
  printf 'Track 06 harness failure: %s\n' "$1" >&2
  exit 1
}

descendants() {
  local parent=$1 child
  while IFS= read -r child; do
    [[ -n "${child}" ]] || continue
    descendants "${child}"
    printf '%s\n' "${child}"
  done < <(pgrep -P "${parent}" 2>/dev/null || true)
}

stop_server() {
  local target wait_status=0 alive=0
  local -a targets=()
  [[ -n "${pid}" ]] || return 0
  while IFS= read -r target; do
    [[ -n "${target}" ]] && targets+=("${target}")
  done < <(descendants "${pid}")
  targets+=("${pid}")
  for target in "${targets[@]}"; do
    kill -TERM "${target}" 2>/dev/null || true
  done
  for _ in {1..60}; do
    alive=0
    for target in "${targets[@]}"; do
      kill -0 "${target}" 2>/dev/null && alive=1
    done
    [[ "${alive}" == 0 ]] && break
    sleep 0.1
  done
  for target in "${targets[@]}"; do
    kill -0 "${target}" 2>/dev/null && kill -KILL "${target}" 2>/dev/null || true
  done
  wait "${pid}" 2>/dev/null || wait_status=$?
  [[ "${wait_status}" == 0 || "${wait_status}" == 143 || "${wait_status}" == 137 ]] \
    || return 1
  for target in "${targets[@]}"; do
    kill -0 "${target}" 2>/dev/null && return 1
  done
  pid=""
}

cleanup() {
  local original=$? cleanup_status=0
  trap - EXIT
  stop_server || cleanup_status=1
  if [[ -d "${work}" && "${work}" == "${prefix}"* ]]; then
    rm -rf -- "${work}" || cleanup_status=1
    [[ ! -e "${work}" ]] || cleanup_status=1
  else
    cleanup_status=1
  fi
  if [[ "${cleanup_status}" == 0 ]]; then
    printf 'Track 06 cleanup: removed verified protected artifacts\n'
  fi
  verification_report_cleanup "${cleanup_status}" 'verified protected artifacts and process removal'
  if [[ "${original}" != 0 ]]; then
    verification_report_finish "${original}" "${cleanup_status}"
    exit "${original}"
  fi
  verification_report_finish 0 "${cleanup_status}"
  exit "${cleanup_status}"
}
trap cleanup EXIT

work="$(mktemp -d "${prefix}XXXXXX")"

if [[ "${TRACK06_SELF_TEST:-0}" == "1" ]]; then
  printf 'private cleanup sentinel' >"${work}/self-test-private"
  ( exit 42 ) &
  pid=$!
  sleep 0.1
  exit 97
fi

cd "${root}"
[[ -d .git && -f Makefile ]] || fail 'wrong repository root'
chmod 700 "${work}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/backend-sample-uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/private/tmp/backend-sample-python}"
export COVERAGE_FILE="${work}/.coverage"

cleanup_probe="${work}/cleanup-probe"
mkdir -m 700 "${cleanup_probe}"
cleanup_probe_status=0
TMPDIR="${cleanup_probe}" TRACK06_SELF_TEST=1 bash "$0" \
  >"${work}/cleanup-self-test.receipt" 2>&1 || cleanup_probe_status=$?
[[ "${cleanup_probe_status}" == 97 ]] || fail 'cleanup self-test lost the original status'
[[ -z "$(find "${cleanup_probe}" -mindepth 1 -print -quit)" ]] \
  || fail 'cleanup self-test retained a private workspace'
printf 'Track 06 cleanup self-test: failure status preserved and private workspace removed\n'

bash scripts/verify-track-05.sh >"${work}/track05.receipt" 2>&1 \
  || fail 'inherited Track 05 gate failed'
printf 'Track 06 inherited Track 05 gate: passed\n'

focused=(
  tests/unit/test_health.py
  tests/unit/test_stats_refresher.py
  tests/unit/test_stats_publisher.py
  tests/unit/test_stats_snapshots.py
  tests/unit/test_current_stats_service.py
  tests/integration/test_bookmark_stats_dirty.py
  tests/integration/test_bookmark_service.py
  tests/integration/test_stats_refresher.py
  tests/integration/test_health_routes.py
)
"${uv}" run pytest -q "${focused[@]}" >"${work}/focused.receipt" \
  || fail 'focused deterministic selector failed'
! rg -q '[1-9][0-9]* (skipped|xfailed|xpassed|deselected)' "${work}/focused.receipt" \
  || fail 'focused selector contains a masked result'
printf 'Track 06 focused deterministic ledger: passed\n'

observability_edges=(
  tests/unit/test_stats_refresher.py::test_start_once_exact_thread_and_failed_cycle_state
  tests/unit/test_stats_refresher.py::test_thread_start_and_join_timeout_failures_are_explicit
  tests/unit/test_stats_refresher.py::test_worker_retry_json_logs_keep_application_source_and_safe_context
  tests/unit/test_stats_publisher.py::test_overflow_invalidates_sets_reconciliation_and_logs_once_per_episode
)
"${uv}" run pytest -q "${observability_edges[@]}" >"${work}/observability-edges.receipt" \
  || fail 'worker topology, retry, join-timeout, or overflow edge evidence failed'
printf 'Track 06 worker topology, retry, join-timeout, and overflow edges: passed\n'
for selector in "${observability_edges[@]}"; do
  printf 'Track 06 edge selector: %s\n' "${selector}"
done

"${uv}" sync --locked >"${work}/sync.receipt" 2>&1 || fail 'locked dependency sync failed'
"${uv}" run ruff format --check . >"${work}/ruff-format.receipt" \
  || fail 'format check failed'
"${uv}" run ruff check . >"${work}/ruff.receipt" || fail 'lint failed'
"${uv}" run mypy app >"${work}/mypy.receipt" || fail 'type check failed'
"${uv}" run coverage erase
"${uv}" run coverage run -m pytest -q >"${work}/coverage.receipt" \
  || fail 'full test suite failed'
"${uv}" run coverage report --fail-under=100 >>"${work}/coverage.receipt" \
  || fail 'statement or branch coverage fell below 100 percent'
! rg -q '[1-9][0-9]* (skipped|xfailed|xpassed|deselected)' "${work}/coverage.receipt" \
  || fail 'full suite contains a masked result'
make check >"${work}/make-check.receipt" 2>&1 || fail 'documented make check failed'
bash scripts/verify-docs.sh >"${work}/docs.receipt" || fail 'documentation gate failed'
git diff --check || fail 'git whitespace gate failed'
test_summary="$(rg -o '[0-9]+ passed(, [0-9]+ subtests passed)?' "${work}/coverage.receipt" | tail -n 1)"
coverage_summary="$(rg '^TOTAL ' "${work}/coverage.receipt" | tail -n 1)"
[[ -n "${test_summary}" && -n "${coverage_summary}" ]] \
  || fail 'safe full-suite summary could not be extracted'
printf 'Track 06 full-suite result: %s\n' "${test_summary}"
printf 'Track 06 coverage result: %s\n' "${coverage_summary}"
printf 'Track 06 quality gate: locked sync, Ruff, mypy, full tests, 100%% coverage, make check, docs passed\n'

migration_database="${work}/migration-lifecycle.sqlite3"
export DATABASE_URL="sqlite:///${migration_database}" APP_ENV=test STATS_REFRESH_ENABLED=false
"${uv}" run alembic upgrade head >"${work}/migration-upgrade.receipt" \
  || fail 'migration upgrade failed'
"${uv}" run alembic downgrade base >"${work}/migration-downgrade.receipt" \
  || fail 'migration downgrade failed'
"${uv}" run alembic upgrade head >"${work}/migration-reupgrade.receipt" \
  || fail 'migration re-upgrade failed'
"${uv}" run alembic check >"${work}/migration-check.receipt" \
  || fail 'migration drift check failed'
printf 'Track 06 migration lifecycle: upgrade, downgrade, re-upgrade, drift check passed\n'

export APP_ENV=test APP_WORKER_COUNT=1 STATS_REFRESH_ENABLED=true
export JWT_SECRET="$("${uv}" run python -c 'import secrets; print(secrets.token_urlsafe(48))')"

select_port() {
  port="$("${uv}" run python - <<'PY'
import socket
with socket.socket() as socket_:
    socket_.bind(("127.0.0.1", 0))
    print(socket_.getsockname()[1])
PY
)"
}

start_server() {
  local log_path=$1 phase=$2 ready=0
  select_port
  "${uv}" run alembic upgrade head >"${log_path}.migration" 2>&1 \
    || fail 'bootstrap migration failed'
  "${uv}" run uvicorn app.main:create_app --factory --host 127.0.0.1 \
    --port "${port}" --workers 1 --no-access-log --log-level critical \
    >"${log_path}" 2>&1 &
  pid=$!
  for _ in {1..150}; do
    if curl --fail --silent "http://127.0.0.1:${port}/health/live" >/dev/null 2>&1; then
      ready=1
      break
    fi
    kill -0 "${pid}" 2>/dev/null || fail 'bootstrap exited before liveness'
    sleep 0.1
  done
  [[ "${ready}" == 1 ]] || fail 'bootstrap liveness timed out'
  printf 'Track 06 application launch: phase=%s port=%s\n' "${phase}" "${port}"
}

parity_database="${work}/parity.sqlite3"
parity_log="${work}/parity.jsonl"
export DATABASE_URL="sqlite:///${parity_database}"
export STATS_REFRESH_INTERVAL_SECONDS=5 STATS_STALE_AFTER_SECONDS=10
export STATS_FULL_RECONCILIATION_SECONDS=10 STATS_DIRTY_MAX_AGE_SECONDS=10
export STATS_EVENT_QUEUE_CAPACITY=10 STATS_DIRTY_MAX_COUNT=1000
start_server "${parity_log}" parity
"${uv}" run python - "${port}" "${parity_log}" >"${work}/parity-driver.receipt" <<'PY'
import datetime as dt
import json
import os
import secrets
import sys
import time
import uuid

import httpx
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

port, log_path = sys.argv[1:]
base = f"http://127.0.0.1:{port}"

def require(condition, message):
    if not condition:
        raise SystemExit(message)

def validate(api, path, method, response):
    try:
        schema = api["paths"][path][method]["responses"][str(response.status_code)]["content"]["application/json"]["schema"]
        registry = Registry().with_resource("urn:t06", Resource.from_contents(api, default_specification=DRAFT202012))
        Draft202012Validator({"$id": "urn:t06", **api, **schema}, registry=registry).validate(response.json())
    except Exception as error:
        raise SystemExit("runtime body failed OpenAPI validation") from error

nonce = secrets.token_urlsafe(18).lower()
password = f"Track06-{secrets.token_urlsafe(32)}"
sensitive = {
    nonce,
    password,
    os.environ["JWT_SECRET"],
    os.environ["DATABASE_URL"],
    str(os.path.dirname(log_path)),
}
with httpx.Client(base_url=base, timeout=10) as client:
    live = client.get("/health/live")
    require(live.status_code == 200 and live.json() == {"status": "live"}, "liveness contract failed")
    require(live.headers.get("cache-control") == "no-store", "liveness cache policy failed")
    ready = None
    for _ in range(100):
        ready = client.get("/health/ready")
        if ready.status_code == 200:
            break
        time.sleep(0.05)
    require(ready is not None and ready.status_code == 200, "initial readiness did not recover")
    require(ready.json() == {"status": "ready"} and ready.headers.get("cache-control") == "no-store", "readiness contract failed")
    api_response = client.get("/openapi.json")
    require(api_response.status_code == 200, "OpenAPI request failed")
    api = api_response.json()
    inventory = {
        (path, method.upper()): {int(code) for code in operation["responses"]}
        for path, methods in api["paths"].items()
        for method, operation in methods.items()
    }
    require(len(inventory) == 10 and sum(map(len, inventory.values())) == 45, "OpenAPI inventory changed")
    limited = {
        ("/api/auth/register", "POST"),
        ("/api/auth/login", "POST"),
        ("/api/bookmarks", "POST"),
        ("/api/bookmarks", "GET"),
        ("/api/bookmarks/stats", "GET"),
        ("/api/bookmarks/{bookmark_id}", "GET"),
        ("/api/bookmarks/{bookmark_id}", "PATCH"),
        ("/api/bookmarks/{bookmark_id}", "DELETE"),
    }
    require(all(429 in inventory[operation] for operation in limited), "rate-limit inventory missing")
    require(all(429 not in statuses for operation, statuses in inventory.items() if operation not in limited), "rate-limit inventory escaped selected operations")
    require(inventory[("/health/live", "GET")] == {200}, "liveness statuses changed")
    require(inventory[("/health/ready", "GET")] == {200, 503}, "readiness statuses changed")
    require(api["paths"]["/health/live"]["get"].get("security") in (None, []), "liveness acquired authentication")
    require(api["paths"]["/health/ready"]["get"].get("security") in (None, []), "readiness acquired authentication")
    clients = []
    for user_index, bookmark_count in ((1, 1), (2, 2)):
        username = f"parity-{user_index}-{nonce[:8]}"
        email = f"{username}@example.com"
        registration = client.post(
            "/api/auth/register",
            json={"username": username, "email": email, "password": password},
        )
        require(registration.status_code == 201, "parity registration failed")
        token = registration.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        sensitive.update({username, email, token, f"Bearer {token}"})
        for bookmark_index in range(bookmark_count):
            suffix = f"{user_index}-{bookmark_index}-{nonce}"
            url = f"https://example.invalid/private-{suffix}"
            title = f"private-title-{suffix}"
            description = f"private-description-{suffix}"
            tag = f"private-tag-{suffix}"
            created = client.post(
                "/api/bookmarks",
                headers=headers,
                json={"url": url, "title": title, "description": description, "tags": [tag]},
            )
            require(created.status_code == 201, "parity bookmark creation failed")
            sensitive.update({url, title, description, tag})
        current = client.get("/api/bookmarks/stats", headers=headers)
        require(current.status_code == 200, "live statistics request failed")
        require(current.headers.get("x-stats-source") == "live", "first statistics source was not live")
        require("x-stats-generated-at" not in current.headers, "live statistics exposed a generation header")
        validate(api, "/api/bookmarks/stats", "get", current)
        clients.append((headers, current.json()))

    require(clients[0][1] != clients[1][1], "two-user live statistics were not distinguishable")
    snapshots = []
    for headers, expected in clients:
        snapshot = None
        for _ in range(120):
            candidate = client.get("/api/bookmarks/stats", headers=headers)
            if candidate.headers.get("x-stats-source") == "snapshot":
                snapshot = candidate
                break
            time.sleep(0.1)
        require(snapshot is not None and snapshot.status_code == 200, "snapshot statistics did not appear")
        require(snapshot.json() == expected, "snapshot and live statistics bodies differ")
        generated = snapshot.headers.get("x-stats-generated-at")
        require(isinstance(generated, str) and generated.endswith("Z"), "snapshot generation header is absent")
        parsed = dt.datetime.fromisoformat(generated.replace("Z", "+00:00"))
        require(parsed.utcoffset() == dt.timedelta(), "snapshot generation header is not UTC")
        validate(api, "/api/bookmarks/stats", "get", snapshot)
        snapshots.append(snapshot.json())
    require(snapshots == [value for _, value in clients], "cross-user snapshot isolation failed")

raw = open(log_path, encoding="utf-8").read()
require(all(value not in raw for value in sensitive), "private parity material leaked to logs")
records = [json.loads(line) for line in raw.splitlines() if line]
events = [record["event"] for record in records]
for event in ("bookmark_stats.refresh_cycle_succeeded", "bookmark_stats.refresher_started", "health.readiness_changed"):
    require(event in events, "required parity worker or health event is absent")
for record in records:
    indexed = json.dumps(record, sort_keys=True)
    require(all(key not in indexed for key in ('"user_id"', '"bookmark_id"', '"resource_id"')), "identifier field leaked to logs")
for event in ("bookmark_stats.refresh_cycle_succeeded", "bookmark_stats.refresher_started"):
    matches = [record for record in records if record["event"] == event]
    require(any(record["thread_name"] == "bookmark-stats-refresher" for record in matches), "worker thread name evidence is absent")
    for record in matches:
        instance = record.get("context", {}).get("service_instance_id")
        require(isinstance(instance, str) and str(uuid.UUID(instance)) == instance, "worker instance id is invalid")
print("Track 06 parity helper passed")
PY
stop_server || fail 'parity process did not stop cleanly'
printf 'Track 06 live-to-snapshot parity and worker identity: passed\n'

overflow_database="${work}/overflow-restart.sqlite3"
overflow_log="${work}/overflow.jsonl"
export DATABASE_URL="sqlite:///${overflow_database}"
export STATS_REFRESH_INTERVAL_SECONDS=3600 STATS_STALE_AFTER_SECONDS=3600
export STATS_FULL_RECONCILIATION_SECONDS=3600 STATS_DIRTY_MAX_AGE_SECONDS=3600
export STATS_EVENT_QUEUE_CAPACITY=1 STATS_DIRTY_MAX_COUNT=1
start_server "${overflow_log}" overflow
"${uv}" run python - "${port}" "${overflow_log}" >"${work}/overflow-driver.receipt" <<'PY'
import json
import os
import secrets
import sys
import time
import uuid

import httpx

port, log_path = sys.argv[1:]
base = f"http://127.0.0.1:{port}"

def require(condition, message):
    if not condition:
        raise SystemExit(message)

nonce = secrets.token_urlsafe(18).lower()
password = f"Track06-{secrets.token_urlsafe(32)}"
tokens = []
sensitive = {nonce, password, os.environ["JWT_SECRET"], os.environ["DATABASE_URL"], str(os.path.dirname(log_path))}
with httpx.Client(base_url=base, timeout=10) as client:
    initial = None
    for _ in range(100):
        initial = client.get("/health/ready")
        if initial.status_code == 200:
            break
        time.sleep(0.05)
    require(initial is not None, "overflow readiness response was absent")
    require(initial.status_code == 200 and initial.json() == {"status": "ready"}, "overflow phase was not initially ready")
    for role in ("first", "second"):
        username = f"{role}-{nonce[:10]}"
        email = f"{username}@example.com"
        url = f"https://example.invalid/{role}-{nonce}"
        title = f"private-{role}-{nonce}"
        description = f"private-description-{role}-{nonce}"
        tag = f"private-{role}-tag-{nonce.lower()}"
        registration = client.post(
            "/api/auth/register",
            json={"username": username, "email": email, "password": password},
        )
        require(registration.status_code == 201, "overflow registration failed")
        token = registration.json()["token"]
        tokens.append(token)
        created = client.post(
            "/api/bookmarks",
            headers={"Authorization": f"Bearer {token}"},
            json={"url": url, "title": title, "description": description, "tags": [tag]},
        )
        require(created.status_code == 201, "overflow mutation failed after commit")
        sensitive.update({username, email, url, title, description, tag, token, f"Bearer {token}"})
    stats = client.get(
        "/api/bookmarks/stats",
        headers={"Authorization": f"Bearer {tokens[0]}"},
    )
    require(stats.status_code == 200 and stats.headers.get("x-stats-source") == "live", "overflow live fallback failed")
    degraded = client.get("/health/ready")
    require(degraded.status_code == 503, "overflow readiness did not degrade")
    require(degraded.json() == {"status": "not_ready"}, "overflow readiness body leaked detail")
    require(degraded.headers.get("cache-control") == "no-store", "degraded readiness cache policy failed")
    records = []
    for _ in range(40):
        raw = open(log_path, encoding="utf-8").read()
        records = [json.loads(line) for line in raw.splitlines() if line]
        if any(record["event"] == "bookmark_stats.queue_overflow" for record in records):
            break
        time.sleep(0.05)

raw = open(log_path, encoding="utf-8").read()
require(all(value not in raw for value in sensitive), "private overflow material leaked to logs")
overflow = [record for record in records if record["event"] == "bookmark_stats.queue_overflow"]
require(len(overflow) == 1, "overflow event was not emitted exactly once")
context = overflow[0].get("context", {})
require(context.get("queue_capacity") == 1 and context.get("overflow_count", 0) >= 1, "overflow context is incomplete")
require(context.get("reconciliation_required") is True, "overflow did not require reconciliation")
instance = context.get("service_instance_id")
require(isinstance(instance, str) and str(uuid.UUID(instance)) == instance, "overflow instance id is invalid")
degraded_logs = [
    record for record in records
    if record["event"] == "health.readiness_changed" and record.get("context", {}).get("ready") is False
]
require(degraded_logs, "degraded readiness transition was not logged")
print("Track 06 overflow helper passed")
PY
stop_server || fail 'overflow process did not stop cleanly'
"${uv}" run python - "${overflow_database}" >"${work}/dirty-before-restart.receipt" <<'PY'
import sqlite3
import sys
with sqlite3.connect(sys.argv[1]) as connection:
    count = connection.execute("SELECT count(*) FROM bookmark_stats_window_dirty").fetchone()[0]
if count < 2:
    raise SystemExit("durable dirty backlog did not survive process stop")
print("Track 06 durable backlog before restart passed")
PY
printf 'Track 06 committed overflow and durable backlog survival: passed\n'

recovery_log="${work}/recovery.jsonl"
export STATS_REFRESH_INTERVAL_SECONDS=1 STATS_STALE_AFTER_SECONDS=2
export STATS_FULL_RECONCILIATION_SECONDS=2 STATS_DIRTY_MAX_AGE_SECONDS=2
export STATS_EVENT_QUEUE_CAPACITY=10 STATS_DIRTY_MAX_COUNT=1
start_server "${recovery_log}" recovery
"${uv}" run python - "${port}" >"${work}/recovery-driver.receipt" <<'PY'
import sys
import time
import httpx

base = f"http://127.0.0.1:{sys.argv[1]}"
with httpx.Client(base_url=base, timeout=10) as client:
    response = None
    for _ in range(100):
        response = client.get("/health/ready")
        if response.status_code == 200:
            break
        time.sleep(0.05)
if response is None or response.status_code != 200:
    raise SystemExit("restart readiness did not recover")
if response.json() != {"status": "ready"} or response.headers.get("cache-control") != "no-store":
    raise SystemExit("restart readiness contract failed")
print("Track 06 restart readiness helper passed")
PY
stop_server || fail 'recovery process did not stop cleanly'
"${uv}" run python - "${overflow_database}" >"${work}/dirty-after-restart.receipt" <<'PY'
import sqlite3
import sys
with sqlite3.connect(sys.argv[1]) as connection:
    count = connection.execute("SELECT count(*) FROM bookmark_stats_window_dirty").fetchone()[0]
if count != 0:
    raise SystemExit("startup recovery left durable dirty work")
print("Track 06 durable backlog after restart passed")
PY
printf 'Track 06 restart reconciliation and readiness recovery: passed\n'

"${uv}" run python - "${parity_log}" "${overflow_log}" "${recovery_log}" \
  >"${work}/combined-log-audit.receipt" <<'PY'
import datetime as dt
import json
import os
import sys
import uuid

paths = sys.argv[1:]

def require(condition, message):
    if not condition:
        raise SystemExit(message)

for path in paths:
    lines = open(path, encoding="utf-8").read().splitlines()
    require(lines and all(line.strip() for line in lines), "application log contains blank lines")
    try:
        records = [json.loads(line) for line in lines]
    except json.JSONDecodeError as error:
        raise SystemExit("application output is not strict JSON Lines") from error
    events = [record.get("event") for record in records]
    for event in ("application.starting", "application.started", "application.stopping", "application.stopped"):
        require(events.count(event) == 1, "application lifecycle evidence is incomplete")
    for event in ("bookmark_stats.refresher_starting", "bookmark_stats.refresher_started", "bookmark_stats.refresher_stopping", "bookmark_stats.refresher_stopped"):
        require(events.count(event) == 1, "exact-one worker lifecycle evidence is incomplete")
    require("bookmark_stats.refresher_join_timeout" not in events, "real worker did not join cleanly")
    cycles = [record for record in records if record.get("event") == "bookmark_stats.refresh_cycle_succeeded"]
    require(cycles, "successful refresh-cycle evidence is absent")
    required = {
        "source", "service", "component", "event", "level", "timestamp", "logger",
        "process_id", "thread_name", "thread_id",
    }
    for record in records:
        require(required <= set(record), "application log base fields are missing")
        source = record["source"]
        require({"pathname", "lineno", "package", "module", "function"} <= set(source), "source attribution is incomplete")
        require(source["pathname"].startswith("/") and source["lineno"] > 0, "source location is invalid")
        require(source["package"].startswith("app") and source["module"].startswith("app."), "source is not application-qualified")
        timestamp = dt.datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
        require(timestamp.utcoffset() == dt.timedelta(), "log timestamp is not UTC")
        require(record["process_id"] > 0 and record["thread_id"] > 0 and record["thread_name"], "execution identity is invalid")
        encoded = json.dumps(record, sort_keys=True)
        require("exception_message" not in record and "traceback" not in record, "raw exception text was indexed")
        require(all(key not in encoded for key in ('"user_id"', '"bookmark_id"', '"resource_id"')), "identifier field leaked to logs")
    started = [record for record in records if record["event"] == "bookmark_stats.refresher_started"]
    require(started[0]["thread_name"] == "bookmark-stats-refresher", "named worker evidence is absent")
    started_context = started[0].get("context", {})
    require(started_context.get("worker_is_daemon") is False, "non-daemon worker evidence is absent")
    require(started_context.get("interval_seconds") > 0, "worker interval evidence is absent")
    for cycle in cycles:
        context = cycle.get("context", {})
        require(
            {"duration_ms", "affected_user_count", "marker_count", "full_reconciliation", "failure_count"} <= set(context),
            "refresh-cycle telemetry is incomplete",
        )
        require(context["duration_ms"] >= 0 and context["affected_user_count"] >= 0 and context["marker_count"] >= 0, "refresh-cycle telemetry is invalid")
    for record in records:
        correlation_id = record.get("correlation_id")
        if correlation_id is not None:
            require(str(uuid.UUID(correlation_id)) == correlation_id, "safe correlation evidence is invalid")
        if record["event"].startswith("bookmark_stats.") or record["event"] == "health.readiness_changed":
            context = record.get("context", {})
            instance = context.get("service_instance_id")
            require(isinstance(instance, str) and str(uuid.UUID(instance)) == instance, "service instance evidence is invalid")
        if record["event"] == "bookmark_stats.queue_overflow":
            context = record.get("context", {})
            require(
                {"queue_capacity", "queue_depth", "reconciliation_required", "overflow_count", "failure_count"} <= set(context),
                "overflow queue/count telemetry is incomplete",
            )
            require(correlation_id is not None, "overflow correlation evidence is absent")

combined = "".join(open(path, encoding="utf-8").read() for path in paths)
for sensitive in (os.environ["JWT_SECRET"], os.environ["DATABASE_URL"], str(os.path.dirname(paths[0])), "Authorization", "Bearer "):
    require(sensitive not in combined, "credential or workspace material leaked to logs")
print("Track 06 combined JSON Lines audit passed")
PY
printf 'Track 06 JSON Lines lifecycle, worker, overflow, readiness, and redaction audit: passed\n'
printf 'Track 06 real-process closure harness: passed\n'
verification_report_summary 'inherited quality gate, worker edges, live runtime, JSON Lines, and redaction evidence completed'
