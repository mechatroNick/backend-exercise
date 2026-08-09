#!/usr/bin/env bash
# Track 07 closure: deterministic projection gates plus disposable real-process evidence.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
report_helper="${root}/scripts/verification-report.sh"
[[ -r "${report_helper}" ]] || { printf 'FAIL: missing verification report helper\n' >&2; exit 1; }
# shellcheck source=verification-report.sh
source "${report_helper}"
verification_report_start 'scripts/verify-track-07.sh' 'Track 07 weekly projection verification'
verification_report_gate 'exact inherited Track 06 receipt'
verification_report_gate 'deterministic projection, migration, quality, and coverage gates'
verification_report_gate 'real process baseline, correction, restart, disabled, mismatch, JSON Lines, and cleanup evidence'

uv="${UV:-uv}"
prefix="${TMPDIR:-/private/tmp}/backend-sample-track07."
work=""
pid=""
port=""

fail() { printf 'Track 07 harness failure: %s\n' "$1" >&2; exit 1; }

descendants() {
    local parent="$1" child
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
    while IFS= read -r target; do [[ -n "${target}" ]] && targets+=("${target}"); done < <(descendants "${pid}")
    targets+=("${pid}")
    for target in "${targets[@]}"; do kill -TERM "${target}" 2>/dev/null || true; done
    for _ in {1..100}; do
        alive=0
        for target in "${targets[@]}"; do kill -0 "${target}" 2>/dev/null && alive=1; done
        [[ "${alive}" == 0 ]] && break
        sleep 0.05
    done
    for target in "${targets[@]}"; do kill -0 "${target}" 2>/dev/null && kill -KILL "${target}" 2>/dev/null || true; done
    wait "${pid}" 2>/dev/null || wait_status=$?
    [[ "${wait_status}" == 0 || "${wait_status}" == 143 || "${wait_status}" == 137 ]] || return 1
    for target in "${targets[@]}"; do kill -0 "${target}" 2>/dev/null && return 1; done
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
    verification_report_cleanup "${cleanup_status}" 'verified protected workspace and process-tree removal'
    verification_report_finish "${original}" "${cleanup_status}"
    if [[ "${original}" != 0 ]]; then
        exit "${original}"
    fi
    exit "${cleanup_status}"
}
trap cleanup EXIT

work="$(mktemp -d "${prefix}XXXXXX")"
chmod 700 "${work}"

if [[ "${TRACK07_SELF_TEST:-0}" == 1 ]]; then
    printf 'private cleanup sentinel' >"${work}/self-test-private"
    sleep 60 &
    pid=$!
    exit 97
fi

cd "${root}"
[[ -d .git && -f Makefile ]] || fail 'wrong repository root'
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/backend-sample-uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/private/tmp/backend-sample-python}"
export COVERAGE_FILE="${work}/.coverage"

run_private() {
    local label="$1"; shift
    "$@" >"${work}/${label}.receipt" 2>&1 || fail "${label} failed"
}

assert_unmasked() {
    local receipt="$1"
    ! rg -q '[1-9][0-9]* (skipped|xfailed|xpassed|deselected)' "${receipt}" || fail 'masked test result'
}

probe_root="$(mktemp -d "${TMPDIR:-/private/tmp}/backend-sample-track07-selftest.XXXXXX")"
child_status=0
TMPDIR="${probe_root}" TRACK07_SELF_TEST=1 bash "$0" >"${work}/cleanup-self-test.receipt" 2>&1 || child_status=$?
[[ "${child_status}" == 97 ]] || fail 'cleanup self-test did not preserve its nonzero status'
[[ -z "$(find "${probe_root}" -mindepth 1 -print -quit)" ]] || fail 'cleanup self-test retained private artifacts'
rmdir "${probe_root}"
printf 'Track 07 cleanup self-test: nonzero status and cleanup verified\n'

run_private inherited-track06 bash scripts/verify-track-06.sh
printf 'Track 07 inherited Track 06 gate: passed\n'

focused=(
  tests/integration/test_projection_schema.py
  tests/integration/test_projection_baseline.py
  tests/integration/test_projection_lifecycle.py
  tests/integration/test_projection_corrections.py
  tests/integration/test_projection_repository.py
  tests/integration/test_bookmark_stats_dirty.py
  tests/integration/test_stats_refresher.py
  tests/integration/test_health_routes.py
  tests/unit/test_projection_service.py
  tests/unit/test_projection_lifecycle.py
  tests/unit/test_stats_refresher.py
  tests/unit/test_health.py
)
run_private focused "${uv}" run pytest -q "${focused[@]}"
assert_unmasked "${work}/focused.receipt"
printf 'Track 07 focused weekly/schema/baseline/lifecycle/correction/dirty/refresher/health selectors: passed\n'

