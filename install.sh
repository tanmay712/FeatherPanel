#!/usr/bin/env bash
# =============================================================================
#  OrveX Panel installer
#
#  Interactive menu:
#    curl -fsSL https://raw.githubusercontent.com/tanmay712/FeatherPanel/develop/install.sh | sudo bash
#
#  Direct commands:
#    ... | sudo bash -s -- panel    [--domain panel.example.com] [--email you@example.com]
#    ... | sudo bash -s -- vps-node [--public-ip 203.0.113.5] [--storage-size 200GiB]
#    ... | sudo bash -s -- update | node-update | status | uninstall | help
#
#  The panel runs in Docker. A VPS node turns any Debian/Ubuntu server into a
#  KVM + LXC hypervisor (Incus) that the panel manages instead of Proxmox:
#  dedicated IPv4, shared IPv4 (NAT with SSH + port forwards), stats, password
#  changes and console.
# =============================================================================
set -Eeuo pipefail

ORVEX_REPO="${ORVEX_REPO:-tanmay712/FeatherPanel}"
ORVEX_DEFAULT_BRANCH="develop"
BRANCH_SET=0 # 1 when the branch was chosen with --branch or ORVEX_BRANCH
[ -n "${ORVEX_BRANCH:-}" ] && BRANCH_SET=1
ORVEX_BRANCH="${ORVEX_BRANCH:-$ORVEX_DEFAULT_BRANCH}"
PANEL_DIR="${ORVEX_PANEL_DIR:-/opt/orvexpanel}"
NODE_DIR="/opt/orvex-node"
NODE_CONFIG_DIR="/etc/orvex-node"
NODE_STATE_DIR="/var/lib/orvex-node"
INSTALLER_URL="https://raw.githubusercontent.com/${ORVEX_REPO}/${ORVEX_BRANCH}/install.sh"

# ---------------------------------------------------------------- options
CMD=""
ASSUME_YES=0
DOMAIN=""
EMAIL=""
PANEL_PORT=""
USE_IMAGES=0
NODE_NAME=""
PUBLIC_IP=""
NODE_PORT="8006"
STORAGE_DRIVER=""
STORAGE_SIZE=""
STORAGE_SOURCE=""
NAT_SUBNET="10.77.0.0/24"
TEMPLATES="ubuntu-24.04-kvm,debian-12-kvm,ubuntu-24.04-lxc,debian-12-lxc"
SKIP_TEMPLATES=0
PANEL_URL=""  # vps-node: connect to this panel...
NODE_TOKEN="" # ...with the one-time token from Admin > VDS Nodes
PURGE=0
UNINSTALL_TARGET=""

# ----------------------------------------------------------------- output
if [ -t 1 ]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_CYAN=$'\033[36m'; C_MAGENTA=$'\033[35m'
else
    C_RESET=""; C_BOLD=""; C_DIM=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_CYAN=""; C_MAGENTA=""
fi

info() { printf '%s\n' "  ${C_CYAN}>${C_RESET} $*"; }
ok() { printf '%s\n' "  ${C_GREEN}✓${C_RESET} $*"; }
warn() { printf '%s\n' "  ${C_YELLOW}!${C_RESET} $*" >&2; }
die() {
    printf '%s\n' "  ${C_RED}✗ $*${C_RESET}" >&2
    exit 1
}
step() { printf '\n%s\n' "${C_BOLD}${C_MAGENTA}==>${C_RESET} ${C_BOLD}$*${C_RESET}"; }

on_error() {
    local code=$? line=${1:-?}
    printf '\n%s\n' "  ${C_RED}✗ The installer stopped (line ${line}, exit code ${code}).${C_RESET}" >&2
    printf '%s\n' "    Re-run it after fixing the problem; every step is safe to repeat." >&2
    exit "$code"
}
trap 'on_error $LINENO' ERR

banner() {
    printf '%s' "${C_MAGENTA}${C_BOLD}"
    cat <<'EOF'

     ██████╗ ██████╗ ██╗   ██╗███████╗██╗  ██╗
    ██╔═══██╗██╔══██╗██║   ██║██╔════╝╚██╗██╔╝
    ██║   ██║██████╔╝██║   ██║█████╗   ╚███╔╝
    ██║   ██║██╔══██╗╚██╗ ██╔╝██╔══╝   ██╔██╗
    ╚██████╔╝██║  ██║ ╚████╔╝ ███████╗██╔╝ ██╗
     ╚═════╝ ╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝
EOF
    printf '%s\n' "${C_RESET}        ${C_BOLD}OrveX Panel${C_RESET} ${C_DIM}· game servers · billing · VPS hosting${C_RESET}"
    printf '%s\n\n' "        ${C_DIM}${ORVEX_REPO}@${ORVEX_BRANCH}${C_RESET}"
}

# ------------------------------------------------------------------ input
# When piped through `curl | bash`, stdin is the script itself: read from the TTY.
HAVE_TTY=0
if { exec 3</dev/tty; } 2>/dev/null; then
    HAVE_TTY=1
fi

ask() { # ask VAR "Question" "default"
    local __var=$1 __question=$2 __default=${3:-} __reply=""
    if [ "$ASSUME_YES" -eq 1 ] || [ "$HAVE_TTY" -eq 0 ]; then
        printf -v "$__var" '%s' "$__default"
        return
    fi
    if [ -n "$__default" ]; then
        printf '  %s %s[%s]%s: ' "$__question" "$C_DIM" "$__default" "$C_RESET" >/dev/tty
    else
        printf '  %s: ' "$__question" >/dev/tty
    fi
    IFS= read -r __reply <&3 || true
    printf -v "$__var" '%s' "${__reply:-$__default}"
}

confirm() { # confirm "Question" [default y|n]; -y answers yes to everything
    local question=$1 default=${2:-y} reply=""
    if [ "$ASSUME_YES" -eq 1 ]; then
        return 0
    fi
    if [ "$HAVE_TTY" -eq 0 ]; then
        [ "$default" = "y" ]
        return
    fi
    local hint="[Y/n]"
    [ "$default" = "n" ] && hint="[y/N]"
    printf '  %s %s ' "$question" "$hint" >/dev/tty
    IFS= read -r reply <&3 || true
    reply=${reply:-$default}
    case "$reply" in [yY]*) return 0 ;; *) return 1 ;; esac
}

