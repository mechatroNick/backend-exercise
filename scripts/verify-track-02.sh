#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
uv_command="${UV:-uv}"
debug="${TRACK02_DEBUG:-0}"
temporary_base="${TMPDIR:-/tmp}"
work_dir_prefix="${temporary_base%/}/backend-sample-track02."
work_dir="$(mktemp -d "${work_dir_prefix}XXXXXX")"
database_path="${work_dir}/track02.sqlite3"
process_output_path="${work_dir}/bootstrap-output.log"
log_path="${work_dir}/application.jsonl"
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
    kill -0 "${child_pid}" 2>/dev/null && { kill -KILL "${child_pid}" 2>/dev/null || cleanup_status=1; }
    wait "${child_pid}" 2>/dev/null || wait_status=$?
    [[ "${wait_status}" -eq 0 || "${wait_status}" -eq 143 ]] || cleanup_status=1
  fi
  if [[ "${debug}" == "1" ]]; then
    printf 'Track 02 harness debug artifacts retained at %s\n' "${work_dir}"
  else
    if [[ ! -d "${work_dir}" || "${work_dir}" != "${work_dir_prefix}"* ]]; then
      printf 'refusing to remove an unverified harness path\n' >&2
      cleanup_status=1
    else
      rm -rf -- "${work_dir}" || cleanup_status=1
    fi
    [[ ! -e "${work_dir}" ]] || cleanup_status=1
    [[ "${cleanup_status}" -eq 0 ]] && printf 'Track 02 harness cleanup: removed verified disposable resources\n'
  fi
  [[ "${original_status}" -ne 0 ]] && exit "${original_status}"
  exit "${cleanup_status}"
}
trap cleanup EXIT

cd "${repository_root}"
[[ -d "${repository_root}/.git" && -f "${repository_root}/Makefile" ]] || {
  printf 'refusing to run outside the repository root\n' >&2
  exit 1
}
chmod 700 "${work_dir}"
export DATABASE_URL="sqlite:///${database_path}"
export APP_ENV=test
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/backend-sample-uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/private/tmp/backend-sample-python}"
export JWT_SECRET="$(${uv_command} run python -c 'import secrets; print(secrets.token_urlsafe(48))')"

port="$(${uv_command} run python - <<'PY'
import socket
with socket.socket() as socket_:
    socket_.bind(("127.0.0.1", 0))
    print(socket_.getsockname()[1])
PY
)"

${uv_command} run python - "${work_dir}" <<'PY'
import json
import secrets
import sys

