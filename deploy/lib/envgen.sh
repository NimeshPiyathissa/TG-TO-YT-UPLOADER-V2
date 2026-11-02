#!/usr/bin/env bash
# Writes the installer's answers into an env file (created from .env.example). Kept separate from
# install.sh so the exact same code can be unit-tested. Requires validate.sh (env_set).
# shellcheck shell=bash

# apply_install_settings ENV_FILE
# Reads: API_ID API_HASH BOT_TOKEN OWNER_ID OAUTH_MODE PUBLIC_IP DOMAIN WEB_PORT ADMIN_USER REQUIRE_TOTP
#        REGION MAX_FILE_BYTES FERNET_KEY_PATH DATA_DIR  and optionally USER_SESSION RELAY_CHAT_ID
# shellcheck disable=SC2154  # the variables above are provided by the caller
apply_install_settings() {
    local f="$1"
    env_set "$f" API_ID "$API_ID"
    env_set "$f" API_HASH "$API_HASH"
    env_set "$f" BOT_TOKEN "$BOT_TOKEN"
    env_set "$f" OWNER_TG_ID "$OWNER_ID"
    env_set "$f" OAUTH_MODE "$OAUTH_MODE"
    env_set "$f" PUBLIC_IP "$PUBLIC_IP"
    env_set "$f" PUBLIC_HOST "$DOMAIN"
    env_set "$f" WEB_PORT "$WEB_PORT"
    env_set "$f" ADMIN_USERNAME "$ADMIN_USER"
    env_set "$f" ADMIN_PASSWORD ""          # never stored: the admin is created directly in the database
    env_set "$f" REQUIRE_TOTP "$REQUIRE_TOTP"
    env_set "$f" YT_REGION_CODE "$REGION"
    env_set "$f" MAX_FILE_BYTES "$MAX_FILE_BYTES"
    env_set "$f" FERNET_KEY_PATH "$FERNET_KEY_PATH"
    env_set "$f" JOBS_DIR "$DATA_DIR/jobs"
    env_set "$f" DB_PATH "$DATA_DIR/tgyt.db"
    # Relay values come from a preset config only. Never blank an existing relay when re-running the installer;
    # `tgyt relay` is what fills them in otherwise.
    [[ -n "${USER_SESSION:-}" ]] && env_set "$f" USER_SESSION "$USER_SESSION"
    [[ -n "${RELAY_CHAT_ID:-}" ]] && env_set "$f" RELAY_CHAT_ID "$RELAY_CHAT_ID"
    return 0
}