# ----------------------------------------------------------------- system
need_root() {
    [ "$(id -u)" -eq 0 ] || die "Run as root (for example: curl -fsSL ${INSTALLER_URL} | sudo bash)"
}

OS_ID=""; OS_VERSION=""; OS_CODENAME=""; ARCH=""
detect_os() {
    [ -r /etc/os-release ] || die "Unsupported system: /etc/os-release not found"
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID=${ID:-}
    OS_VERSION=${VERSION_ID:-}
    OS_CODENAME=${VERSION_CODENAME:-}
    ARCH=$(dpkg --print-architecture 2>/dev/null || uname -m)
    case "$ARCH" in amd64 | arm64) ;; *) die "Unsupported CPU architecture: $ARCH (amd64 or arm64 required)" ;; esac
    case "$OS_ID:$OS_VERSION" in
        debian:11 | debian:12 | debian:13 | ubuntu:20.04 | ubuntu:22.04 | ubuntu:24.04) ;;
        *) die "Unsupported OS: ${PRETTY_NAME:-$OS_ID $OS_VERSION}. Use Debian 11-13 or Ubuntu 20.04/22.04/24.04." ;;
    esac
    ok "System: ${PRETTY_NAME:-$OS_ID $OS_VERSION} ($ARCH)"
}

APT_UPDATED=0
apt_install() {
    export DEBIAN_FRONTEND=noninteractive
    if [ "$APT_UPDATED" -eq 0 ]; then
        apt-get update -qq
        APT_UPDATED=1
    fi
    apt-get install -y -qq -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold "$@" >/dev/null
}

detect_public_ipv4() {
    local ip=""
    ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit }}') || true
    [ -n "$ip" ] || ip=$(hostname -I 2>/dev/null | awk '{print $1}') || true
    printf '%s' "$ip"
}

detect_uplink() {
    ip -4 route show default 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "dev") { print $(i + 1); exit }}'
}

port_in_use() { ss -ltnH "sport = :$1" 2>/dev/null | grep -q .; }

gen_secret() { openssl rand -hex 24; }

ufw_active() { command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; }

# Without --branch, an existing checkout keeps following the branch it was installed
# from (falling back to the default branch if that branch was deleted on GitHub).
follow_checkout_branch() { # follow_checkout_branch DIR
    local branch
    [ "$BRANCH_SET" -eq 1 ] && return 0
    branch=$(git -C "$1" symbolic-ref --quiet --short HEAD 2>/dev/null) || return 0
    [ -n "$branch" ] || return 0
    ORVEX_BRANCH=$branch
    INSTALLER_URL="https://raw.githubusercontent.com/${ORVEX_REPO}/${ORVEX_BRANCH}/install.sh"
}

fetch_repo() { # fetch_repo DIR [sparse-dir]
    local dir=$1 sparse=${2:-}
    if [ -d "$dir/.git" ]; then
        follow_checkout_branch "$dir"
        info "Updating existing checkout in $dir ($ORVEX_BRANCH)"
        if ! git -C "$dir" fetch -q --depth 1 origin "$ORVEX_BRANCH"; then
            [ "$BRANCH_SET" -eq 0 ] && [ "$ORVEX_BRANCH" != "$ORVEX_DEFAULT_BRANCH" ] ||
                die "Could not fetch branch $ORVEX_BRANCH from github.com/${ORVEX_REPO}"
            warn "Branch $ORVEX_BRANCH is no longer on GitHub; switching to $ORVEX_DEFAULT_BRANCH"
            ORVEX_BRANCH=$ORVEX_DEFAULT_BRANCH
            INSTALLER_URL="https://raw.githubusercontent.com/${ORVEX_REPO}/${ORVEX_BRANCH}/install.sh"
            git -C "$dir" fetch -q --depth 1 origin "$ORVEX_BRANCH" ||
                die "Could not fetch branch $ORVEX_BRANCH from github.com/${ORVEX_REPO}"
        fi
        git -C "$dir" checkout -q -f -B "$ORVEX_BRANCH" FETCH_HEAD
    elif [ -n "$sparse" ]; then
        git clone -q --depth 1 --filter=blob:none --sparse -b "$ORVEX_BRANCH" "https://github.com/${ORVEX_REPO}.git" "$dir"
        git -C "$dir" sparse-checkout set "$sparse"
    else
        git clone -q --depth 1 -b "$ORVEX_BRANCH" "https://github.com/${ORVEX_REPO}.git" "$dir"
    fi
    ok "Source ready: $(git -C "$dir" log -1 --format='%h %s' | cut -c1-70)"
}

install_cli_helper() { # /usr/local/bin/orvex -> this installer
    local source_file=$1
    if [ -f "$source_file" ]; then
        install -m 0755 "$source_file" /usr/local/bin/orvex
        ok "Command 'orvex' installed (orvex status, orvex update, orvex help)"
    fi
}

# ================================================================== PANEL
PANEL_STATE="$PANEL_DIR/.orvex-install.conf"

load_panel_state() {
    COMPOSE_FILE="docker-compose.v2.git.yml"
    if [ -f "$PANEL_STATE" ]; then
        # shellcheck disable=SC1090
        . "$PANEL_STATE"
    fi
}

compose() { (cd "$PANEL_DIR" && docker compose -f "$COMPOSE_FILE" "$@"); }

ensure_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo installed) with Compose"
        return
    fi
    info "Installing Docker Engine (get.docker.com)"
    curl -fsSL https://get.docker.com | sh >/dev/null
    systemctl enable --now docker >/dev/null 2>&1 || true
    docker compose version >/dev/null 2>&1 || die "Docker Compose plugin is missing after installing Docker"
    ok "Docker installed"
}

