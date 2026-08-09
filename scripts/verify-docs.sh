#!/usr/bin/env bash
# Documentation-only verifier; it does not exercise product runtime behavior.
set -Eeuo pipefail
IFS=$'\n\t'

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "${script_dir}/.." && pwd -P)"
report_helper="${script_dir}/verification-report.sh"
[[ -r "${report_helper}" ]] || { printf 'FAIL: missing verification report helper\n' >&2; exit 1; }
# shellcheck source=verification-report.sh
source "${report_helper}"
verification_report_start 'scripts/verify-docs.sh' 'Documentation integrity verification'
verification_report_gate 'documentation inventory and durable control-plane files'
verification_report_gate 'current Markdown link and repository-path resolution'
verification_report_gate 'whitespace and Git diff hygiene'
trap 'verification_report_finish "$?" 0' EXIT
cd "${repo_root}"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

require_file() {
    [[ -f "$1" ]] || fail "missing expected file: $1"
}

for expected_file in \
    .docs/README.md \
    .docs/ASSESSMENT.md \
    .docs/DELIVERY-PLAN.md \
    .docs/SOLUTION-DESIGN.md \
    .docs/ENGINEERING-VERIFICATION-GUIDELINE.md \
    .tracks/README.md \
    .tracks/00-contract-baseline/SPEC.md \
    .tracks/00-contract-baseline/PLAN.md \
    .tracks/00-contract-baseline/HISTORY.md \
    .tracks/00-contract-baseline/TEST-REPORT.md; do
    require_file "${expected_file}"
done

require_file .tracks/ADR/ADR-001-application-stack-and-data-access.md
require_file .tracks/ADR/ADR-002-api-contract-and-timestamps.md
require_file .tracks/ADR/ADR-003-identity-and-token-security.md
require_file .tracks/ADR/ADR-004-event-driven-statistics-service.md
require_file .tracks/ADR/ADR-005-windowed-statistics-data-points.md
require_file .tracks/ADR/ADR-006-engineering-verification-and-closure-evidence.md
require_file .tracks/ADR/ADR-007-local-rate-limiting-and-cursor-pagination.md
require_file .tracks/ADR/ADR-008-pydantic-internal-models-and-lifecycle-events.md
require_file .tracks/ADR/ADR-009-track-07-weekly-projection-revival.md
require_file .tracks/07-weekly-projections/SPEC.md
require_file .tracks/07-weekly-projections/PLAN.md
require_file .tracks/07-weekly-projections/HISTORY.md
require_file .tracks/08-final-handoff/SPEC.md
require_file .tracks/08-final-handoff/PLAN.md
require_file .tracks/08-final-handoff/HISTORY.md
require_file .tracks/09-final-cleanup-docs/SPEC.md
require_file .tracks/09-final-cleanup-docs/PLAN.md
require_file .tracks/09-final-cleanup-docs/HISTORY.md

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"
}

require_command rg
require_command python3
require_command git

requirement_id_count="$(sed -n '/^## Requirement matrix$/,/^## Accepted decisions$/p' .docs/ASSESSMENT.md \
    | rg -o '^\| [A-Z]+-[0-9]{2} \|' \
    | wc -l \
    | tr -d ' ')"
[[ "${requirement_id_count}" -eq 43 ]] || fail "expected 43 requirement IDs; found ${requirement_id_count}"
unique_requirement_id_count="$(sed -n '/^## Requirement matrix$/,/^## Accepted decisions$/p' .docs/ASSESSMENT.md \
    | rg -o '^\| [A-Z]+-[0-9]{2} \|' \
    | sort -u \
    | wc -l \
    | tr -d ' ')"
[[ "${unique_requirement_id_count}" -eq 43 ]] || fail 'requirement IDs are not unique'

accepted_adr_count="$(rg -l -- '- Status: Accepted' .tracks/ADR/*.md | wc -l | tr -d ' ')"
[[ "${accepted_adr_count}" -eq 9 ]] || fail "expected 9 accepted ADRs; found ${accepted_adr_count}"

