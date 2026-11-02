#!/usr/bin/env bash
# TG → YT Uploader — interactive, idempotent installer for Ubuntu 22.04 / 24.04 / 26.04.
#
#   sudo ./install.sh                        interactive wizard
#   sudo ./install.sh --config my.conf       non-interactive (see deploy/install.conf.example)
#   TGYT_DOMAIN=... TGYT_BOT_TOKEN=... sudo -E ./install.sh --non-interactive
#
# Safe to re-run: existing settings, the database, the Fernet key and the env file are never
# overwritten without an explicit choice. A full log (secrets redacted) is written to
# /var/log/tgyt-install.log.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/validate.sh
source "$SCRIPT_DIR/lib/validate.sh"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=lib/envgen.sh
source "$SCRIPT_DIR/lib/envgen.sh"

VERSION="$(tr -d '[:space:]' <"$REPO_DIR/VERSION" 2>/dev/null || echo dev)"
INSTALL_DIR="/opt/tgyt-uploader"
SRC_DIR="/opt/tgyt-src"
DATA_DIR="/var/lib/tgyt"
ENV_DIR="/etc/tgyt"
ENV_FILE="$ENV_DIR/tgyt.env"
TLS_DIR="$ENV_DIR/tls"
FERNET_KEY_PATH="$ENV_DIR/fernet.key"
BACKUP_DIR="/var/backups/tgyt"
SERVICE_USER="tgyt"
# shellcheck disable=SC2034
STEP_TOTAL=13
LOG_FILE="/var/log/tgyt-install.log"

usage() {
    cat <<EOF
TG → YT Uploader installer v$VERSION

Usage: sudo ./install.sh [options]
  --config FILE        read answers from FILE (KEY=VALUE lines, see deploy/install.conf.example)
  --non-interactive    never prompt; fail if a required value is missing
  -y, --yes            answer "yes" to confirmations
  -h, --help           show this help

Supported systems: Ubuntu 24.04 LTS and 26.04 LTS (tested), 22.04 LTS, x86_64 or arm64.
EOF
}

# ---------------------------------------------------------------------------------------
# Arguments and non-interactive configuration
# ---------------------------------------------------------------------------------------
CONFIG_FILE=""
while (($#)); do
    case "$1" in
        --config) CONFIG_FILE="${2:-}"; shift 2 ;;
        --config=*) CONFIG_FILE="${1#*=}"; shift ;;
        --non-interactive) NONINTERACTIVE=1; shift ;;
        -y | --yes) ASSUME_YES=1; shift ;;
        -h | --help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

ALLOWED_CONFIG_KEYS=" TGYT_ACCESS_MODE TGYT_DOMAIN TGYT_PUBLIC_IP TGYT_LE_EMAIL TGYT_BOT_TOKEN TGYT_API_ID TGYT_API_HASH \
TGYT_OWNER_ID TGYT_ADMIN_USER TGYT_ADMIN_PASSWORD TGYT_REQUIRE_TOTP TGYT_REGION TGYT_WEB_PORT TGYT_MAX_FILE_BYTES \
TGYT_USER_SESSION TGYT_RELAY_CHAT_ID TGYT_SETUP_RELAY TGYT_ENABLE_FIREWALL TGYT_ENABLE_FAIL2BAN TGYT_HARDEN_SSH \
TGYT_SSH_KEY_CONFIRMED TGYT_SKIP_DNS_CHECK TGYT_LE_STAGING TGYT_SKIP_CERT TGYT_RECONFIGURE TGYT_BACKUP_SCHEDULE \
TGYT_FORCE_OS TGYT_NONINTERACTIVE "

load_config_file() {
    local file="$1" line key value n=0
    [[ -r "$file" ]] || die "Cannot read config file: $file"
    while IFS= read -r line || [[ -n "$line" ]]; do
        n=$((n + 1))
        line="${line%$'\r'}"
        [[ -z "${line//[[:space:]]/}" || "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" =~ ^[[:space:]]*(TGYT_[A-Z_]+)=(.*)$ ]] || die "$file line $n: expected KEY=VALUE"
        key="${BASH_REMATCH[1]}"
        value="${BASH_REMATCH[2]}"
        [[ "$ALLOWED_CONFIG_KEYS" == *" $key "* ]] || die "$file line $n: unknown setting $key"
        value="${value#\"}"; value="${value%\"}"; value="${value#\'}"; value="${value%\'}"
        # real environment variables win over the file
        [[ -n "${!key:-}" ]] || printf -v "$key" '%s' "$value"
    done <"$file"
}

if [[ -n "$CONFIG_FILE" ]]; then
    load_config_file "$CONFIG_FILE"
    NONINTERACTIVE=1
fi
[[ "${TGYT_NONINTERACTIVE:-}" == "1" ]] && NONINTERACTIVE=1

# Interactive prompts must read from the terminal even under `curl ... | sudo bash`.
if [[ "$NONINTERACTIVE" != "1" && ! -t 0 ]]; then
    if { exec </dev/tty; } 2>/dev/null; then :; else
        NONINTERACTIVE=1
    fi
fi

# Map TGYT_* settings onto the internal variables used below.
ACCESS_MODE="${TGYT_ACCESS_MODE:-}"        # domain | sslip | loopback
DOMAIN="${TGYT_DOMAIN:-}"
PUBLIC_IP="${TGYT_PUBLIC_IP:-}"
LE_EMAIL="${TGYT_LE_EMAIL:-}"
BOT_TOKEN="${TGYT_BOT_TOKEN:-}"
API_ID="${TGYT_API_ID:-}"
API_HASH="${TGYT_API_HASH:-}"
OWNER_ID="${TGYT_OWNER_ID:-}"
ADMIN_USER="${TGYT_ADMIN_USER:-}"
ADMIN_PASSWORD="${TGYT_ADMIN_PASSWORD:-}"
REQUIRE_TOTP="${TGYT_REQUIRE_TOTP:-}"
REGION="${TGYT_REGION:-}"
WEB_PORT="${TGYT_WEB_PORT:-}"
MAX_FILE_BYTES="${TGYT_MAX_FILE_BYTES:-}"
USER_SESSION="${TGYT_USER_SESSION:-}"
RELAY_CHAT_ID="${TGYT_RELAY_CHAT_ID:-}"
SETUP_RELAY="${TGYT_SETUP_RELAY:-}"
ENABLE_FIREWALL="${TGYT_ENABLE_FIREWALL:-}"
ENABLE_FAIL2BAN="${TGYT_ENABLE_FAIL2BAN:-}"
HARDEN_SSH="${TGYT_HARDEN_SSH:-}"
BACKUP_SCHEDULE="${TGYT_BACKUP_SCHEDULE:-}"
OAUTH_MODE=""
KEEP_EXISTING=0
CERT_OK=0
export NONINTERACTIVE ASSUME_YES

