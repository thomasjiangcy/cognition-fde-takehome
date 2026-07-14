#!/bin/sh

set -eu

cleanup() {
    set +e
    kill -TERM "${api_pid:-}" "${nginx_pid:-}" 2>/dev/null
    wait "${api_pid:-}" "${nginx_pid:-}" 2>/dev/null
}

shutdown() {
    trap - EXIT INT TERM
    cleanup
    exit 0
}

trap cleanup EXIT
trap shutdown INT TERM

uvicorn api.main:app --host 127.0.0.1 --port 8000 --root-path /api &
api_pid=$!

nginx -g "daemon off;" &
nginx_pid=$!

while kill -0 "$api_pid" 2>/dev/null && kill -0 "$nginx_pid" 2>/dev/null; do
    sleep 1
done

status=0
if ! kill -0 "$api_pid" 2>/dev/null; then
    wait "$api_pid" || status=$?
else
    wait "$nginx_pid" || status=$?
fi

exit "$status"
