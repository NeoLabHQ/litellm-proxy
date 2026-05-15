#!/usr/bin/env bash
#
# LiteLLM Proxy — bare-metal installer
#
# Usage:
#   sudo ./install.sh              Install or restart (idempotent)
#   sudo ./install.sh --uninstall  Stop service, remove everything
#
# Files are symlinked from the repo, not copied.
# Update workflow: git pull && sudo ./install.sh
#
set -euo pipefail

# --- Configuration -----------------------------------------------------------
INSTALL_DIR="/opt/litellm-proxy"
VENV_DIR="${INSTALL_DIR}/venv"
SERVICE_NAME="litellm-proxy"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LITELLM_VERSION="1.83.7"
LITELLM_PORT=4000

# Files to symlink from repo into install dir
LINK_FILES=(config.yaml custom_auth.py request_transformer.py .env)

# --- Helpers ------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

info()  { echo -e "\033[1;32m[+]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[!]\033[0m $*"; }
error() { echo -e "\033[1;31m[-]\033[0m $*" >&2; }
die()   { error "$@"; exit 1; }

require_root() {
    [[ $EUID -eq 0 ]] || die "This script must be run as root (use sudo)"
}

is_installed() {
    [[ -f "${SERVICE_FILE}" ]] && [[ -d "${VENV_DIR}" ]]
}

# --- Install / Restart --------------------------------------------------------
do_install() {
    require_root

    if is_installed; then
        info "Already installed — restarting service..."
        link_files
        systemctl restart "${SERVICE_NAME}"
        systemctl --no-pager status "${SERVICE_NAME}"
        return
    fi

    info "Installing LiteLLM Proxy (bare metal)..."

    # System dependencies
    info "Installing system packages..."
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv git > /dev/null

    # Install directory + venv
    mkdir -p "${INSTALL_DIR}"
    info "Creating Python virtual environment..."
    python3 -m venv "${VENV_DIR}"

    # Install litellm
    info "Installing litellm==${LITELLM_VERSION} (this may take a minute)..."
    "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
    "${VENV_DIR}/bin/pip" install --quiet "litellm[proxy]==${LITELLM_VERSION}"

    # Symlink files
    link_files

    # systemd service
    info "Creating systemd service..."
    cat > "${SERVICE_FILE}" <<UNIT
[Unit]
Description=LiteLLM Proxy
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${VENV_DIR}/bin/litellm --config ${INSTALL_DIR}/config.yaml --port ${LITELLM_PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}"
    systemctl start "${SERVICE_NAME}"

    info "Done! Service is running on port ${LITELLM_PORT}"
    info "Check status:  systemctl status ${SERVICE_NAME}"
    info "View logs:     journalctl -u ${SERVICE_NAME} -f"
    info "Health check:  curl http://localhost:${LITELLM_PORT}/health"
}

# --- Uninstall ----------------------------------------------------------------
do_uninstall() {
    require_root
    info "Uninstalling LiteLLM Proxy..."

    if systemctl is-active "${SERVICE_NAME}" &>/dev/null; then
        info "Stopping service..."
        systemctl stop "${SERVICE_NAME}"
    fi
    if systemctl is-enabled "${SERVICE_NAME}" &>/dev/null; then
        systemctl disable "${SERVICE_NAME}"
    fi

    if [[ -f "${SERVICE_FILE}" ]]; then
        rm -f "${SERVICE_FILE}"
        systemctl daemon-reload
    fi

    if [[ -d "${INSTALL_DIR}" ]]; then
        info "Removing ${INSTALL_DIR}..."
        rm -rf "${INSTALL_DIR}"
    fi

    info "Done!"
}

# --- Symlink files ------------------------------------------------------------
link_files() {
    for f in "${LINK_FILES[@]}"; do
        local src="${SCRIPT_DIR}/${f}"
        local dst="${INSTALL_DIR}/${f}"

        if [[ ! -f "${src}" ]]; then
            [[ "${f}" == ".env" ]] && warn "No .env found — create one: cp .env.example .env"
            continue
        fi

        rm -f "${dst}"
        ln -s "${src}" "${dst}"
    done
}

# --- Main ---------------------------------------------------------------------
case "${1:-}" in
    --uninstall) do_uninstall ;;
    --help|-h)
        echo "Usage: sudo $0 [--uninstall|--help]"
        echo ""
        echo "  (no args)    Install or restart (idempotent)"
        echo "  --uninstall  Stop service, remove everything"
        ;;
    "") do_install ;;
    *)  die "Unknown option: $1 (use --help)" ;;
esac
