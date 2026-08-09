#!/usr/bin/env bash
# Final clean-clone evidence gate. It performs no submission/deploy/upload action; the locked
# pip-audit advisory query intentionally contacts the PyPA/PyPI vulnerability service.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

script_path="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/$(basename -- "${BASH_SOURCE[0]}")"
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
uv_command="${UV:-uv}"
development_preflight="${TRACK08_DEVELOPMENT_PREFLIGHT:-0}"
skip_docker="${TRACK08_SKIP_DOCKER:-0}"
workspace=""
clone_root=""
server_pid=""
runtime_port=""
docker_image=""
docker_container=""
docker_migrate_container=""
docker_volume=""
docker_env_file=""
cleanup_failed=0
reader_documents_ready=1

fail() {
    printf 'FAIL: Track 08 %s\n' "$*" >&2
    exit 1
}

safe_message() {
    printf 'Track 08: %s\n' "$*"
}

is_verified_workspace() {
    [[ -n "${workspace}" && -d "${workspace}" ]] || return 1
    [[ "$(basename -- "${workspace}")" == backend-sample-track08.* ]] || return 1
    [[ "${workspace}" != / && "${workspace}" != "${source_root}" ]] || return 1
}

descendants() {
    local parent="$1"
    pgrep -P "${parent}" 2>/dev/null || true
}

signal_tree() {
    local parent="$1"
    local signal="$2"
    local child
    for child in $(descendants "${parent}"); do
        signal_tree "${child}" "${signal}"
    done
    kill "-${signal}" "${parent}" 2>/dev/null || true
}

captured_processes=()

capture_process_tree() {
    local parent="$1"
    local child
    for child in $(descendants "${parent}"); do
        captured_processes+=("${child}")
        capture_process_tree "${child}"
    done
}

captured_survivor_count() {
    local process_id
    local count=0
    for process_id in "${captured_processes[@]}"; do
        if kill -0 "${process_id}" 2>/dev/null; then
            count=$((count + 1))
        fi
    done
    printf '%s' "${count}"
}

stop_server() {
    local status=0
    local attempt
    local survivor_count
    local process_id
    [[ -n "${server_pid}" ]] || return 0
    captured_processes=("${server_pid}")
    capture_process_tree "${server_pid}"
    if kill -0 "${server_pid}" 2>/dev/null; then
        # Signal the Uvicorn supervisor/root first; it owns graceful child propagation.
        kill -TERM "${server_pid}" 2>/dev/null || true
        for attempt in $(seq 1 100); do
            survivor_count="$(captured_survivor_count)"
            [[ "${survivor_count}" -eq 0 ]] && break
            sleep 0.1
        done
        survivor_count="$(captured_survivor_count)"
        if [[ "${survivor_count}" -ne 0 ]]; then
            for process_id in "${captured_processes[@]}"; do
                if kill -0 "${process_id}" 2>/dev/null; then
                    signal_tree "${process_id}" KILL
                fi
            done
            for attempt in $(seq 1 30); do
                survivor_count="$(captured_survivor_count)"
                [[ "${survivor_count}" -eq 0 ]] && break
                sleep 0.1
            done
        fi
    fi
    survivor_count="$(captured_survivor_count)"
    if [[ "${survivor_count}" -ne 0 ]]; then
        status=1
    fi
    wait "${server_pid}" 2>/dev/null || true
    if [[ "${status}" -ne 0 ]]; then
        printf 'FAIL: Track 08 server did not stop after TERM\n' >&2
        return 1
    fi
    server_pid=""
    safe_message "receipt: selector=Uvicorn supervisor TERM, bounded captured-process wait, recursive KILL fallback; captured=${#captured_processes[@]}; exit=0; no captured process remained"
    captured_processes=()
}

cleanup_docker() {
    local status=0
    if [[ -n "${docker_migrate_container}" ]] && command -v docker >/dev/null 2>&1; then
        docker rm -f "${docker_migrate_container}" >/dev/null 2>&1 || status=1
    fi
    if [[ -n "${docker_container}" ]] && command -v docker >/dev/null 2>&1; then
        docker rm -f "${docker_container}" >/dev/null 2>&1 || status=1
    fi
    if [[ -n "${docker_volume}" ]] && command -v docker >/dev/null 2>&1; then
        docker volume rm -f "${docker_volume}" >/dev/null 2>&1 || status=1
    fi
    if [[ -n "${docker_image}" ]] && command -v docker >/dev/null 2>&1; then
        docker image rm -f "${docker_image}" >/dev/null 2>&1 || status=1
    fi
    docker_container=""
    docker_migrate_container=""
    docker_volume=""
    docker_image=""
    docker_env_file=""
    return "${status}"
}

cleanup() {
    local original_status=$?
    local status=0
    trap - EXIT
    stop_server || status=1
    cleanup_docker || status=1
    if [[ -n "${workspace}" ]]; then
        if is_verified_workspace; then
            rm -rf -- "${workspace}" || status=1
            [[ ! -e "${workspace}" ]] || status=1
        else
            printf 'FAIL: Track 08 refused to remove an unverified workspace\n' >&2
            status=1
        fi
    fi
    if [[ "${status}" -eq 0 ]]; then
        safe_message 'receipt: selector=verified cleanup; exit=0; no server/container children and no private workspace remained'
    else
        printf 'FAIL: Track 08 cleanup verification failed\n' >&2
        cleanup_failed=1
    fi
    if [[ "${original_status}" -ne 0 ]]; then
        exit "${original_status}"
    fi
    exit "${status}"
}
trap cleanup EXIT
trap 'exit 143' INT TERM

create_workspace() {
    local temporary_base="${TMPDIR:-/private/tmp}"
    workspace="$(mktemp -d "${temporary_base%/}/backend-sample-track08.XXXXXX")"
    is_verified_workspace || fail 'mktemp returned an unsafe workspace path'
    chmod 700 "${workspace}"
}

