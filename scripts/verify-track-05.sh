#!/usr/bin/env bash
# Track 05 mandatory-core closure. Private inputs exist only in the Python helper memory.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
report_helper="${root}/scripts/verification-report.sh"
[[ -r "${report_helper}" ]] || { printf 'FAIL: missing verification report helper\n' >&2; exit 1; }
# shellcheck source=verification-report.sh
source "${report_helper}"
verification_report_start 'scripts/verify-track-05.sh' 'Track 05 mandatory quality-gate verification'
verification_report_gate 'exact inherited Track 01--04 real-process gates'
verification_report_gate 'mandatory contract collection and 100 percent branch coverage'
verification_report_gate 'live mandatory API, logging, and cleanup evidence'
uv="${UV:-uv}"
prefix="${TMPDIR:-/tmp}/backend-sample-track05."
work=""
database_path=""
log_path=""
pid="" port=""

fail() { printf 'Track 05 harness failure: %s\n' "$1" >&2; exit 1; }
descendants() { local parent=$1 child; while IFS= read -r child; do [[ -n "$child" ]] || continue; descendants "$child"; printf '%s\n' "$child"; done < <(pgrep -P "$parent" 2>/dev/null || true); }
stop_server() {
  local target status=0; local -a targets=()
  [[ -n "$pid" ]] || return 0
  while IFS= read -r target; do targets+=("$target"); done < <(descendants "$pid")
  targets+=("$pid"); for target in "${targets[@]}"; do kill -TERM "$target" 2>/dev/null || true; done
  for _ in {1..50}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
  for target in "${targets[@]}"; do kill -0 "$target" 2>/dev/null && kill -KILL "$target" 2>/dev/null || true; done
  wait "$pid" 2>/dev/null || status=$?; [[ "$status" == 0 || "$status" == 143 || "$status" == 137 ]] || return 1
  for target in "${targets[@]}"; do kill -0 "$target" 2>/dev/null && return 1; done
  pid=""
}
cleanup() {
  local original=$? status=0
  trap - EXIT
  stop_server || status=1
  if [[ -d "$work" && "$work" == "${prefix}"* ]]; then
    rm -rf -- "$work" || status=1
    [[ ! -e "$work" ]] || status=1
  else
    status=1
  fi
  [[ "$status" == 0 ]] && printf 'Track 05 cleanup: removed verified protected artifacts\n'
  verification_report_cleanup "${status}" 'verified protected artifacts and process removal'
  if [[ "$original" != 0 ]]; then
    verification_report_finish "${original}" "${status}"
    exit "$original"
  fi
  verification_report_finish 0 "${status}"
  exit "$status"
}
trap cleanup EXIT

work="$(mktemp -d "${prefix}XXXXXX")"
database_path="${work}/track05.sqlite3"
log_path="${work}/bootstrap.jsonl"

if [[ "${TRACK05_SELF_TEST:-0}" == "1" ]]; then
  printf 'private cleanup sentinel' >"${work}/self-test-secret"
  ( exit 42 ) &
  pid="$!"
  sleep 0.1
  exit 97
fi

cd "$root"; [[ -d .git && -f Makefile ]] || fail 'wrong repository root'; chmod 700 "$work"
export DATABASE_URL="sqlite:///${database_path}" APP_ENV=test STATS_REFRESH_ENABLED=false
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/backend-sample-uv-cache}" UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/private/tmp/backend-sample-python}"
export JWT_SECRET="$("$uv" run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export COVERAGE_FILE="${work}/.coverage"
cleanup_probe="${work}/cleanup-probe"
mkdir -m 700 "${cleanup_probe}"
cleanup_probe_status=0
TMPDIR="${cleanup_probe}" TRACK05_SELF_TEST=1 bash "$0" >"${work}/cleanup-self-test.receipt" 2>&1 || cleanup_probe_status=$?
[[ "${cleanup_probe_status}" == 97 ]] || fail 'cleanup self-test did not preserve the original failure status'
[[ -z "$(find "${cleanup_probe}" -mindepth 1 -print -quit)" ]] || fail 'cleanup self-test retained a private workspace'
printf 'Track 05 cleanup self-test: unexpected child status preserved and private workspace removed\n'
port="$("$uv" run python - <<'PY'
import socket
with socket.socket() as s:
    s.bind(('127.0.0.1', 0)); print(s.getsockname()[1])
PY
)"

for track in 01 02 03 04; do
  if bash "scripts/verify-track-${track}.sh" >"${work}/upstream-${track}.receipt" 2>&1; then printf 'Track 05 upstream selector scripts/verify-track-%s.sh: passed\n' "$track"; else fail "upstream Track ${track} failed"; fi