[[ $EUID -eq 0 ]] || {
    echo "This installer must run as root. Try:  sudo ./install.sh" >&2
    exit 1
}
init_log
register_secret "$BOT_TOKEN"; register_secret "$API_HASH"; register_secret "$ADMIN_PASSWORD"; register_secret "$USER_SESSION"
# shellcheck disable=SC2154
trap 'rc=$?; err "Installer stopped on line $LINENO (exit $rc)."; printf "  Full log: %s\n  Re-running the installer is safe; it continues where it can.\n" "$LOG_FILE" >&2' ERR

banner "$VERSION"

# ---------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------
# Run a command as the service user from a directory it can read (sudo -u fails if the cwd is e.g. /root).
as_service() { (cd "$INSTALL_DIR" 2>/dev/null || cd /tmp; sudo -u "$SERVICE_USER" "$@"); }

web_suffix() { [[ "$WEB_PORT" == "443" ]] && echo "" || echo ":$WEB_PORT"; }

detect_public_ip() {
    local ip svc
    for svc in https://api.ipify.org https://ifconfig.me https://icanhazip.com; do
        ip="$(curl -4fsS --max-time 6 "$svc" 2>/dev/null | tr -d '[:space:]' || true)"
        if is_ipv4 "$ip"; then echo "$ip"; return 0; fi
    done
    return 1
}

dns_a_records() {
    # prints the distinct IPv4 A records for $1 seen via public resolvers and the system resolver
    local host="$1" r
    {
        for r in 1.1.1.1 8.8.8.8; do dig +short +time=3 +tries=1 A "$host" "@$r" 2>/dev/null || true; done
        getent ahostsv4 "$host" 2>/dev/null | awk '{print $1}' || true
    } | grep -E '^[0-9]+(\.[0-9]+){3}$' | sort -u || true
}

telegram_getme() {
    # prints the bot username on success
    curl -fsS --max-time 15 "https://api.telegram.org/bot$1/getMe" 2>/dev/null |
        python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["result"]["username"]) if d.get("ok") else sys.exit(1)'
}

# ---------------------------------------------------------------------------------------
step "Checking your server"
# ---------------------------------------------------------------------------------------
check_server() {
    local os_id="" os_ver="" arch ram_mb disk_gb
    # shellcheck disable=SC1091
    [[ -r /etc/os-release ]] && os_id="$(. /etc/os-release && echo "${ID:-}")" && os_ver="$(. /etc/os-release && echo "${VERSION_ID:-}")"
    if [[ "$os_id" != "ubuntu" || ! "$os_ver" =~ ^(22\.04|24\.04|26\.04)$ ]]; then
        if [[ "${TGYT_FORCE_OS:-}" == "1" ]]; then
            warn "Unsupported OS ($os_id $os_ver); continuing because TGYT_FORCE_OS=1."
        else
            die "Unsupported operating system: ${os_id:-unknown} ${os_ver:-}." \
                "Supported: Ubuntu 24.04 LTS and 26.04 LTS (tested), and 22.04 LTS." \
                "Create a new VPS with Ubuntu 24.04 or 26.04 and run the installer again."
        fi
    else
        ok "Operating system: Ubuntu $os_ver"
    fi
    arch="$(uname -m)"
    [[ "$arch" == "x86_64" || "$arch" == "aarch64" ]] || die "Unsupported CPU architecture: $arch" "Supported: x86_64 and aarch64 (arm64)."
    ok "CPU architecture: $arch"
    [[ -d /run/systemd/system ]] || die "systemd is not running on this machine." "This installer needs a normal Ubuntu VPS (not a minimal container)."

    ram_mb="$(awk '/^MemTotal:/{printf "%d", $2/1024}' /proc/meminfo)"
    if ((ram_mb < 900)); then
        die "Only ${ram_mb} MB of RAM detected." "At least 1 GB is required (2 GB recommended for large videos)."
    elif ((ram_mb < 1800)); then
        warn "${ram_mb} MB RAM: workable, but a 2 GB swap file will be added. 2 GB RAM is recommended."
    else
        ok "Memory: ${ram_mb} MB"
    fi

    disk_gb="$(df -BG --output=avail / | tail -n1 | tr -dc '0-9')"
    if ((disk_gb < 8)); then
        die "Only ${disk_gb} GB of free disk space on /." "At least 8 GB is required; 25 GB+ is recommended because every video is stored on disk while it uploads."
    elif ((disk_gb < 20)); then
        warn "${disk_gb} GB free: fine to start, but a 4 GB video needs about 5 GB plus the 5 GB safety margin."
    else
        ok "Free disk space: ${disk_gb} GB"
    fi

    if need_cmd apt-get; then
        retry 3 5 "Installing installer prerequisites (curl, dig, rsync)" \
            bash -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update -y && apt-get install -y --no-install-recommends curl ca-certificates bind9-dnsutils rsync openssl git iproute2 python3'
    fi
    run "Checking internet access (Telegram, PyPI, Let's Encrypt)" \
        bash -c 'curl -fsS --max-time 15 -o /dev/null https://api.telegram.org && curl -fsS --max-time 15 -o /dev/null https://pypi.org/simple/ && curl -fsS --max-time 15 -o /dev/null https://acme-v02.api.letsencrypt.org/directory' ||
        die "This server cannot reach the internet services it needs." \
            "Check the VPS network / outbound firewall and DNS (try: curl -I https://api.telegram.org)."

    local busy
    busy="$(ss -ltnpH 'sport = :80 or sport = :443' 2>/dev/null | grep -v nginx | head -n3 || true)"
    if [[ -n "$busy" ]]; then
        warn "Something other than nginx is already listening on port 80/443:"
        printf '      %s\n' "$busy" >&2
        confirm "Continue anyway? (certificate issuance will probably fail)" n || die "Stop that service (e.g. 'sudo systemctl disable --now apache2') and run the installer again."
    fi
    if [[ -f /var/lib/dpkg/lock-frontend ]] && fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; then
        die "Another package manager (apt/unattended-upgrades) is running." "Wait a minute and run the installer again."
    fi
}
check_server

