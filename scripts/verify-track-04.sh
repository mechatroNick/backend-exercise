#!/usr/bin/env bash
# Real-process Track 04 evidence.  This deliberately makes no N+1 or Track 06+ claim.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
uv="${UV:-uv}"
prefix="${TMPDIR:-/tmp}/backend-sample-track04."
work="$(mktemp -d "${prefix}XXXXXX")"
database_path="${work}/track04.sqlite3"
output_path="${work}/bootstrap-output.log"
log_path="${work}/application.jsonl"
pid=""
port=""

fail() {
  printf 'Track 04 harness failure: %s\n' "$1" >&2
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
  while IFS= read -r target; do targets+=("${target}"); done < <(descendants "${pid}")
  targets+=("${pid}")
  for target in "${targets[@]}"; do kill -TERM "${target}" 2>/dev/null || true; done
  for _ in {1..40}; do
    alive=0
    for target in "${targets[@]}"; do kill -0 "${target}" 2>/dev/null && alive=1; done
    [[ "${alive}" == 0 ]] && break
    sleep 0.1
  done
  for target in "${targets[@]}"; do kill -0 "${target}" 2>/dev/null && kill -KILL "${target}" 2>/dev/null || true; done
  wait "${pid}" 2>/dev/null || wait_status=$?
  [[ "${wait_status}" == 0 || "${wait_status}" == 143 || "${wait_status}" == 137 ]] || fail 'bootstrap returned an unexpected status'
  for target in "${targets[@]}"; do kill -0 "${target}" 2>/dev/null && fail 'a bootstrap descendant remained after termination'; done
  pid=""
}

cleanup() {
  local original=$? cleanup_status=0
  trap - EXIT
  stop_server || cleanup_status=1
  if [[ -d "${work}" && "${work}" == "${prefix}"* ]]; then
    rm -rf -- "${work}" || cleanup_status=1
    [[ ! -e "${work}" ]] || cleanup_status=1
    [[ "${cleanup_status}" == 0 ]] && printf 'Track 04 harness cleanup: removed verified disposable resources\n'
  else
    printf 'refusing to remove an unverified Track 04 harness path\n' >&2
    cleanup_status=1
  fi
  [[ "${original}" != 0 ]] && exit "${original}"
  exit "${cleanup_status}"
}
trap cleanup EXIT

cd "${root}"
[[ -d .git && -f Makefile ]] || fail 'refusing to run outside repository root'
chmod 700 "${work}"
export DATABASE_URL="sqlite:///${database_path}" APP_ENV=test
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/backend-sample-uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/private/tmp/backend-sample-python}"
export JWT_SECRET="$("${uv}" run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
printf '%s' "${JWT_SECRET}" >"${work}/jwt-secret"
port="$("${uv}" run python - <<'PY'
import socket
with socket.socket() as socket_:
    socket_.bind(("127.0.0.1", 0))
    print(socket_.getsockname()[1])
PY
)"

"${uv}" run python - "${work}" <<'PY'
import json
import secrets
import sys