done
mandatory=(tests/contract/test_runtime_contract.py tests/contract/test_schemathesis_gets.py tests/contract/test_mandatory_gate_meta.py tests/contract/test_openapi_metadata.py tests/integration/test_bookmark_query_plans.py tests/integration/test_bookmark_search.py tests/integration/test_bookmark_stats_reader.py tests/unit/test_bookmark_stats_reader.py tests/unit/test_logging.py)
"$uv" run pytest --collect-only -q -m mandatory -p tests.contract.mandatory_gate --mandatory-gate --strict-config --strict-markers "${mandatory[@]}" >"${work}/mandatory-collect.receipt"
mandatory_count="$(rg -c '^tests/.*::' tests/contract/mandatory-nodeids.txt)"
[[ "$(rg -c '^tests/.*::' "${work}/mandatory-collect.receipt")" == "${mandatory_count}" ]] || fail 'mandatory selector count changed'
"$uv" run pytest -q -m mandatory -p tests.contract.mandatory_gate --mandatory-gate --strict-config --strict-markers "${mandatory[@]}" >"${work}/mandatory-execution.receipt"
! rg -q '[1-9][0-9]* (skipped|xfailed|xpassed|deselected)' "${work}/mandatory-execution.receipt" || fail 'mandatory execution summary contains a masked or deselected result'
printf 'Track 05 mandatory selector: %s collected and executed; query-plan, raw-SQL, and JSON Lines evidence included\n' "${mandatory_count}"
"$uv" run coverage erase
"$uv" run coverage run -m pytest -q >"${work}/coverage.receipt"
"$uv" run coverage report --fail-under=100 >>"${work}/coverage.receipt"
! rg -q '[1-9][0-9]* (skipped|xfailed|xpassed|deselected)' "${work}/coverage.receipt" || fail 'full coverage suite contains a masked or deselected result'
printf 'Track 05 coverage selector: app statement and branch coverage 100%% passed\n'

make bootstrap HOST=127.0.0.1 PORT="$port" >"$log_path" 2>&1 & pid="$!"
for _ in {1..100}; do curl --fail --silent "http://127.0.0.1:${port}/openapi.json" >/dev/null 2>&1 && break; kill -0 "$pid" 2>/dev/null || fail 'bootstrap exited before readiness'; sleep 0.1; done
kill -0 "$pid" 2>/dev/null || fail 'bootstrap was not ready'

"$uv" run python - "$port" "$log_path" "$work" <<'PY'
import datetime as dt, json, os, secrets, stat, sys, uuid
from pathlib import Path
import httpx
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

port, log_path, work = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]); base=f'http://127.0.0.1:{port}'
nonce=secrets.token_urlsafe(12); password=f'Track05-{secrets.token_urlsafe(24)}'
def user(role): return {'username':f'{role}-{nonce[:8]}','email':f'{role}-{nonce[:8]}@example.com','password':password}
def bookmark(name, tags): return {'url':f'https://example.invalid/{nonce}/{name}','title':f'Track05 {name}','description':'private input','tags':tags}
def check(response, status): assert response.status_code == status, (response.request.method, response.request.url.path, response.status_code)
def validate(api, path, method, response):
    if response.status_code == 204: assert response.content == b''; return
    assert response.headers['content-type'].startswith('application/json')
    schema=api['paths'][path][method]['responses'][str(response.status_code)]['content']['application/json']['schema']
    registry=Registry().with_resource('urn:t05', Resource.from_contents(api, default_specification=DRAFT202012))
    Draft202012Validator({'$id':'urn:t05', **api, **schema}, registry=registry).validate(response.json())
