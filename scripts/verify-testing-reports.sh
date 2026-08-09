#!/usr/bin/env bash
# Verify the committed public receipts without replaying their expensive commands.
# The receipt bundle is evidence, so its inventory, provenance, and hashes are
# treated as a strict data contract rather than best-effort documentation.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
source_root="$(cd -- "${script_dir}/.." && pwd -P)"
report_dir="${VERIFY_TESTING_REPORTS_DIR:-${source_root}/.testing_report}"
report_helper="${script_dir}/verification-report.sh"
report_dir_override="${VERIFY_TESTING_REPORTS_DIR:-}"

[[ -r "${report_helper}" ]] || { printf 'FAIL: report verifier missing verification report helper\n' >&2; exit 1; }
# shellcheck source=verification-report.sh
source "${report_helper}"
verification_report_start 'scripts/verify-testing-reports.sh' 'Committed testing-report bundle verification'
verification_report_gate 'exact receipt inventory, manifest structure, and SHA-256 integrity'
verification_report_gate 'captured-source provenance and executable/owner-skip dispositions'
verification_report_gate 'public-safety scan for logs, credentials, tokens, and absolute local paths'
trap 'verification_report_finish "$?" 0' EXIT

expected_files=(
    '00-contract-baseline.txt'
    '01-foundation.txt'
    '02-auth-errors.txt'
    '03-bookmark-crud.txt'
    '04-search-stats.txt'
    '05-mandatory-quality-gate.txt'
    '06-event-driven-stats.txt'
    '07-weekly-projections-skipped.txt'
    '08-final-handoff.txt'
    '09-final-cleanup-docs.txt'
)
expected_commands=(
    'bash scripts/verify-docs.sh'
    'bash scripts/verify-track-01.sh'
    'bash scripts/verify-track-02.sh'
    'bash scripts/verify-track-03.sh'
    'bash scripts/verify-track-04.sh'
    'bash scripts/verify-track-05.sh'
    'bash scripts/verify-track-06.sh'
    'none'
    'bash scripts/verify-track-08.sh'
    'bash scripts/verify-track-09.sh'
)

fail() {
    printf 'FAIL: testing-report bundle %s\n' "$*" >&2
    exit 1
}

require_exact_count() {
    local pattern="$1"
    local expected="$2"
    local receipt="$3"
    local actual
    actual="$(rg -N --count-matches -- "${pattern}" "${receipt}" || true)"
    actual="${actual:-0}"
    [[ "${actual}" == "${expected}" ]] || fail "${receipt##*/} must contain ${expected} match(es) for ${pattern}; found ${actual}"
}