PUBLIC_IP="${PUBLIC_IP:-$(detect_public_ip || true)}"
if [[ -z "$PUBLIC_IP" ]] || ! is_ipv4 "$PUBLIC_IP"; then
    PUBLIC_IP=""
    ask PUBLIC_IP "Could not detect this server's public IPv4 address. Enter it" is_ipv4 "" "" "Enter an IPv4 address such as 203.0.113.10."
fi
ok "Public IP address of this server: $PUBLIC_IP"

# ---------------------------------------------------------------------------------------
step "Your settings"
# ---------------------------------------------------------------------------------------
if [[ -f "$ENV_FILE" ]]; then
    say ""
    say "  An existing installation was found ($ENV_FILE)."
    if [[ "${TGYT_RECONFIGURE:-}" == "yes" ]]; then
        KEEP_EXISTING=0
    elif ! is_interactive || [[ "$ASSUME_YES" == "1" ]]; then
        KEEP_EXISTING=1
    else
        say "    1) Keep my settings and just repair / update the installation   (recommended)"
        say "    2) Change some settings (I will ask the questions again)"
        say "    3) Cancel"
        CHOICE=""
        while [[ ! "$CHOICE" =~ ^[123]$ ]]; do read -r -p "  Choose 1, 2 or 3 [1]: " CHOICE || CHOICE=1; CHOICE="${CHOICE:-1}"; done
        case "$CHOICE" in 1) KEEP_EXISTING=1 ;; 2) KEEP_EXISTING=0 ;; 3) say "  Nothing changed."; exit 0 ;; esac
    fi
fi

load_existing_settings() {
    OAUTH_MODE="$(env_get "$ENV_FILE" OAUTH_MODE)"; OAUTH_MODE="${OAUTH_MODE:-hostname}"
    DOMAIN="$(env_get "$ENV_FILE" PUBLIC_HOST)"
    WEB_PORT="$(env_get "$ENV_FILE" WEB_PORT)"; WEB_PORT="${WEB_PORT:-443}"
    BOT_TOKEN="$(env_get "$ENV_FILE" BOT_TOKEN)"
    register_secret "$BOT_TOKEN"; register_secret "$(env_get "$ENV_FILE" API_HASH)"
    register_secret "$(env_get "$ENV_FILE" USER_SESSION)"; register_secret "$(env_get "$ENV_FILE" SESSION_SECRET)"
}