with httpx.Client(base_url=base, timeout=10) as client:
    docs=client.get('/docs'); check(docs,200); assert 'Swagger UI' in docs.text
    api=client.get('/openapi.json'); check(api,200); openapi=api.json(); assert openapi['openapi'].startswith(('3.0','3.1'))
    owner=client.post('/api/auth/register',json=user('owner')); other=client.post('/api/auth/register',json=user('other')); check(owner,201); check(other,201)
    owner_headers={'Authorization':'Bearer '+owner.json()['token']}; other_headers={'Authorization':'Bearer '+other.json()['token']}
    one=client.post('/api/bookmarks',headers=owner_headers,json=bookmark('one',['Alpha','Beta'])); two=client.post('/api/bookmarks',headers=owner_headers,json=bookmark('two',['Alpha'])); foreign=client.post('/api/bookmarks',headers=other_headers,json=bookmark('other',['Other']))
    for response in (one,two,foreign): check(response,201); validate(openapi,'/api/bookmarks','post',response)
    one_id=one.json()['id']; page=client.get('/api/bookmarks',headers=owner_headers,params={'q':'track05','page':1,'page_size':1}); detail=client.get(f'/api/bookmarks/{one_id}',headers=owner_headers); patch=client.patch(f'/api/bookmarks/{one_id}',headers=owner_headers,json={'title':'Track05 changed','tags':['Alpha']}); isolated=client.get(f'/api/bookmarks/{one_id}',headers=other_headers); stats=client.get('/api/bookmarks/stats',headers=owner_headers); deleted=client.delete(f'/api/bookmarks/{one_id}',headers=owner_headers); unauth=client.get('/api/bookmarks'); invalid=client.get('/api/bookmarks',headers=owner_headers,params={'page':0}); missing=client.get('/api/bookmarks/999999',headers=owner_headers); fault=client.get('/openapi.json',headers={'X-Track01-Harness-Fault':'1'})
    for response,status in ((page,200),(detail,200),(patch,200),(isolated,404),(stats,200),(deleted,204),(unauth,401),(invalid,422),(missing,404),(fault,500)): check(response,status)
    for path,method,response in [('/api/bookmarks','get',page),('/api/bookmarks/{bookmark_id}','get',detail),('/api/bookmarks/{bookmark_id}','patch',patch),('/api/bookmarks/{bookmark_id}','get',isolated),('/api/bookmarks/stats','get',stats),('/api/bookmarks','get',unauth),('/api/bookmarks','get',invalid),('/api/bookmarks/{bookmark_id}','get',missing)]: validate(openapi,path,method,response)
    assert page.json()['total']==2 and page.json()['page']==1 and page.json()['page_size']==1 and len(page.json()['items'])==1
    assert [tag['name'] for tag in one.json()['tags']]==['alpha','beta'] and [tag['name'] for tag in patch.json()['tags']]==['alpha']
    for response in (one, two, patch):
        body=response.json(); assert body['created_at'].endswith('Z') and body['updated_at'].endswith('Z') and body['updated_at'] >= body['created_at']
    assert stats.json()=={'total_bookmarks':2,'total_tags':1,'top_tags':[{'name':'alpha','count':2}],'bookmarks_per_month':stats.json()['bookmarks_per_month']}
    assert all(entry['count'] > 0 and entry['month'].count('-') == 1 for entry in stats.json()['bookmarks_per_month'])
    expected={'authentication_failed':unauth,'validation_error':invalid,'not_found':missing,'internal_error':fault}
    for code,response in expected.items(): assert response.json()=={'error':{'code':code,'message':response.json()['error']['message'],'details':response.json()['error']['details']}}
    assert unauth.json()['error']=={'code':'authentication_failed','message':'Authentication failed.','details':None}
    assert invalid.json()['error']['details'] and missing.json()['error']['details'] is None and fault.json()['error']=={'code':'internal_error','message':'Internal server error.','details':None}
    assert deleted.headers.get('content-type') is None and 'content' not in openapi['paths']['/api/bookmarks/{bookmark_id}']['delete']['responses']['204']
    sensitive={password, nonce, owner.json()['token'], other.json()['token']}
    for payload in (user('owner'), user('other'), bookmark('one',['Alpha','Beta']), bookmark('two',['Alpha']), bookmark('other',['Other'])):
        sensitive.update(value for value in payload.values() if isinstance(value, str))
        sensitive.update(value for value in payload.values() if isinstance(value, list) for value in value)
records=[json.loads(line) for line in log_path.read_text().splitlines() if line.startswith('{')]
required={'source','service','component','event','level','timestamp','logger','process_id','thread_name','thread_id'}; assert records and all(required <= set(r) for r in records)
def exception_tree(exc):
    assert {'type','module','message','frames'} <= set(exc) and exc['message']=='[REDACTED]' and exc['frames']
    for frame in exc['frames']: assert {'pathname','lineno','package','module','function'} <= set(frame) and frame['pathname'].startswith('/') and frame['lineno']>0 and frame['package'] and frame['module']
    for key in ('cause','context'):
        if exc.get(key) is not None: exception_tree(exc[key])
    for member in exc.get('members',[]): exception_tree(member)
for record in records:
    source=record['source']; assert {'pathname','lineno','package','module','function'} <= set(source) and source['pathname'].startswith('/') and source['lineno']>0 and source['package'].startswith('app') and source['module'].startswith('app.')
    assert all(isinstance(record[key],str) and record[key] for key in ('service','component','event','level','logger','thread_name')) and record['process_id']>0 and record['thread_id']>0
    assert record['timestamp'].endswith('Z') and dt.datetime.fromisoformat(record['timestamp'].replace('Z','+00:00')).utcoffset()==dt.timedelta()
faults=[r for r in records if r['event']=='http.request.unexpected_exception']; assert len(faults)==1; exception_tree(faults[0]['exception']); assert str(uuid.UUID(faults[0]['correlation_id']))==faults[0]['correlation_id']
raw=log_path.read_text(); assert all(str(value) not in raw for value in sensitive | {os.environ['JWT_SECRET'], os.environ['DATABASE_URL'], str(work)})
assert all(stat.S_IMODE(path.stat().st_mode)&0o077 == 0 for path in work.iterdir() if path.is_file())
print('Track 05 evidence: migrated live HTTP, OpenAPI/docs, auth/isolation/CRUD/search/live stats/errors, schema and JSONL/redaction validated')
PY
stop_server
printf 'Track 05 live mandatory-core harness: passed (Track 06 health/snapshot/worker behavior excluded)\n'
verification_report_summary 'inherited gates, mandatory coverage, live API, JSON Lines, and redaction evidence completed'