validate_manifest() {
    local manifest="${report_dir}/MANIFEST.md"
    local line_count line capture_line algorithm_line table_header separator row index expected_file row_file row_hash

    [[ -f "${manifest}" ]] || fail 'MANIFEST.md is missing'
    [[ "$(wc -l < "${manifest}" | tr -d '[:space:]')" -ge 15 ]] || fail 'MANIFEST.md must contain the 15-line checksum contract'
    [[ "$(sed -n '1p' "${manifest}")" == '# Verification report manifest' ]] || fail 'MANIFEST.md title is invalid'
    capture_line="$(sed -n '2p' "${manifest}")"
    algorithm_line="$(sed -n '3p' "${manifest}")"
    [[ "${capture_line}" =~ ^-\ Capture\ source\ HEAD:\ \`([0-9a-f]{40})\`$ ]] || fail 'MANIFEST.md capture source HEAD syntax is invalid'
    manifest_head="${BASH_REMATCH[1]}"
    [[ "${algorithm_line}" == '- Hash algorithm: `SHA-256`' ]] || fail 'MANIFEST.md must declare SHA-256'
    [[ "$(sed -n '4p' "${manifest}")" == '| Receipt | SHA-256 |' ]] || fail 'MANIFEST.md checksum table header is invalid'
    [[ "$(sed -n '5p' "${manifest}")" == '| --- | --- |' ]] || fail 'MANIFEST.md checksum table separator is invalid'
    ! sed -n '16,$p' "${manifest}" | rg -q '^\|' \
        || fail 'MANIFEST.md must not contain checksum-table rows beyond the ten receipts'

    for index in "${!expected_files[@]}"; do
        expected_file="${expected_files[${index}]}"
        row="$(sed -n "$((index + 6))p" "${manifest}")"
        [[ "${row}" =~ ^\|\ \`([^\`]+)\`\ \|\ \`([0-9a-f]{64})\`\ \|$ ]] \
            || fail "MANIFEST.md checksum row for ${expected_file} is invalid"
        row_file="${BASH_REMATCH[1]}"
        row_hash="${BASH_REMATCH[2]}"
        [[ "${row_file}" == "${expected_file}" ]] || fail "MANIFEST.md inventory order/name mismatch: expected ${expected_file}, found ${row_file}"
        manifest_hashes[${index}]="${row_hash}"
    done
}

validate_inventory_and_hashes() {
    local expected_set actual_file index expected_file actual_hash
    local tracked_files=()

    [[ -d "${report_dir}" ]] || fail 'testing-report directory is missing'
    while IFS= read -r actual_file; do
        tracked_files+=("${actual_file##*/}")
    done < <(find "${report_dir}" -maxdepth 1 -type f -print | LC_ALL=C sort)
    [[ "${#tracked_files[@]}" -eq 11 ]] || fail 'testing-report directory must contain exactly ten .txt receipts and MANIFEST.md'
    for index in "${!expected_files[@]}"; do
        expected_file="${expected_files[${index}]}"
        [[ "${tracked_files[${index}]:-}" == "${expected_file}" ]] || fail "receipt inventory mismatch at position ${index}: expected ${expected_file}"
    done
    [[ "${tracked_files[10]:-}" == 'MANIFEST.md' ]] || fail 'testing-report directory must include only MANIFEST.md after the ten receipts'

    for index in "${!expected_files[@]}"; do
        expected_file="${expected_files[${index}]}"
        actual_hash="$(shasum -a 256 "${report_dir}/${expected_file}" | awk '{print $1}')"
        [[ "${actual_hash}" == "${manifest_hashes[${index}]}" ]] \
            || fail "SHA-256 mismatch for ${expected_file}"
    done
}

validate_tracking() {
    local expected_file

    if [[ -n "${report_dir_override}" ]]; then
        [[ "${VERIFY_TESTING_REPORTS_TEST_SEAM:-0}" == 1 ]] \
            || fail 'VERIFY_TESTING_REPORTS_DIR is reserved for the explicit test seam'
        return 0
    fi
    for expected_file in MANIFEST.md "${expected_files[@]}"; do
        git -C "${source_root}" ls-files --error-unmatch ".testing_report/${expected_file}" \
            >/dev/null 2>&1 || fail ".testing_report/${expected_file} is not tracked"
        git -C "${source_root}" cat-file -e "HEAD:.testing_report/${expected_file}" \
            2>/dev/null || fail ".testing_report/${expected_file} is not committed at HEAD"
        git -C "${source_root}" diff --quiet HEAD -- ".testing_report/${expected_file}" \
            || fail ".testing_report/${expected_file} differs from committed HEAD"
    done
}

validate_provenance_and_dispositions() {
    local source_head index receipt expected_command

    command -v git >/dev/null 2>&1 || fail 'git is unavailable for provenance verification'
    git -C "${source_root}" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
        || fail 'source root is not a Git worktree'
    git -C "${source_root}" cat-file -e "${manifest_head}^{commit}" 2>/dev/null \
        || fail "captured source commit ${manifest_head} does not resolve"
    source_head="$(git -C "${source_root}" rev-parse HEAD)"
    git -C "${source_root}" merge-base --is-ancestor "${manifest_head}" "${source_head}" \
        || fail "captured source commit ${manifest_head} is not an ancestor of HEAD ${source_head}"

    for index in "${!expected_files[@]}"; do
        receipt="${report_dir}/${expected_files[${index}]}"
        expected_command="${expected_commands[${index}]}"
        require_exact_count "^SOURCE_HEAD: ${manifest_head}$" 1 "${receipt}"
        require_exact_count '^SOURCE_HEAD:' 1 "${receipt}"
        require_exact_count "^COMMAND: ${expected_command}$" 1 "${receipt}"
        require_exact_count '^COMMAND:' 1 "${receipt}"
        if [[ "${expected_command}" == 'none' ]]; then
            require_exact_count '^DISPOSITION: SKIPPED \(owner decision\)$' 1 "${receipt}"
            require_exact_count '^RESULT: PASS$' 0 "${receipt}"
            require_exact_count '^EXIT: not applicable$' 1 "${receipt}"
        else
            require_exact_count '^RESULT: PASS$' 1 "${receipt}"
            require_exact_count '^EXIT: 0$' 1 "${receipt}"
        fi
    done
}

validate_public_safety() {
    local safety_targets=("${report_dir}/MANIFEST.md" "${report_dir}"/*.txt)

    ! find "${report_dir}" -maxdepth 1 -type f -name '*.log' -print -quit | grep -q . \
        || fail 'runtime .log files are forbidden from the public testing-report bundle'
    ! rg -n -i -e '/(Users|private)(/|$)' "${safety_targets[@]}" \
        || fail 'absolute local /Users or /private path leaked into the public testing-report bundle'
    ! rg -n -e '(-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})' "${safety_targets[@]}" \
        || fail 'private-key or known token pattern leaked into the public testing-report bundle'
    ! rg -n -i -e '(token|secret|api[_-]?key)[[:space:]]*[:=][[:space:]]*[^[:space:]]{16,}' "${safety_targets[@]}" \
        || fail 'token-like assignment leaked into the public testing-report bundle'
}

main() {
    declare -a manifest_hashes
    validate_manifest
    validate_inventory_and_hashes
    validate_tracking
    validate_provenance_and_dispositions
    validate_public_safety
    verification_report_summary 'ten receipts, SHA-256 manifest, provenance, dispositions, and public-safety scan verified'
    printf '%s\n' 'PASS: committed testing-report bundle is complete, tamper-evident, and safe to retain'
}

main "$@"
