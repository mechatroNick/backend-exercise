#!/usr/bin/env bash
# Track 09 clean-source closure.  Captured receipts stay private in the disposable
# workspace; terminal output is limited to safe gate names and summaries.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
source_root="$(cd -- "${script_dir}/.." && pwd -P)"
report_helper="${script_dir}/verification-report.sh"
[[ -r "${report_helper}" ]] || { printf 'FAIL: Track 09 missing verification report helper\n' >&2; exit 1; }
# shellcheck source=verification-report.sh
source "${report_helper}"
verification_report_start 'scripts/verify-track-09.sh' 'Track 09 final clean-source verification'
verification_report_gate 'clean committed source, locked sync, and dependency advisory'
verification_report_gate 'dataclass, lifecycle, lifespan, and type-source contracts'
verification_report_gate 'Ruff, mypy, Pyright, warnings, full branch coverage, and migrations'
verification_report_gate 'documentation, runtime/inherited evidence, security, hygiene, Docker, and cleanup'

uv_command="${UV:-uv}"
development_static="${TRACK09_DEVELOPMENT_STATIC:-0}"
workspace=""
clone_root=""

fail() {
    printf 'FAIL: Track 09 %s\n' "$*" >&2
    exit 1
}

is_verified_workspace() {
    [[ -n "${workspace}" && -d "${workspace}" ]] || return 1
    [[ "$(basename -- "${workspace}")" == backend-sample-track09.* ]] || return 1
    [[ "${workspace}" != / && "${workspace}" != "${source_root}" ]] || return 1
}

cleanup() {
    local original_status=$?
    local cleanup_status=0
    trap - EXIT
    if [[ -n "${workspace}" ]]; then
        if is_verified_workspace; then
            rm -rf -- "${workspace}" || cleanup_status=1
            [[ ! -e "${workspace}" ]] || cleanup_status=1
        else
            printf 'FAIL: Track 09 refused to remove an unverified workspace\n' >&2
            cleanup_status=1
        fi
    fi
    verification_report_cleanup "${cleanup_status}" 'verified clean clone, private receipts, and disposable workspace removal'
    if [[ "${original_status}" -ne 0 ]]; then
        verification_report_finish "${original_status}" "${cleanup_status}"
        exit "${original_status}"
    fi
    verification_report_finish 0 "${cleanup_status}"
    exit "${cleanup_status}"
}
trap cleanup EXIT

create_workspace() {
    local temporary_base="${TMPDIR:-/private/tmp}"
    workspace="$(mktemp -d "${temporary_base%/}/backend-sample-track09.XXXXXX")"
    is_verified_workspace || fail 'mktemp returned an unsafe workspace path'
    chmod 700 "${workspace}"
    mkdir -p "${workspace}/receipts"
}

run_private() {
    local name="$1"
    shift
    local receipt="${workspace}/receipts/${name}.log"
    if "$@" >"${receipt}" 2>&1; then
        printf 'RECEIPT: %s; exit=0\n' "${name}"
    else
        local command_status=$?
        printf 'FAIL: Track 09 gate %s failed; private receipt retained only until cleanup\n' "${name}" >&2
        return "${command_status}"
    fi
}

require_clean_source() {
    [[ -d "${source_root}/.git" ]] || fail 'must run from a Git working tree'
    [[ -z "$(git -C "${source_root}" status --porcelain=v1 --untracked-files=all)" ]] \
        || fail 'source working tree is dirty or has untracked files'
    git -C "${source_root}" diff --check
}

clone_committed_source() {
    clone_root="${workspace}/source"
    git -C "${source_root}" clone --no-local --no-hardlinks "${source_root}" "${clone_root}" \
        >"${workspace}/receipts/clone.log" 2>&1 || fail 'clean clone creation failed'
    [[ "$(git -C "${clone_root}" rev-parse HEAD)" == "$(git -C "${source_root}" rev-parse HEAD)" ]] \
        || fail 'clean clone HEAD differs from reviewed source HEAD'
    [[ -z "$(git -C "${clone_root}" status --porcelain=v1 --untracked-files=all)" ]] \
        || fail 'clean clone is dirty after creation'
}

configure_clone() {
    command -v "${uv_command}" >/dev/null 2>&1 || fail 'uv is unavailable'
    export UV_CACHE_DIR="${workspace}/uv-cache"
    export UV_PYTHON_INSTALL_DIR="${workspace}/python-install"
    (cd "${clone_root}" && run_private lock-check "${uv_command}" lock --check)
    (cd "${clone_root}" && run_private locked-sync "${uv_command}" sync --locked)
    (cd "${clone_root}" && run_private dependency-audit "${uv_command}" run pip-audit --local --progress-spinner off --desc off)
    rg -q 'No known vulnerabilities found' "${workspace}/receipts/dependency-audit.log" \
        || fail 'pip-audit did not confirm that no known vulnerabilities were found'
}

verify_source_contracts() {
    (cd "${clone_root}" && run_private no-dataclasses bash -c "! rg -n 'from dataclasses import|import dataclasses|@dataclass' app tests")
    (cd "${clone_root}" && run_private lifecycle-source bash -c "rg -q 'ApplicationLifecycleEvent' app && rg -q 'application.starting' app")
    (cd "${clone_root}" && run_private lifespan-source bash -c "rg -q '@asynccontextmanager' app && rg -q 'lifespan=' app")
    (cd "${clone_root}" && run_private pyright-locked bash -c \
        "rg -q '\"pyright\\[nodejs\\]==1\\.1\\.411\"' pyproject.toml && \
         rg -q '^\\[tool\\.pyright\\]$' pyproject.toml && \
         rg -q 'name = \"pyright\"' uv.lock")
}