# The frontend production build (next build --webpack) peaks well above 3 GB, and
# the image build gives Node a 4 GB heap (frontendv2/Dockerfile), so make sure
# RAM + swap is about 6 GB before building from source.
ensure_build_memory() {
    local mem_kb swap_kb total_mb need_mb=6144 add_mb free_mb
    mem_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
    swap_kb=$(awk '/SwapTotal/ {print $2}' /proc/meminfo)
    total_mb=$(((mem_kb + swap_kb) / 1024))
    [ "$total_mb" -ge "$need_mb" ] && return
    add_mb=$((need_mb - total_mb))
    [ "$add_mb" -lt 2048 ] && add_mb=2048
    warn "Building the panel from source needs about 6 GB of RAM + swap (found ${total_mb} MB)."
    if [ -f /swapfile-orvex ]; then
        if ! grep -q '^/swapfile-orvex ' /proc/swaps; then
            swapon /swapfile-orvex 2>/dev/null || warn "Could not enable /swapfile-orvex"
        fi
        return
    fi
    free_mb=$(df -Pm / 2>/dev/null | awk 'NR==2 {print $4}') || free_mb=""
    if [ -n "$free_mb" ] && [ "$free_mb" -lt $((add_mb + 4096)) ]; then
        warn "Not enough free disk space for a ${add_mb} MB swap file. The build may run out of memory; use --images or a larger server if it fails."
        return
    fi
    if confirm "Create a ${add_mb} MB swap file (/swapfile-orvex)?" y; then
        if make_swapfile /swapfile-orvex "$add_mb"; then
            grep -q '^/swapfile-orvex ' /etc/fstab || echo '/swapfile-orvex none swap sw 0 0' >>/etc/fstab
            ok "Swap enabled (${add_mb} MB)"
        else
            rm -f /swapfile-orvex
            warn "Could not enable swap here (common in containers and some VPS types). The build may run out of memory; use --images or a larger server if it fails."
        fi
    fi
}

# make_swapfile PATH SIZE_MB: fallocate first, then a written-out file for
# filesystems that reject sparse or preallocated swap files.
make_swapfile() {
    local f=$1 mb=$2 attempt
    for attempt in fallocate dd; do
        swapoff "$f" 2>/dev/null
        rm -f "$f"
        touch "$f" && chmod 600 "$f" || return 1
        chattr +C "$f" 2>/dev/null # btrfs swap files must be no-copy-on-write
        if [ "$attempt" = fallocate ]; then
            fallocate -l "${mb}M" "$f" 2>/dev/null || continue
        else
            dd if=/dev/zero of="$f" bs=1M count="$mb" status=none 2>/dev/null || return 1
        fi
        mkswap "$f" >/dev/null 2>&1 && swapon "$f" 2>/dev/null && return 0
    done
    return 1
}