run_private() {
    local name="$1"
    shift
    local receipt="${workspace}/receipts/${name}.log"
    if "$@" >"${receipt}" 2>&1; then
        case "${name}" in
            lock-check) safe_message 'receipt: command=uv lock --check; exit=0' ;;
            locked-sync) safe_message 'receipt: command=uv sync --locked; exit=0' ;;
            pip-audit) safe_message 'receipt: command=uv run pip-audit --local --progress-spinner off --desc off; exit=0' ;;
            verify-docs) safe_message 'receipt: command=bash scripts/verify-docs.sh; exit=0' ;;
            verify-track-01) safe_message 'receipt: command=bash scripts/verify-track-01.sh; exit=0' ;;
            verify-track-02) safe_message 'receipt: command=bash scripts/verify-track-02.sh; exit=0' ;;
            verify-track-03) safe_message 'receipt: command=bash scripts/verify-track-03.sh; exit=0' ;;
            verify-track-04) safe_message 'receipt: command=bash scripts/verify-track-04.sh; exit=0' ;;
            verify-track-05) safe_message 'receipt: command=bash scripts/verify-track-05.sh; exit=0' ;;
            verify-track-06) safe_message 'receipt: command=bash scripts/verify-track-06.sh; exit=0' ;;
            bonus-focused) safe_message 'receipt: command=uv run pytest -q [focused Track 08 bonus selectors]; exit=0' ;;
            ruff-format) safe_message 'receipt: command=uv run ruff format --check .; exit=0' ;;
            ruff-check) safe_message 'receipt: command=uv run ruff check .; exit=0' ;;
            mypy-app) safe_message 'receipt: command=uv run mypy app; exit=0' ;;
            alembic-upgrade-empty) safe_message 'receipt: command=uv run alembic upgrade head [empty SQLite]; exit=0' ;;
            alembic-downgrade-empty) safe_message 'receipt: command=uv run alembic downgrade base [empty SQLite]; exit=0' ;;
            alembic-reupgrade-empty) safe_message 'receipt: command=uv run alembic upgrade head [re-upgrade SQLite]; exit=0' ;;
            alembic-check) safe_message 'receipt: command=uv run alembic check; exit=0' ;;
            coverage-run) safe_message 'receipt: command=uv run coverage run --branch -m pytest -q; exit=0' ;;
            coverage-report) safe_message 'receipt: command=uv run coverage report --fail-under=100; exit=0' ;;
            seed-migrate) safe_message 'receipt: command=uv run alembic upgrade head [seed SQLite]; exit=0' ;;
            seed-first) safe_message 'receipt: command=uv run python -m app.seed [explicit isolated SQLite]; exit=0' ;;
            seed-second) safe_message 'receipt: command=uv run python -m app.seed [idempotency repeat]; exit=0' ;;
            runtime-migrate) safe_message 'receipt: command=uv run alembic upgrade head [runtime SQLite]; exit=0' ;;
            *) fail "unrecognised private receipt name: ${name}" ;;
        esac
    else
        local command_status=$?
        printf 'FAIL: Track 08 %s failed (private receipt retained only until cleanup)\n' "${name}" >&2
        return "${command_status}"
    fi
}

require_clean_source() {
    [[ -d "${source_root}/.git" ]] || fail 'must run from a Git working tree'
    [[ -z "$(git -C "${source_root}" status --porcelain=v1 --untracked-files=all)" ]] \
        || fail 'source working tree is dirty or has untracked files'
    git -C "${source_root}" diff --check
}

assert_reader_documents() {
    local missing=0
    local document
    # The root reader document is deliberately a final handoff gate.  The existing
    # .docs index remains required so a future README cannot point at a missing handoff.
    for document in \
        README.md \
        .docs/README.md \
        .docs/SOLUTION-DESIGN.md \
        .docs/DELIVERY-PLAN.md \
        .docs/WALKTHROUGH.md \
        .docs/AI-ASSISTED-WORK.md \
        .docs/RELEASE-HANDOFF.md; do
        if [[ ! -f "${clone_root}/${document}" ]]; then
            missing=1
        fi
    done
    if [[ "${missing}" -eq 0 ]]; then
        safe_message 'reader/handoff documents: present'
        return 0
    fi
    if [[ "${development_preflight}" == 1 ]]; then
        reader_documents_ready=0
        safe_message 'DEVELOPMENT INCOMPLETE: reader/handoff documents are not delivered'
        return 0
    fi
    fail 'required root reader/handoff documentation is missing'
}

clone_committed_source() {
    local source_head
    source_head="$(git -C "${source_root}" rev-parse HEAD)"
    clone_root="${workspace}/clean-clone"
    git -C "${source_root}" clone --no-local --no-hardlinks "${source_root}" "${clone_root}" \
        >"${workspace}/receipts/clone.log" 2>&1 || fail 'clean clone creation failed'
    [[ "$(git -C "${clone_root}" rev-parse HEAD)" == "${source_head}" ]] \
        || fail 'clean clone HEAD differs from reviewed source HEAD'
    [[ -z "$(git -C "${clone_root}" status --porcelain=v1 --untracked-files=all)" ]] \
        || fail 'new clean clone is not clean'
    safe_message "receipt: source HEAD=${source_head}; command=git clone --no-local --no-hardlinks [local reviewed source]; exit=0"
}