run_private sync "${uv}" sync --locked
run_private ruff-format "${uv}" run ruff format --check .
run_private ruff "${uv}" run ruff check .
run_private mypy "${uv}" run mypy app
run_private pyright "${uv}" run pyright app
"${uv}" run coverage erase
run_private coverage "${uv}" run coverage run --branch -m pytest -q
"${uv}" run coverage report --fail-under=100 >>"${work}/coverage.receipt" 2>&1 || fail 'branch coverage fell below 100 percent'
assert_unmasked "${work}/coverage.receipt"
run_private make-check make check
run_private docs bash scripts/verify-docs.sh
git diff --check || fail 'git whitespace gate failed'
printf 'Track 07 quality gate: locked sync, Ruff, mypy, Pyright, full branch coverage, make check, docs, diff: passed\n'
test_summary="$(rg -o '[0-9]+ passed(, [0-9]+ subtests passed)?' "${work}/coverage.receipt" | tail -n 1)"
coverage_summary="$(rg '^TOTAL ' "${work}/coverage.receipt" | tail -n 1)"
[[ -n "${test_summary}" && -n "${coverage_summary}" ]] || fail 'safe full-suite or coverage summary was unavailable'
printf 'Track 07 full-suite result: %s\n' "${test_summary}"
printf 'Track 07 coverage result: %s\n' "${coverage_summary}"

migration_database="${work}/migration-lifecycle.sqlite3"
export DATABASE_URL="sqlite:///${migration_database}" APP_ENV=test STATS_REFRESH_ENABLED=false
run_private migration-upgrade "${uv}" run alembic upgrade head
run_private migration-downgrade "${uv}" run alembic downgrade base
run_private migration-reupgrade "${uv}" run alembic upgrade head
run_private migration-check "${uv}" run alembic check
printf 'Track 07 migration lifecycle: upgrade, downgrade, re-upgrade, drift check passed\n'

select_port() {
    port="$("${uv}" run python - <<'PY'
import socket
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    print(listener.getsockname()[1])
PY
)"
}

start_server() {
    local database="$1" log_path="$2" projection="$3" ready=0
    select_port
    export DATABASE_URL="sqlite:///${database}" APP_ENV=test APP_WORKER_COUNT=1 STATS_REFRESH_ENABLED=true
    export STATS_REFRESH_INTERVAL_SECONDS=1 STATS_STALE_AFTER_SECONDS=3
    export STATS_FULL_RECONCILIATION_SECONDS=3 STATS_DIRTY_MAX_AGE_SECONDS=3
    export STATS_EVENT_QUEUE_CAPACITY=100 STATS_DIRTY_MAX_COUNT=1000
    if [[ "${projection}" == enabled ]]; then unset STATS_PROJECTION_ENABLED; else export STATS_PROJECTION_ENABLED=false; fi
    "${uv}" run alembic upgrade head >"${log_path}.migration" 2>&1 || fail 'process migration failed'
    "${uv}" run uvicorn app.main:create_app --factory --host 127.0.0.1 --port "${port}" --workers 1 --no-access-log --log-level critical >"${log_path}" 2>&1 &
    pid=$!
    for _ in {1..200}; do
        if curl --fail --silent "http://127.0.0.1:${port}/health/live" >/dev/null 2>&1; then ready=1; break; fi
        kill -0 "${pid}" 2>/dev/null || fail 'application exited before liveness'
        sleep 0.05
    done
    [[ "${ready}" == 1 ]] || fail 'application liveness timed out'
}

runtime_database="${work}/projection.sqlite3"
runtime_state="${work}/runtime-state.json"
disabled_database="${work}/projection-disabled.sqlite3"
mismatch_database="${work}/projection-mismatch.sqlite3"
bootstrap_log="${work}/bootstrap.jsonl"
projection_log="${work}/projection.jsonl"
restart_log="${work}/restart.jsonl"
disabled_log="${work}/disabled.jsonl"
mismatch_log="${work}/mismatch.jsonl"
export JWT_SECRET="$("${uv}" run python -c 'import secrets; print(secrets.token_urlsafe(48))')"

