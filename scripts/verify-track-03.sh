#!/usr/bin/env bash
# Real-process evidence for Track 03 only; it intentionally does not claim Track 04--06 behavior.
set -Eeuo pipefail
IFS=$'\n\t'

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd "${script_dir}/.." && pwd)"
report_helper="${script_dir}/verification-report.sh"
[[ -r "${report_helper}" ]] || { printf 'FAIL: missing verification report helper\n' >&2; exit 1; }
# shellcheck source=verification-report.sh
source "${report_helper}"
verification_report_start 'scripts/verify-track-03.sh' 'Track 03 bookmark CRUD real-process verification'
verification_report_gate 'isolated bootstrap, CRUD, ownership, and error contracts'
verification_report_gate 'OpenAPI, lifecycle JSON Lines, and redaction evidence'
verification_report_gate 'verified disposable-process cleanup'
uv_command="${UV:-uv}"
temporary_base="${TMPDIR:-/tmp}"
work_dir_prefix="${temporary_base%/}/backend-sample-track03."
work_dir=""
database_path=""
process_output_path=""
log_path=""
port=""
child_pid=""

cleanup() {
  local original_status=$? cleanup_status=0 wait_status=0
  trap - EXIT
  if [[ -n "${child_pid}" ]] && kill -0 "${child_pid}" 2>/dev/null; then
    kill "${child_pid}" 2>/dev/null || cleanup_status=1
    for _ in {1..30}; do kill -0 "${child_pid}" 2>/dev/null || break; sleep 0.1; done
    kill -0 "${child_pid}" 2>/dev/null && kill -KILL "${child_pid}" 2>/dev/null || true
    wait "${child_pid}" 2>/dev/null || wait_status=$?
    [[ "${wait_status}" -eq 0 || "${wait_status}" -eq 143 || "${wait_status}" -eq 137 ]] || cleanup_status=1
  fi
  if [[ -d "${work_dir}" && "${work_dir}" == "${work_dir_prefix}"* ]]; then
    rm -f -- "${work_dir}"/* 2>/dev/null || cleanup_status=1
    rmdir -- "${work_dir}" 2>/dev/null || cleanup_status=1
  else
    printf 'refusing to remove an unverified Track 03 harness path\n' >&2
    cleanup_status=1
  fi
  [[ ! -e "${work_dir}" ]] || cleanup_status=1
  [[ "${cleanup_status}" -eq 0 ]] && printf 'Track 03 harness cleanup: removed verified disposable credentials, requests, responses, database, and logs\n'
  verification_report_cleanup "${cleanup_status}" 'verified disposable credentials, requests, responses, database, and logs removal'
  if [[ "${original_status}" -ne 0 ]]; then
    verification_report_finish "${original_status}" "${cleanup_status}"
    exit "${original_status}"
  fi
  verification_report_finish 0 "${cleanup_status}"
  exit "${cleanup_status}"
}
trap cleanup EXIT

work_dir="$(mktemp -d "${work_dir_prefix}XXXXXX")"
database_path="${work_dir}/track03.sqlite3"
process_output_path="${work_dir}/bootstrap-output.log"
log_path="${work_dir}/application.jsonl"

cd "${repository_root}"
[[ -d .git && -f Makefile ]] || { printf 'refusing to run outside the repository root\n' >&2; exit 1; }
chmod 700 "${work_dir}"
export DATABASE_URL="sqlite:///${database_path}"
export APP_ENV=test
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/backend-sample-uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/private/tmp/backend-sample-python}"
export JWT_SECRET="$(${uv_command} run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
printf '%s' "${JWT_SECRET}" >"${work_dir}/jwt-secret"
port="$(${uv_command} run python - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"

${uv_command} run python - "${work_dir}" <<'PY'
import json, secrets, sys
root = sys.argv[1]
nonce = secrets.token_urlsafe(12)
sentinels = {
    "password": f"Track03 {secrets.token_urlsafe(28)} {nonce}",
    "url": f"https://example.invalid/track03-{nonce}",
    "title": f"Track03 title {nonce}",
    "description": f"Track03 description {nonce}",
    "tag": f"track03-{nonce.lower()}",
    "nonce": nonce,
}
payloads = {
    "register-one.json": {"username": f"track03-one-{nonce[:8]}", "email": f"track03-one-{nonce[:8]}@example.com", "password": sentinels["password"]},
    "register-two.json": {"username": f"track03-two-{nonce[:8]}", "email": f"track03-two-{nonce[:8]}@example.com", "password": sentinels["password"]},
    "login-one.json": {"email": f"track03-one-{nonce[:8]}@example.com", "password": sentinels["password"]},
    "login-two.json": {"email": f"track03-two-{nonce[:8]}@example.com", "password": sentinels["password"]},
    "create.json": {"url": sentinels["url"], "title": sentinels["title"], "description": sentinels["description"], "tags": [f" {sentinels['tag']} ", sentinels["tag"].upper(), "alpha", "alpha"]},
    "duplicate.json": {"url": sentinels["url"], "title": f"duplicate {nonce}", "description": None, "tags": ["duplicate"]},
    "patch-material.json": {"title": f"Track03 changed {nonce}"},
    "patch-clear.json": {"description": None},
    "patch-tags.json": {"tags": [" Beta ", "beta", "alpha"]},
    "patch-reordered.json": {"tags": ["beta", "alpha", "beta"]},
}
for name, payload in payloads.items():
    with open(f"{root}/{name}", "w", encoding="utf-8") as handle: json.dump(payload, handle)
with open(f"{root}/sentinels.json", "w", encoding="utf-8") as handle: json.dump(sentinels, handle)
PY
chmod 600 "${work_dir}"/*

make bootstrap HOST=127.0.0.1 PORT="${port}" >"${process_output_path}" 2>&1 &
child_pid="$!"
for _ in {1..100}; do
  curl --fail --silent "http://127.0.0.1:${port}/openapi.json" >"${work_dir}/openapi.json" 2>/dev/null && break
  kill -0 "${child_pid}" 2>/dev/null || { printf 'bootstrap exited before readiness\n' >&2; exit 1; }
  sleep 0.1
done
[[ -s "${work_dir}/openapi.json" ]] || { printf 'timed out waiting for bootstrap\n' >&2; exit 1; }
chmod 600 "${work_dir}/openapi.json"

request() { # method path request-file response-file status-file curl-config(optional)
  local method=$1 path=$2 request_file=$3 response_file=$4 status_file=$5 config_file=${6:-}
  local args=(--silent --show-error --output "${response_file}" --write-out '%{http_code}' --request "${method}")
  [[ -n "${config_file}" ]] && args+=(--config "${config_file}")
  [[ -n "${request_file}" ]] && args+=(--header 'Content-Type: application/json' --data-binary @"${request_file}")
  curl "${args[@]}" "http://127.0.0.1:${port}${path}" >"${status_file}"
  chmod 600 "${response_file}" "${status_file}"
}

for person in one two; do
  request POST /api/auth/register "${work_dir}/register-${person}.json" "${work_dir}/register-${person}.response" "${work_dir}/register-${person}.status"
  [[ "$(<"${work_dir}/register-${person}.status")" == 201 ]]
  request POST /api/auth/login "${work_dir}/login-${person}.json" "${work_dir}/login-${person}.response" "${work_dir}/login-${person}.status"
  [[ "$(<"${work_dir}/login-${person}.status")" == 200 ]]
done
${uv_command} run python - "${work_dir}" <<'PY'
import json, sys
root=sys.argv[1]
for person in ("one", "two"):
    # Registration has already issued the bearer token; login is independently
    # asserted above, but is not relied on as a credential-file source.
    response=json.load(open(f"{root}/register-{person}.response", encoding="utf-8"))
    assert set(response) == {"user", "token"}, response.get("error", {}).get("code", sorted(response))
    token=response["token"]
    open(f"{root}/{person}.curl", "w", encoding="utf-8").write(f'header = "Authorization: Bearer {token}"\n')
PY
chmod 600 "${work_dir}"/*.curl

request POST /api/bookmarks "${work_dir}/create.json" "${work_dir}/create.response" "${work_dir}/create.status" "${work_dir}/one.curl"; [[ "$(<"${work_dir}/create.status")" == 201 ]]
request POST /api/bookmarks "${work_dir}/duplicate.json" "${work_dir}/duplicate.response" "${work_dir}/duplicate.status" "${work_dir}/one.curl"; [[ "$(<"${work_dir}/duplicate.status")" == 201 ]]
request GET /api/bookmarks '' "${work_dir}/list-one.response" "${work_dir}/list-one.status" "${work_dir}/one.curl"; [[ "$(<"${work_dir}/list-one.status")" == 200 ]]
request GET /api/bookmarks '' "${work_dir}/list-two.response" "${work_dir}/list-two.status" "${work_dir}/two.curl"; [[ "$(<"${work_dir}/list-two.status")" == 200 ]]
bookmark_id="$(${uv_command} run python - "${work_dir}/create.response" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], encoding='utf-8'))['id'])
PY
)"
request GET "/api/bookmarks/${bookmark_id}" '' "${work_dir}/detail.response" "${work_dir}/detail.status" "${work_dir}/one.curl"; [[ "$(<"${work_dir}/detail.status")" == 200 ]]
request PATCH "/api/bookmarks/${bookmark_id}" "${work_dir}/patch-material.json" "${work_dir}/patch-material.response" "${work_dir}/patch-material.status" "${work_dir}/one.curl"; [[ "$(<"${work_dir}/patch-material.status")" == 200 ]]
request PATCH "/api/bookmarks/${bookmark_id}" "${work_dir}/patch-clear.json" "${work_dir}/patch-clear.response" "${work_dir}/patch-clear.status" "${work_dir}/one.curl"; [[ "$(<"${work_dir}/patch-clear.status")" == 200 ]]
request PATCH "/api/bookmarks/${bookmark_id}" "${work_dir}/patch-tags.json" "${work_dir}/patch-tags.response" "${work_dir}/patch-tags.status" "${work_dir}/one.curl"; [[ "$(<"${work_dir}/patch-tags.status")" == 200 ]]
request PATCH "/api/bookmarks/${bookmark_id}" "${work_dir}/patch-reordered.json" "${work_dir}/patch-reordered.response" "${work_dir}/patch-reordered.status" "${work_dir}/one.curl"; [[ "$(<"${work_dir}/patch-reordered.status")" == 200 ]]
for action in get patch delete; do
  case "${action}" in
    get) request GET "/api/bookmarks/${bookmark_id}" '' "${work_dir}/cross-get.response" "${work_dir}/cross-get.status" "${work_dir}/two.curl" ;;
    patch) request PATCH "/api/bookmarks/${bookmark_id}" "${work_dir}/patch-material.json" "${work_dir}/cross-patch.response" "${work_dir}/cross-patch.status" "${work_dir}/two.curl" ;;
    delete) request DELETE "/api/bookmarks/${bookmark_id}" '' "${work_dir}/cross-delete.response" "${work_dir}/cross-delete.status" "${work_dir}/two.curl" ;;
  esac
  [[ "$(<"${work_dir}/cross-${action}.status")" == 404 ]]
done
request GET /api/bookmarks/999999 '' "${work_dir}/missing.response" "${work_dir}/missing.status" "${work_dir}/two.curl"; [[ "$(<"${work_dir}/missing.status")" == 404 ]]
request GET /api/bookmarks/0 '' "${work_dir}/invalid-id.response" "${work_dir}/invalid-id.status" "${work_dir}/one.curl"; [[ "$(<"${work_dir}/invalid-id.status")" == 422 ]]
request POST /api/bookmarks "${work_dir}/create.json" "${work_dir}/unauthorized.response" "${work_dir}/unauthorized.status"; [[ "$(<"${work_dir}/unauthorized.status")" == 401 ]]
request DELETE "/api/bookmarks/${bookmark_id}" '' "${work_dir}/delete.response" "${work_dir}/delete.status" "${work_dir}/one.curl"; [[ "$(<"${work_dir}/delete.status")" == 204 && ! -s "${work_dir}/delete.response" ]]
request GET "/api/bookmarks/${bookmark_id}" '' "${work_dir}/after-delete.response" "${work_dir}/after-delete.status" "${work_dir}/one.curl"; [[ "$(<"${work_dir}/after-delete.status")" == 404 ]]
curl --silent --show-error --output "${work_dir}/fault.response" --write-out '%{http_code}' --header 'X-Track01-Harness-Fault: 1' "http://127.0.0.1:${port}/openapi.json" >"${work_dir}/fault.status"
[[ "$(<"${work_dir}/fault.status")" == 500 ]]
kill -0 "${child_pid}" 2>/dev/null

kill "${child_pid}"; wait_status=0; wait "${child_pid}" 2>/dev/null || wait_status=$?; [[ "${wait_status}" -eq 0 || "${wait_status}" -eq 143 ]]; child_pid=""
awk '/^\{/{print}' "${process_output_path}" >"${log_path}"; chmod 600 "${log_path}"

${uv_command} run python - "${work_dir}" "${log_path}" "${process_output_path}" <<'PY'
import json, sys, uuid
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
root, log_path, output_path = sys.argv[1:]
def load(name): return json.load(open(f"{root}/{name}", encoding="utf-8"))
sentinels=load("sentinels.json"); openapi=load("openapi.json")
created, detail = load("create.response"), load("detail.response")
assert set(created) == {"id","url","title","description","tags","created_at","updated_at"}
assert detail == created
assert [tag["name"] for tag in created["tags"]] == ["alpha", sentinels["tag"]]
assert load("duplicate.response")["url"] == created["url"]
assert load("list-two.response") == {"items": [], "total": 0, "page": 1, "page_size": 20}
one_list=load("list-one.response"); assert set(one_list)=={"items","total","page","page_size"} and one_list["total"]==2 and one_list["page"]==1 and one_list["page_size"]==20
material, cleared, tagged, reordered=(load(n) for n in ("patch-material.response","patch-clear.response","patch-tags.response","patch-reordered.response"))
assert material["created_at"] == created["created_at"] and material["updated_at"] > created["updated_at"]
assert cleared["description"] is None and cleared["updated_at"] > material["updated_at"]
assert [tag["name"] for tag in tagged["tags"]] == ["alpha","beta"] and tagged["updated_at"] > cleared["updated_at"]
assert reordered == tagged
not_found=load("missing.response")
assert not_found == load("cross-get.response") == load("cross-patch.response") == load("cross-delete.response") == load("after-delete.response") == {"error":{"code":"not_found","message":"Resource not found.","details":None}}
assert load("unauthorized.response") == {"error":{"code":"authentication_failed","message":"Authentication failed.","details":None}}
assert load("invalid-id.response")["error"]["code"] == "validation_error"
assert load("fault.response") == {"error":{"code":"internal_error","message":"Internal server error.","details":None}}
paths=openapi["paths"]; expected={"/api/bookmarks","/api/bookmarks/{bookmark_id}"}; assert expected <= set(paths)
assert openapi["components"]["securitySchemes"]["BearerAuth"] == {"type":"http","scheme":"bearer","bearerFormat":"JWT"}
assert set(paths["/api/bookmarks"]) == {"get","post"}; assert set(paths["/api/bookmarks/{bookmark_id}"]) == {"get","patch","delete"}
assert set(paths["/api/bookmarks"]["post"]["responses"]) == {"201","401","422","429","500"}
assert set(paths["/api/bookmarks"]["get"]["responses"]) == {"200","401","422","429","500"}
assert set(paths["/api/bookmarks/{bookmark_id}"]["get"]["responses"]) == {"200","401","404","422","429","500"}
assert set(paths["/api/bookmarks/{bookmark_id}"]["patch"]["responses"]) == {"200","401","404","422","429","500"}
assert set(paths["/api/bookmarks/{bookmark_id}"]["delete"]["responses"]) == {"204","401","404","422","429","500"}
for path, method in (("/api/bookmarks","post"),("/api/bookmarks","get"),("/api/bookmarks/{bookmark_id}","get"),("/api/bookmarks/{bookmark_id}","patch"),("/api/bookmarks/{bookmark_id}","delete")):
    rate=paths[path][method]["responses"]["429"]
    assert set(rate["headers"]) == {"Retry-After","Cache-Control"}
    assert rate["content"]["application/json"]["schema"] == {"$ref":"#/components/schemas/ErrorEnvelope"}
for path, method, success, body in (("/api/bookmarks","post","201",created),("/api/bookmarks","get","200",one_list),("/api/bookmarks/{bookmark_id}","get","200",detail),("/api/bookmarks/{bookmark_id}","patch","200",tagged)):
    operation=paths[path][method]; assert operation.get("security") == [{"BearerAuth": []}]
    schema=operation["responses"][success]["content"]["application/json"]["schema"]
    registry=Registry().with_resource("urn:track03:openapi", Resource.from_contents(openapi, default_specification=DRAFT202012))
    Draft202012Validator({"$id":"urn:track03:openapi", **openapi, **schema}, registry=registry).validate(body)
for path, method, status, body in (("/api/bookmarks","post","401",load("unauthorized.response")),("/api/bookmarks/{bookmark_id}","get","404",not_found),("/api/bookmarks/{bookmark_id}","get","422",load("invalid-id.response")),("/api/bookmarks","post","500",load("fault.response"))):
    schema=paths[path][method]["responses"][status]["content"]["application/json"]["schema"]
    Draft202012Validator({"$id":"urn:track03:openapi", **openapi, **schema}, registry=Registry().with_resource("urn:track03:openapi", Resource.from_contents(openapi, default_specification=DRAFT202012))).validate(body)
delete_response=paths["/api/bookmarks/{bookmark_id}"]["delete"]["responses"]["204"]
assert "content" not in delete_response and paths["/api/bookmarks/{bookmark_id}"]["delete"].get("security") == [{"BearerAuth": []}]
records=[json.loads(line) for line in open(log_path, encoding="utf-8") if line.strip()]
unexpected=[record for record in records if record["event"] == "http.request.unexpected_exception"]
assert len(unexpected)==1 and unexpected[0]["exception"]["type"]=="RuntimeError" and unexpected[0]["exception"]["frames"]
assert unexpected[0]["exception"]["message"]=="[REDACTED]" and unexpected[0]["context"]=={"method":"GET"}
events=[record["event"] for record in records]
for event in ("application.starting","application.started","application.stopping","application.stopped"): assert events.count(event)==1
application_records=[record for record in records if record["event"].startswith("application.")]
assert {record["process_id"] for record in application_records} == {unexpected[0]["process_id"]}
assert str(uuid.UUID(unexpected[0]["correlation_id"])) == unexpected[0]["correlation_id"]
for record in records:
    assert {"source","service","component","event","level","timestamp","logger","process_id","thread_id"} <= record.keys()
    assert record["timestamp"].endswith("Z") and record["source"]["pathname"].startswith("/") and record["source"]["lineno"] > 0
raw_output=open(output_path, encoding="utf-8").read(); raw_logs=open(log_path, encoding="utf-8").read()
def strings(value):
    if isinstance(value, str): return [value]
    if isinstance(value, dict): return [item for child in value.values() for item in strings(child)]
    if isinstance(value, list): return [item for child in value for item in strings(child)]
    return []
sensitive=set(sentinels.values()) | {open(f"{root}/jwt-secret", encoding="utf-8").read()}
for name in ("register-one.json","register-two.json","login-one.json","login-two.json","create.json","duplicate.json","patch-material.json","patch-clear.json","patch-tags.json","patch-reordered.json"):
    sensitive.update(strings(load(name)))
for person in ("one","two"):
    for operation in ("register","login"):
        sensitive.add(load(f"{operation}-{person}.response")["token"])
assert unexpected[0]["correlation_id"] not in sensitive
for raw in (raw_output, raw_logs):
    for value in sensitive: assert value not in raw
    for internal in ("Authorization", "Bearer", "$argon2", "password_hash", "sqlite:///"): assert internal not in raw
print("Track 03 process evidence: real CRUD, ownership concealment, canonical tags, timestamps, bodyless delete, bounded OpenAPI, redacted owning fault")
PY
verification_report_summary 'CRUD, ownership, OpenAPI, lifecycle, and redaction evidence completed'