report_tool_versions_and_dependencies() {
    local python_version
    local uv_version
    local pytest_version
    local coverage_version
    local ruff_version
    local mypy_version
    local alembic_version
    local uvicorn_version
    local inventory_summary
    python_version="$(cd "${clone_root}" && "${uv_command}" run python --version)"
    uv_version="$("${uv_command}" --version)"
    pytest_version="$(cd "${clone_root}" && "${uv_command}" run pytest --version | head -1)"
    coverage_version="$(cd "${clone_root}" && "${uv_command}" run coverage --version | head -1)"
    ruff_version="$(cd "${clone_root}" && "${uv_command}" run ruff --version)"
    mypy_version="$(cd "${clone_root}" && "${uv_command}" run mypy --version)"
    alembic_version="$(cd "${clone_root}" && "${uv_command}" run alembic --version)"
    uvicorn_version="$(cd "${clone_root}" && "${uv_command}" run uvicorn --version)"
    safe_message "tool versions: ${python_version}; ${uv_version}; ${pytest_version}; ${coverage_version}; ${ruff_version}; ${mypy_version}; ${alembic_version}; ${uvicorn_version}"
    (cd "${clone_root}" && "${uv_command}" run python - >"${workspace}/receipts/dependency-license-inventory.log" <<'PY'
from importlib import metadata

unknown_names: list[str] = []
total = 0
for distribution in metadata.distributions():
    total += 1
    license_value = distribution.metadata.get("License", "").strip()
    license_expression = distribution.metadata.get("License-Expression", "").strip()
    classifiers = distribution.metadata.get_all("Classifier") or []
    if not license_value and not license_expression and not any(item.startswith("License ::") for item in classifiers):
        unknown_names.append(distribution.metadata.get("Name", distribution.name))
sorted_unknown_names = ",".join(sorted(set(unknown_names))) or "NONE"
print(
    f"distribution_count={total} unknown_license_count={len(unknown_names)} "
    f"unknown_license_names={sorted_unknown_names}"
)
PY
    )
    inventory_summary="$(cat "${workspace}/receipts/dependency-license-inventory.log")"
    [[ "${inventory_summary}" =~ ^distribution_count=[0-9]+\ unknown_license_count=[0-9]+\ unknown_license_names=.+$ ]] \
        || fail 'dependency/license inventory did not produce a safe count summary'
    safe_message "dependency/license inventory: ${inventory_summary}; UNKNOWN licenses require owner review and do not fail this gate"
}