rg -q 'ADR-006-engineering-verification-and-closure-evidence\.md' .docs/README.md \
    || fail 'docs index does not link ADR-006'
rg -q 'ADR-006-engineering-verification-and-closure-evidence\.md' .tracks/README.md \
    || fail 'track index does not link ADR-006'
rg -q 'ADR-007-local-rate-limiting-and-cursor-pagination\.md' .docs/README.md \
    || fail 'docs index does not link ADR-007'
rg -q 'ADR-007-local-rate-limiting-and-cursor-pagination\.md' .tracks/README.md \
    || fail 'track index does not link ADR-007'
rg -q 'ADR-008-pydantic-internal-models-and-lifecycle-events\.md' .docs/README.md \
    || fail 'docs index does not link ADR-008'
rg -q 'ADR-008-pydantic-internal-models-and-lifecycle-events\.md' .tracks/README.md \
    || fail 'track index does not link ADR-008'
rg -q 'ADR-009-track-07-weekly-projection-revival\.md' .docs/README.md \
    || fail 'docs index does not link ADR-009'
rg -q 'ADR-009-track-07-weekly-projection-revival\.md' .tracks/README.md \
    || fail 'track index does not link ADR-009'

python3 - <<'PY'
from pathlib import Path
import re
import sys

expected_documents = frozenset(
    {
        "AI-ASSISTED-WORK.md",
        "ASSESSMENT.md",
        "DELIVERY-PLAN.md",
        "ENGINEERING-VERIFICATION-GUIDELINE.md",
        "README.md",
        "RELEASE-HANDOFF.md",
        "SOLUTION-DESIGN.md",
        "Technical Assessment Senior Software_Engineer.pdf",
        "WALKTHROUGH.md",
    }
)
docs_root = Path(".docs")
if not docs_root.is_dir() or docs_root.is_symlink():
    print(".docs must be a real documentation directory", file=sys.stderr)
    raise SystemExit(1)
if Path("docs").exists() or Path("docs").is_symlink():
    print("docs compatibility directory or symlink must not exist", file=sys.stderr)
    raise SystemExit(1)
actual_documents = frozenset(path.name for path in docs_root.iterdir() if path.is_file())
if actual_documents != expected_documents:
    print(
        f".docs inventory mismatch: expected={sorted(expected_documents)} actual={sorted(actual_documents)}",
        file=sys.stderr,
    )
    raise SystemExit(1)

# These historical Track 00 receipts record commands that actually ran before the
# migration.  Keeping only these exact filename literals preserves that evidence;
# every current repository-document path must use .docs/.  FastAPI's /docs route is
# not matched because it is an HTTP endpoint, not a repository-document filename.
historical_literal_docs_paths = frozenset(
    {
        (".tracks/00-contract-baseline/TEST-REPORT.md", "docs/ASSESSMENT.md"),
        (".tracks/00-contract-baseline/TEST-REPORT.md", "docs/DELIVERY-PLAN.md"),
    }
)
document_names = "|".join(re.escape(name) for name in sorted(expected_documents))
stale_path_pattern = re.compile(rf"(?<![.A-Za-z0-9_-])docs/({document_names})")
bad = []
for source in (Path("README.md"), Path(".dockerignore"), Path(".docs"), Path(".tracks"), Path("scripts/verify-track-08.sh"), Path("tests/contract/test_track08_harness_contract.py")):
    paths = (source,) if source.is_file() else source.rglob("*.md")
    for path in paths:
        for match in stale_path_pattern.finditer(path.read_text(encoding="utf-8")):
            receipt = (path.as_posix(), match.group(0))
            if receipt not in historical_literal_docs_paths:
                bad.append(f"{path}: stale repository path {match.group(0)}")
if bad:
    print("\n".join(bad), file=sys.stderr)
    raise SystemExit(1)
PY

track_dir_count="$(find .tracks -mindepth 1 -maxdepth 1 -type d -name '[0-9][0-9]-*' -print | wc -l | tr -d ' ')"
[[ "${track_dir_count}" -eq 10 ]] || fail "expected 10 track directories; found ${track_dir_count}"

