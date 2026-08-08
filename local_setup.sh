#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
VENV_ACTIVATE="${PROJECT_DIR}/venv/bin/activate"

BACKEND_SESSION="aoe_backend"
CELERY_SESSION="aoe_celery"

# Ofogh uses port 8000, so AOE uses 8009.
BACKEND_PORT="${BACKEND_PORT:-8009}"

cd "$PROJECT_DIR"

required_commands=(
    screen
    lsof
    pgrep
    ps
    readlink
)

for command_name in "${required_commands[@]}"; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "ERROR: Required command not found: $command_name"
        exit 1
    fi
done

if [[ ! -f "$VENV_ACTIVATE" ]]; then
    echo "ERROR: Python virtual environment not found:"
    echo "  $VENV_ACTIVATE"
    echo
    echo "Create it first with:"
    echo "  python3 -m venv venv"
    exit 1
fi

if ! [[ "$BACKEND_PORT" =~ ^[0-9]+$ ]] \
    || (( BACKEND_PORT < 1 || BACKEND_PORT > 65535 )); then
    echo "ERROR: Invalid BACKEND_PORT: $BACKEND_PORT"
    exit 1
fi

stop_screen_session() {
    local session_name="$1"

    screen -S "$session_name" -X quit >/dev/null 2>&1 || true
}

listener_pids() {
    local port="$1"

    lsof -t \
        -iTCP:"$port" \
        -sTCP:LISTEN \
        2>/dev/null |
        sort -u || true
}

validate_project_gunicorn_pid() {
    local pid="$1"
    local cmdline=""
    local process_dir=""

    cmdline="$(ps -o command= -p "$pid" 2>/dev/null || true)"
    process_dir="$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)"

    if [[ "$cmdline" != *gunicorn* ]] || [[ "$process_dir" != "$PROJECT_DIR" ]]; then
        echo "ERROR: Port $BACKEND_PORT is occupied by another process:"
        echo "  PID: $pid"
        echo "  Working directory: $process_dir"
        echo "  Command: $cmdline"
        echo
        echo "Refusing to kill it."
        exit 1
    fi
}

kill_project_gunicorn_on_port() {
    local port="$1"
    local attempt
    local -a pids=()

    mapfile -t pids < <(listener_pids "$port")

    if (( ${#pids[@]} == 0 )); then
        return 0
    fi

    for pid in "${pids[@]}"; do
        validate_project_gunicorn_pid "$pid"
    done

    echo "Stopping existing AOE Gunicorn processes on port $port..."

    kill -TERM "${pids[@]}" 2>/dev/null || true

    for ((attempt = 0; attempt < 20; attempt++)); do
        mapfile -t pids < <(listener_pids "$port")

        if (( ${#pids[@]} == 0 )); then
            return 0
        fi

        sleep 0.2
    done

    mapfile -t pids < <(listener_pids "$port")

    if (( ${#pids[@]} > 0 )); then
        for pid in "${pids[@]}"; do
            validate_project_gunicorn_pid "$pid"
        done

        echo "Gunicorn did not stop normally; forcing it to stop..."
        kill -KILL "${pids[@]}" 2>/dev/null || true
    fi
}

kill_project_celery_processes() {
    local pid
    local process_dir=""
    local -a candidates=()
    local -a project_pids=()
    local -a remaining_pids=()

    mapfile -t candidates < <(
        pgrep -f \
            'celery.*(-A[[:space:]]+aoe_tour|--app([=[:space:]]+)aoe_tour)' \
            2>/dev/null || true
    )

    for pid in "${candidates[@]}"; do
        process_dir="$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)"

        if [[ "$process_dir" == "$PROJECT_DIR" ]]; then
            project_pids+=("$pid")
        fi
    done

    if (( ${#project_pids[@]} == 0 )); then
        return 0
    fi

    echo "Stopping existing AOE Celery processes..."

    kill -TERM "${project_pids[@]}" 2>/dev/null || true
    sleep 1

    for pid in "${project_pids[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            process_dir="$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)"

            if [[ "$process_dir" == "$PROJECT_DIR" ]]; then
                remaining_pids+=("$pid")
            fi
        fi
    done

    if (( ${#remaining_pids[@]} > 0 )); then
        echo "Some Celery processes are still running; forcing them to stop..."
        kill -KILL "${remaining_pids[@]}" 2>/dev/null || true
    fi
}

start_screen_session() {
    local session_name="$1"
    shift

    local argument
    local command_line=""
    local shell_command=""

    for argument in "$@"; do
        printf -v command_line '%s %q' "$command_line" "$argument"
    done

    printf -v shell_command \
        'cd %q && source %q &&%s; exit_code=$?; echo; echo "[%s] stopped with exit code ${exit_code}"; exec bash -i' \
        "$PROJECT_DIR" \
        "$VENV_ACTIVATE" \
        "$command_line" \
        "$session_name"

    screen -dmS "$session_name" bash -lc "$shell_command"
}

stop_screen_session "$BACKEND_SESSION"
stop_screen_session "$CELERY_SESSION"

sleep 0.5

kill_project_gunicorn_on_port "$BACKEND_PORT"
kill_project_celery_processes

start_screen_session \
    "$BACKEND_SESSION" \
    gunicorn \
    -b "127.0.0.1:${BACKEND_PORT}" \
    -w 2 \
    aoe_tour.wsgi:application \
    --access-logfile - \
    --error-logfile - \
    --timeout 600

start_screen_session \
    "$CELERY_SESSION" \
    celery \
    -A aoe_tour \
    worker \
    -l info \
    -B \
    -S django

sleep 1

echo
echo "AOE Tour started:"
echo "  Backend: http://127.0.0.1:${BACKEND_PORT}"
echo
echo "Screen sessions:"
echo "  screen -r ${BACKEND_SESSION}"
echo "  screen -r ${CELERY_SESSION}"
echo
echo "List all sessions:"
echo "  screen -ls"