set_env_var() { # set_env_var FILE KEY VALUE (replace or append)
    local file=$1 key=$2 value=$3 escaped
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        escaped=${value//\\/\\\\}
        escaped=${escaped//&/\\&}
        escaped=${escaped//|/\\|}
        sed -i "s|^${key}=.*|${key}=${escaped}|" "$file"
    else
        echo "${key}=${value}" >>"$file"
    fi
}

# The panel builds the OrveX node install command from these (same repo/branch as the panel).
write_installer_source() {
    local env_file="$PANEL_DIR/.env"
    [ -f "$env_file" ] || return 0
    set_env_var "$env_file" ORVEX_REPO "$ORVEX_REPO"
    set_env_var "$env_file" ORVEX_BRANCH "$ORVEX_BRANCH"
}

write_panel_env() {
    local env_file="$PANEL_DIR/.env" bind_port=$1
    if [ -f "$env_file" ]; then
        ok "Keeping existing secrets in $env_file"
        set_env_var "$env_file" FEATHERPANEL_PANEL_PORT "$bind_port"
        write_installer_source
        return
    fi
    umask 077
    cat >"$env_file" <<EOF
# OrveX Panel - generated by install.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ). Keep this file secret.
MARIADB_ROOT_PASSWORD=$(gen_secret)
MARIADB_DATABASE=featherpanel
MARIADB_USER=featherpanel
MARIADB_PASSWORD=$(gen_secret)
REDIS_PASSWORD=$(gen_secret)
FEATHERPANEL_PANEL_PORT=${bind_port}
ORVEX_REPO=${ORVEX_REPO}
ORVEX_BRANCH=${ORVEX_BRANCH}
EOF
    umask 022
    ok "Generated database and Redis secrets ($env_file)"
}

setup_caddy() {
    local domain=$1 port=$2 email=$3
    if port_in_use 80 || port_in_use 443; then
        if ! systemctl is-active --quiet caddy 2>/dev/null; then
            warn "Ports 80/443 are already used by another web server; skipping HTTPS setup."
            warn "Point your reverse proxy at http://127.0.0.1:${port} for ${domain}."
            return 1
        fi
    fi
    if ! command -v caddy >/dev/null 2>&1; then
        info "Installing Caddy (automatic HTTPS)"
        apt_install debian-keyring debian-archive-keyring apt-transport-https gnupg
        curl -fsSL 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
        curl -fsSL 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' >/etc/apt/sources.list.d/caddy-stable.list
        APT_UPDATED=0
        apt_install caddy
    fi
    local caddyfile=/etc/caddy/Caddyfile
    if [ ! -f "$caddyfile" ] || grep -q 'root \* /usr/share/caddy' "$caddyfile"; then
        : >"$caddyfile"
    fi
    sed -i '/# BEGIN orvexpanel/,/# END orvexpanel/d' "$caddyfile"
    {
        echo "# BEGIN orvexpanel"
        if [ -n "$email" ]; then
            printf '{\n\temail %s\n}\n' "$email"
        fi
        printf '%s {\n\tencode zstd gzip\n\treverse_proxy 127.0.0.1:%s\n}\n' "$domain" "$port"
        echo "# END orvexpanel"
    } >>"$caddyfile"
    caddy fmt --overwrite "$caddyfile" >/dev/null 2>&1 || true
    systemctl enable caddy >/dev/null 2>&1 || true
    systemctl reload caddy 2>/dev/null || systemctl restart caddy
    ok "HTTPS for https://${domain} (certificate is issued automatically)"
}

wait_for_panel() {
    local port=$1 deadline=$((SECONDS + 1200))
    info "Waiting for the panel to come online (first start runs database migrations)"
    while [ "$SECONDS" -lt "$deadline" ]; do
        if curl -fsS -o /dev/null --max-time 5 "http://127.0.0.1:${port}/api/system/health" 2>/dev/null; then
            ok "Panel is online"
            return 0
        fi
        sleep 5
    done
    warn "The panel did not answer yet. Check: cd $PANEL_DIR && docker compose -f $COMPOSE_FILE logs -f backend"
    return 1
}

install_panel() {
    need_root
    detect_os
    if [ -z "$DOMAIN" ] && [ "$ASSUME_YES" -eq 0 ] && [ "$HAVE_TTY" -eq 1 ]; then
        ask DOMAIN "Domain for the panel (leave empty to use http://<server-ip>:4831)" ""
    fi
    if [ -n "$DOMAIN" ] && [ -z "$EMAIL" ]; then
        ask EMAIL "E-mail for Let's Encrypt notices (optional)" ""
    fi
    PANEL_PORT=${PANEL_PORT:-4831}

    step "Installing base packages"
    apt_install ca-certificates curl git openssl iproute2
    ok "Base packages installed"

    step "Docker"
    ensure_docker

    step "Downloading OrveX Panel"
    mkdir -p "$(dirname "$PANEL_DIR")"
    fetch_repo "$PANEL_DIR"
    COMPOSE_FILE="docker-compose.v2.git.yml"
    if [ "$USE_IMAGES" -eq 1 ]; then
        COMPOSE_FILE="docker-compose.yml"
    fi

    step "Configuration"
    local bind_port="$PANEL_PORT"
    if [ -n "$DOMAIN" ]; then
        bind_port="127.0.0.1:${PANEL_PORT}" # only reachable through Caddy
    fi
    write_panel_env "$bind_port"
    cat >"$PANEL_STATE" <<EOF
COMPOSE_FILE=${COMPOSE_FILE}
DOMAIN=${DOMAIN}
PANEL_PORT=${PANEL_PORT}
EOF

    step "Starting OrveX Panel"
    if [ "$USE_IMAGES" -eq 1 ]; then
        info "Pulling images from ghcr.io/${ORVEX_REPO%%/*}"
        compose pull
        compose up -d
    else
        ensure_build_memory
        info "Building from source - this takes 10-25 minutes the first time"
        COMPOSE_PARALLEL_LIMIT=1 compose up -d --build
    fi
    ok "Containers started"

    if [ -n "$DOMAIN" ]; then
        step "HTTPS"
        setup_caddy "$DOMAIN" "$PANEL_PORT" "$EMAIL" || true
    fi

    if ufw_active; then
        if [ -n "$DOMAIN" ]; then
            ufw allow 80/tcp >/dev/null
            ufw allow 443/tcp >/dev/null
        else
            ufw allow "${PANEL_PORT}/tcp" >/dev/null
        fi
        ok "Firewall (ufw) opened for the panel"
    fi

    step "Health check"
    wait_for_panel "$PANEL_PORT" || true
    install_cli_helper "$PANEL_DIR/install.sh"

    local url
    if [ -n "$DOMAIN" ]; then url="https://${DOMAIN}"; else url="http://$(detect_public_ipv4):${PANEL_PORT}"; fi
    printf '\n%s\n' "${C_GREEN}${C_BOLD}  OrveX Panel is installed!${C_RESET}"
    cat <<EOF

    Open:      ${C_BOLD}${url}${C_RESET}
    First:     register an account - the first account becomes the administrator.
    Files:     ${PANEL_DIR}   (secrets in ${PANEL_DIR}/.env)
    Manage:    orvex status | orvex update

    Add VPS hosting (KVM + LXC, no Proxmox needed): in the panel open
      Admin > Nodes (VPS) > Create and run the command it shows on the server
      that should host the VPS. The node connects itself.

EOF
}

update_panel() {
    need_root
    [ -d "$PANEL_DIR/.git" ] || die "OrveX Panel is not installed in $PANEL_DIR"
    load_panel_state
    step "Updating OrveX Panel"
    fetch_repo "$PANEL_DIR"
    write_installer_source
    if [ "$COMPOSE_FILE" = "docker-compose.yml" ]; then
        compose pull
        compose up -d
    else
        ensure_build_memory
        COMPOSE_PARALLEL_LIMIT=1 compose up -d --build
    fi
    docker image prune -f >/dev/null 2>&1 || true
    install_cli_helper "$PANEL_DIR/install.sh"
    wait_for_panel "${PANEL_PORT:-4831}" || true
    ok "Panel updated"
}

uninstall_panel() {
    [ -d "$PANEL_DIR" ] || {
        info "OrveX Panel is not installed"
        return
    }
    load_panel_state
    if [ "$PURGE" -eq 1 ]; then
        warn "This deletes the panel AND all its data (database, uploads, backups)."
    fi
    confirm "Remove OrveX Panel from $PANEL_DIR?" n || return
    if [ "$PURGE" -eq 1 ]; then compose down -v || true; else compose down || true; fi
    if [ -f /etc/caddy/Caddyfile ]; then
        sed -i '/# BEGIN orvexpanel/,/# END orvexpanel/d' /etc/caddy/Caddyfile
        systemctl reload caddy 2>/dev/null || true
    fi
    if [ "$PURGE" -eq 1 ]; then
        rm -rf "$PANEL_DIR"
    else
        rm -f "$PANEL_STATE"
        info "Kept ${PANEL_DIR}/.env and Docker volumes (use --purge to delete everything)"
    fi
    ok "OrveX Panel removed"
}

# ================================================================ VPS NODE
check_virtualization() {
    if command -v systemd-detect-virt >/dev/null 2>&1; then
        local container
        container=$(systemd-detect-virt -c 2>/dev/null || true)
        if [ -n "$container" ] && [ "$container" != "none" ]; then
            die "This server is a container ($container). VPS nodes need a KVM VM or a dedicated server."
        fi
    fi
    KVM_OK=0
    if [ -e /dev/kvm ]; then
        KVM_OK=1
        ok "Hardware virtualization available (/dev/kvm): KVM + LXC"
    elif grep -qE '(vmx|svm)' /proc/cpuinfo 2>/dev/null; then
        modprobe kvm_intel 2>/dev/null || modprobe kvm_amd 2>/dev/null || true
        if [ -e /dev/kvm ]; then
            KVM_OK=1
            ok "KVM module loaded: KVM + LXC"
        fi
    fi
    if [ "$KVM_OK" -eq 0 ]; then
        warn "No hardware virtualization (/dev/kvm missing). LXC containers work; KVM VMs need"
        warn "a dedicated server or a VPS with nested virtualization enabled."
        confirm "Continue with LXC containers only?" y || exit 1
    fi
}

check_conflicts() {
    if command -v pveversion >/dev/null 2>&1; then
        die "Proxmox VE is installed here. Add this server to the panel as a Proxmox node instead."
    fi
    if command -v snap >/dev/null 2>&1 && snap list lxd >/dev/null 2>&1; then
        die "LXD (snap) is installed. Remove it first (snap remove lxd) - OrveX nodes use Incus."
    fi
}

install_incus() {
    if command -v incus >/dev/null 2>&1; then
        ok "Incus already installed ($(incus version 2>/dev/null | awk -F': ' '/Server/ {print $2}' || true))"
        return
    fi
    info "Adding the Zabbly Incus repository (stable)"
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://pkgs.zabbly.com/key.asc -o /etc/apt/keyrings/zabbly.asc
    cat >/etc/apt/sources.list.d/zabbly-incus-stable.sources <<EOF
Enabled: yes
Types: deb
URIs: https://pkgs.zabbly.com/incus/stable
Suites: ${OS_CODENAME}
Components: main
Architectures: ${ARCH}
Signed-By: /etc/apt/keyrings/zabbly.asc
EOF
    APT_UPDATED=0
    if apt_install incus; then
        ok "Incus installed (Zabbly)"
        return
    fi
    warn "Zabbly packages are not available for ${OS_CODENAME}; trying the distribution packages"
    rm -f /etc/apt/sources.list.d/zabbly-incus-stable.sources
    APT_UPDATED=0
    local extra=()
    if [ "$KVM_OK" -eq 1 ]; then
        if [ "$ARCH" = "amd64" ]; then extra=(qemu-system-x86 ovmf); else extra=(qemu-system-arm qemu-efi-aarch64); fi
    fi
    if [ "$OS_ID" = "debian" ] && [ "$OS_VERSION" = "12" ]; then
        echo "deb http://deb.debian.org/debian bookworm-backports main" >/etc/apt/sources.list.d/orvex-backports.list
        APT_UPDATED=0
        apt_install -t bookworm-backports incus "${extra[@]}" || die "Could not install Incus"
    else
        apt_install incus "${extra[@]}" || die "Could not install Incus on ${OS_ID} ${OS_VERSION}"
    fi
    ok "Incus installed (distribution package)"
}

init_incus() {
    local gateway prefix
    gateway=$(python3 -c "import ipaddress,sys; n=ipaddress.ip_network(sys.argv[1], strict=False); print(n.network_address + 1)" "$NAT_SUBNET")
    prefix=${NAT_SUBNET#*/}
    systemctl enable --now incus.socket incus.service >/dev/null 2>&1 || true
    if incus storage show default >/dev/null 2>&1; then
        ok "Storage pool 'default' exists"
    else
        local args=()
        [ -n "$STORAGE_SOURCE" ] && args+=("source=${STORAGE_SOURCE}")
        if [ -z "$STORAGE_SOURCE" ] && [ "$STORAGE_DRIVER" != "dir" ] && [ -n "$STORAGE_SIZE" ]; then
            args+=("size=${STORAGE_SIZE}")
        fi
        info "Creating storage pool 'default' (${STORAGE_DRIVER}${STORAGE_SIZE:+, ${STORAGE_SIZE}}${STORAGE_SOURCE:+, on ${STORAGE_SOURCE}})"
        incus storage create default "$STORAGE_DRIVER" "${args[@]}" >/dev/null
        ok "Storage pool ready"
    fi
    if incus network show orvexnat0 >/dev/null 2>&1; then
        ok "Shared IPv4 bridge orvexnat0 exists"
    else
        incus network create orvexnat0 "ipv4.address=${gateway}/${prefix}" ipv4.nat=true ipv6.address=none >/dev/null
        ok "Shared IPv4 bridge orvexnat0 (${gateway}/${prefix}, NAT)"
    fi
    if ! incus profile device show default 2>/dev/null | grep -q '^root:'; then
        incus profile device add default root disk path=/ pool=default >/dev/null
    fi
    NAT_GATEWAY=$gateway
}

configure_sysctl() {
    cat >/etc/sysctl.d/99-orvex-node.conf <<'EOF'
# OrveX VPS Node: routing for dedicated/shared IPv4 and Incus limits
net.ipv4.ip_forward = 1
fs.inotify.max_user_instances = 1048576
fs.inotify.max_user_watches = 1048576
fs.inotify.max_queued_events = 1048576
vm.max_map_count = 262144
kernel.keys.maxkeys = 2000
EOF
    sysctl --system >/dev/null 2>&1 || sysctl -p /etc/sysctl.d/99-orvex-node.conf >/dev/null
    ok "Kernel settings applied (IPv4 forwarding on)"
}

write_node_config() {
    local uplink=$1
    mkdir -p "$NODE_CONFIG_DIR/tls" "$NODE_STATE_DIR"
    chmod 700 "$NODE_CONFIG_DIR"
    if [ ! -f "$NODE_CONFIG_DIR/templates.json" ]; then
        install -m 0644 "$NODE_DIR/src/vps-node/templates.json" "$NODE_CONFIG_DIR/templates.json"
    fi
    ORVEX_NAME="$NODE_NAME" ORVEX_PORT="$NODE_PORT" ORVEX_IP="$PUBLIC_IP" ORVEX_UPLINK="$uplink" \
        ORVEX_SUBNET="$NAT_SUBNET" ORVEX_GW="$NAT_GATEWAY" python3 - "$NODE_CONFIG_DIR/config.json" <<'PY'
import json, os, sys, uuid
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as handle:
        cfg = json.load(handle)
except (OSError, ValueError):
    cfg = {}
cfg.setdefault("api_user", "orvex@orvex")
cfg.setdefault("api_token_id", "panel")
if not cfg.get("api_token_secret"):
    cfg["api_token_secret"] = str(uuid.uuid4())
cfg["node_name"] = os.environ["ORVEX_NAME"]
cfg["port"] = int(os.environ["ORVEX_PORT"])
cfg["public_ipv4"] = os.environ["ORVEX_IP"]
cfg["uplink_interface"] = os.environ["ORVEX_UPLINK"]
nat = cfg.setdefault("nat", {})
nat["network"] = "orvexnat0"
nat["subnet"] = os.environ["ORVEX_SUBNET"]
nat["gateway"] = os.environ["ORVEX_GW"]
cfg.setdefault("storage_pool", "default")
cfg.setdefault("tls_cert", "/etc/orvex-node/tls/cert.pem")
cfg.setdefault("tls_key", "/etc/orvex-node/tls/key.pem")
cfg.setdefault("templates_file", "/etc/orvex-node/templates.json")
with open(path + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(cfg, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.chmod(path + ".tmp", 0o600)
os.replace(path + ".tmp", path)
PY
    ok "Node configuration: $NODE_CONFIG_DIR/config.json"
    if [ ! -f "$NODE_CONFIG_DIR/tls/cert.pem" ]; then
        local san="IP:${PUBLIC_IP}"
        san="${san},DNS:$(hostname -f 2>/dev/null || hostname)"
        openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 3650 \
            -keyout "$NODE_CONFIG_DIR/tls/key.pem" -out "$NODE_CONFIG_DIR/tls/cert.pem" \
            -subj "/CN=${NODE_NAME}" -addext "subjectAltName=${san}" >/dev/null 2>&1
        chmod 600 "$NODE_CONFIG_DIR/tls/key.pem"
        ok "TLS certificate created (self-signed, valid 10 years)"
    fi
}

configure_node_firewall() {
    if ! ufw_active; then
        return
    fi
    local first last
    first=$(python3 -c "import ipaddress,sys; n=ipaddress.ip_network(sys.argv[1]); print(n.num_addresses-2)" "$NAT_SUBNET")
    last=$((30000 + first * 20 + 19))
    ufw allow "${NODE_PORT}/tcp" >/dev/null
    ufw allow "22001:$((22000 + first))/tcp" >/dev/null
    ufw allow "30020:${last}/tcp" >/dev/null
    ufw allow "30020:${last}/udp" >/dev/null
    ufw allow in on orvexnat0 >/dev/null
    ufw route allow in on orvexnat0 >/dev/null
    ufw route allow out on orvexnat0 >/dev/null
    ok "Firewall (ufw): API port ${NODE_PORT}, NAT SSH and service ports, guest routing"
}

install_vps_node() {
    need_root
    if [ -n "$PANEL_URL$NODE_TOKEN" ]; then
        [ -n "$PANEL_URL" ] && [ -n "$NODE_TOKEN" ] || die "--panel and --token belong together (copy the whole command from the panel)"
        [[ $PANEL_URL =~ ^https?://[^[:space:]/]+ ]] || die "--panel must be the panel URL, e.g. https://panel.example.com"
        [[ $NODE_TOKEN =~ ^orvx_[1-9][0-9]{0,9}_[A-Za-z0-9]{48}$ ]] || die "--token is not an OrveX install token (copy it from the panel again)"
        PANEL_URL=${PANEL_URL%/}
    fi
    detect_os
    check_virtualization
    check_conflicts
    [ -n "$NODE_NAME" ] || NODE_NAME=$(hostname -s 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-\n' '-')
    [ -n "$PUBLIC_IP" ] || PUBLIC_IP=$(detect_public_ipv4)
    ask NODE_NAME "Node name" "$NODE_NAME"
    ask PUBLIC_IP "Public IPv4 of this server (used for shared-IPv4 port forwards)" "$PUBLIC_IP"
    [ -n "$PUBLIC_IP" ] || die "Could not detect the public IPv4; pass --public-ip"
    if [ -z "$PANEL_URL" ] && [ "$ASSUME_YES" -eq 0 ] && [ "$HAVE_TTY" -eq 1 ]; then
        info "To connect automatically, create the node in OrveX Panel first: Admin > Nodes (VPS) > Create."
        ask PANEL_URL "Panel URL (press Enter to connect later)" ""
        if [ -n "$PANEL_URL" ]; then
            ask NODE_TOKEN "Install token shown by the panel (orvx_...)" ""
            PANEL_URL=${PANEL_URL%/}
            if [[ ! $PANEL_URL =~ ^https?://[^[:space:]/]+ ]] || [[ ! $NODE_TOKEN =~ ^orvx_[1-9][0-9]{0,9}_[A-Za-z0-9]{48}$ ]]; then
                warn "That panel URL or token does not look right; connect later with: orvex-node register --panel URL --token TOKEN"
                PANEL_URL=""
                NODE_TOKEN=""
            fi
        fi
    fi
    if [ -z "$STORAGE_DRIVER" ]; then
        STORAGE_DRIVER=btrfs
        ask STORAGE_DRIVER "Storage driver (btrfs, dir, lvm, or zfs on Ubuntu)" "$STORAGE_DRIVER"
    fi
    case "$STORAGE_DRIVER" in btrfs | dir | lvm | zfs) ;; *) die "Unknown storage driver: $STORAGE_DRIVER" ;; esac
    if [ "$STORAGE_DRIVER" = "zfs" ] && [ "$OS_ID" != "ubuntu" ]; then
        warn "ZFS is only set up automatically on Ubuntu; using btrfs instead"
        STORAGE_DRIVER=btrfs
    fi
    if [ -n "$STORAGE_SOURCE" ]; then
        warn "The storage pool will be created on ${STORAGE_SOURCE}. ALL DATA ON IT WILL BE DESTROYED."
        confirm "Use ${STORAGE_SOURCE} for VPS storage?" n || die "Aborted"
    elif [ "$STORAGE_DRIVER" != "dir" ] && [ -z "$STORAGE_SIZE" ]; then
        local free_gb
        free_gb=$(df -BG --output=avail /var/lib 2>/dev/null | tail -n1 | tr -dc '0-9')
        free_gb=${free_gb:-40}
        local suggested=$((free_gb * 70 / 100))
        [ "$suggested" -lt 20 ] && suggested=20
        ask STORAGE_SIZE "Storage pool size (disk image on /var/lib/incus)" "${suggested}GiB"
    fi
    if [ "$SKIP_TEMPLATES" -eq 0 ] && [ "$ASSUME_YES" -eq 0 ] && [ "$HAVE_TTY" -eq 1 ]; then
        confirm "Pre-download Ubuntu 24.04 and Debian 12 templates now (faster first deploys)?" y || SKIP_TEMPLATES=1
    fi

    step "Installing packages"
    local pkgs=(ca-certificates curl git openssl python3 zstd iproute2 uuid-runtime)
    case "$STORAGE_DRIVER" in
        btrfs) pkgs+=(btrfs-progs) ;;
        lvm) pkgs+=(lvm2 thin-provisioning-tools) ;;
        zfs) pkgs+=(zfsutils-linux) ;;
    esac
    apt_install "${pkgs[@]}"
    ok "Packages installed"

    step "Incus (LXC + KVM engine)"
    install_incus
    init_incus

    step "Networking"
    configure_sysctl
    local uplink
    uplink=$(detect_uplink)
    ok "Dedicated IPv4 uplink: ${uplink:-unknown} (bridge orvexpub0 in the panel)"

    step "OrveX node agent"
    mkdir -p "$NODE_DIR"
    fetch_repo "$NODE_DIR/src" vps-node
    [ -f "$NODE_DIR/src/vps-node/orvexnode/__init__.py" ] || die "Agent sources missing in $NODE_DIR/src/vps-node"
    install -m 0755 "$NODE_DIR/src/vps-node/orvex-node" /usr/local/bin/orvex-node
    install -m 0644 "$NODE_DIR/src/vps-node/orvex-node.service" /etc/systemd/system/orvex-node.service
    write_node_config "$uplink"
    configure_node_firewall
    systemctl daemon-reload
    systemctl enable orvex-node >/dev/null 2>&1
    systemctl restart orvex-node
    for _ in $(seq 1 30); do
        port_in_use "$NODE_PORT" && break
        sleep 1
    done
    port_in_use "$NODE_PORT" || die "The agent did not start: journalctl -u orvex-node -n 50"
    ok "Agent running on port ${NODE_PORT} (systemctl status orvex-node)"
    install_cli_helper "$NODE_DIR/src/install.sh"

    local registered=0
    if [ -n "$PANEL_URL" ]; then
        step "Connecting to OrveX Panel"
        if orvex-node register --panel "$PANEL_URL" --token "$NODE_TOKEN"; then
            registered=1
        else
            warn "The node is installed but not connected to the panel yet."
            warn "Fix the problem above, then in the panel open the node > Connect > New install command"
            warn "and run: orvex-node register --panel ${PANEL_URL} --token <new token>"
        fi
    fi

    if [ "$SKIP_TEMPLATES" -eq 0 ]; then
        step "Downloading templates"
        local list="${TEMPLATES//,/ }"
        if [ "$KVM_OK" -eq 0 ]; then
            # shellcheck disable=SC2086 # word splitting of the template list is intended
            list=$(printf '%s\n' $list | grep -v -- '-kvm$' | tr '\n' ' ')
        fi
        # shellcheck disable=SC2086
        orvex-node cache-templates $list || warn "Some templates failed to download; they download on first use instead."
    fi

    step "Self check"
    orvex-node doctor || true

    if [ "$registered" -eq 1 ]; then
        printf '\n%s\n' "${C_GREEN}${C_BOLD}  OrveX VPS Node is installed and connected to ${PANEL_URL}${C_RESET}"
        cat <<EOF

    Templates and the shared-IPv4 pool were added to this node in the panel.
    Next in OrveX Panel:
      1. Node > IP Pool: add any extra public IPv4s of this server (dedicated IPs, bridge ${C_BOLD}orvexpub0${C_RESET}).
      2. Admin > Settings: turn on "Proxy VNC via panel" for the in-browser console of KVM servers.
      3. Admin > Virtual Servers (VPS) > Create: pick this node, a template, an IP and resources for a user.

    Manage: orvex-node status | orvex-node doctor | orvex node-update

EOF
        return
    fi

    orvex-node info
    cat <<EOF
  ${C_BOLD}Connect this node to OrveX Panel${C_RESET}
    Easiest: in the panel open Admin > Nodes (VPS) > Create and run the
    "orvex-node register ..." part of the command it shows on this server.

    By hand instead (if this server cannot reach the panel): Admin > Nodes (VDS) >
    Create with the values above (enable "Skip TLS verification"). The panel sees the
    orvex@orvex user and lists the node under Nodes (VPS); add the shared pool,
    templates (VMIDs above) and dedicated IPv4s (bridge ${C_BOLD}orvexpub0${C_RESET}) there yourself.

EOF
}

update_vps_node() {
    need_root
    [ -d "$NODE_DIR/src/.git" ] || die "No OrveX VPS node agent found in $NODE_DIR"
    step "Updating the OrveX node agent"
    fetch_repo "$NODE_DIR/src" vps-node
    install -m 0755 "$NODE_DIR/src/vps-node/orvex-node" /usr/local/bin/orvex-node
    install -m 0644 "$NODE_DIR/src/vps-node/orvex-node.service" /etc/systemd/system/orvex-node.service
    install_cli_helper "$NODE_DIR/src/install.sh"
    systemctl daemon-reload
    systemctl restart orvex-node
    ok "Agent updated and restarted ($(orvex-node version 2>/dev/null || echo unknown))"
}

uninstall_vps_node() {
    [ -f /etc/systemd/system/orvex-node.service ] || {
        info "No OrveX VPS node agent installed"
        return
    }
    warn "Guests keep running in Incus; delete them in the panel first if you want them gone."
    confirm "Remove the OrveX node agent?" n || return
    systemctl disable --now orvex-node >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/orvex-node.service /usr/local/bin/orvex-node
    systemctl daemon-reload
    rm -rf "$NODE_DIR"
    if [ "$PURGE" -eq 1 ]; then
        rm -rf "$NODE_CONFIG_DIR" "$NODE_STATE_DIR"
        ok "Agent removed (configuration and state deleted)"
    else
        ok "Agent removed (configuration kept in $NODE_CONFIG_DIR)"
    fi
}

# ================================================================ GENERAL
show_status() {
    step "OrveX status"
    if [ -f "$PANEL_STATE" ]; then
        load_panel_state
        ok "Panel: $PANEL_DIR (${COMPOSE_FILE}${DOMAIN:+, https://$DOMAIN})"
        compose ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}' 2>/dev/null || compose ps || true
    else
        info "Panel: not installed on this server"
    fi
    if [ -f /etc/systemd/system/orvex-node.service ]; then
        ok "VPS node agent: $(systemctl is-active orvex-node 2>/dev/null || true) ($(orvex-node version 2>/dev/null || echo '?'))"
        orvex-node status || true
    else
        info "VPS node: not installed on this server"
    fi
}

uninstall_menu() {
    local choice=""
    case "$UNINSTALL_TARGET" in
        panel) choice=1 ;;
        node | vps-node) choice=2 ;;
        *)
            printf '\n  1) Remove OrveX Panel\n  2) Remove OrveX VPS node agent\n  0) Back\n'
            ask choice "Choose" "0"
            ;;
    esac
    case "$choice" in
        1) uninstall_panel ;;
        2) uninstall_vps_node ;;
        *) ;;
    esac
}