start_server "${runtime_database}" "${bootstrap_log}" disabled
"${uv}" run python - "${port}" "${runtime_state}" <<'PY'
import json, secrets, sys
import httpx
port, state_path = sys.argv[1:]
nonce = secrets.token_hex(10)
password = f"Track07-{secrets.token_urlsafe(32)}"
with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
    registration = client.post("/api/auth/register", json={"username": f"t07-{nonce}", "email": f"t07-{nonce}@example.test", "password": password})
    if registration.status_code != 201: raise SystemExit("bootstrap registration failed")
    token = registration.json()["token"]
    created = client.post("/api/bookmarks", headers={"Authorization": f"Bearer {token}"}, json={"url": f"https://example.invalid/{nonce}", "title": f"private-{nonce}", "tags": [f"private-{nonce}"]})
    if created.status_code != 201: raise SystemExit("bootstrap mutation failed")
    json.dump({"token": token, "bookmark_id": created.json()["id"], "nonce": nonce, "password": password}, open(state_path, "w", encoding="utf-8"))
print("Track 07 disabled bootstrap public mutation passed")
PY
stop_server || fail 'disabled bootstrap did not stop cleanly'
"${uv}" run python - "${runtime_database}" <<'PY'
import datetime as dt, sqlite3, sys
database = sys.argv[1]
now = dt.datetime.now(dt.UTC)
prior_monday = (now - dt.timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
with sqlite3.connect(database) as connection:
    rows = connection.execute("SELECT id FROM bookmarks").fetchall()
    if len(rows) != 1: raise SystemExit("disposable bootstrap cardinality is unsafe")
    connection.execute("UPDATE bookmarks SET created_at=? WHERE id=?", (prior_monday.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), rows[0][0]))
print("Track 07 safe disposable historic timestamp preparation passed")
PY

start_server "${runtime_database}" "${projection_log}" enabled
"${uv}" run python - "${port}" "${runtime_database}" "${runtime_state}" baseline <<'PY'
import json, sqlite3, sys, time
import httpx
port, database, state_path, phase = sys.argv[1:]
state = json.load(open(state_path, encoding="utf-8"))
headers = {"Authorization": f"Bearer {state['token']}"}
def require(value, message):
    if not value: raise SystemExit(message)
with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
    ready = None
    for _ in range(200):
        ready = client.get("/health/ready")
        if ready.status_code == 200: break
        time.sleep(.05)
    require(ready is not None and ready.status_code == 200 and ready.json() == {"status":"ready"}, "baseline readiness did not recover")
    require(ready.headers.get("cache-control") == "no-store", "readiness cache policy changed")
    api = client.get("/openapi.json").json()
    operations = {(path, method): response for path, methods in api["paths"].items() for method, response in methods.items()}
    require(len(operations) == 10 and sum(len(item["responses"]) for item in operations.values()) == 45, "OpenAPI inventory changed")
    require(not any("history" in path for path in api["paths"]), "public history surface appeared")
    before = client.get("/api/bookmarks/stats", headers=headers)
    require(before.status_code == 200 and before.json().get("total_bookmarks") == 1 and before.headers.get("x-stats-source") in {"live", "snapshot"}, "current stats initial total failed")
    if before.headers.get("x-stats-source") == "live": require("x-stats-generated-at" not in before.headers, "live statistics header parity failed")
    else: require(before.headers.get("x-stats-generated-at", "").endswith("Z"), "snapshot statistics header parity failed")
    created = client.post("/api/bookmarks", headers=headers, json={"url":"https://example.invalid/current", "title":"private-current", "tags":["private-current"]})
    require(created.status_code == 201, "current public mutation failed")
    state["current_id"] = created.json()["id"]
    after = None
    for _ in range(200):
        after = client.get("/api/bookmarks/stats", headers=headers)
        if after.status_code == 200 and after.json().get("total_bookmarks") == 2: break
        time.sleep(.05)
    require(after is not None and after.status_code == 200 and after.json().get("total_bookmarks") == 2 and set(after.json()) == set(before.json()), "current statistics body/total parity changed")
    if after.headers.get("x-stats-source") == "live": require("x-stats-generated-at" not in after.headers, "live statistics header parity changed")
    else: require(after.headers.get("x-stats-generated-at", "").endswith("Z"), "snapshot statistics header parity changed")
    json.dump(state, open(state_path, "w", encoding="utf-8"))
