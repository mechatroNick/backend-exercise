#!/bin/sh
set -eu

if [ "${1:-}" = "migrate-only" ]; then
    exec alembic upgrade head
fi

alembic upgrade head
exec "$@"