track07_spec_status="$(sed -n 's/^- Status: \*\*\(.*\)\*\*$/\1/p' .tracks/07-weekly-projections/SPEC.md)"
track07_plan_status="$(sed -n 's/^- Status: \*\*\(.*\)\*\*$/\1/p' .tracks/07-weekly-projections/PLAN.md)"
[[ "${track07_spec_status}" == "${track07_plan_status}" ]] \
    || fail 'Track 07 specification and plan statuses disagree'
case "${track07_spec_status}" in
    "In progress")
        [[ ! -e .tracks/07-weekly-projections/TEST-REPORT.md ]] \
            || fail 'Track 07 In progress must not claim closure with TEST-REPORT.md'
        [[ ! -e scripts/verify-track-07.sh || -x scripts/verify-track-07.sh ]] \
            || fail 'an in-progress Track 07 harness must be executable'
        ;;
    "Complete")
        require_file .tracks/07-weekly-projections/TEST-REPORT.md
        require_file scripts/verify-track-07.sh
        ;;
    *)
        fail "unexpected Track 07 status: ${track07_spec_status}"
        ;;
esac
rg -q 'ADR-009' .tracks/07-weekly-projections/SPEC.md \
    || fail 'Track 07 specification does not govern the revival through ADR-009'
rg -q 'STATS_PROJECTION_ENABLED' .tracks/07-weekly-projections/SPEC.md \
    || fail 'Track 07 specification does not record projection disable semantics'
rg -q 'mismatch fails projection readiness' .tracks/ADR/ADR-009-track-07-weekly-projection-revival.md \
    || fail 'ADR-009 does not record calculation-version mismatch readiness semantics'
for required_bonus in 'seed data' 'Docker' 'rate limiting' 'cursor pagination'; do
    rg -qi "${required_bonus}" .tracks/08-final-handoff/SPEC.md \
        || fail "Track 08 specification is missing required bonus: ${required_bonus}"
    rg -qi "${required_bonus}" .tracks/08-final-handoff/PLAN.md \
        || fail "Track 08 plan is missing required bonus: ${required_bonus}"
done

python3 - <<'PY'
from pathlib import Path
from urllib.parse import unquote
import re
import sys

roots = (Path('README.md'), Path('.docs'), Path('.tracks'))
link_pattern = re.compile(r'!?\[[^\]]*\]\(([^)]+)\)')
bad = []
for root in roots:
    paths = (root,) if root.is_file() else root.rglob('*.md')
    for path in paths:
        text = path.read_text(encoding='utf-8')
        for target in link_pattern.findall(text):
            target = target.strip()
            if target.startswith(('#', 'http://', 'https://', 'mailto:')):
                continue
            target_path = target.split('#', 1)[0]
            if not target_path:
                continue
            decoded_target = unquote(target_path)
            if not (path.parent / decoded_target).exists():
                bad.append(f'{path}: {target}')
if bad:
    print('\n'.join(bad), file=sys.stderr)
    raise SystemExit(1)
PY

if rg -n '[[:blank:]]$' README.md .docs .tracks; then
    fail 'trailing whitespace found'
fi

python3 - <<'PY'
from pathlib import Path

roots = (Path("README.md"), Path(".docs"), Path(".tracks"))
paths = []
for root in roots:
    paths.extend((root,) if root.is_file() else root.rglob("*.md"))
bad = []
for path in paths:
    contents = path.read_bytes()
    if not contents.endswith(b"\n") or contents.endswith(b"\n\n"):
        bad.append(str(path))
if bad:
    print("Markdown files must end with exactly one newline:", *bad, sep="\n")
    raise SystemExit(1)
PY

git diff --check
verification_report_summary '43 requirement IDs, 9 accepted ADRs, and 10 tracks verified'
printf 'PASS: documentation-only verification (43 requirement IDs, 9 accepted ADRs, 10 tracks).\n'
