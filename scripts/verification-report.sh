#!/usr/bin/env bash
# Shared, non-interactive terminal receipt formatting for verification harnesses.
# Callers retain ownership of exit status and cleanup; this file never executes a
# command supplied by a caller or prints captured command output.

verification_report_start() {
    local script_identity="$1"
    local title="$2"
    VERIFY_REPORT_INCOMPLETE=0
    VERIFY_REPORT_CLEANUP_EMITTED=0
    printf '%s\n' '=== Verification report ==='
    printf 'SCRIPT: %s\n' "${script_identity}"
    printf 'TITLE: %s\n' "${title}"
    printf 'START: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
}

verification_report_gate() {
    printf 'GATE: %s\n' "$1"
}

verification_report_summary() {
    printf 'SUMMARY: %s\n' "$1"
}

verification_report_incomplete() {
    VERIFY_REPORT_INCOMPLETE=1
    printf 'STATUS: INCOMPLETE — %s\n' "$1"
}

verification_report_cleanup() {
    local cleanup_status="$1"
    local detail="$2"
    VERIFY_REPORT_CLEANUP_EMITTED=1
    if [[ "${cleanup_status}" -eq 0 ]]; then
        printf 'CLEANUP: PASS — %s\n' "${detail}"
    else
        printf 'CLEANUP: FAIL — %s\n' "${detail}" >&2
    fi
}

verification_report_finish() {
    local command_status="$1"
    local cleanup_status="${2:-0}"
    if [[ "${VERIFY_REPORT_CLEANUP_EMITTED:-0}" -eq 0 ]]; then
        verification_report_cleanup "${cleanup_status}" 'no disposable resources were created'
    fi
    if [[ "${cleanup_status}" -ne 0 ]]; then
        printf 'RESULT: FAIL (cleanup exit=%s)\n' "${cleanup_status}" >&2
    elif [[ "${VERIFY_REPORT_INCOMPLETE:-0}" -eq 1 ]]; then
        printf 'RESULT: INCOMPLETE (exit=%s)\n' "${command_status}" >&2
    elif [[ "${command_status}" -ne 0 ]]; then
        printf 'RESULT: FAIL (exit=%s)\n' "${command_status}" >&2
    else
        printf '%s\n' 'RESULT: PASS'
    fi
}