root = sys.argv[1]
nonce = secrets.token_urlsafe(12)
sentinels = {
    "password": f"Track04 {secrets.token_urlsafe(28)} {nonce}",
    "url": f"https://example.invalid/track04-{nonce}",
    "title": f"Track04 literal %_\\ {nonce}",
    "description": f"Track04 content {nonce}",
    "tag": f"track04-{nonce.lower()}",
    "other_title": f"Track04 other {nonce}",
    "nonce": nonce,
}
payloads = {
    "register-owner.json": {"username": f"track04-owner-{nonce[:8]}", "email": f"track04-owner-{nonce[:8]}@example.com", "password": sentinels["password"]},
    "register-other.json": {"username": f"track04-other-{nonce[:8]}", "email": f"track04-other-{nonce[:8]}@example.com", "password": sentinels["password"]},
    "bookmark-one.json": {"url": sentinels["url"] + "/one", "title": sentinels["title"], "description": sentinels["description"], "tags": ["Alpha", "Beta"]},
    "bookmark-two.json": {"url": sentinels["url"] + "/two", "title": f"Track04 two {nonce}", "description": sentinels["description"], "tags": ["Alpha", "Gamma"]},
    "bookmark-three.json": {"url": sentinels["url"] + "/three", "title": f"Track04 three {nonce}", "description": sentinels["description"], "tags": ["Beta", "Gamma"]},
    "bookmark-four.json": {"url": sentinels["url"] + "/four", "title": f"Track04 four {nonce}", "description": sentinels["description"], "tags": ["Solo"]},
    "bookmark-other.json": {"url": sentinels["url"] + "/other", "title": sentinels["other_title"], "description": sentinels["description"], "tags": [sentinels["tag"]]},
}
for name, payload in payloads.items():
    with open(f"{root}/{name}", "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
with open(f"{root}/sentinels.json", "w", encoding="utf-8") as handle:
    json.dump(sentinels, handle)
PY
chmod 600 "${work}"/*

start_server() {
  make bootstrap HOST=127.0.0.1 PORT="${port}" >>"${output_path}" 2>&1 &
  pid="$!"
  for _ in {1..100}; do
    curl --fail --silent "http://127.0.0.1:${port}/openapi.json" >"${work}/openapi.json" 2>/dev/null && break
    kill -0 "${pid}" 2>/dev/null || fail 'bootstrap exited before readiness'
    sleep 0.1
  done
  [[ -s "${work}/openapi.json" ]] || fail 'timed out waiting for bootstrap'
  chmod 600 "${work}/openapi.json"
}

request() { # method path request-file response-file status-file curl-config(optional)
  local method=$1 path=$2 request_file=$3 response_file=$4 status_file=$5 config_file=${6:-}
  local -a args=(--silent --show-error --output "${response_file}" --write-out '%{http_code}' --request "${method}")
  [[ -n "${config_file}" ]] && args+=(--config "${config_file}")
  [[ -n "${request_file}" ]] && args+=(--header 'Content-Type: application/json' --data-binary @"${request_file}")
  curl "${args[@]}" "http://127.0.0.1:${port}${path}" >"${status_file}"
  chmod 600 "${response_file}" "${status_file}"
}

start_server
for person in owner other; do
  request POST /api/auth/register "${work}/register-${person}.json" "${work}/register-${person}.response" "${work}/register-${person}.status"
  [[ "$(<"${work}/register-${person}.status")" == 201 ]] || fail 'registration did not return 201'
done
"${uv}" run python - "${work}" <<'PY'
import json
import sys

root = sys.argv[1]
for person in ("owner", "other"):
    response = json.load(open(f"{root}/register-{person}.response", encoding="utf-8"))
    if set(response) != {"user", "token"}:
        raise SystemExit("registration shape mismatch")
    with open(f"{root}/{person}.curl", "w", encoding="utf-8") as handle:
        handle.write(f'header = "Authorization: Bearer {response["token"]}"\n')
PY
chmod 600 "${work}"/*.curl
for number in one two three four; do
  request POST /api/bookmarks "${work}/bookmark-${number}.json" "${work}/created-${number}.response" "${work}/created-${number}.status" "${work}/owner.curl"
  [[ "$(<"${work}/created-${number}.status")" == 201 ]] || fail 'owner bookmark creation did not return 201'
done
request POST /api/bookmarks "${work}/bookmark-other.json" "${work}/created-other.response" "${work}/created-other.status" "${work}/other.curl"
[[ "$(<"${work}/created-other.status")" == 201 ]] || fail 'other-user bookmark creation did not return 201'
"${uv}" run python - "${work}" <<'PY'
import json
import sys
root = sys.argv[1]
ids = {name: json.load(open(f"{root}/created-{name}.response", encoding="utf-8"))["id"] for name in ("one", "two", "three", "four", "other")}
with open(f"{root}/ids.json", "w", encoding="utf-8") as handle:
    json.dump(ids, handle)
PY
chmod 600 "${work}/ids.json"

# The API intentionally owns timestamps.  Stop its process before applying these
# parameterized fixture updates to the migrated disposable SQLite database.
stop_server
"${uv}" run python - "${database_path}" "${work}/ids.json" <<'PY'
import json
import sqlite3
import sys

database, ids_path = sys.argv[1:]
ids = json.load(open(ids_path, encoding="utf-8"))
timestamps = {
    "one": ("2026-01-10T12:00:00.000000Z", "2026-01-11T12:00:00.000000Z"),
    "two": ("2026-02-10T12:00:00.000000Z", "2026-03-02T12:00:00.000000Z"),
    "three": ("2026-02-20T12:00:00.000000Z", "2026-03-03T12:00:00.000000Z"),
    "four": ("2026-03-10T12:00:00.000000Z", "2026-03-10T12:00:00.000000Z"),
}
with sqlite3.connect(database) as connection:
    connection.executemany(
        "UPDATE bookmarks SET created_at = ?, updated_at = ? WHERE id = ?",
        [(created, updated, ids[name]) for name, (created, updated) in timestamps.items()],
    )
PY

start_server
request GET '/api/bookmarks?page=1&page_size=2' '' "${work}/page-one.response" "${work}/page-one.status" "${work}/owner.curl"
request GET '/api/bookmarks?page=2&page_size=2' '' "${work}/page-two.response" "${work}/page-two.status" "${work}/owner.curl"
request GET '/api/bookmarks?page=1&page_size=100' '' "${work}/max-page.response" "${work}/max-page.status" "${work}/owner.curl"
request GET '/api/bookmarks?tag=%20gAmMa%20' '' "${work}/tag.response" "${work}/tag.status" "${work}/owner.curl"
request GET '/api/bookmarks?from=2026-02-10&to=2026-02-20' '' "${work}/created-range.response" "${work}/created-range.status" "${work}/owner.curl"
request GET '/api/bookmarks?to=2026-02-10' '' "${work}/created-day.response" "${work}/created-day.status" "${work}/owner.curl"
request GET '/api/bookmarks?updated_from=2026-03-02&updated_to=2026-03-03' '' "${work}/updated-range.response" "${work}/updated-range.status" "${work}/owner.curl"
request GET '/api/bookmarks?q=TRACK04&page_size=100' '' "${work}/case-query.response" "${work}/case-query.status" "${work}/owner.curl"
request GET '/api/bookmarks?from=2026-03-01&to=2026-02-01' '' "${work}/reversed-created.response" "${work}/reversed-created.status" "${work}/owner.curl"
request GET '/api/bookmarks?updated_from=2026-03-03&updated_to=2026-03-02' '' "${work}/reversed-updated.response" "${work}/reversed-updated.status" "${work}/owner.curl"
request GET '/api/bookmarks?page=0' '' "${work}/invalid-page.response" "${work}/invalid-page.status" "${work}/owner.curl"
request GET '/api/bookmarks?page_size=0' '' "${work}/invalid-page-size.response" "${work}/invalid-page-size.status" "${work}/owner.curl"
request GET '/api/bookmarks?page_size=101' '' "${work}/too-large-page-size.response" "${work}/too-large-page-size.status" "${work}/owner.curl"
curl --silent --show-error --output "${work}/literal.response" --write-out '%{http_code}' --get --data-urlencode 'q=%_\' --config "${work}/owner.curl" "http://127.0.0.1:${port}/api/bookmarks" >"${work}/literal.status"
chmod 600 "${work}/literal.response" "${work}/literal.status"
request GET /api/bookmarks '' "${work}/other-list.response" "${work}/other-list.status" "${work}/other.curl"
request GET /api/bookmarks '' "${work}/unauth-list.response" "${work}/unauth-list.status"
curl --silent --show-error --dump-header "${work}/owner-before.headers" --output "${work}/owner-before.response" --write-out '%{http_code}' --config "${work}/owner.curl" "http://127.0.0.1:${port}/api/bookmarks/stats" >"${work}/owner-before.status"
chmod 600 "${work}/owner-before.headers" "${work}/owner-before.response" "${work}/owner-before.status"
request GET /api/bookmarks/stats '' "${work}/other-stats.response" "${work}/other-stats.status" "${work}/other.curl"
request GET /api/bookmarks/stats '' "${work}/unauth-stats.response" "${work}/unauth-stats.status"
curl --silent --show-error --dump-header "${work}/fault.headers" --output "${work}/fault.response" --write-out '%{http_code}' --header 'X-Track01-Harness-Fault: 1' "http://127.0.0.1:${port}/openapi.json" >"${work}/fault.status"
chmod 600 "${work}/fault.headers"
for status in page-one page-two max-page tag created-range created-day updated-range case-query literal other-list owner-before other-stats; do [[ "$(<"${work}/${status}.status")" == 200 ]] || fail 'expected successful Track 04 request failed'; done
for status in reversed-created reversed-updated invalid-page invalid-page-size too-large-page-size; do [[ "$(<"${work}/${status}.status")" == 422 ]] || fail 'invalid search request did not return 422'; done
[[ "$(<"${work}/unauth-stats.status")" == 401 ]] || fail 'unauthorized stats did not return 401'
[[ "$(<"${work}/unauth-list.status")" == 401 ]] || fail 'unauthorized list did not return 401'
[[ "$(<"${work}/fault.status")" == 500 ]] || fail 'fault seam did not return 500'

# Remove one owner link and one owner bookmark while the server is stopped, then
# prove stats are live rather than a retained snapshot.
stop_server
"${uv}" run python - "${database_path}" "${work}/ids.json" <<'PY'
import json
import sqlite3
import sys

database, ids_path = sys.argv[1:]
ids = json.load(open(ids_path, encoding="utf-8"))
with sqlite3.connect(database) as connection:
    connection.execute(
        "DELETE FROM bookmark_tags WHERE bookmark_id = ? AND tag_id = (SELECT id FROM tags WHERE name = ?)",
        (ids["one"], "beta"),
    )
    connection.execute("DELETE FROM bookmarks WHERE id = ?", (ids["four"],))
PY
start_server
request GET /api/bookmarks/stats '' "${work}/owner-after.response" "${work}/owner-after.status" "${work}/owner.curl"
[[ "$(<"${work}/owner-after.status")" == 200 ]] || fail 'live stats did not return 200'
stop_server
awk '/^\{/{print}' "${output_path}" >"${log_path}"
chmod 600 "${log_path}"

"${uv}" run python - "${work}" "${database_path}" "${output_path}" "${log_path}" <<'PY'
import json
import pathlib
import sys

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

root, database, output_path, log_path = map(pathlib.Path, sys.argv[1:])

def load(name):
    return json.loads((root / name).read_text(encoding="utf-8"))

def require(condition, message):
    if not condition:
        raise SystemExit(message)

def validate_response(openapi, operation, status, body):
    schema = operation["responses"][status]["content"]["application/json"]["schema"]
    registry = Registry().with_resource(
        "urn:track04:openapi",
        Resource.from_contents(openapi, default_specification=DRAFT202012),
    )
    Draft202012Validator({"$id": "urn:track04:openapi", **openapi, **schema}, registry=registry).validate(body)

sentinels = load("sentinels.json")
ids = load("ids.json")
openapi = load("openapi.json")
created = {name: load(f"created-{name}.response") for name in ("one", "two", "three", "four", "other")}
page_one, page_two, max_page = (load(name) for name in ("page-one.response", "page-two.response", "max-page.response"))
owner_before, owner_after, other_stats = (load(name) for name in ("owner-before.response", "owner-after.response", "other-stats.response"))
require([item["id"] for item in page_one["items"] + page_two["items"]] == [ids["four"], ids["three"], ids["two"], ids["one"]], "page order is not stable")
require(page_one["total"] == page_two["total"] == 4, "page totals differ")
require(not ({item["id"] for item in page_one["items"]} & {item["id"] for item in page_two["items"]}), "pages overlap")
require(max_page["page_size"] == 100 and max_page["total"] == 4 and len(max_page["items"]) == 4, "maximum page size failed")
require([item["id"] for item in load("tag.response")["items"]] == [ids["three"], ids["two"]], "tag normalization failed")
require([item["id"] for item in load("created-range.response")["items"]] == [ids["three"], ids["two"]], "created range failed")
require([item["id"] for item in load("created-day.response")["items"]] == [ids["two"], ids["one"]], "calendar-day upper bound failed")
require([item["id"] for item in load("updated-range.response")["items"]] == [ids["three"], ids["two"]], "updated range failed")
require([item["id"] for item in load("case-query.response")["items"]] == [ids["four"], ids["three"], ids["two"], ids["one"]], "ASCII case-insensitive query failed")
require([item["id"] for item in load("literal.response")["items"]] == [ids["one"]], "literal LIKE escaping failed")
require([tag["name"] for tag in created["one"]["tags"]] == ["alpha", "beta"], "created tags are not normalized")
for name in ("reversed-created.response", "reversed-updated.response", "invalid-page.response", "invalid-page-size.response", "too-large-page-size.response"):
    require(load(name)["error"]["code"] == "validation_error", "invalid query body was not safe")
expected_auth = {"error": {"code": "authentication_failed", "message": "Authentication failed.", "details": None}}
require(load("unauth-stats.response") == expected_auth, "unauthorized stats body changed")
require(load("unauth-list.response") == expected_auth, "unauthorized list body changed")
require(load("fault.response") == {"error": {"code": "internal_error", "message": "Internal server error.", "details": None}}, "fault body changed")
require(load("other-list.response")["items"] == [created["other"]] and load("other-list.response")["total"] == 1, "owner isolation failed")
require(owner_before == {"total_bookmarks": 4, "total_tags": 4, "top_tags": [{"name": "alpha", "count": 2}, {"name": "beta", "count": 2}, {"name": "gamma", "count": 2}, {"name": "solo", "count": 1}], "bookmarks_per_month": [{"month": "2026-01", "count": 1}, {"month": "2026-02", "count": 2}, {"month": "2026-03", "count": 1}]}, "initial stats mismatch")
require(owner_after == {"total_bookmarks": 3, "total_tags": 3, "top_tags": [{"name": "alpha", "count": 2}, {"name": "gamma", "count": 2}, {"name": "beta", "count": 1}], "bookmarks_per_month": [{"month": "2026-01", "count": 1}, {"month": "2026-02", "count": 2}]}, "live stats mismatch")
require(other_stats == {"total_bookmarks": 1, "total_tags": 1, "top_tags": [{"name": sentinels["tag"], "count": 1}], "bookmarks_per_month": [{"month": other_stats["bookmarks_per_month"][0]["month"], "count": 1}]}, "cross-user stats mismatch")
stats_headers = (root / "owner-before.headers").read_text(encoding="utf-8").lower()
for forbidden_header in ("etag:", "cache-control:"):
    require(forbidden_header not in stats_headers, "unsupported statistics cache header appeared")

paths = openapi["paths"]
bookmarks = paths["/api/bookmarks"]["get"]
stats = paths["/api/bookmarks/stats"]["get"]
require(bookmarks.get("security") == [{"BearerAuth": []}] and stats.get("security") == [{"BearerAuth": []}], "OpenAPI security changed")
require(set(bookmarks["responses"]) == {"200", "401", "422", "429", "500"}, "list OpenAPI responses changed")
require(set(stats["responses"]) == {"200", "401", "429", "500"}, "stats OpenAPI responses changed")
for operation in (bookmarks, stats):
    rate = operation["responses"]["429"]
    require(set(rate["headers"]) == {"Retry-After", "Cache-Control"}, "rate-limit headers changed")
    require(rate["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorEnvelope"}, "rate-limit schema changed")
require(stats.get("parameters", []) == [], "stats acquired inputs")
parameters = {item["name"]: item for item in bookmarks["parameters"]}
require(set(parameters) == {"tag", "q", "from", "to", "updated_from", "updated_to", "page", "page_size", "pagination", "cursor"}, "list OpenAPI parameters changed")
require(parameters["page"]["schema"] == {"type": "integer", "minimum": 1, "default": 1, "examples": [1], "title": "Page"}, "page contract changed")
require(parameters["page_size"]["schema"] == {"type": "integer", "maximum": 100, "minimum": 1, "default": 20, "examples": [20], "title": "Page Size"}, "page size contract changed")
require(parameters["pagination"]["schema"].get("enum") == ["page", "cursor"] and parameters["pagination"]["schema"].get("default") == "page", "pagination mode contract changed")
require(parameters["cursor"]["schema"].get("maxLength") == 2048, "cursor length contract changed")
require(bookmarks["responses"]["200"]["headers"]["X-Next-Cursor"]["required"] is False, "cursor response header contract changed")
require(parameters["q"]["schema"]["anyOf"][0] == {"type": "string", "maxLength": 200}, "query length contract changed")
require(all(not item.get("required", False) for item in parameters.values()), "optional list parameter became required")
for name in ("from", "to", "updated_from", "updated_to"):
    require(parameters[name]["schema"] == {"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}], "examples": ["2025-01-01" if name.endswith("from") or name == "from" else "2025-12-31"], "title": parameters[name]["schema"]["title"]}, "date parameter contract changed")
validate_response(openapi, bookmarks, "200", max_page)
validate_response(openapi, stats, "200", owner_before)
validate_response(openapi, stats, "401", expected_auth)
validate_response(openapi, bookmarks, "401", expected_auth)
validate_response(openapi, bookmarks, "422", load("invalid-page.response"))

# Pass B owns JSON Lines/source/redaction/retained-artifact scans.  It leaves no
# debug-retention switch: this workspace contains credentials and is always removed.
import datetime as dt
import os
import sqlite3
import stat
import uuid

def strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [entry for item in value.values() for entry in strings(item)]
    if isinstance(value, list):
        return [entry for item in value for entry in strings(item)]
    return []

def validate_exception_tree(exception):
    require({"type", "module", "message", "frames"} <= set(exception), "exception evidence is incomplete")
    require(exception["message"] == "[REDACTED]", "exception evidence exposed its message")
    require(isinstance(exception["type"], str) and isinstance(exception["module"], str), "exception identity is invalid")
    require(isinstance(exception["frames"], list) and exception["frames"], "exception frames are missing")
    for frame in exception["frames"]:
        require({"pathname", "lineno", "package", "module", "function"} <= set(frame), "exception frame lacks source attribution")
        require(frame["pathname"].startswith("/") and isinstance(frame["lineno"], int) and frame["lineno"] > 0, "exception frame location is invalid")
        require(isinstance(frame["package"], str) and frame["package"] and isinstance(frame["module"], str) and frame["module"], "exception frame qualified source is invalid")
    for key in ("cause", "context"):
        if exception.get(key) is not None:
            validate_exception_tree(exception[key])
    for member in exception.get("members", []):
        validate_exception_tree(member)

def protected(path):
    return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0

require(stat.S_IMODE(root.stat().st_mode) == 0o700, "workspace directory permissions are not private")
artifacts = list(root.iterdir())
require(artifacts, "verification artifacts are missing")
for artifact in artifacts:
    require(artifact.is_file() and protected(artifact), "credential or diagnostic artifact is not private")

lines = log_path.read_text(encoding="utf-8").splitlines()
require(lines and all(line.strip() for line in lines), "application output contains blank physical lines")
records = []
for line in lines:
    try:
        records.append(json.loads(line))
    except json.JSONDecodeError as exc:
        raise SystemExit("application output is not strict JSON Lines") from exc
require(records, "application JSON Lines are missing")
for record in records:
    required = {"source", "service", "component", "event", "level", "timestamp", "logger", "process_id", "thread_name", "thread_id"}
    require(required <= set(record), "application log base fields are missing")
    source = record["source"]
    require({"pathname", "lineno", "package", "module", "function"} <= set(source), "log source fields are missing")
    require(source["pathname"].startswith("/") and isinstance(source["lineno"], int) and source["lineno"] > 0, "log source location is invalid")
    require(isinstance(source["package"], str) and source["package"].startswith("app"), "log source package is not qualified")
    require(isinstance(source["module"], str) and source["module"].startswith("app."), "log source module is not qualified")
    for field in ("service", "component", "event", "level", "logger", "thread_name"):
        require(isinstance(record[field], str) and record[field], "log classification field is invalid")
    require(isinstance(record["process_id"], int) and record["process_id"] > 0, "log process id is invalid")
    require(isinstance(record["thread_id"], int) and record["thread_id"] > 0, "log thread execution id is invalid")
    timestamp = dt.datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
    require(timestamp.tzinfo is not None and timestamp.utcoffset() == dt.timedelta(), "log timestamp is not UTC")
    require("exception_message" not in record and "traceback" not in record, "raw exception text was indexed")

events = [record["event"] for record in records]
for lifecycle in ("application.starting", "application.started", "application.stopping", "application.stopped"):
    require(events.count(lifecycle) == 3, "expected lifecycle evidence is incomplete")
faults = [record for record in records if record["event"] == "http.request.unexpected_exception"]
require(len(faults) == 1, "owning fault was not logged exactly once")
fault = faults[0]
require(fault.get("context") == {"method": "GET"}, "owning fault context changed")
validate_exception_tree(fault["exception"])
correlation = fault.get("correlation_id")
require(isinstance(correlation, str) and str(uuid.UUID(correlation)) == correlation, "fault correlation is not a UUID")
for header in (root / "fault.headers").read_text(encoding="utf-8").splitlines():
    name, separator, value = header.partition(":")
    if separator and name.lower() in {"x-correlation-id", "x-request-id"}:
        require(value.strip() == correlation, "exposed fault correlation header disagrees with log evidence")

sensitive = set(sentinels.values()) | {os.environ["DATABASE_URL"], str(database), str(root), (root / "jwt-secret").read_text(encoding="utf-8")}
for artifact in artifacts:
    if artifact.name.startswith(("register-", "bookmark-")) and artifact.suffix == ".json":
        sensitive.update(strings(json.loads(artifact.read_text(encoding="utf-8"))))
for person in ("owner", "other"):
    registration = load(f"register-{person}.response")
    sensitive.add(registration["token"])
    sensitive.update(strings(registration["user"]))
    sensitive.add((root / f"{person}.curl").read_text(encoding="utf-8"))
sensitive.update({"Authorization", "Bearer", "$argon2", "password_hash", "sqlite:///"})
require(correlation not in sensitive, "fault correlation reused sensitive material")
raw_logs = output_path.read_text(encoding="utf-8") + log_path.read_text(encoding="utf-8")
indexed = json.dumps(records, ensure_ascii=False, sort_keys=True)
for value in sensitive:
    require(value not in raw_logs and value not in indexed, "sensitive submitted or credential material leaked to logs")

with sqlite3.connect(database) as connection:
    revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    require(revision is not None and revision[0], "Alembic head is absent")
    bookmark_indexes = {row[1] for row in connection.execute("PRAGMA index_list(bookmarks)")}
    association_indexes = {row[1] for row in connection.execute("PRAGMA index_list(bookmark_tags)")}
    require({"ix_bookmarks_user_created_id", "ix_bookmarks_user_updated_id"} <= bookmark_indexes, "Track 04 bookmark indexes are absent")
    require("ix_bookmark_tags_tag_bookmark" in association_indexes, "Track 04 association index is absent")
    owner_row = connection.execute("SELECT id FROM users WHERE username LIKE 'track04-owner-%'").fetchone()
    require(owner_row is not None, "owner row is absent")
    owner_bookmarks = connection.execute("SELECT count(*) FROM bookmarks WHERE user_id = ?", owner_row).fetchone()[0]
    owner_associations = connection.execute("SELECT count(*) FROM bookmark_tags bt JOIN bookmarks b ON b.id = bt.bookmark_id WHERE b.user_id = ?", owner_row).fetchone()[0]
    require(owner_bookmarks == 3 and owner_associations == 5, "owner data or associations are inconsistent")

repository = (pathlib.Path.cwd() / "app/bookmarks/repository.py").read_text(encoding="utf-8")
service = (pathlib.Path.cwd() / "app/bookmarks/service.py").read_text(encoding="utf-8")
stats_source = (pathlib.Path.cwd() / "app/bookmarks/stats/raw_sql.py").read_text(encoding="utf-8")
require("text(" not in repository and "TextClause" not in repository and "text(" not in service, "ordinary search left the ORM boundary")
require(stats_source.count("text(") == 3 and stats_source.count("WHERE b.user_id = :user_id") == 3, "stats raw SQL boundary or ownership changed")
require("f\"" not in stats_source and "f'" not in stats_source and ".format(" not in stats_source, "stats SQL interpolation appeared")
for prohibited in ("queue", "cache", "dirty", "worker", "history", "stats_snapshot"):
    require(prohibited not in stats_source.lower(), "future Track 06 or 07 behavior appeared")

print("Track 04 evidence: HTTP search and live stats; all JSONL logs, redaction, private artifacts, cleanup, SQLite indexes, and source boundaries verified; no N+1 claim")
PY