for _ in range(200):
    with sqlite3.connect(database) as connection:
        state_row = connection.execute("SELECT status FROM bookmark_stats_projection_state").fetchone()
        roots = connection.execute("SELECT count(*) FROM bookmark_stats_window_point WHERE revision=1 AND source_generation=0").fetchone()[0]
        working = connection.execute("SELECT count(*) FROM bookmark_stats_window_working WHERE source_generation > 0").fetchone()[0]
        pending = connection.execute("SELECT count(*) FROM bookmark_stats_window_dirty WHERE generation != projection_completed_generation").fetchone()[0]
    if state_row == ("active",) and roots == 1 and working >= 1 and pending == 0:
        break
    time.sleep(.05)
require(state_row == ("active",) and roots == 1 and working >= 1 and pending == 0, "baseline root/source-zero and dirty-created working/completion proof failed")
print("Track 07 default baseline, OpenAPI parity, current statistics, and durable source-generation proof passed")
PY
stop_server || fail 'projection phase did not stop cleanly'

start_server "${runtime_database}" "${restart_log}" enabled
"${uv}" run python - "${port}" "${runtime_database}" "${runtime_state}" correction <<'PY'
import json, sqlite3, sys, time
import httpx
port, database, state_path, phase = sys.argv[1:]
state = json.load(open(state_path, encoding="utf-8")); headers={"Authorization": f"Bearer {state['token']}"}
def require(value, message):
    if not value: raise SystemExit(message)
with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
    deleted = client.delete(f"/api/bookmarks/{state['bookmark_id']}", headers=headers)
    require(deleted.status_code == 204 and not deleted.content, "historic public delete failed")
    for _ in range(200):
        with sqlite3.connect(database) as connection:
            revisions = connection.execute("SELECT revision, supersedes_id FROM bookmark_stats_window_point ORDER BY revision").fetchall()
            pending = connection.execute("SELECT count(*) FROM bookmark_stats_window_dirty WHERE generation != projection_completed_generation").fetchone()[0]
            markers = connection.execute("SELECT count(*) FROM bookmark_stats_window_dirty").fetchone()[0]
        if len(revisions) == 2 and revisions[-1][0] == 2 and revisions[-1][1] is not None and pending == 0 and markers == 0: break
        time.sleep(.05)
require(len(revisions) == 2 and pending == 0 and markers == 0, "correction revision or dual completion failed")
stats = None
for _ in range(200):
    stats = client.get("/api/bookmarks/stats", headers=headers)
    if stats.status_code == 200 and stats.json().get("total_bookmarks") == 1: break
    time.sleep(.05)
require(stats is not None and stats.status_code == 200 and stats.json().get("total_bookmarks") == 1 and stats.headers.get("x-stats-source") in {"live", "snapshot"}, "current stats total changed by correction")
with sqlite3.connect(database) as connection:
    checkpoint = connection.execute("SELECT status FROM bookmark_stats_projection_state").fetchone()
    count = connection.execute("SELECT count(*) FROM bookmark_stats_window_point").fetchone()[0]
require(checkpoint == ("active",) and count == 2, "restart idempotence state failed")
print("Track 07 public historic deletion correction, dual completion, and restart idempotence passed")
PY
stop_server || fail 'restart phase did not stop cleanly'

postrestart_log="${work}/postrestart.jsonl"
start_server "${runtime_database}" "${postrestart_log}" enabled
"${uv}" run python - "${port}" "${runtime_database}" "${runtime_state}" <<'PY'
import json, sqlite3, sys, time
import httpx
port, database, state_path = sys.argv[1:]
state=json.load(open(state_path, encoding="utf-8")); headers={"Authorization": f"Bearer {state['token']}"}
with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
    ready=None
    for _ in range(200):
        ready=client.get("/health/ready")
        if ready.status_code == 200: break
        time.sleep(.05)
    stats=client.get("/api/bookmarks/stats", headers=headers)
    if not (ready is not None and ready.status_code == 200 and ready.json() == {"status":"ready"} and stats.status_code == 200 and stats.json().get("total_bookmarks") == 1): raise SystemExit("post-correction restart readiness/current-total failed")
with sqlite3.connect(database) as connection:
    state_row=connection.execute("SELECT status FROM bookmark_stats_projection_state").fetchone()
    points=connection.execute("SELECT count(*) FROM bookmark_stats_window_point").fetchone()[0]
    dirty=connection.execute("SELECT count(*) FROM bookmark_stats_window_dirty").fetchone()[0]