gather_config() {
    local sslip_host
    sslip_host="${PUBLIC_IP//./-}.sslip.io"
    say ""
    say "  I will ask a few questions. Each one explains where to find the answer."
    say "  Secrets you type are hidden and never written to the log."

    # ---- how people reach the panel
    say ""
    say "${C_BOLD}  1. Web address of the admin panel${C_OFF}"
    say "     Google only accepts a real hostname (not a bare IP) for sign-in, so the panel needs one."
    say "       1) My own domain or subdomain, e.g. upload.example.com        (recommended)"
    say "       2) A free hostname from sslip.io  ($sslip_host) - no domain purchase needed"
    say "       3) Advanced: no hostname at all (self-signed certificate + SSH tunnel for linking)"
    if [[ -z "$ACCESS_MODE" ]]; then
        if [[ -n "$DOMAIN" ]]; then ACCESS_MODE=domain
        elif is_interactive; then
            local c=""
            while [[ ! "$c" =~ ^[123]$ ]]; do read -r -p "  Choose 1, 2 or 3 [1]: " c || c=1; c="${c:-1}"; done
            case "$c" in 1) ACCESS_MODE=domain ;; 2) ACCESS_MODE=sslip ;; 3) ACCESS_MODE=loopback ;; esac
        else
            die "TGYT_ACCESS_MODE (domain | sslip | loopback) or TGYT_DOMAIN is required in non-interactive mode."
        fi
    fi
    case "$ACCESS_MODE" in
        domain)
            OAUTH_MODE=hostname
            say "     Enter the full name, e.g. upload.example.com (lowercase, no https://, no path)."
            ask DOMAIN "Domain / subdomain" is_domain "" "" "Enter a full lowercase hostname like upload.example.com (not an IP address)."
            ;;
        sslip) OAUTH_MODE=hostname; DOMAIN="$sslip_host"; ok "Using $DOMAIN" ;;
        loopback) OAUTH_MODE=loopback; DOMAIN=""; ;;
        *) die "TGYT_ACCESS_MODE must be domain, sslip or loopback (got '$ACCESS_MODE')." ;;
    esac
    WEB_PORT="${WEB_PORT:-443}"
    is_port "$WEB_PORT" || die "Invalid web port: $WEB_PORT"

    # ---- DNS check
    if [[ "$ACCESS_MODE" == "domain" ]]; then
        check_dns_interactive
    fi

    # ---- certificate email
    if [[ "$OAUTH_MODE" == "hostname" ]]; then
        say ""
        say "${C_BOLD}  2. Email for Let's Encrypt (free HTTPS certificate)${C_OFF}"
        say "     Used only for expiry warnings. Leave empty to skip."
        if [[ -z "$LE_EMAIL" ]] && is_interactive; then
            read -r -p "  Email (optional): " LE_EMAIL || LE_EMAIL=""
        fi
        while [[ -n "$LE_EMAIL" ]] && ! is_email "$LE_EMAIL"; do
            is_interactive || die "Invalid TGYT_LE_EMAIL."
            err "That is not a valid email address."
            read -r -p "  Email (optional, Enter to skip): " LE_EMAIL || LE_EMAIL=""
        done
    fi

    # ---- Telegram
    say ""
    say "${C_BOLD}  3. Telegram bot token${C_OFF}"
    say "     In Telegram open @BotFather -> /newbot (or /mybots -> your bot -> API Token). It looks like"
    say "     123456789:AAH... — I check it with Telegram right now."
    while true; do
        ask BOT_TOKEN "Bot token (hidden)" is_bot_token "" secret "That is not a bot token. It looks like 123456789:AAH-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx."
        if BOT_USERNAME="$(telegram_getme "$BOT_TOKEN")"; then
            ok "Telegram accepted the token: bot is @$BOT_USERNAME"
            break
        fi
        err "Telegram rejected this token (revoked, mistyped, or no connection)."
        is_interactive || die "Bot token rejected by Telegram."
        BOT_TOKEN=""
    done

    say ""
    say "${C_BOLD}  4. Telegram API ID and API hash${C_OFF}"
    say "     Go to https://my.telegram.org -> log in -> 'API development tools' -> create an app"
    say "     (any name). Copy 'App api_id' (digits) and 'App api_hash' (32 characters)."
    ask API_ID "API ID (digits)" is_api_id "" "" "The API ID is a number, e.g. 1234567."
    ask API_HASH "API hash (hidden)" is_api_hash "" secret "The API hash is 32 lowercase letters/digits (0-9, a-f)."

    say ""
    say "${C_BOLD}  5. Your Telegram user ID (you become the bot's owner)${C_OFF}"
    say "     Open Telegram, message @userinfobot and copy the number after 'Id:'."
    ask OWNER_ID "Your numeric Telegram ID" is_tg_user_id "" "" "The ID is a number such as 123456789."

    # ---- panel account
    say ""
    say "${C_BOLD}  6. Admin panel login${C_OFF}"
    ask ADMIN_USER "Admin username" is_username "admin" "" "3-32 characters: letters, digits, dot, dash, underscore."
    say "     Password: at least 12 characters, mixing 3 of lowercase / UPPERCASE / digits / symbols."
    ask_password ADMIN_PASSWORD "Admin password (hidden)"
    say "     Two-factor login (TOTP) asks for a 6-digit code from an authenticator app (Google Authenticator,"
    say "     Aegis, 1Password...) at every login. Strongly recommended for a public server."
    if [[ -z "$REQUIRE_TOTP" ]]; then
        if confirm "Require two-factor (TOTP) for the panel?" y; then REQUIRE_TOTP=true; else REQUIRE_TOTP=false; fi
    fi
    is_bool "$REQUIRE_TOTP" || die "TGYT_REQUIRE_TOTP must be true or false."

    # ---- region + limits
    say ""
    say "${C_BOLD}  7. YouTube region and limits${C_OFF}"
    say "     The 2-letter country code YouTube uses for category lists (US, GB, LK, IN, DE ...)."
    ask REGION "YouTube region code" is_region_code "US" "" "Use two capital letters, e.g. US."
    say "     Largest video the bot will accept. 2 GB works for every Telegram account;"
    say "     4 GB needs Telegram Premium on the relay account (set up next; I can detect it automatically)."
    ask MAX_FILE_BYTES "Max file size in bytes" is_positive_int "2147483648" "" "Enter a number of bytes, e.g. 2147483648 for 2 GB."

    # ---- relay
    say ""
    say "${C_BOLD}  8. Large-file relay (videos over 20 MB)${C_OFF}"
    say "     Telegram bots can only download 20 MB. For bigger files a second, real Telegram account logs in"
    say "     and downloads them through a private channel. Without it, videos over 20 MB are rejected."
    say "     You need: a private channel containing that account, with your bot added as an administrator."
    if [[ -z "$SETUP_RELAY" ]]; then
        if [[ -n "$USER_SESSION" ]]; then SETUP_RELAY=preset
        elif confirm "Set up the relay now? (you can also do it later with: sudo tgyt relay)" y; then SETUP_RELAY=yes; else SETUP_RELAY=no; fi
    fi

    # ---- security extras
    say ""
    say "${C_BOLD}  9. Protection${C_OFF}"
    say "     Firewall (ufw): only SSH, 80 (certificates) and the panel port are reachable."
    say "     fail2ban: temporarily blocks IPs that keep guessing SSH passwords."
    [[ -n "$ENABLE_FIREWALL" ]] || { confirm "Enable the firewall?" y && ENABLE_FIREWALL=yes || ENABLE_FIREWALL=no; }
    [[ -n "$ENABLE_FAIL2BAN" ]] || { confirm "Enable fail2ban?" y && ENABLE_FAIL2BAN=yes || ENABLE_FAIL2BAN=no; }
    [[ -n "$BACKUP_SCHEDULE" ]] || { confirm "Back up the database and keys automatically every night?" y && BACKUP_SCHEDULE=yes || BACKUP_SCHEDULE=no; }

    # ---- summary
    say ""
    say "${C_BOLD}  Summary${C_OFF}"
    info "Panel address : $( [[ "$OAUTH_MODE" == hostname ]] && echo "https://$DOMAIN$(web_suffix)" || echo "https://$PUBLIC_IP$(web_suffix) (self-signed)" )"
    info "Bot           : @${BOT_USERNAME:-?}   owner ID $OWNER_ID"
    info "Panel login   : $ADMIN_USER  (TOTP: $REQUIRE_TOTP)"
    info "Region / limit: $REGION / $(human_bytes "$MAX_FILE_BYTES")"
    info "Relay         : $SETUP_RELAY     Firewall: $ENABLE_FIREWALL     fail2ban: $ENABLE_FAIL2BAN     nightly backup: $BACKUP_SCHEDULE"
    confirm "Everything correct? Start the installation" y || die "Cancelled. Nothing has been installed. Run the installer again to start over."
}

check_dns_interactive() {
    local found attempt=0 choice
    [[ "${TGYT_SKIP_DNS_CHECK:-}" == "1" ]] && { warn "DNS check skipped (TGYT_SKIP_DNS_CHECK=1)."; return 0; }
    say ""
    say "  Checking that $DOMAIN points to this server ($PUBLIC_IP)..."
    while true; do
        found="$(dns_a_records "$DOMAIN" | tr '\n' ' ')"
        found="${found% }"
        if [[ " $found " == *" $PUBLIC_IP "* ]] && [[ "$(echo "$found" | wc -w)" -eq 1 ]]; then
            ok "$DOMAIN -> $PUBLIC_IP"
            return 0
        fi
        if [[ " $found " == *" $PUBLIC_IP "* ]]; then
            warn "$DOMAIN resolves to several addresses ($found). Remove the others, or certificate issuance may fail."
            return 0
        fi
        if [[ -z "$found" ]]; then
            warn "$DOMAIN does not resolve yet (no A record found)."
        else
            warn "$DOMAIN currently points to: $found   (this server is $PUBLIC_IP)"
            say "     If you use Cloudflare, set the record to 'DNS only' (grey cloud), not proxied."
        fi
        say ""
        say "     Add this record at your domain registrar / DNS provider:"
        say "         Type: A     Name: ${DOMAIN%%.*}  (the part before the first dot; use @ for a bare domain)"
        say "         Value: $PUBLIC_IP     TTL: 300 (or Auto)"
        is_interactive || die "DNS for $DOMAIN does not point to $PUBLIC_IP." "Create the A record, wait a few minutes, and run again (or set TGYT_SKIP_DNS_CHECK=1 to override)."
        say ""
        say "     [Enter] check again   [w] wait and re-check automatically (up to 10 min)   [s] skip this check   [q] quit"
        read -r -p "  Your choice: " choice || choice=q
        case "${choice,,}" in
            w)
                attempt=0
                while ((attempt < 40)); do
                    sleep 15; attempt=$((attempt + 1))
                    found="$(dns_a_records "$DOMAIN" | tr '\n' ' ')"
                    printf '    ...checking (%d/40): %s\n' "$attempt" "${found:-no record yet}"
                    [[ " $found " == *" $PUBLIC_IP "* ]] && break
                done ;;
            s) warn "Skipping the DNS check. HTTPS certificate issuance will fail unless the record is correct."; return 0 ;;
            q) die "Stopped. Add the DNS record and run the installer again." ;;
        esac
    done
}

