#!/usr/bin/env bash
# Pure input validators and env-file helpers. No side effects, no output, safe to source
# from tests. Every validator returns 0 (valid) or 1 (invalid).
# shellcheck shell=bash

# ---- network / identity -----------------------------------------------------------------
is_ipv4() {
    local ip="$1" o
    [[ "$ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || return 1
    local IFS=.
    for o in $ip; do
        ((10#$o <= 255)) || return 1
    done
    return 0
}

# A fully-qualified, lowercase hostname such as upload.example.com. Rejects IPs, single
# labels, underscores, over-long names and anything with characters that could break a
# config file.
is_domain() {
    local d="$1"
    [[ ${#d} -le 253 ]] || return 1
    is_ipv4 "$d" && return 1
    [[ "$d" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$ ]]
}

is_email() {
    [[ "$1" =~ ^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$ ]]
}

is_port() {
    [[ "$1" =~ ^[0-9]{1,5}$ ]] && ((10#$1 >= 1 && 10#$1 <= 65535))
}

# ---- Telegram ---------------------------------------------------------------------------
is_bot_token() { [[ "$1" =~ ^[0-9]{6,12}:[A-Za-z0-9_-]{30,50}$ ]]; }
is_api_id() { [[ "$1" =~ ^[1-9][0-9]{0,9}$ ]]; }
is_api_hash() { [[ "$1" =~ ^[a-f0-9]{32}$ ]]; }
is_tg_user_id() { [[ "$1" =~ ^[1-9][0-9]{4,14}$ ]]; }
is_relay_chat_id() { [[ "$1" =~ ^-100[0-9]{5,}$ ]]; }
is_session_string() { [[ "$1" =~ ^[A-Za-z0-9_=-]{200,}$ ]]; }

# ---- panel / app settings ---------------------------------------------------------------
is_username() { [[ "$1" =~ ^[A-Za-z0-9_.-]{3,32}$ ]]; }
is_region_code() { [[ "$1" =~ ^[A-Z]{2}$ ]]; }
is_bool() { [[ "$1" == "true" || "$1" == "false" ]]; }
is_positive_int() { [[ "$1" =~ ^[1-9][0-9]{0,11}$ ]]; }
is_log_level() { [[ "$1" =~ ^(DEBUG|INFO|WARNING|ERROR)$ ]]; }
is_privacy() { [[ "$1" =~ ^(private|unlisted|public)$ ]]; }
is_oauth_mode() { [[ "$1" == "hostname" || "$1" == "loopback" ]]; }
# Upload chunks must be a multiple of 256 KiB (Google's resumable-upload rule).
is_chunk_bytes() { [[ "$1" =~ ^[1-9][0-9]*$ ]] && ((10#$1 % 262144 == 0)); }

# Prints nothing and returns 0 when the password is acceptable; otherwise prints the reason
# and returns 1. Mirrors tools/admin_user.py::password_problem.
password_problem() {
    local pw="$1" classes=0 uniq
    if ((${#pw} < 12)); then
        echo "must be at least 12 characters"
        return 1
    fi
    [[ "$pw" =~ [a-z] ]] && classes=$((classes + 1))
    [[ "$pw" =~ [A-Z] ]] && classes=$((classes + 1))
    [[ "$pw" =~ [0-9] ]] && classes=$((classes + 1))
    [[ "$pw" =~ [^A-Za-z0-9] ]] && classes=$((classes + 1))
    if ((classes < 3)); then
        echo "must mix at least 3 of: lowercase, uppercase, digits, symbols"
        return 1
    fi
    uniq=$(printf '%s' "$pw" | fold -w1 | sort -u | wc -l)
    if ((uniq < 6)); then
        echo "uses too few different characters"
        return 1
    fi
    return 0
}

# ---- env file helpers (pure bash; values are never interpolated into sed/awk programs) --
env_get() {
    # env_get FILE KEY -> prints the last value for KEY (empty if absent)
    local file="$1" key="$2" line value=""
    [[ -f "$file" ]] || return 0
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ "$line" == "$key="* ]] && value="${line#"$key"=}"
    done <"$file"
    printf '%s' "$value"
}

env_set() {
    # env_set FILE KEY VALUE -> replaces the first KEY= line or appends one; keeps mode/owner.
    local file="$1" key="$2" value="$3" line replaced=0 tmp
    [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]] && return 1
    tmp="${file}.tmp.$$"
    : >"$tmp" || return 1
    if [[ -f "$file" ]]; then
        while IFS= read -r line || [[ -n "$line" ]]; do
            if ((replaced == 0)) && [[ "$line" == "$key="* ]]; then
                printf '%s=%s\n' "$key" "$value" >>"$tmp"
                replaced=1
            else
                printf '%s\n' "$line" >>"$tmp"
            fi
        done <"$file"
        chmod --reference="$file" "$tmp" 2>/dev/null || chmod 600 "$tmp"
        chown --reference="$file" "$tmp" 2>/dev/null || true
    else
        chmod 600 "$tmp"
    fi
    ((replaced)) || printf '%s=%s\n' "$key" "$value" >>"$tmp"
    mv -f "$tmp" "$file"
}

env_has_key() { [[ -f "$1" ]] && grep -q "^$2=" "$1"; }

# Keys whose values must never be printed or logged.
is_sensitive_key() { [[ "$1" =~ (TOKEN|HASH|SECRET|PASSWORD|SESSION|KEY)$ ]] || [[ "$1" == "USER_SESSION" ]]; }

# Validator name for each setting `tgyt config` is allowed to change (empty = unknown key).
validator_for_key() {
    case "$1" in
        API_ID) echo is_api_id ;;
        API_HASH) echo is_api_hash ;;
        BOT_TOKEN) echo is_bot_token ;;
        OWNER_TG_ID) echo is_tg_user_id ;;
        USER_SESSION) echo is_session_string ;;
        RELAY_CHAT_ID) echo is_relay_chat_id ;;
        PUBLIC_HOST) echo is_domain ;;
        WEB_PORT | LOOPBACK_PORT) echo is_port ;;
        OAUTH_MODE) echo is_oauth_mode ;;
        PROJECT_AUDITED | REQUIRE_TOTP) echo is_bool ;;
        YT_REGION_CODE) echo is_region_code ;;
        ADMIN_USERNAME) echo is_username ;;
        MAX_FILE_BYTES | MAX_CONCURRENT_DOWNLOADS | MAX_CONCURRENT_UPLOADS | JOB_RETENTION_HOURS | MIN_FREE_DISK_BYTES) echo is_positive_int ;;
        UPLOAD_CHUNK_BYTES) echo is_chunk_bytes ;;
        DEFAULT_PRIVACY) echo is_privacy ;;
        LOG_LEVEL) echo is_log_level ;;
        *) echo "" ;;
    esac
}
