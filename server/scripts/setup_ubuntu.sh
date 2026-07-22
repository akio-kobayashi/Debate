#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER_DIR="${PROJECT_DIR}/server"
MODEL="${OLLAMA_MODEL:-gemma4:31b}"
OVERLAY_PROVIDER="${OVERLAY_PROVIDER:-}"
TAILSCALE_SERVE=0
SKIP_MODEL=0
DEBATE_PORT="${DEBATE_PORT:-8000}"
DEBATE_USER="${DEBATE_USER:-${SUDO_USER:-$(id -un)}}"

log() {
  printf '[Debate setup] %s\n' "$*"
}

warn() {
  printf '[Debate setup][warning] %s\n' "$*" >&2
}

die() {
  printf '[Debate setup][error] %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage:
  sudo DEBATE_USER=<ubuntu-user> ./server/scripts/setup_ubuntu.sh --overlay tailscale

Options:
  --overlay netbird|tailscale|none
  --model <ollama-model>       Default: gemma4:31b
  --tailscale-serve            Tailscale only; expose the API through Tailscale HTTPS
  --skip-model                 Do not run ollama pull
  --project-dir <path>         Debate project directory
  --help

The script installs packages, Ollama, the selected overlay client, the Python
environment, the model, and a systemd unit for the Debate API.
It never runs netbird up or tailscale up; enrollment remains an explicit
operator action.
USAGE
}

while (($# > 0)); do
  case "$1" in
    --overlay)
      (($# >= 2)) || die "--overlay requires a value"
      OVERLAY_PROVIDER="$2"
      shift 2
      ;;
    --model)
      (($# >= 2)) || die "--model requires a value"
      MODEL="$2"
      shift 2
      ;;
    --tailscale-serve)
      TAILSCALE_SERVE=1
      shift
      ;;
    --skip-model)
      SKIP_MODEL=1
      shift
      ;;
    --project-dir)
      (($# >= 2)) || die "--project-dir requires a value"
      PROJECT_DIR="$(cd "$2" && pwd)"
      SERVER_DIR="${PROJECT_DIR}/server"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || die "run this script with sudo"
[[ -d "$SERVER_DIR/app" ]] || die "server/app was not found under $PROJECT_DIR"

case "$OVERLAY_PROVIDER" in
  netbird|tailscale|none) ;;
  "") die "choose --overlay netbird, --overlay tailscale, or --overlay none" ;;
  *) die "unsupported overlay provider: $OVERLAY_PROVIDER" ;;
esac

if [[ "$TAILSCALE_SERVE" -eq 1 && "$OVERLAY_PROVIDER" != "tailscale" ]]; then
  die "--tailscale-serve requires --overlay tailscale"
fi

export DEBIAN_FRONTEND=noninteractive
log "project: $PROJECT_DIR"
log "model: $MODEL"
log "overlay: $OVERLAY_PROVIDER"
log "runtime user: $DEBATE_USER"

apt-get update
apt-get install -y curl ca-certificates python3 python3-venv python3-pip

if ! command -v ollama >/dev/null 2>&1; then
  log "installing Ollama"
  curl -fsSL https://ollama.com/install.sh | sh
fi
command -v ollama >/dev/null 2>&1 || die "ollama command was not installed"

mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/debate.conf <<'OLLAMA_CONF'
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_NO_CLOUD=1"
OLLAMA_CONF
systemctl daemon-reload
systemctl restart ollama
systemctl enable --now ollama

log "waiting for Ollama"
ollama_ready=0
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then
    ollama_ready=1
    break
  fi
  sleep 1
done
[[ "$ollama_ready" -eq 1 ]] || die "Ollama did not become ready; inspect: journalctl -u ollama"

if [[ "$SKIP_MODEL" -eq 0 ]]; then
  log "pulling model: $MODEL"
  if id ollama >/dev/null 2>&1; then
    runuser -u ollama -- env HOME=/usr/share/ollama ollama pull "$MODEL"
  else
    ollama pull "$MODEL"
  fi
fi

if [[ "$OVERLAY_PROVIDER" == "netbird" ]] && ! command -v netbird >/dev/null 2>&1; then
  log "installing NetBird"
  curl -fsSL https://pkgs.netbird.io/install.sh | sh
fi
if [[ "$OVERLAY_PROVIDER" == "tailscale" ]] && ! command -v tailscale >/dev/null 2>&1; then
  log "installing Tailscale"
  curl -fsSL https://tailscale.com/install.sh | sh
fi

case "$OVERLAY_PROVIDER" in
  netbird)
    command -v netbird >/dev/null 2>&1 || die "netbird command was not installed"
    ;;
  tailscale)
    command -v tailscale >/dev/null 2>&1 || die "tailscale command was not installed"
    ;;
esac

log "creating Python virtual environment"
python3 -m venv "$SERVER_DIR/.venv"
"$SERVER_DIR/.venv/bin/python" -m pip install --upgrade pip
"$SERVER_DIR/.venv/bin/pip" install -r "$SERVER_DIR/requirements.txt"

if [[ "$TAILSCALE_SERVE" -eq 1 ]]; then
  BIND_HOST=127.0.0.1
else
  BIND_HOST="${DEBATE_BIND_HOST:-0.0.0.0}"
fi

cat > /etc/debate-api.env <<ENV_FILE
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=$MODEL
OLLAMA_NUM_CTX=${OLLAMA_NUM_CTX:-8192}
OLLAMA_TIMEOUT_SECONDS=${OLLAMA_TIMEOUT_SECONDS:-300}
DEBATE_BIND_HOST=$BIND_HOST
DEBATE_PORT=$DEBATE_PORT
OVERLAY_PROVIDER=$OVERLAY_PROVIDER
ENV_FILE
chmod 0644 /etc/debate-api.env

cat > /etc/systemd/system/debate-api.service <<SERVICE_FILE
[Unit]
Description=Debate Demo API
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
User=$DEBATE_USER
Group=$DEBATE_USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=/etc/debate-api.env
ExecStart=$SERVER_DIR/.venv/bin/uvicorn server.app.main:app --host $BIND_HOST --port $DEBATE_PORT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICE_FILE

systemctl daemon-reload
systemctl enable --now debate-api

api_ready=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:"$DEBATE_PORT"/health >/dev/null; then
    api_ready=1
    break
  fi
  sleep 1
done
[[ "$api_ready" -eq 1 ]] || die "Debate API did not become ready; inspect: journalctl -u debate-api"

if [[ "$TAILSCALE_SERVE" -eq 1 ]]; then
  log "configuring Tailscale Serve"
  if ! tailscale serve --bg --https=443 http://127.0.0.1:"$DEBATE_PORT"; then
    warn "Tailscale Serve was not configured. Enable HTTPS certificates and run the command manually."
  fi
fi

log "setup completed"
log "local API: http://127.0.0.1:$DEBATE_PORT"
case "$OVERLAY_PROVIDER" in
  netbird)
    log "next: sudo netbird up"
    log "then inspect the server address with: netbird status"
    log "direct client URL: http://<netbird-ip>:$DEBATE_PORT"
    ;;
  tailscale)
    log "next: sudo tailscale up"
    log "then inspect the server address with: tailscale status && tailscale ip -4"
    if [[ "$TAILSCALE_SERVE" -eq 1 ]]; then
      log "after Serve is enabled, use the HTTPS URL shown by: tailscale serve status"
    else
      log "direct client URL: http://<tailscale-ip>:$DEBATE_PORT"
    fi
    ;;
  none)
    log "overlay disabled; use the API only from this server or a separately secured network"
    ;;
esac