if ((KEEP_EXISTING)); then
    ENABLE_FIREWALL="${ENABLE_FIREWALL:-keep}"; ENABLE_FAIL2BAN="${ENABLE_FAIL2BAN:-keep}"
    BACKUP_SCHEDULE="${BACKUP_SCHEDULE:-keep}"; SETUP_RELAY="${SETUP_RELAY:-keep}"; HARDEN_SSH="${HARDEN_SSH:-no}"
    load_existing_settings
    ok "Keeping the existing settings (${OAUTH_MODE} mode${DOMAIN:+, $DOMAIN})."
    ACCESS_MODE="${ACCESS_MODE:-keep}"
else
    gather_config
fi

# ---------------------------------------------------------------------------------------
step "Installing system packages"
# ---------------------------------------------------------------------------------------
PKGS=(python3 python3-venv python3-pip python3-dev build-essential ffmpeg nginx certbot git openssl curl rsync bind9-dnsutils ufw fail2ban python3-systemd sqlite3)
retry 3 10 "Installing ${#PKGS[@]} packages (a few minutes on a new server)" \
    bash -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update -y && apt-get install -y "$@"' _ "${PKGS[@]}" ||
    die "Package installation failed." "Look at the last lines above; usually a network blip or a busy apt lock. Run the installer again."
ok "Python $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])'), nginx $(nginx -v 2>&1 | cut -d/ -f2), ffmpeg present"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || die "Python 3.10 or newer is required."

# ---------------------------------------------------------------------------------------
step "Creating the service user and folders"
# ---------------------------------------------------------------------------------------
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir /home/tgyt --shell /usr/sbin/nologin "$SERVICE_USER"
    ok "Created system user '$SERVICE_USER' (no login shell)"
else
    ok "System user '$SERVICE_USER' already exists"
fi
usermod -aG systemd-journal "$SERVICE_USER"   # lets the panel's Logs page read the service journal
# Deliberately NOT relocating data to /mnt or any "bigger" disk: on many clouds that is ephemeral storage.
mkdir -p "$DATA_DIR/jobs" "$ENV_DIR" "$BACKUP_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"; chmod 0750 "$DATA_DIR"
# The app rewrites the env file in place (tmp file + rename) from the panel, so the service group needs write access to the dir.
chown root:"$SERVICE_USER" "$ENV_DIR"; chmod 0770 "$ENV_DIR"
chmod 0700 "$BACKUP_DIR"
install -m 0644 "$REPO_DIR/deploy/tmpfiles.conf" /etc/tmpfiles.d/tgyt.conf
systemd-tmpfiles --create /etc/tmpfiles.d/tgyt.conf || true
ok "Data folder $DATA_DIR (real disk, mode 0750), config folder $ENV_DIR"

RAM_MB="$(awk '/^MemTotal:/{printf "%d", $2/1024}' /proc/meminfo)"
if ((RAM_MB < 1800)) && [[ ! -f /swapfile ]] && ! swapon --show --noheadings | grep -q .; then
    if run "Creating a 2 GB swap file (low-memory server)" bash -c 'fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048; chmod 600 /swapfile; mkswap /swapfile; swapon /swapfile'; then
        grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
    fi
fi

# ---------------------------------------------------------------------------------------
step "Installing the application files"
# ---------------------------------------------------------------------------------------
# Keep a git checkout in $SRC_DIR so `tgyt update` can pull new versions.
if [[ "$(readlink -f "$REPO_DIR")" != "$(readlink -f "$SRC_DIR")" ]]; then
    mkdir -p "$SRC_DIR"
    rsync -a --delete --exclude '__pycache__' --exclude '.pytest_cache' "$REPO_DIR/" "$SRC_DIR/"
fi
mkdir -p "$INSTALL_DIR"
rsync -a --delete --exclude 'venv' --exclude '.venv' --exclude '.git' --exclude '__pycache__' --exclude '.pytest_cache' \
    --exclude 'tests' "$SRC_DIR/" "$INSTALL_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod 0755 "$INSTALL_DIR/deploy/tgyt"
ln -sf "$INSTALL_DIR/deploy/tgyt" /usr/local/bin/tgyt
ok "Application installed to $INSTALL_DIR (source copy in $SRC_DIR); management command: tgyt"

# ---------------------------------------------------------------------------------------
step "Setting up the Python environment"
# ---------------------------------------------------------------------------------------
[[ -d "$INSTALL_DIR/venv" ]] || run "Creating virtual environment" as_service python3 -m venv "$INSTALL_DIR/venv" || die "Could not create the Python virtual environment."
VENV_PY="$INSTALL_DIR/venv/bin/python"
retry 3 10 "Upgrading pip" as_service "$VENV_PY" -m pip install --quiet --upgrade pip
retry 3 10 "Installing pinned dependencies (a few minutes)" as_service "$VENV_PY" -m pip install --quiet -r "$INSTALL_DIR/requirements.txt" ||
    die "Installing the Python dependencies failed." "Usually a network blip; run the installer again. If it keeps failing, see docs/troubleshooting.md."
# TgCrypto only speeds up Telegram encryption; the app works without it, so a failed build is not fatal.
if [[ -f "$INSTALL_DIR/requirements-optional.txt" ]]; then
    run "Installing optional speed-up (tgcrypto)" as_service "$VENV_PY" -m pip install --quiet -r "$INSTALL_DIR/requirements-optional.txt" ||
        warn "tgcrypto could not be built; continuing without it (Telegram transfers are slower but work)."
fi

