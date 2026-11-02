#!/usr/bin/env bash
# TG → YT Uploader — one-command bootstrap.
#
#   curl -fsSL https://raw.githubusercontent.com/NimeshPiyathissa/TG-TO-YT-UPLOADER-V2/main/install.sh | sudo bash
#
# or, from a clone of the repository:
#
#   git clone https://github.com/NimeshPiyathissa/TG-TO-YT-UPLOADER-V2.git && cd "$(basename "$_" .git)" && sudo ./install.sh
#
# This small script only fetches the project into /opt/tgyt-src and hands over to deploy/install.sh
# (the real, interactive installer). Everything it does is visible in that file. Pass options through:
#   curl -fsSL .../install.sh | sudo bash -s -- --config /root/install.conf
#
# Pin a version:  TGYT_REF=v1.0.1  (a tag or branch).  Use a fork:  TGYT_REPO_URL=https://github.com/you/fork.git
set -Eeuo pipefail

TGYT_REPO_URL="${TGYT_REPO_URL:-https://github.com/NimeshPiyathissa/TG-TO-YT-UPLOADER-V2.git}"
TGYT_REF="${TGYT_REF:-main}"
SRC_DIR="/opt/tgyt-src"

fail() { printf '\n  ✖ %s\n\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Please run as root:  curl -fsSL <url> | sudo bash"

# Running from a checkout? Use it directly.
SELF="${BASH_SOURCE[0]:-}"
if [[ -n "$SELF" && -f "$SELF" ]]; then
    HERE="$(cd "$(dirname "$SELF")" && pwd)"
    if [[ -f "$HERE/deploy/install.sh" ]]; then
        exec bash "$HERE/deploy/install.sh" "$@"
    fi
fi

[[ "$TGYT_REPO_URL" != *__GITHUB_REPO__* ]] || fail "This copy of install.sh has no repository configured. Set TGYT_REPO_URL=https://github.com/<you>/<repo>.git"

echo "  → Fetching TG → YT Uploader ($TGYT_REF) ..."
if ! command -v git >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    if ! { apt-get update -y >/dev/null && apt-get install -y git curl ca-certificates >/dev/null; }; then
        fail "Could not install git/curl (network or apt problem)."
    fi
fi

mkdir -p "$(dirname "$SRC_DIR")"
if [[ -d "$SRC_DIR/.git" ]]; then
    git -C "$SRC_DIR" remote set-url origin "$TGYT_REPO_URL"
    git -C "$SRC_DIR" fetch --tags --prune origin || fail "Could not reach $TGYT_REPO_URL"
else
    rm -rf "$SRC_DIR"
    git clone --quiet "$TGYT_REPO_URL" "$SRC_DIR" || fail "Could not download $TGYT_REPO_URL (check the URL and your internet connection)."
fi
if ! git -C "$SRC_DIR" checkout --quiet --force "$TGYT_REF" 2>/dev/null; then
    git -C "$SRC_DIR" checkout --quiet --force "origin/$TGYT_REF" 2>/dev/null || fail "Version '$TGYT_REF' does not exist in the repository."
fi
[[ -f "$SRC_DIR/deploy/install.sh" ]] || fail "Downloaded project is incomplete (deploy/install.sh missing)."

exec bash "$SRC_DIR/deploy/install.sh" "$@"