root = sys.argv[1]
sentinel = f"track02-submitted-{secrets.token_urlsafe(16)}"
password = f"Track02 {secrets.token_urlsafe(24)} {sentinel}"
for name, payload in {
    "register.json": {"username": "track02-user", "email": "track02@example.com", "password": password},
    "login.json": {"email": "track02@example.com", "password": password},
    "duplicate.json": {"username": "TRACK02-USER", "email": "other@example.com", "password": password},
    "invalid.json": {"email": "missing@example.com", "password": password},
}.items():
    with open(f"{root}/{name}", "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
with open(f"{root}/sentinel.txt", "w", encoding="utf-8") as handle:
    handle.write(sentinel)
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

curl --fail --silent --show-error --output "${work_dir}/register.response" --write-out '%{http_code}' \
  --header 'Content-Type: application/json' --data-binary @"${work_dir}/register.json" \
  "http://127.0.0.1:${port}/api/auth/register" >"${work_dir}/register.status"
[[ "$(<"${work_dir}/register.status")" == "201" ]]
curl --fail --silent --show-error --output "${work_dir}/login.response" --write-out '%{http_code}' \
  --header 'Content-Type: application/json' --data-binary @"${work_dir}/login.json" \
  "http://127.0.0.1:${port}/api/auth/login" >"${work_dir}/login.status"
[[ "$(<"${work_dir}/login.status")" == "200" ]]
${uv_command} run python - "${work_dir}" <<'PY'
import json
import sys
import jwt

root = sys.argv[1]
registered = json.load(open(f"{root}/register.response", encoding="utf-8"))
logged_in = json.load(open(f"{root}/login.response", encoding="utf-8"))
assert set(registered) == set(logged_in) == {"user", "token"}
assert registered["user"] == {"id": 1, "username": "track02-user", "email": "track02@example.com"}
assert logged_in["user"] == registered["user"]
claims = jwt.decode(logged_in["token"], options={"verify_signature": False})
assert set(claims) == {"sub", "iat", "exp"} and claims["sub"] == "1"
assert type(claims["iat"]) is int and type(claims["exp"]) is int
assert claims["exp"] > claims["iat"]
with open(f"{root}/protected.curl", "w", encoding="utf-8") as handle:
    handle.write(f'header = "Authorization: Bearer {logged_in["token"]}"\n')
PY
chmod 600 "${work_dir}/protected.curl"
curl --fail --silent --show-error --config "${work_dir}/protected.curl" \
  "http://127.0.0.1:${port}/__track02/protected" >"${work_dir}/protected.response"
curl --silent --show-error --output "${work_dir}/duplicate.response" --write-out '%{http_code}' \
  --header 'Content-Type: application/json' --data-binary @"${work_dir}/duplicate.json" \
  "http://127.0.0.1:${port}/api/auth/register" >"${work_dir}/duplicate.status"
[[ "$(<"${work_dir}/duplicate.status")" == "409" ]]
curl --silent --show-error --output "${work_dir}/invalid.response" --write-out '%{http_code}' \
  --header 'Content-Type: application/json' --data-binary @"${work_dir}/invalid.json" \
  "http://127.0.0.1:${port}/api/auth/login" >"${work_dir}/invalid.status"
[[ "$(<"${work_dir}/invalid.status")" == "401" ]]
curl --silent --show-error --output "${work_dir}/fault.response" --write-out '%{http_code}' \
  --header 'X-Track01-Harness-Fault: 1' "http://127.0.0.1:${port}/openapi.json" >"${work_dir}/fault.status"
[[ "$(<"${work_dir}/fault.status")" == "500" ]]
kill -0 "${child_pid}" 2>/dev/null

kill "${child_pid}"
wait_status=0
wait "${child_pid}" 2>/dev/null || wait_status=$?
[[ "${wait_status}" -eq 0 || "${wait_status}" -eq 143 ]] || exit "${wait_status}"
child_pid=""
awk '/^\{/{print}' "${process_output_path}" >"${log_path}"
${uv_command} run python - "${work_dir}" "${log_path}" "${process_output_path}" <<'PY'
import json
import sys
import uuid
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

root, log_path, output_path = sys.argv[1:]
records = [json.loads(line) for line in open(log_path, encoding="utf-8") if line.strip()]
assert records
events = [record["event"] for record in records]
for event in ("application.starting", "application.started", "application.stopping", "application.stopped"):
    assert events.count(event) == 1
unexpected = [record for record in records if record["event"] == "http.request.unexpected_exception"]
assert len(unexpected) == 1 and unexpected[0]["exception"]["frames"]
assert unexpected[0]["exception"]["type"] == "RuntimeError"
assert unexpected[0]["exception"]["message"] == "[REDACTED]"
assert unexpected[0]["message"] == "unexpected HTTP request exception"
assert unexpected[0]["context"] == {"method": "GET"}
assert json.load(open(f"{root}/fault.response", encoding="utf-8")) == {"error": {"code": "internal_error", "message": "Internal server error.", "details": None}}
for record in records:
    assert {"source", "service", "component", "event", "level", "timestamp", "logger", "process_id", "thread_id"} <= record.keys()
    assert record["timestamp"].endswith("Z") and record["source"]["pathname"].startswith("/") and record["source"]["lineno"] > 0
correlation_id = unexpected[0]["correlation_id"]
assert str(uuid.UUID(correlation_id)) == correlation_id
application_records = [record for record in records if record["event"].startswith("application.")]
assert len({record["process_id"] for record in application_records}) == 1
assert unexpected[0]["process_id"] == application_records[0]["process_id"]
assert json.load(open(f"{root}/protected.response", encoding="utf-8")) == {"user_id": 1}
assert json.load(open(f"{root}/duplicate.response", encoding="utf-8"))["error"]["code"] == "identity_conflict"
assert json.load(open(f"{root}/invalid.response", encoding="utf-8"))["error"]["code"] == "authentication_failed"
openapi = json.load(open(f"{root}/openapi.json", encoding="utf-8"))
assert set(openapi["paths"]) == {
    "/api/auth/register",
    "/api/auth/login",
    "/api/bookmarks",
    "/api/bookmarks/stats",
    "/api/bookmarks/{bookmark_id}",
    "/health/live",
    "/health/ready",
}
assert openapi["components"]["securitySchemes"]["BearerAuth"] == {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
registry = Registry().with_resource("urn:track02:openapi", Resource.from_contents(openapi, default_specification=DRAFT202012))
def validate(path, status, payload):
    response_schema = openapi["paths"][path]["post"]["responses"][status]["content"]["application/json"]["schema"]
    Draft202012Validator({"$id": "urn:track02:openapi", **openapi, **response_schema}, registry=registry).validate(payload)
validate("/api/auth/register", "201", json.load(open(f"{root}/register.response", encoding="utf-8")))
validate("/api/auth/login", "200", json.load(open(f"{root}/login.response", encoding="utf-8")))
validate("/api/auth/register", "409", json.load(open(f"{root}/duplicate.response", encoding="utf-8")))
validate("/api/auth/login", "401", json.load(open(f"{root}/invalid.response", encoding="utf-8")))
validate("/api/auth/login", "500", json.load(open(f"{root}/fault.response", encoding="utf-8")))
raw = open(output_path, encoding="utf-8").read()
register_payload = json.load(open(f"{root}/register.json", encoding="utf-8"))
token = json.load(open(f"{root}/login.response", encoding="utf-8"))["token"]
sentinel = open(f"{root}/sentinel.txt", encoding="utf-8").read()
assert correlation_id not in {register_payload["password"], token, sentinel, register_payload["email"], register_payload["username"]}
for sensitive in (register_payload["password"], token, sentinel, register_payload["email"], register_payload["username"], f"Bearer {token}", "Authorization", "$argon2", "password_hash"):
    assert sensitive not in raw
assert sentinel not in unexpected[0]["exception"].get("message", "")
assert "track01-secret-sentinel-do-not-emit" not in raw
assert "track01-submitted-bookmark-sentinel-do-not-emit" not in raw
print("Track 02 process evidence: bootstrap, auth contract, protected bearer, redacted owning fault")
PY