if not (state_row == ("active",) and points == 2 and dirty == 0): raise SystemExit("post-correction restart duplicated history or dirty work")
print("Track 07 post-correction restart idempotence passed")
PY
stop_server || fail 'post-correction restart did not stop cleanly'

start_server "${disabled_database}" "${disabled_log}" disabled
"${uv}" run python - "${port}" "${disabled_database}" <<'PY'
import sqlite3, sys
import httpx
port, database = sys.argv[1:]
with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
    registered=client.post("/api/auth/register", json={"username":"disabled-t07", "email":"disabled-t07@example.test", "password":"Track07-disabled-password"})
    if registered.status_code != 201: raise SystemExit("disabled registration failed")
    token=registered.json()["token"]; headers={"Authorization": f"Bearer {token}"}
    mutation=client.post("/api/bookmarks", headers=headers, json={"url":"https://example.invalid/disabled", "title":"private-disabled", "tags":["private-disabled"]})
    stats=client.get("/api/bookmarks/stats", headers=headers); live=client.get("/health/live"); ready=client.get("/health/ready")
    if not (mutation.status_code == 201 and stats.status_code == 200 and live.json() == {"status":"live"} and ready.status_code == 503 and ready.json() == {"status":"not_ready"}): raise SystemExit("disabled public/readiness contract failed")
with sqlite3.connect(database) as connection:
    pending=connection.execute("SELECT count(*) FROM bookmark_stats_window_dirty WHERE generation != projection_completed_generation").fetchone()[0]
    fabricated=sum(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in ("bookmark_stats_projection_state", "bookmark_stats_window_working", "bookmark_stats_window_point"))
if pending < 1 or fabricated != 0: raise SystemExit("disabled retention/fabrication contract failed")
print("Track 07 disabled projection retention and public-current/liveness independence passed")
PY
stop_server || fail 'disabled phase did not stop cleanly'

DATABASE_URL="sqlite:///${mismatch_database}" "${uv}" run alembic upgrade head >"${work}/mismatch-migration.receipt" 2>&1 || fail 'mismatch migration failed'
"${uv}" run python - "${mismatch_database}" <<'PY'
import datetime as dt, sqlite3, sys
with sqlite3.connect(sys.argv[1]) as connection:
    now=dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    connection.execute("INSERT INTO bookmark_stats_projection_state (id,status,calculation_version,checkpoint_user_id,checkpoint_window_start,baseline_started_at,baseline_completed_at,updated_at,last_projection_success_at,failure_code) VALUES (1,'active','incompatible',NULL,NULL,?, ?, ?, NULL, NULL)", (now,now,now))
print("Track 07 incompatible durable state preparation passed")
PY
start_server "${mismatch_database}" "${mismatch_log}" enabled
"${uv}" run python - "${port}" "${mismatch_database}" <<'PY'
import sqlite3, sys, time
import httpx
port, database = sys.argv[1:]
with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
    registered=client.post("/api/auth/register", json={"username":"mismatch-t07", "email":"mismatch-t07@example.test", "password":"Track07-mismatch-password"})
    if registered.status_code != 201: raise SystemExit("mismatch registration failed")
    headers={"Authorization": f"Bearer {registered.json()['token']}"}
    mutation=client.post("/api/bookmarks", headers=headers, json={"url":"https://example.invalid/mismatch", "title":"private-mismatch", "tags":["private-mismatch"]})
    stats=client.get("/api/bookmarks/stats", headers=headers); live=client.get("/health/live")
    ready=None
    for _ in range(200):
        ready=client.get("/health/ready")
        if ready.status_code == 503: break
        time.sleep(.05)
    if not (mutation.status_code == 201 and stats.status_code == 200 and live.json() == {"status":"live"} and ready is not None and ready.status_code == 503 and ready.json() == {"status":"not_ready"}): raise SystemExit("mismatch public/readiness contract failed")
with sqlite3.connect(database) as connection:
    version=connection.execute("SELECT calculation_version FROM bookmark_stats_projection_state").fetchone()[0]
    points=connection.execute("SELECT count(*) FROM bookmark_stats_window_point").fetchone()[0]
if version != "incompatible" or points != 0: raise SystemExit("mismatch state was auto-rewritten")
print("Track 07 calculation-version mismatch preserves current statistics and durable rows passed")
PY
stop_server || fail 'mismatch phase did not stop cleanly'

