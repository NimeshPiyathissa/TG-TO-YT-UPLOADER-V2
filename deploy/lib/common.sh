#!/usr/bin/env bash
# Shared UI, logging (with secret redaction), retry and prompt helpers for install.sh and tgyt.
# Source validate.sh first. shellcheck shell=bash
# shellcheck shell=bash

LOG_FILE="${LOG_FILE:-/var/log/tgyt-install.log}"
NONINTERACTIVE="${NONINTERACTIVE:-0}"
ASSUME_YES="${ASSUME_YES:-0}"
declare -a _SECRETS=()
STEP_NO=0
STEP_TOTAL="${STEP_TOTAL:-0}"

if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'
    C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_DIM=""; C_OFF=""
fi

# ---- redaction --------------------------------------------------------------------------
# Register a literal secret so it is masked everywhere it appears in the log.
register_secret() { [[ -n "${1:-}" ]] && _SECRETS+=("$1"); return 0; }

_sed_escape() { printf '%s' "$1" | sed -e 's/[][\/.^$*+?(){}|&]/\\&/g'; }

redact() {
    local -a args=(
        -E
        -e 's/[0-9]{6,12}:[A-Za-z0-9_-]{30,50}/[REDACTED-BOT-TOKEN]/g'
        -e 's/(USER_SESSION|BOT_TOKEN|API_HASH|SESSION_SECRET|ADMIN_PASSWORD|PASSWORD|SECRET|TOKEN)=[^[:space:]]+/\1=[REDACTED]/g'
        -e 's/[A-Za-z0-9_=-]{120,}/[REDACTED-LONG-STRING]/g'
        -e 's/\b[a-f0-9]{32}\b/[REDACTED-HEX32]/g'
    )
    local s
    for s in "${_SECRETS[@]}"; do
        [[ ${#s} -ge 4 ]] && args+=(-e "s/$(_sed_escape "$s")/[REDACTED]/g")
    done
    sed "${args[@]}"
}

_log_raw() {
    [[ -n "$LOG_FILE" ]] || return 0
    printf '%s %s\n' "$(date '+%F %T')" "$*" | redact >>"$LOG_FILE" 2>/dev/null || true
}

init_log() {
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
    : >>"$LOG_FILE" 2>/dev/null && chmod 600 "$LOG_FILE" 2>/dev/null || true
    _log_raw "===== $(basename "$0") started (pid $$) ====="
}

# ---- output -----------------------------------------------------------------------------
say() { printf '%s\n' "$*"; _log_raw "$*"; }
info() { printf '  %s\n' "$*"; _log_raw "INFO $*"; }
ok() { printf '  %s✔%s %s\n' "$C_GREEN" "$C_OFF" "$*"; _log_raw "OK   $*"; }
warn() { printf '  %s⚠ %s%s\n' "$C_YELLOW" "$*" "$C_OFF" >&2; _log_raw "WARN $*"; }
err() { printf '  %s✖ %s%s\n' "$C_RED" "$*" "$C_OFF" >&2; _log_raw "ERR  $*"; }
dim() { printf '  %s%s%s\n' "$C_DIM" "$*" "$C_OFF"; }

die() {
    err "$1"
    shift
    local line
    for line in "$@"; do printf '    %s\n' "$line" >&2; done
    printf '\n  Full log: %s\n' "$LOG_FILE" >&2
    exit 1
}

step() {
    STEP_NO=$((STEP_NO + 1))
    local bar="" i filled=0
    if ((STEP_TOTAL > 0)); then
        filled=$((STEP_NO * 20 / STEP_TOTAL))
        for ((i = 0; i < 20; i++)); do ((i < filled)) && bar+="█" || bar+="░"; done
        printf '\n%s[%d/%d] %s %s%s\n' "$C_BOLD$C_BLUE" "$STEP_NO" "$STEP_TOTAL" "$bar" "$1" "$C_OFF"
    else
        printf '\n%s==> %s%s\n' "$C_BOLD$C_BLUE" "$1" "$C_OFF"
    fi
    _log_raw "STEP $STEP_NO/$STEP_TOTAL $1"
}

banner() {
    cat <<EOF
${C_BOLD}${C_RED}
  ╔══════════════════════════════════════════════╗
  ║   TG → YT Uploader  ·  installer  v${1:-?}
  ╚══════════════════════════════════════════════╝${C_OFF}
EOF
}

# ---- running commands -------------------------------------------------------------------
# run "description" cmd args...  -> hides output (kept in the log), shows a spinner on a TTY and
# the tail of the output if the command fails. Returns the command's exit code.
run() {
    local desc="$1"
    shift
    local out rc=0 pid i=0 bs="" spin='|/-+'
    [[ -t 1 ]] && bs=$'\b'
    out="$(mktemp)"
    _log_raw "RUN  $desc :: $*"
    printf '  • %s ' "$desc"
    "$@" >"$out" 2>&1 &
    pid=$!
    if [[ -t 1 ]]; then
        while kill -0 "$pid" 2>/dev/null; do
            printf '\b%s' "${spin:i++%4:1}"
            sleep 0.2
        done
    fi
    wait "$pid" || rc=$?
    redact <"$out" >>"$LOG_FILE" 2>/dev/null || true
    if ((rc == 0)); then
        printf '%s%s✔%s\n' "$bs" "$C_GREEN" "$C_OFF"
    else
        printf '%s%s✖%s\n' "$bs" "$C_RED" "$C_OFF"
        err "'$desc' failed (exit $rc). Last lines of output:"
        tail -n 25 "$out" | redact | sed 's/^/      /' >&2
    fi
    rm -f "$out"
    return "$rc"
}

# retry TRIES DELAY desc cmd... -> for flaky network operations.
retry() {
    local tries="$1" delay="$2" desc="$3" n=1
    shift 3
    until run "$desc (attempt $n/$tries)" "$@"; do
        ((n >= tries)) && return 1
        warn "Retrying in ${delay}s..."
        sleep "$delay"
        n=$((n + 1))
    done
}

# ---- prompts ----------------------------------------------------------------------------
# All prompts read from the terminal. In non-interactive mode they never block: they return the
# default or fail loudly.
is_interactive() { [[ "$NONINTERACTIVE" != "1" ]]; }

confirm() {
    # confirm "Question?" [default y|n]
    local q="$1" def="${2:-y}" ans hint="[Y/n]"
    [[ "$def" == "n" ]] && hint="[y/N]"
    # --yes / non-interactive mode accept the *default* answer, so risky questions (default "no") stay "no".
    if [[ "$ASSUME_YES" == "1" ]] || ! is_interactive; then [[ "$def" == "y" ]]; return; fi
    while true; do
        read -r -p "  $q $hint " ans || ans=""
        ans="${ans:-$def}"
        case "${ans,,}" in
            y | yes) return 0 ;;
            n | no) return 1 ;;
        esac
    done
}

# ask VAR "Question" validator [default] [secret] [error message]
# If $VAR is already set and valid (from env vars / the config file) it is used without asking.
# Interactive: keeps asking until valid. Non-interactive: dies when missing or invalid.
ask() {
    local var="$1" question="$2" validator="$3" default="${4:-}" secret="${5:-}" errmsg="${6:-That does not look right, please try again.}"
    local value
    value="${!var:-}"
    if [[ -n "$value" ]]; then
        if "$validator" "$value"; then
            [[ -n "$secret" ]] && register_secret "$value"
            return 0
        fi
        is_interactive || die "Invalid value for $var: $errmsg"
        warn "The preset value for $var is invalid ($errmsg). Please enter it again."
        value=""
    fi
    if ! is_interactive; then
        if [[ -n "$default" ]]; then
            printf -v "$var" '%s' "$default"
            return 0
        fi
        die "$var is required in non-interactive mode." "Set it in the config file or as an environment variable."
    fi
    local shown="" in
    [[ -n "$default" ]] && shown=" [$default]"
    while true; do
        if [[ -n "$secret" ]]; then
            read -r -s -p "  $question$shown: " in || in=""
            echo
        else
            read -r -p "  $question$shown: " in || in=""
        fi
        in="${in:-$default}"
        if [[ -n "$in" ]] && "$validator" "$in"; then
            printf -v "$var" '%s' "$in"
            [[ -n "$secret" ]] && register_secret "$in"
            return 0
        fi
        err "$errmsg"
    done
}

# ask_password VAR "Question"  (hidden, confirmed, strength-checked)
ask_password() {
    local var="$1" question="$2" value pw pw2 problem
    value="${!var:-}"
    if [[ -n "$value" ]]; then
        if problem="$(password_problem "$value")"; then
            register_secret "$value"
            return 0
        fi
        is_interactive || die "Weak admin password: $problem"
        warn "The preset password is too weak ($problem)."
    fi
    is_interactive || die "$var is required in non-interactive mode."
    while true; do
        read -r -s -p "  $question: " pw || pw=""
        echo
        if ! problem="$(password_problem "$pw")"; then
            err "Password $problem."
            continue
        fi
        read -r -s -p "  Repeat the password: " pw2 || pw2=""
        echo
        if [[ "$pw" != "$pw2" ]]; then
            err "The two passwords do not match."
            continue
        fi
        printf -v "$var" '%s' "$pw"
        register_secret "$pw"
        return 0
    done
}

pause() { is_interactive && [[ "$ASSUME_YES" != "1" ]] && read -r -p "  Press Enter to continue... " _ || true; }

# ---- misc -------------------------------------------------------------------------------
need_cmd() { command -v "$1" >/dev/null 2>&1; }

human_bytes() {
    awk -v b="$1" 'BEGIN{split("B KB MB GB TB",u); i=1; while (b>=1024 && i<5){b/=1024;i++} printf "%.1f %s", b, u[i]}'
}

# Wait until a command succeeds or the timeout (seconds) expires.
wait_for() {
    local timeout="$1" interval="$2"
    shift 2
    local waited=0
    until "$@" >/dev/null 2>&1; do
        ((waited >= timeout)) && return 1
        sleep "$interval"
        waited=$((waited + interval))
    done
}
