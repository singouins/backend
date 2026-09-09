#!/bin/sh
# PID 1 wrapper for main.py, for debugging.
#
# Starts main.py once. If you `docker exec`/`kubectl exec` in and kill it
# (e.g. `pkill -f main.py`), it is NOT restarted automatically -- this
# script just parks in an idle loop to keep the container alive, so you
# can manually re-run main.py yourself with whatever debug flags/env you
# want, as many times as you want.
#
# A real `docker stop`/`kubectl delete pod` (SIGTERM/SIGINT) is forwarded
# to whatever is currently running and this script then exits too, so
# normal container lifecycle still works.
set -u

STOP=0
CHILD_PID=""

term_handler() {
    STOP=1
    if [ -n "$CHILD_PID" ]; then
        kill -TERM "$CHILD_PID" 2>/dev/null
    fi
}
trap term_handler TERM INT

echo "[entrypoint] starting: python3 /code/main.py" >&2
python3 /code/main.py &
CHILD_PID=$!
wait "$CHILD_PID"
code=$?
echo "[entrypoint] main.py exited (code=$code)" >&2

if [ "$STOP" -eq 0 ]; then
    echo "[entrypoint] not restarting automatically -- container staying alive; exec in and run 'python3 /code/main.py [flags]' manually" >&2
    while [ "$STOP" -eq 0 ]; do
        sleep 3600 &
        CHILD_PID=$!
        wait "$CHILD_PID"
    done
fi

echo "[entrypoint] shutting down" >&2