sensitivities="${work}/sensitivities.txt"
"${uv}" run python - "${runtime_state}" "${sensitivities}" "${work}" "${runtime_database}" "${disabled_database}" "${mismatch_database}" <<'PY'
import json, sys
state_path, sensitive_path, *paths = sys.argv[1:]
state=json.load(open(state_path, encoding="utf-8"))
nonce=state["nonce"]
values={state["token"], state["password"], nonce, f"private-{nonce}", f"https://example.invalid/{nonce}", *paths,
        "Track07-disabled-password", "Track07-mismatch-password", "private-current", "private-disabled", "private-mismatch",
        "https://example.invalid/current", "https://example.invalid/disabled", "https://example.invalid/mismatch"}
with open(sensitive_path, "w", encoding="utf-8") as output:
    output.write("\n".join(sorted(values)) + "\n")
PY

"${uv}" run python - "${sensitivities}" "${bootstrap_log}" "${projection_log}" "${restart_log}" "${postrestart_log}" "${disabled_log}" "${mismatch_log}" <<'PY'
import datetime as dt, json, os, sys
sensitive_path, *paths=sys.argv[1:]
def require(value, message):
    if not value: raise SystemExit(message)
sensitive={line for line in open(sensitive_path, encoding="utf-8").read().splitlines() if line}
sensitive.add(os.environ["JWT_SECRET"])
for path in paths:
    lines=open(path, encoding="utf-8").read().splitlines()
    require(lines and all(line.strip() for line in lines), "server output has blank/non-JSON Lines")
    records=[json.loads(line) for line in lines]
    events=[record.get("event") for record in records]
    for event in ("application.starting","application.started","application.stopping","application.stopped"):
        require(events.count(event) == 1, "application lifecycle is not exact once")
    refresher=("bookmark_stats.refresher_starting","bookmark_stats.refresher_started","bookmark_stats.refresher_stopping","bookmark_stats.refresher_stopped")
    require(all(events.count(event) == 1 for event in refresher), "exact one named worker lifecycle is absent")
    require("bookmark_stats.refresher_join_timeout" not in events, "worker did not stop cleanly")
    for record in records:
        require({"source","service","component","event","level","timestamp","logger","process_id","thread_id","thread_name"} <= record.keys(), "log schema is incomplete")
        source=record["source"]; require(source["pathname"].startswith("/") and source["lineno"] > 0 and source["package"].startswith("app") and source["module"].startswith("app."), "log source is not an absolute application location")
        require(dt.datetime.fromisoformat(record["timestamp"].replace("Z","+00:00")).utcoffset() == dt.timedelta(), "log time is not UTC")
        encoded=json.dumps(record, sort_keys=True)
        require(not any(value in encoded for value in ('"user_id"','"bookmark_id"','"resource_id"','Authorization','Bearer ','payload','content_hash','SELECT ','sqlite:///')), "unsafe log material leaked")
    starts=[record for record in records if record.get("event") == "bookmark_stats.refresher_started"]
    require(len(starts) == 1 and starts[0].get("thread_name") == "bookmark-stats-refresher" and starts[0].get("context", {}).get("worker_is_daemon") is False, "named non-daemon worker log is absent")
    projection_events=[record for record in records if record.get("event", "").startswith("bookmark_stats.projection_")]
    require(all(record.get("thread_name") == "bookmark-stats-refresher" for record in projection_events), "projection event escaped the named worker")
by_path={os.path.basename(path): open(path, encoding="utf-8").read() for path in paths}
for basename, event in (("projection.jsonl", "bookmark_stats.projection_baseline_completed"), ("disabled.jsonl", "bookmark_stats.projection_disabled"), ("mismatch.jsonl", "bookmark_stats.projection_failed")):
    records=[json.loads(line) for line in by_path[basename].splitlines() if line.strip()]
    require(any(record.get("event") == event for record in records), "required projection lifecycle event is absent")
combined=''.join(open(path, encoding='utf-8').read() for path in paths)
require(all(value not in combined for value in sensitive), "credential, workspace, fixed, or random private material leaked to logs")
print("Track 07 strict JSON Lines, one-worker, lifecycle, redaction, and signal-cleanup audit passed")
PY

printf 'Track 07 real-process baseline, correction, restart, disabled, mismatch, JSON Lines, and cleanup evidence: passed\n'
verification_report_summary 'inherited Track 06, deterministic projection, migration, real-process lifecycle, and redaction evidence completed'