usage() {
    cat <<EOF
${C_BOLD}OrveX Panel installer${C_RESET}

Usage: install.sh [command] [options]

Commands:
  panel          Install OrveX Panel (Docker)
  vps-node       Turn this server into an OrveX VPS node (KVM + LXC, dedicated + shared IPv4)
  update         Update OrveX Panel
  node-update    Update the VPS node agent
  status         Show what is installed and running
  uninstall      Remove the panel or the node agent: uninstall [panel|vps-node] [--purge]
  help           Show this help

Panel options:
  --domain NAME          Serve the panel on https://NAME (automatic Let's Encrypt via Caddy)
  --email ADDRESS        E-mail for Let's Encrypt
  --port PORT            Local panel port (default 4831)
  --images               Use prebuilt images from GHCR instead of building from source

VPS node options:
  --panel URL --token T  Connect to OrveX Panel automatically. The panel shows this command
                         with both values: Admin > Nodes (VPS) > Create
  --name NAME            Node name on the server (default: hostname)
  --public-ip IP         Public IPv4 for shared-IPv4 port forwards (auto-detected)
  --storage-driver D     btrfs (default), dir, lvm or zfs (Ubuntu)
  --storage-size SIZE    Size of the storage pool image, e.g. 200GiB
  --storage-source DEV   Use a whole disk/partition for the pool (DESTROYS ITS DATA)
  --nat-subnet CIDR      Shared IPv4 subnet (default 10.77.0.0/24)
  --api-port PORT        Node API port (default 8006)
  --templates LIST       Templates to pre-download (default: ${TEMPLATES})
  --no-templates         Skip template downloads

General:
  -y, --yes              Non-interactive: accept the defaults
  --branch NAME          Install from another branch (default ${ORVEX_DEFAULT_BRANCH}).
                         Updates keep the branch a server was installed from.

Examples:
  curl -fsSL ${INSTALLER_URL} | sudo bash
  curl -fsSL ${INSTALLER_URL} | sudo bash -s -- panel --domain panel.example.com
  curl -fsSL ${INSTALLER_URL} | sudo bash -s -- vps-node --panel https://panel.example.com --token orvx_... -y
  curl -fsSL ${INSTALLER_URL} | sudo bash -s -- vps-node --storage-size 300GiB -y
EOF
}