# ---------------------------------------------------------------------------------------
step "Creating keys and the configuration file"
# ---------------------------------------------------------------------------------------
if [[ ! -f "$FERNET_KEY_PATH" ]]; then
    "$VENV_PY" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" >"$FERNET_KEY_PATH"
    chown "$SERVICE_USER:$SERVICE_USER" "$FERNET_KEY_PATH"; chmod 0400 "$FERNET_KEY_PATH"
    ok "Generated the encryption key $FERNET_KEY_PATH"
    warn "BACK THIS KEY UP (tgyt backup). Without it, saved YouTube logins cannot be decrypted."
else
    ok "Encryption key already exists - left untouched"
fi

mkdir -p "$TLS_DIR"
if [[ ! -f "$TLS_DIR/selfsigned.crt" || ! -f "$TLS_DIR/selfsigned.key" ]]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -keyout "$TLS_DIR/selfsigned.key" -out "$TLS_DIR/selfsigned.crt" \
        -subj "/CN=tgyt-uploader" >/dev/null 2>&1
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$TLS_DIR"; chmod 0750 "$TLS_DIR"; chmod 0400 "$TLS_DIR/selfsigned.key"

write_env_file() {
    local ts; ts="$(date +%Y%m%d-%H%M%S)"
    if [[ -f "$ENV_FILE" ]]; then
        cp -p "$ENV_FILE" "$BACKUP_DIR/tgyt.env.$ts"; chmod 600 "$BACKUP_DIR/tgyt.env.$ts"
        info "Previous settings copied to $BACKUP_DIR/tgyt.env.$ts"
    else
        install -m 0600 -o "$SERVICE_USER" -g "$SERVICE_USER" "$INSTALL_DIR/.env.example" "$ENV_FILE"
        env_set "$ENV_FILE" SESSION_SECRET "$(openssl rand -hex 32)"
    fi
    apply_install_settings "$ENV_FILE"
    return 0
}

if ((KEEP_EXISTING)); then
    ok "Existing configuration kept: $ENV_FILE"
else
    write_env_file
    ok "Wrote $ENV_FILE (mode 600, owner $SERVICE_USER). Secrets are not shown or logged."
fi
chown "$SERVICE_USER:$SERVICE_USER" "$ENV_FILE"; chmod 0600 "$ENV_FILE"

# Admin account: created directly in the database so the password never sits in a file.
admin_exists() {
    [[ -f "$DATA_DIR/tgyt.db" ]] || return 1
    "$VENV_PY" -c "import sqlite3,sys; c=sqlite3.connect('$DATA_DIR/tgyt.db'); sys.exit(0 if c.execute('select count(*) from app_users').fetchone()[0] else 1)" 2>/dev/null
}
systemctl stop tgyt.service 2>/dev/null || true
if ((KEEP_EXISTING)) && admin_exists; then
    ok "Admin account already exists - not touched (reset it with: sudo tgyt admin)"
elif [[ -n "$ADMIN_PASSWORD" ]]; then
    # shellcheck disable=SC2024  # the log redirect is meant to run as root
    if printf '%s\n' "$ADMIN_PASSWORD" | as_service env TGYT_ENV_FILE="$ENV_FILE" "$VENV_PY" "$INSTALL_DIR/tools/admin_user.py" \
        --username "$ADMIN_USER" --password-stdin >>"$LOG_FILE" 2>&1; then
        ok "Admin account '$ADMIN_USER' created in the database"
    else
        die "Could not create the admin account." "See $LOG_FILE. Try later with: sudo tgyt admin"
    fi
    ADMIN_PASSWORD=""
else
    warn "No admin account yet. Create one with: sudo tgyt admin"
fi

# ---------------------------------------------------------------------------------------
step "Installing the system service"
# ---------------------------------------------------------------------------------------
for unit in tgyt-bot.service tgyt-oauth.service; do   # v1 leftovers
    if systemctl list-unit-files 2>/dev/null | grep -q "^${unit}"; then
        systemctl disable --now "$unit" 2>/dev/null || true
        rm -f "/etc/systemd/system/$unit"
    fi
done
install -m 0644 "$INSTALL_DIR/deploy/tgyt.service" /etc/systemd/system/tgyt.service
if ((RAM_MB < 2600)); then   # keep the memory cap meaningful on small servers
    mkdir -p /etc/systemd/system/tgyt.service.d
    printf '[Service]\nMemoryMax=%dM\n' "$((RAM_MB * 85 / 100))" >/etc/systemd/system/tgyt.service.d/memory.conf
fi
install -m 0644 "$INSTALL_DIR/deploy/tgyt-backup.service" /etc/systemd/system/tgyt-backup.service
install -m 0644 "$INSTALL_DIR/deploy/tgyt-backup.timer" /etc/systemd/system/tgyt-backup.timer
systemctl daemon-reload

# The panel's Restart button needs no root: the app exits cleanly and Restart=always brings it back.
# Remove the sudoers rule older versions installed for it (it could never work under NoNewPrivileges).
rm -f /etc/sudoers.d/tgyt-restart

systemctl enable tgyt.service >/dev/null 2>&1
if [[ "$BACKUP_SCHEDULE" == "yes" ]]; then systemctl enable --now tgyt-backup.timer >/dev/null 2>&1 && ok "Nightly backups enabled (03:30, kept in $BACKUP_DIR)"; fi
systemctl restart tgyt.service
if wait_for 45 3 systemctl is-active --quiet tgyt.service; then
    ok "Service tgyt is running (auto-starts on boot, restarts on failure)"
else
    err "The service did not start. Recent log:"; journalctl -u tgyt -n 20 --no-pager | redact | sed 's/^/      /' >&2
    die "tgyt.service failed to start." "The messages above say why (often a wrong value in $ENV_FILE). Fix it with: sudo tgyt config   then: sudo tgyt restart"
fi