verify_quality_and_migrations() {
    local database_path="${workspace}/track09.sqlite3"
    export APP_ENV=test
    export DATABASE_URL="sqlite:///${database_path}"
    export JWT_SECRET="$(cd "${clone_root}" && "${uv_command}" run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
    (cd "${clone_root}" && run_private ruff-format "${uv_command}" run ruff format --check .)
    (cd "${clone_root}" && run_private ruff-check "${uv_command}" run ruff check .)
    (cd "${clone_root}" && run_private typecheck make typecheck)
    (cd "${clone_root}" && run_private warning-tests "${uv_command}" run pytest -q \
        -W 'error::DeprecationWarning' \
        -W 'error::starlette.exceptions.StarletteDeprecationWarning')
    (cd "${clone_root}" && run_private coverage-run "${uv_command}" run coverage run --branch -m pytest -q)
    (cd "${clone_root}" && run_private coverage-report "${uv_command}" run coverage report --fail-under=100)
    (cd "${clone_root}" && run_private alembic-upgrade "${uv_command}" run alembic upgrade head)
    (cd "${clone_root}" && run_private alembic-downgrade "${uv_command}" run alembic downgrade base)
    (cd "${clone_root}" && run_private alembic-reupgrade "${uv_command}" run alembic upgrade head)
    (cd "${clone_root}" && run_private alembic-check "${uv_command}" run alembic check)
    rg -q '^TOTAL.*100%' "${workspace}/receipts/coverage-report.log" \
        || fail 'coverage report did not report 100 percent'
}

verify_documentation_and_hygiene() {
    (cd "${clone_root}" && run_private verify-docs bash scripts/verify-docs.sh)
    (cd "${clone_root}" && run_private hygiene bash -c '
        git diff --check
        ! git ls-files | rg -q "(^|/)(\\.coverage|.*\\.(db|sqlite|sqlite3|log|pem|key)|__pycache__|\\.pytest_cache|\\.mypy_cache|\\.ruff_cache)(/|$)"
        ! git grep -I -q -E "(-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})"
        test -z "$(git status --porcelain=v1 --untracked-files=all)"
    ')
}

verify_inherited_final_gate() {
    # Track 08 contains the literal exact Track 01--06 invocations and Docker path;
    # this final gate must execute it rather than replacing it with equivalent tests.
    (cd "${clone_root}" && run_private verify-track-08 bash scripts/verify-track-08.sh)
}

verify_final_clone_cleanliness() {
    [[ -z "$(git -C "${clone_root}" status --porcelain=v1 --untracked-files=all)" ]] \
        || fail 'clean clone changed during final verification'
    git -C "${clone_root}" diff --check
    printf 'RECEIPT: final-clone-cleanliness; exit=0\n'
}

run_cleanup_self_test() {
    local probe_root
    local child_status=0
    probe_root="$(mktemp -d "${TMPDIR:-/private/tmp}/backend-sample-track09-selftest.XXXXXX")"
    chmod 700 "${probe_root}"
    TMPDIR="${probe_root}" TRACK09_SELF_TEST_CHILD=1 bash "${script_dir}/verify-track-09.sh" >/dev/null 2>&1 || child_status=$?
    [[ "${child_status}" -eq 97 ]] || { rm -rf -- "${probe_root}"; fail 'cleanup self-test did not preserve the injected failure status'; }
    [[ -z "$(find "${probe_root}" -mindepth 1 -print -quit)" ]] || { rm -rf -- "${probe_root}"; fail 'cleanup self-test retained a private workspace'; }
    rmdir "${probe_root}"
    printf 'RECEIPT: cleanup-self-test; exit=0\n'
}

main() {
    if [[ "${TRACK09_SELF_TEST_CHILD:-0}" == 1 ]]; then
        create_workspace
        exit 97
    fi
    if [[ "${TRACK09_SELF_TEST:-0}" == 1 ]]; then
        run_cleanup_self_test
        verification_report_summary 'injected failure preserved its nonzero exit and removed its private workspace'
        return 0
    fi
    [[ "${development_static}" == 0 || "${development_static}" == 1 ]] \
        || fail 'TRACK09_DEVELOPMENT_STATIC must be 0 or 1'
    if [[ "${development_static}" == 1 ]]; then
        verification_report_incomplete 'development static seam does not provide clean-source, runtime, or Docker evidence'
        create_workspace
        run_private static-shell-syntax bash -n "${script_dir}/verify-track-09.sh"
        return 86
    fi
    require_clean_source
    create_workspace
    clone_committed_source
    configure_clone
    verify_source_contracts
    verify_quality_and_migrations
    verify_documentation_and_hygiene
    run_cleanup_self_test
    verify_inherited_final_gate
    verify_final_clone_cleanliness
    verification_report_summary 'clean-source type, warning, coverage, migration, documentation, hygiene, inherited Track 08, Docker, and cleanup evidence completed'
    printf '%s\n' 'FINAL PASS: clean-source Track 09 evidence complete; no external action was performed'
}

main "$@"