configure_clean_clone() {
    local resolved_python
    [[ "$(tr -d '[:space:]' < "${clone_root}/.python-version")" == 3.12.12 ]] \
        || fail '.python-version is not exactly 3.12.12 in the clean clone'
    command -v "${uv_command}" >/dev/null 2>&1 || fail 'uv is unavailable'
    export UV_CACHE_DIR="${workspace}/uv-cache"
    export UV_PYTHON_INSTALL_DIR="${workspace}/python-install"
    resolved_python="$(cd "${clone_root}" && "${uv_command}" python find 3.12.12)"
    [[ -n "${resolved_python}" && -x "${resolved_python}" ]] || fail 'uv did not resolve Python 3.12.12'
    [[ "$("${resolved_python}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')" == 3.12.12 ]] \
        || fail 'resolved interpreter is not Python 3.12.12'
    (cd "${clone_root}" && run_private lock-check "${uv_command}" lock --check)
    (cd "${clone_root}" && run_private locked-sync "${uv_command}" sync --locked)
    (cd "${clone_root}" && run_private pip-audit "${uv_command}" run pip-audit --local --progress-spinner off --desc off)
    rg -q 'No known vulnerabilities found' "${workspace}/receipts/pip-audit.log" \
        || fail 'pip-audit did not confirm that no known vulnerabilities were found'
    local missing_dependency_line
    while IFS= read -r missing_dependency_line; do
        [[ "${missing_dependency_line}" == *bookmarks-api* ]] \
            || fail 'pip-audit skipped a dependency other than the local bookmarks-api project'
    done < <(rg -i 'dependency.*not found' "${workspace}/receipts/pip-audit.log" || true)
    if rg -qi 'dependency.*not found' "${workspace}/receipts/pip-audit.log"; then
        safe_message 'pip-audit: accepted local bookmarks-api dependency-not-found skip; exit=0'
    fi
    safe_message 'dependency advisory: pip-audit queried PyPA/PyPI known-vulnerability data; this is not source or malware proof'
    report_tool_versions_and_dependencies
    safe_message 'toolchain: committed Python 3.12 pin, resolved interpreter, lock check, and locked sync verified'
}

assert_upstream_provenance() {
    local track="$1"
    local report="$2"
    local plan="$3"
    local report_commit
    local plan_commit
    local candidate
    local valid_cited_commit_count=0
    [[ -f "${clone_root}/${report}" ]] || fail "missing upstream closure report ${report}"
    rg -q -- '- Status: Passed' "${clone_root}/${report}" || fail "upstream report is not Passed: ${report}"
    [[ -f "${clone_root}/${plan}" ]] || fail "missing upstream plan ${plan}"
    rg -q -- '^- Status: Complete$' "${clone_root}/${plan}" || fail "upstream plan is not Complete: ${plan}"
    report_commit="$(git -C "${clone_root}" log -1 --format=%H -- "${report}")"
    [[ -n "${report_commit}" ]] || fail "upstream report has no committed provenance: ${report}"
    git -C "${clone_root}" merge-base --is-ancestor "${report_commit}" HEAD \
        || fail "upstream report provenance is not an ancestor of current HEAD: ${report}"
    plan_commit="$(git -C "${clone_root}" log -1 --format=%H -- "${plan}")"
    [[ -n "${plan_commit}" ]] || fail "upstream plan has no committed provenance: ${plan}"
    git -C "${clone_root}" merge-base --is-ancestor "${plan_commit}" "${report_commit}" \
        || fail "upstream plan is newer than its report provenance: ${plan}"
    for candidate in $(rg -o '`[0-9a-fA-F]{7,40}`' "${clone_root}/${report}" | tr -d '`' || true); do
        if git -C "${clone_root}" cat-file -e "${candidate}^{commit}" 2>/dev/null; then
            git -C "${clone_root}" merge-base --is-ancestor "${candidate}" "${report_commit}" \
                || fail "cited report commit is not an ancestor of the report: ${report}"
            valid_cited_commit_count=$((valid_cited_commit_count + 1))
        fi
    done
    [[ "${valid_cited_commit_count}" -ge 1 ]] \
        || fail "upstream report has no valid cited commit provenance: ${report}"
    safe_message "Track ${track} provenance: report=${report}; plan=${plan}; report_commit=${report_commit}; plan_commit=${plan_commit}; valid_cited_commits=${valid_cited_commit_count}; Passed/Complete/ancestor chain and current exact harness compatibility exit=0"
}

verify_upstream_evidence() {
    (cd "${clone_root}" && run_private verify-docs bash scripts/verify-docs.sh)
    # These literal invocations are intentional: no equivalent selector may replace a track harness.
    (cd "${clone_root}" && run_private verify-track-01 bash scripts/verify-track-01.sh)
    (cd "${clone_root}" && run_private verify-track-02 bash scripts/verify-track-02.sh)
    (cd "${clone_root}" && run_private verify-track-03 bash scripts/verify-track-03.sh)
    (cd "${clone_root}" && run_private verify-track-04 bash scripts/verify-track-04.sh)
    (cd "${clone_root}" && run_private verify-track-05 bash scripts/verify-track-05.sh)
    (cd "${clone_root}" && run_private verify-track-06 bash scripts/verify-track-06.sh)

    assert_upstream_provenance 01 .tracks/01-foundation/TEST-REPORT.md .tracks/01-foundation/PLAN.md
    assert_upstream_provenance 02 .tracks/02-auth-errors/TEST-REPORT.md .tracks/02-auth-errors/PLAN.md
    assert_upstream_provenance 03 .tracks/03-bookmark-crud/TEST-REPORT.md .tracks/03-bookmark-crud/PLAN.md
    assert_upstream_provenance 04 .tracks/04-search-stats/TEST-REPORT.md .tracks/04-search-stats/PLAN.md
    assert_upstream_provenance 05 .tracks/05-mandatory-quality-gate/TEST-REPORT.md .tracks/05-mandatory-quality-gate/PLAN.md
    assert_upstream_provenance 06 .tracks/06-event-driven-stats/TEST-REPORT.md .tracks/06-event-driven-stats/PLAN.md
    safe_message 'upstream closure reports: non-circular provenance and current exact harness compatibility verified'
}

assert_no_masked_test_results() {
    local receipt="$1"
    ! rg -q '[1-9][0-9]* (skipped|xfailed|xpassed|deselected)' "${receipt}" \
        || fail 'test execution contained skipped, xfailed, xpassed, or deselected tests'
}

run_bonus_focus() {
    local -a bonus_tests=(
        tests/contract/test_docker_delivery.py
        tests/integration/test_seed.py
        tests/unit/test_rate_limit.py
        tests/integration/test_rate_limit_routes.py
        tests/contract/test_rate_limit_openapi.py
        tests/unit/test_bookmark_pagination.py
        tests/unit/test_bookmark_dependencies.py
        tests/integration/test_cursor_pagination.py
        tests/contract/test_openapi_metadata.py
    )
    (cd "${clone_root}" && run_private bonus-focused "${uv_command}" run pytest -q "${bonus_tests[@]}")
    assert_no_masked_test_results "${workspace}/receipts/bonus-focused.log"
    local bonus_summary
    local bonus_selector
    bonus_summary="$(rg -e '[0-9]+ passed' "${workspace}/receipts/bonus-focused.log" | tail -1 || true)"
    [[ -n "${bonus_summary}" ]] || fail 'focused bonus receipt lacks an exact passing summary'
    for bonus_selector in "${bonus_tests[@]}"; do
        safe_message "focused bonus selector: ${bonus_selector}; exit=0"
    done
    safe_message "focused bonus pytest summary: ${bonus_summary}"
}

run_quality_and_migrations() {
    local database_path="${workspace}/empty-migration.sqlite3"
    export APP_ENV=test
    export DATABASE_URL="sqlite:///${database_path}"
    export JWT_SECRET="$(cd "${clone_root}" && "${uv_command}" run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
    (cd "${clone_root}" && run_private ruff-format "${uv_command}" run ruff format --check .)
    (cd "${clone_root}" && run_private ruff-check "${uv_command}" run ruff check .)
    (cd "${clone_root}" && run_private mypy-app "${uv_command}" run mypy app)
    (cd "${clone_root}" && run_private alembic-upgrade-empty "${uv_command}" run alembic upgrade head)
    (cd "${clone_root}" && run_private alembic-downgrade-empty "${uv_command}" run alembic downgrade base)
    (cd "${clone_root}" && run_private alembic-reupgrade-empty "${uv_command}" run alembic upgrade head)
    (cd "${clone_root}" && run_private alembic-check "${uv_command}" run alembic check)
    (cd "${clone_root}" && run_private coverage-run "${uv_command}" run coverage run --branch -m pytest -q)
    (cd "${clone_root}" && run_private coverage-report "${uv_command}" run coverage report --fail-under=100)
    assert_no_masked_test_results "${workspace}/receipts/coverage-run.log"
    local test_summary
    local total_summary
    test_summary="$(rg -e '[0-9]+ passed' "${workspace}/receipts/coverage-run.log" | tail -1 || true)"
    total_summary="$(rg '^TOTAL' "${workspace}/receipts/coverage-report.log" | tail -1 || true)"
    [[ -n "${test_summary}" && -n "${total_summary}" ]] || fail 'coverage receipt lacks exact test and TOTAL summaries'
    safe_message "full pytest summary: ${test_summary}"
    safe_message "coverage TOTAL: ${total_summary}"
}

verify_seed() {
    local seed_database="${workspace}/seed.sqlite3"
    export DATABASE_URL="sqlite:///${seed_database}"
    export APP_ENV=test
    (cd "${clone_root}" && run_private seed-migrate "${uv_command}" run alembic upgrade head)
    (cd "${clone_root}" && run_private seed-first "${uv_command}" run python -m app.seed)
    (cd "${clone_root}" && run_private seed-second "${uv_command}" run python -m app.seed)
    (cd "${clone_root}" && "${uv_command}" run python - "${seed_database}" \
        >"${workspace}/receipts/seed-state.log" 2>&1 <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as connection:
    counts = {
        table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("users", "bookmarks", "tags", "bookmark_tags")
    }
    revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
if counts != {"users": 1, "bookmarks": 2, "tags": 3, "bookmark_tags": 4} or not revision:
    raise SystemExit("deterministic seed state was not exact or migrated")
print("seed state exact and idempotent")
PY
    )
    safe_message 'receipt: selector=explicit isolated SQLite seed state; exit=0; migrated, seeded twice, and exact idempotent state verified'
}

allocate_port() {
    (cd "${clone_root}" && "${uv_command}" run python - <<'PY'
import socket
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
    )
}

wait_for_service() {
    local port="$1"
    local attempt
    for attempt in $(seq 1 150); do
        if curl --fail --silent "http://127.0.0.1:${port}/health/live" >/dev/null 2>&1; then
            return 0
        fi
        kill -0 "${server_pid}" 2>/dev/null || fail 'Uvicorn exited before liveness'
        sleep 0.1
    done
    fail 'timed out waiting for Uvicorn liveness'
}

start_server() {
    local runtime_database="${workspace}/runtime.sqlite3"
    export DATABASE_URL="sqlite:///${runtime_database}"
    export APP_ENV=test
    export JWT_SECRET="$(cd "${clone_root}" && "${uv_command}" run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
    export APP_WORKER_COUNT=1
    export RATE_LIMIT_AUTH_REQUESTS=3
    export RATE_LIMIT_AUTH_WINDOW_SECONDS=60
    (cd "${clone_root}" && run_private runtime-migrate "${uv_command}" run alembic upgrade head)
    runtime_port="$(allocate_port)"
    (cd "${clone_root}" && exec "${uv_command}" run uvicorn app.main:create_app --factory --host 127.0.0.1 --port "${runtime_port}" --workers 1 --no-access-log --log-level critical >"${workspace}/receipts/runtime.jsonl" 2>&1) &
    server_pid=$!
    wait_for_service "${runtime_port}"
}

exercise_runtime() {
    local port="$1"
    if ! (cd "${clone_root}" && "${uv_command}" run python - "${port}" <<'PY'
import secrets
import sys
from datetime import datetime
import httpx

port = sys.argv[1]
base = f"http://127.0.0.1:{port}"
password = f"Track08-{secrets.token_urlsafe(24)}"
nonce = secrets.token_hex(10)

def require(response: httpx.Response, status: int) -> None:
    if response.status_code != status:
        raise SystemExit(f"unexpected safe status: {response.request.method} {response.request.url.path}")

def user(label: str) -> dict[str, str]:
    return {"username": f"{label}-{nonce}", "email": f"{label}-{nonce}@example.com", "password": password}

def bookmark(label: str, title: str, tag: str) -> dict[str, object]:
    return {
        "url": f"https://example.test/{nonce}/{label}",
        "title": title,
        "tags": [tag],
    }

with httpx.Client(base_url=base, timeout=10) as client:
    for path in ("/health/live", "/health/ready", "/docs"):
        response = client.get(path)
        require(response, 200)
    document_response = client.get("/openapi.json"); require(document_response, 200)
    document = document_response.json()
    if document.get("openapi") != "3.1.0":
        raise SystemExit("OpenAPI version is not the delivered 3.1.0 contract")
    operations = [
        operation
        for methods in document.get("paths", {}).values()
        for operation in methods.values()
    ]
    if len(operations) != 10 or sum(len(operation.get("responses", {})) for operation in operations) != 45:
        raise SystemExit("OpenAPI operation or response inventory changed")
    bearer = document.get("components", {}).get("securitySchemes", {}).get("BearerAuth")
    if bearer != {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}:
        raise SystemExit("OpenAPI bearer scheme changed")
    list_operation = document["paths"]["/api/bookmarks"]["get"]
    parameters = {parameter["name"] for parameter in list_operation.get("parameters", [])}
    if not {"pagination", "cursor"} <= parameters or "X-Next-Cursor" not in list_operation["responses"]["200"].get("headers", {}):
        raise SystemExit("OpenAPI cursor parameter or continuation header is absent")
    limited_operations = (
        ("/api/auth/register", "post"), ("/api/auth/login", "post"),
        ("/api/bookmarks", "post"), ("/api/bookmarks", "get"),
        ("/api/bookmarks/stats", "get"), ("/api/bookmarks/{bookmark_id}", "get"),
        ("/api/bookmarks/{bookmark_id}", "patch"), ("/api/bookmarks/{bookmark_id}", "delete"),
    )
    if any("429" not in document["paths"][path][method]["responses"] for path, method in limited_operations):
        raise SystemExit("OpenAPI selected rate-limit responses are absent")
    owner = client.post("/api/auth/register", json=user("owner")); require(owner, 201)
    other = client.post("/api/auth/register", json=user("other")); require(other, 201)
    owner_headers = {"Authorization": "Bearer " + owner.json()["token"]}
    other_headers = {"Authorization": "Bearer " + other.json()["token"]}
    created = [
        client.post("/api/bookmarks", headers=owner_headers, json=bookmark("alpha", "Alpha title", "alpha-tag")),
        client.post("/api/bookmarks", headers=owner_headers, json=bookmark("query", "Needle title", "beta-tag")),
        client.post("/api/bookmarks", headers=owner_headers, json=bookmark("gamma", "Gamma title", "gamma-tag")),
    ]
    for response in created:
        require(response, 201)
    other_created = client.post(
        "/api/bookmarks", headers=other_headers, json=bookmark("other", "Other title", "other-tag")
    ); require(other_created, 201)
    ids = [response.json()["id"] for response in created]
    query_match = client.get(
        "/api/bookmarks",
        headers=owner_headers,
        params={"q": "needle title", "page_size": 10},
    ); require(query_match, 200)
    if query_match.json()["total"] != 1 or [item["id"] for item in query_match.json()["items"]] != [ids[1]]:
        raise SystemExit("query filter did not return the exact owner item")
    tag_match = client.get(
        "/api/bookmarks", headers=owner_headers, params={"tag": "alpha-tag", "page_size": 10}
    ); require(tag_match, 200)
    if tag_match.json()["total"] != 1 or [item["id"] for item in tag_match.json()["items"]] != [ids[0]]:
        raise SystemExit("tag filter did not return the exact owner item")
    future = client.get(
        "/api/bookmarks", headers=owner_headers, params={"from": "2999-01-01", "page_size": 10}
    ); require(future, 200)
    if future.json()["total"] != 0 or future.json()["items"] != []:
        raise SystemExit("future created-from filter was ignored")
    detail = client.get(f"/api/bookmarks/{ids[0]}", headers=owner_headers); require(detail, 200)
    before_patch = detail.json()
    patched = client.patch(f"/api/bookmarks/{ids[0]}", headers=owner_headers, json={"title": "Track08 patched"}); require(patched, 200)
    patched_body = patched.json()
    if patched_body["title"] != "Track08 patched" or patched_body["created_at"] != before_patch["created_at"]:
        raise SystemExit("PATCH response did not preserve the documented title/timestamp contract")
    if datetime.fromisoformat(patched_body["updated_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(before_patch["updated_at"].replace("Z", "+00:00")):
        raise SystemExit("PATCH response did not advance updated_at")
    isolated = client.get(f"/api/bookmarks/{ids[0]}", headers=other_headers); require(isolated, 404)
    first = client.get("/api/bookmarks", headers=owner_headers, params={"pagination": "cursor", "page_size": 1}); require(first, 200)
    cursor = first.headers.get("X-Next-Cursor")
    if not cursor:
        raise SystemExit("first cursor page lacked a continuation")
    second = client.get("/api/bookmarks", headers=owner_headers, params={"pagination": "cursor", "cursor": cursor, "page_size": 1}); require(second, 200)
    if first.json()["items"][0]["id"] == second.json()["items"][0]["id"]:
        raise SystemExit("cursor pagination repeated an item")
    tampered = client.get("/api/bookmarks", headers=owner_headers, params={"pagination": "cursor", "cursor": cursor + "x"}); require(tampered, 422)
    if tampered.json()["error"]["code"] != "invalid_cursor":
        raise SystemExit("tampered cursor did not use the fixed envelope")
    exclusive = client.get("/api/bookmarks", headers=owner_headers, params={"pagination": "cursor", "cursor": cursor, "page": 1}); require(exclusive, 422)
    stats = client.get("/api/bookmarks/stats", headers=owner_headers); require(stats, 200)
    if stats.json()["total_bookmarks"] != 3:
        raise SystemExit("current stats did not reflect owner data")
    deleted = client.delete(f"/api/bookmarks/{ids[2]}", headers=owner_headers); require(deleted, 204)
    login = client.post("/api/auth/login", json={"email": user("owner")["email"], "password": password}); require(login, 200)
    limited = client.post("/api/auth/login", json={"email": user("owner")["email"], "password": password}); require(limited, 429)
    if limited.headers.get("Cache-Control") != "no-store" or int(limited.headers.get("Retry-After", "0")) < 1:
        raise SystemExit("rate limit headers were not deterministic and safe")
    if limited.json()["error"]["code"] != "rate_limited":
        raise SystemExit("rate limit envelope changed")
print("Track 08 runtime safe-driver: health/OpenAPI/docs, auth, owner isolation, CRUD/search, cursor, current stats, and 429 contract passed")
PY
    ) >"${workspace}/receipts/runtime-driver.log" 2>&1; then
        fail 'runtime safe-driver failed'
    fi
    rg -q 'Track 08 runtime safe-driver:' "${workspace}/receipts/runtime-driver.log" || fail 'runtime driver lacked a safe completion receipt'
    safe_message 'receipt: selector=real Uvicorn safe in-memory HTTP driver; exit=0; no tokens or protected response bodies persisted'
}

safe_runtime_lifecycle_counts() {
    (cd "${clone_root}" && "${uv_command}" run python - "${workspace}/receipts/runtime.jsonl" <<'PY'
import json
import sys

counts: dict[str, int] = {}
invalid_json_lines = 0
for line in open(sys.argv[1], encoding="utf-8"):
    if not line.strip():
        continue
    try:
        event = json.loads(line).get("event")
    except json.JSONDecodeError:
        invalid_json_lines += 1
        continue
    if isinstance(event, str):
        counts[event] = counts.get(event, 0) + 1
events = ",".join(f"{event}={counts[event]}" for event in sorted(counts)) or "NONE"
print(f"events={events}; invalid_json_lines={invalid_json_lines}")
PY
    )
}

audit_runtime_logs() {
    if ! (cd "${clone_root}" && "${uv_command}" run python - "${workspace}/receipts/runtime.jsonl" <<'PY'
import datetime as dt
import json
import sys

lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
if not lines:
    raise SystemExit("runtime emitted no JSON Lines")
records = [json.loads(line) for line in lines]
required = {"source", "service", "component", "event", "level", "timestamp", "logger", "process_id", "thread_id"}
for record in records:
    if not required <= record.keys():
        raise SystemExit("JSON Lines schema is incomplete")
    source = record["source"]
    if not {"pathname", "lineno", "package", "module", "function"} <= source.keys():
        raise SystemExit("JSON Lines source schema is incomplete")
    if not source["pathname"].startswith("/") or source["lineno"] <= 0:
        raise SystemExit("JSON Lines source attribution is invalid")
    if dt.datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00")).utcoffset() != dt.timedelta():
        raise SystemExit("JSON Lines timestamp is not UTC")
encoded = json.dumps(records, sort_keys=True)
if any(value in encoded for value in ("Authorization", "Bearer ", "password_hash", "sqlite:///")):
    raise SystemExit("runtime JSON Lines contain credential-shaped material")
events = [record["event"] for record in records]
for event in ("application.starting", "application.started", "application.stopping", "application.stopped"):
    if events.count(event) != 1:
        raise SystemExit("runtime application lifecycle evidence is not exactly once")
refresher_events = (
    "bookmark_stats.refresher_starting",
    "bookmark_stats.refresher_started",
    "bookmark_stats.refresher_stopping",
    "bookmark_stats.refresher_stopped",
)
if any(event in events for event in refresher_events):
    if any(events.count(event) != 1 for event in refresher_events):
        raise SystemExit("runtime refresher lifecycle evidence is incomplete")
print("runtime JSON Lines schema, redaction, and shutdown lifecycle audit passed")
PY
    ) >"${workspace}/receipts/runtime-audit.log" 2>&1; then
        safe_message "runtime lifecycle audit failure: $(safe_runtime_lifecycle_counts)"
        fail 'runtime JSON Lines audit failed'
    fi
    safe_message 'receipt: selector=runtime JSON Lines schema/redaction/shutdown lifecycle; exit=0; exact exception ownership selectors ran in Track 01, 05, and 06 receipts'
}

verify_track07_absence() {
    rg -q 'Status: \*\*Skipped \(owner decision\)\*\*' "${clone_root}/.tracks/07-weekly-projections/SPEC.md" \
        || fail 'Track 07 skip disposition is absent'
    [[ ! -e "${clone_root}/.tracks/07-weekly-projections/TEST-REPORT.md" ]] || fail 'Track 07 has an implementation report'
    [[ ! -e "${clone_root}/scripts/verify-track-07.sh" ]] || fail 'Track 07 has an executable harness'
    ! rg -qi 'weekly|projection|developing|developed|history' "${clone_root}/alembic/versions" \
        || fail 'weekly projection migration artifacts are present'
    ! rg -qi '/api/.+history|weekly' "${clone_root}/app" || fail 'weekly/history runtime API is present'
    safe_message 'receipt: selector=Track 07 owner-skipped disposition and absence boundary; exit=0'
}

verify_hygiene() {
    (cd "${clone_root}" && git diff --check)
    (cd "${clone_root}" && "${uv_command}" lock --check >"${workspace}/receipts/lock-final.log" 2>&1)
    if git -C "${clone_root}" ls-files | rg -q '(^|/)(\.coverage|.*\.(db|sqlite|sqlite3|log|pem|key)|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache)(/|$)'; then
        fail 'tracked generated, database, cache, log, or key artifact found'
    fi
    if git -C "${clone_root}" grep -I -q -E '(-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})'; then
        fail 'plausible committed secret found'
    fi
    [[ -z "$(git -C "${clone_root}" status --porcelain=v1 --untracked-files=all)" ]] \
        || fail 'clean clone is dirty at closure'
    safe_message 'receipt: command=git diff --check + tracked-artifact/secret/lock/clean-status hygiene; exit=0'
}

wait_for_docker_removal() {
    local container_name="$1"
    local receipt_label="$2"
    local attempt
    for attempt in $(seq 1 100); do
        if ! docker container inspect "${container_name}" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.1
    done
    fail "Docker ${receipt_label} remained visible after bounded removal wait"
}

verify_docker() {
    if [[ "${skip_docker}" == 1 ]]; then
        safe_message 'DEVELOPMENT INCOMPLETE: Docker execution explicitly skipped by TRACK08_SKIP_DOCKER=1'
        return 0
    fi
    command -v docker >/dev/null 2>&1 || fail 'Docker is required for final Track 08 evidence'
    docker info >/dev/null 2>&1 || fail 'Docker daemon is required for final Track 08 evidence'
    local short_head
    local port
    short_head="$(git -C "${clone_root}" rev-parse --short=12 HEAD)"
    docker_image="backend-sample-track08-${short_head}-$$"
    docker_container="backend-sample-track08-${short_head}-$$"
    docker_volume="backend-sample-track08-${short_head}-$$"
    docker build --tag "${docker_image}" "${clone_root}" >"${workspace}/receipts/docker-build.log" 2>&1 || fail 'Docker build failed'
    [[ "$(docker image inspect --format '{{.Config.User}}' "${docker_image}")" == app ]] || fail 'Docker image is not non-root'
    docker volume create "${docker_volume}" >/dev/null
    docker_env_file="${workspace}/docker.env"
    (cd "${clone_root}" && "${uv_command}" run python - >"${docker_env_file}" <<'PY'
import secrets
print(f"JWT_SECRET={secrets.token_urlsafe(48)}")
PY
    )
    chmod 600 "${docker_env_file}"
    docker_migrate_container="${docker_container}-migrate"
    docker run --name "${docker_migrate_container}" --volume "${docker_volume}:/data" \
        --env-file "${docker_env_file}" \
        "${docker_image}" migrate-only >"${workspace}/receipts/docker-migrate.log" 2>&1 || fail 'Docker migrate-only failed'
    docker rm "${docker_migrate_container}" >/dev/null || fail 'Docker migrate-only container removal failed'
    wait_for_docker_removal "${docker_migrate_container}" 'migrate-only container'
    ! docker container inspect "${docker_migrate_container}" >/dev/null 2>&1 \
        || fail 'Docker migrate-only container remained after removal visibility wait'
    docker_migrate_container=""
    docker_container="backend-sample-track08-${short_head}-$$"
    port="$(allocate_port)"
    docker run --detach --name "${docker_container}" --publish "127.0.0.1:${port}:8000" --volume "${docker_volume}:/data" \
        --env-file "${docker_env_file}" \
        --env APP_WORKER_COUNT=1 "${docker_image}" >"${workspace}/receipts/docker-container-id.log"
    local attempt
    for attempt in $(seq 1 400); do
        if curl --fail --silent "http://127.0.0.1:${port}/health/live" >/dev/null 2>&1 \
            && curl --fail --silent "http://127.0.0.1:${port}/health/ready" >/dev/null 2>&1 \
            && [[ "$(docker container inspect --format '{{.State.Health.Status}}' "${docker_container}")" == healthy ]]; then
            break
        fi
        sleep 0.1
    done
    curl --fail --silent "http://127.0.0.1:${port}/health/live" >/dev/null || fail 'Docker liveness failed'
    curl --fail --silent "http://127.0.0.1:${port}/health/ready" >/dev/null || fail 'Docker readiness failed'
    [[ "$(docker exec "${docker_container}" id -u)" == 10001 ]] || fail 'Docker runtime did not use the app user'
    docker top "${docker_container}" -eo pid,args >"${workspace}/receipts/docker-processes.log" 2>&1
    [[ "$(rg -c 'uvicorn .*app\.main:create_app.*--workers 1' "${workspace}/receipts/docker-processes.log")" == 1 ]] \
        || fail 'Docker runtime did not retain exactly one Uvicorn worker'
    docker stop --time 10 "${docker_container}" >/dev/null || fail 'Docker SIGTERM shutdown failed'
    docker logs "${docker_container}" >"${workspace}/receipts/docker.jsonl" 2>&1
    (cd "${clone_root}" && "${uv_command}" run python - "${workspace}/receipts/docker.jsonl" <<'PY'
import json
import sys

records = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
if not records:
    raise SystemExit("Docker runtime emitted no JSON Lines")
events = [record.get("event") for record in records]
for event in ("application.starting", "application.started", "application.stopping", "application.stopped"):
    if events.count(event) != 1:
        raise SystemExit("Docker application lifecycle evidence is not exactly once")
refresher_events = (
    "bookmark_stats.refresher_starting",
    "bookmark_stats.refresher_started",
    "bookmark_stats.refresher_stopping",
    "bookmark_stats.refresher_stopped",
)
if any(event in events for event in refresher_events):
    if any(events.count(event) != 1 for event in refresher_events):
        raise SystemExit("Docker refresher lifecycle evidence is incomplete")
for record in records:
    if not {"source", "event", "timestamp", "process_id", "thread_id"} <= record.keys():
        raise SystemExit("Docker JSON Lines schema is incomplete")
print("Docker JSON Lines schema and shutdown lifecycle audit passed")
PY
    )
    docker rm "${docker_container}" >/dev/null || fail 'Docker container removal failed after SIGTERM'
    wait_for_docker_removal "${docker_container}" 'runtime container'
    ! docker container inspect "${docker_container}" >/dev/null 2>&1 || fail 'Docker container remained after SIGTERM'
    docker_container=""
    docker_env_file=""
    safe_message 'receipt: command=docker build/run migrate-only + non-root one-worker health/JSON Lines/SIGTERM/removal; exit=0'
}

run_cleanup_self_test() {
    local probe_root
    local child_status=0
    probe_root="$(mktemp -d "${TMPDIR:-/private/tmp}/backend-sample-track08-selftest.XXXXXX")"
    chmod 700 "${probe_root}"
    TMPDIR="${probe_root}" TRACK08_SELF_TEST_CHILD=1 bash "${script_path}" >/dev/null 2>&1 || child_status=$?
    [[ "${child_status}" -eq 97 ]] || { rm -rf -- "${probe_root}"; fail 'cleanup self-test did not preserve the injected failure status'; }
    [[ -z "$(find "${probe_root}" -mindepth 1 -print -quit)" ]] || { rm -rf -- "${probe_root}"; fail 'cleanup self-test retained a child workspace'; }
    rmdir "${probe_root}"
    safe_message 'receipt: selector=cleanup self-test injected failure status/private workspace removal; exit=0'
}

run_self_test_child() {
    create_workspace
    sleep 60 &
    server_pid=$!
    exit 97
}

main() {
    if [[ "${TRACK08_SELF_TEST_CHILD:-0}" == 1 ]]; then
        run_self_test_child
    fi
    if [[ "${TRACK08_SELF_TEST:-0}" == 1 ]]; then
        run_cleanup_self_test
        return 0
    fi
    [[ "${development_preflight}" == 0 || "${development_preflight}" == 1 ]] \
        || fail 'TRACK08_DEVELOPMENT_PREFLIGHT must be 0 or 1'
    [[ "${skip_docker}" == 0 || "${skip_docker}" == 1 ]] || fail 'TRACK08_SKIP_DOCKER must be 0 or 1'
    require_clean_source
    create_workspace
    mkdir -p "${workspace}/receipts"
    clone_committed_source
    assert_reader_documents
    if [[ "${reader_documents_ready}" -eq 0 ]]; then
        fail 'development preflight stopped before executable evidence; reader/handoff documents remain missing'
    fi
    configure_clean_clone
    verify_upstream_evidence
    run_bonus_focus
    run_quality_and_migrations
    verify_seed
    start_server
    exercise_runtime "${runtime_port}"
    stop_server
    audit_runtime_logs
    verify_track07_absence
    verify_hygiene
    verify_docker
    if [[ "${development_preflight}" == 1 || "${skip_docker}" == 1 ]]; then
        fail 'development seam was used; this is not a final Track 08 receipt'
    fi
    safe_message 'FINAL PASS: clean-clone Track 08 evidence complete; no external action was performed'
}

main "$@"