# ---------------------------------------------------------------------------------------
step "Web server and HTTPS"
# ---------------------------------------------------------------------------------------
setup_nginx() {
    local suffix; suffix="$(web_suffix)"
    render_vhost() {  # render_vhost CERT KEY
        sed -e "s#__PUBLIC_HOST__#$DOMAIN#g" -e "s#__WEB_PORT_SUFFIX__#$suffix#g" -e "s#__WEB_PORT__#$WEB_PORT#g" \
            -e "s#__SSL_CERT__#$1#g" -e "s#__SSL_KEY__#$2#g" "$INSTALL_DIR/deploy/nginx.conf" >/etc/nginx/sites-available/tgyt.conf
        ln -sf /etc/nginx/sites-available/tgyt.conf /etc/nginx/sites-enabled/tgyt.conf
        nginx -t >>"$LOG_FILE" 2>&1 || { nginx -t 2>&1 | sed 's/^/      /' >&2; die "nginx rejected its configuration." "See above; then run the installer again."; }
        systemctl reload nginx 2>/dev/null || systemctl restart nginx
    }
    mkdir -p /var/www/html
    local live="/etc/letsencrypt/live/$DOMAIN"
    if [[ -s "$live/fullchain.pem" ]]; then
        ok "A certificate for $DOMAIN already exists - reusing it"
        render_vhost "$live/fullchain.pem" "$live/privkey.pem"; CERT_OK=1
    else
        render_vhost "$TLS_DIR/selfsigned.crt" "$TLS_DIR/selfsigned.key"   # lets nginx answer the HTTP challenge
        if [[ "${TGYT_SKIP_CERT:-}" == "1" ]]; then
            warn "Certificate issuance skipped (TGYT_SKIP_CERT=1). The panel uses a self-signed certificate."
            return 0
        fi
        local -a cargs=(certonly --webroot -w /var/www/html -d "$DOMAIN" --non-interactive --agree-tos
            --deploy-hook "systemctl reload nginx")
        if [[ -n "$LE_EMAIL" ]]; then cargs+=(-m "$LE_EMAIL"); else cargs+=(--register-unsafely-without-email); fi
        [[ "${TGYT_LE_STAGING:-}" == "1" ]] && cargs+=(--staging)
        local tries=0
        while true; do
            tries=$((tries + 1))
            if run "Requesting a free HTTPS certificate from Let's Encrypt for $DOMAIN" certbot "${cargs[@]}"; then
                CERT_OK=1; break
            fi
            say ""
            err "Let's Encrypt could not issue a certificate. The usual causes:"
            say "     • the DNS A record for $DOMAIN does not point to $PUBLIC_IP yet (or has not propagated)"
            say "     • port 80 is blocked by your hosting provider's firewall / security group (open 80 and $WEB_PORT)"
            say "     • too many certificate requests for this name recently (Let's Encrypt rate limit)"
            is_interactive || { warn "Continuing with a self-signed certificate. Fix the cause and re-run the installer."; return 0; }
            if ((tries < 5)) && confirm "Fix it now, then try again?" y; then continue; fi
            warn "Continuing with a self-signed certificate (browsers will warn). Re-run the installer after fixing DNS/firewall."
            return 0
        done
        live="/etc/letsencrypt/live/$DOMAIN"
        render_vhost "$live/fullchain.pem" "$live/privkey.pem"
        ok "HTTPS certificate installed; renewal runs automatically (certbot.timer)"
    fi
    systemctl enable --now certbot.timer >/dev/null 2>&1 || true
}

if [[ "$OAUTH_MODE" == "hostname" ]]; then
    [[ -n "$DOMAIN" ]] || die "OAUTH_MODE=hostname but no domain is configured." "Run the installer again and choose a domain or sslip.io."
    setup_nginx
else
    info "Advanced mode (no hostname): the app serves a self-signed certificate directly; nginx is not used."
    rm -f /etc/nginx/sites-enabled/tgyt.conf; systemctl reload nginx 2>/dev/null || true
fi

# ---------------------------------------------------------------------------------------
step "Firewall and brute-force protection"
# ---------------------------------------------------------------------------------------
ssh_ports() {
    {
        sshd -T 2>/dev/null | awk '/^port /{print $2}'
        [[ -n "${SSH_CONNECTION:-}" ]] && awk '{print $4}' <<<"$SSH_CONNECTION"
        echo 22
    } | sort -un
}
if [[ "$ENABLE_FIREWALL" == "yes" ]]; then
    for p in $(ssh_ports); do ufw allow "$p/tcp" comment 'SSH' >/dev/null; done
    ufw allow 80/tcp comment 'HTTP (certificates)' >/dev/null
    ufw allow "$WEB_PORT/tcp" comment 'tgyt panel' >/dev/null
    ufw default deny incoming >/dev/null; ufw default allow outgoing >/dev/null
    ufw --force enable >/dev/null
    ok "Firewall on: SSH ($(ssh_ports | tr '\n' ' ')), 80, $WEB_PORT. Everything else is closed."
    info "Also open ports 80 and $WEB_PORT in your VPS provider's own firewall / security group if it has one."
elif [[ "$ENABLE_FIREWALL" == "keep" ]]; then
    info "Firewall left as it is (existing installation kept)."
else
    warn "Firewall not enabled (you chose not to). Only the cloud provider's own firewall protects this server."
fi
if [[ "$ENABLE_FAIL2BAN" == "yes" ]]; then
    if [[ -f /etc/fail2ban/jail.d/tgyt.local ]]; then
        info "Keeping the existing /etc/fail2ban/jail.d/tgyt.local (your own settings are not overwritten)."
    else
        install -m 0644 "$INSTALL_DIR/deploy/fail2ban-tgyt.local" /etc/fail2ban/jail.d/tgyt.local
    fi
    # The ufw ban action needs ufw itself to be active; otherwise fall back to fail2ban's default (iptables).
    if ! ufw status 2>/dev/null | grep -q 'Status: active' && grep -q '^banaction *= *ufw' /etc/fail2ban/jail.d/tgyt.local; then
        sed -i -E -e 's/^(banaction *= *)ufw$/\1iptables-multiport/' -e 's/^(banaction_allports *= *)ufw$/\1iptables-allports/' \
            /etc/fail2ban/jail.d/tgyt.local
        info "ufw is off, so fail2ban uses iptables bans instead."
    fi
    systemctl enable fail2ban >/dev/null 2>&1; systemctl restart fail2ban
    if wait_for 20 2 systemctl is-active --quiet fail2ban; then ok "fail2ban is protecting SSH (repeated failed logins = temporary ban; open sessions are never cut)"; else warn "fail2ban did not start; see: journalctl -u fail2ban"; fi
fi