menu() {
    local choice=""
    cat <<EOF
  ${C_BOLD}What do you want to do?${C_RESET}

    ${C_MAGENTA}1${C_RESET}) Install OrveX Panel
    ${C_MAGENTA}2${C_RESET}) Install OrveX VPS Node   ${C_DIM}(KVM + LXC · dedicated & shared IPv4)${C_RESET}
    ${C_MAGENTA}3${C_RESET}) Update OrveX Panel
    ${C_MAGENTA}4${C_RESET}) Update OrveX VPS Node
    ${C_MAGENTA}5${C_RESET}) Status
    ${C_MAGENTA}6${C_RESET}) Uninstall
    ${C_MAGENTA}0${C_RESET}) Exit

EOF
    ask choice "Choose an option" "1"
    case "$choice" in
        1) install_panel ;;
        2) install_vps_node ;;
        3) update_panel ;;
        4) update_vps_node ;;
        5) show_status ;;
        6) uninstall_menu ;;
        *) exit 0 ;;
    esac
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            panel | vps-node | node)
                if [ "$CMD" = "uninstall" ]; then UNINSTALL_TARGET=$1; else CMD=$1; fi
                ;;
            update | node-update | status | uninstall | help) CMD=$1 ;;
            -h | --help) CMD=help ;;
            -y | --yes) ASSUME_YES=1 ;;
            --domain) DOMAIN=${2:?--domain needs a value}; shift ;;
            --email) EMAIL=${2:?--email needs a value}; shift ;;
            --port) PANEL_PORT=${2:?--port needs a value}; shift ;;
            --images) USE_IMAGES=1 ;;
            --name) NODE_NAME=${2:?--name needs a value}; shift ;;
            --public-ip) PUBLIC_IP=${2:?--public-ip needs a value}; shift ;;
            --storage-driver) STORAGE_DRIVER=${2:?--storage-driver needs a value}; shift ;;
            --storage-size) STORAGE_SIZE=${2:?--storage-size needs a value}; shift ;;
            --storage-source) STORAGE_SOURCE=${2:?--storage-source needs a value}; shift ;;
            --nat-subnet) NAT_SUBNET=${2:?--nat-subnet needs a value}; shift ;;
            --api-port) NODE_PORT=${2:?--api-port needs a value}; shift ;;
            --templates) TEMPLATES=${2:?--templates needs a value}; shift ;;
            --no-templates) SKIP_TEMPLATES=1 ;;
            --panel) PANEL_URL=${2:?--panel needs a value}; shift ;;
            --token) NODE_TOKEN=${2:?--token needs a value}; shift ;;
            --branch)
                ORVEX_BRANCH=${2:?--branch needs a value}
                BRANCH_SET=1
                INSTALLER_URL="https://raw.githubusercontent.com/${ORVEX_REPO}/${ORVEX_BRANCH}/install.sh"
                shift
                ;;
            --purge) PURGE=1 ;;
            *) die "Unknown option: $1 (see: install.sh help)" ;;
        esac
        shift
    done
}

main() {
    parse_args "$@"
    if [ "$CMD" = "help" ]; then
        usage
        return
    fi
    banner
    case "$CMD" in
        panel) install_panel ;;
        vps-node | node) install_vps_node ;;
        update) update_panel ;;
        node-update) update_vps_node ;;
        status) show_status ;;
        uninstall) need_root; uninstall_menu ;;
        "")
            if [ "$HAVE_TTY" -eq 1 ] && [ "$ASSUME_YES" -eq 0 ]; then
                menu
            else
                usage
            fi
            ;;
    esac
}

# Everything above only defines functions: a partially downloaded script does nothing.
main "$@"