# ---------------------------------------------------------------------------------------
step "Large-file relay"
# ---------------------------------------------------------------------------------------
case "${SETUP_RELAY:-no}" in
    yes)
        if is_interactive; then
            say "  Prepare in Telegram first: (1) create a PRIVATE channel, (2) add your bot as administrator"
            say "  (permissions: post + delete messages), (3) make sure the relay account is a member."
            pause
            if "$VENV_PY" "$INSTALL_DIR/tools/generate_session.py" --env-file "$ENV_FILE"; then
                chown "$SERVICE_USER:$SERVICE_USER" "$ENV_FILE"; chmod 0600 "$ENV_FILE"
                systemctl restart tgyt.service
                ok "Relay configured and the service restarted"
            else
                warn "Relay setup did not finish. Run it again any time with: sudo tgyt relay"
            fi
        else
            warn "Interactive relay login is not possible in non-interactive mode. Run: sudo tgyt relay"
        fi ;;
    preset)
        if [[ -n "$USER_SESSION" && -n "$RELAY_CHAT_ID" ]] && is_session_string "$USER_SESSION" && is_relay_chat_id "$RELAY_CHAT_ID"; then
            env_set "$ENV_FILE" USER_SESSION "$USER_SESSION"; env_set "$ENV_FILE" RELAY_CHAT_ID "$RELAY_CHAT_ID"
            systemctl restart tgyt.service; ok "Relay settings applied from the provided configuration"
        else
            warn "TGYT_USER_SESSION / TGYT_RELAY_CHAT_ID missing or malformed; relay not configured."
        fi ;;
    keep) info "Existing relay settings kept (change them with: sudo tgyt relay)." ;;
    *) info "Skipped. Videos over 20 MB are rejected until you run: sudo tgyt relay" ;;
esac

# ---------------------------------------------------------------------------------------
step "Optional: harden SSH"
# ---------------------------------------------------------------------------------------
harden_ssh() {
    local dropin="/etc/ssh/sshd_config.d/00-tgyt-hardening.conf" answer
    say "  This turns off password logins and root logins over SSH, so bots can't guess their way in."
    say "  ${C_BOLD}Only do this if you can already log in with an SSH key${C_OFF} - otherwise you would be locked out."
    if [[ "${TGYT_SSH_KEY_CONFIRMED:-}" != "yes" ]]; then
        is_interactive || { info "Skipped (non-interactive mode needs TGYT_SSH_KEY_CONFIRMED=yes)."; return 0; }
        say "  Open a SECOND terminal window now and log in to this server with your key (no password prompt)."
        read -r -p "  Did that work without typing a password? Type 'yes' to continue: " answer || answer=""
        [[ "$answer" == "yes" ]] || { info "Skipped - SSH left as it was."; return 0; }
    fi
    local has_user_key=0
    while IFS=: read -r _ _ uid _ _ home _; do
        ((uid >= 1000 && uid < 60000)) && [[ -s "$home/.ssh/authorized_keys" ]] && has_user_key=1
    done </etc/passwd
    if [[ ! -s /root/.ssh/authorized_keys && $has_user_key -eq 0 ]]; then
        warn "No authorized SSH keys were found for any account. Refusing to disable passwords."
        return 0
    fi
    local root_login="no"
    ((has_user_key)) || root_login="prohibit-password"   # only root has a key: keep key-based root login
    [[ -f "$dropin" ]] && cp -p "$dropin" "$dropin.prev"
    # shellcheck disable=SC2016
    printf '# Written by the TG→YT installer. Remove this file and run `systemctl reload ssh` to undo.\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin %s\n' "$root_login" >"$dropin"
    if ! sshd -t 2>>"$LOG_FILE"; then rm -f "$dropin"; warn "sshd rejected the change; reverted."; return 0; fi
    systemctl reload ssh 2>/dev/null || systemctl reload sshd
    if is_interactive; then
        say "  Applied. Now open ANOTHER new terminal and confirm you can still log in with your key."
        read -r -t 120 -p "  Type 'ok' within 2 minutes to keep this (otherwise it is reverted automatically): " answer || answer=""
        if [[ "$answer" != "ok" ]]; then
            rm -f "$dropin"; systemctl reload ssh 2>/dev/null || systemctl reload sshd
            warn "No confirmation - SSH hardening was reverted. Nothing is locked."
            return 0
        fi
    fi
    ok "SSH hardened: key-only login, root login '$root_login'. Undo: sudo rm $dropin && sudo systemctl reload ssh"
}
if [[ -z "$HARDEN_SSH" ]]; then
    if is_interactive && [[ "$ASSUME_YES" != "1" ]] && confirm "Harden SSH now (key-only login)? Skip unless you already use an SSH key" n; then HARDEN_SSH=yes; else HARDEN_SSH=no; fi
fi
if [[ "$HARDEN_SSH" == "yes" ]]; then harden_ssh; else info "SSH settings left unchanged."; fi

# ---------------------------------------------------------------------------------------
step "Checking that everything works"
# ---------------------------------------------------------------------------------------
"$INSTALL_DIR/deploy/tgyt" doctor || true

PANEL_URL="https://${DOMAIN:-$PUBLIC_IP}$(web_suffix)"
REDIRECT_URI="$PANEL_URL/oauth/callback"
[[ "$OAUTH_MODE" == "loopback" ]] && REDIRECT_URI="http://127.0.0.1:$(env_get "$ENV_FILE" LOOPBACK_PORT)/oauth/callback"
cat <<EOF

${C_BOLD}${C_GREEN}Installation finished.${C_OFF}

  Admin panel : ${C_BOLD}${PANEL_URL}${C_OFF}
  Username    : $(env_get "$ENV_FILE" ADMIN_USERNAME)   (the password you chose; $( [[ "$(env_get "$ENV_FILE" REQUIRE_TOTP)" == "true" ]] && echo "you will be asked to set up two-factor on first login" || echo "two-factor is off" ))
  Install log : $LOG_FILE
  Manage      : tgyt status | logs | doctor | backup | update | config | relay   (tgyt help)

${C_BOLD}Next steps${C_OFF}
  1. Google Cloud: create the OAuth client with this exact redirect URI:
         ${REDIRECT_URI}
     (full walkthrough: docs/05-google-cloud.md)
  2. Open the panel -> Settings, upload the downloaded client_secret JSON, then Channels -> Add a channel.
  3. In Telegram send /start to your bot.
  4. Off-site backups (encrypted, Backblaze B2 / S3):  sudo tgyt offsite setup
     Without a copy off this server, losing the server means re-linking every channel.
EOF
if [[ "$OAUTH_MODE" == "hostname" && "$CERT_OK" != "1" ]]; then
    warn "HTTPS is NOT set up yet (self-signed certificate). Fix DNS / port 80, then run this installer again."
fi
trap - ERR
_log_raw "===== finished OK ====="
