#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER_DIR="${PROJECT_DIR}/server"
ENV_FILE=/etc/debate-api.env
PULL_CODE=0
UPDATE_OLLAMA=0
PULL_MODEL=0

log() {
  printf '[Debate update] %s\n' "$*"
}

die() {
  printf '[Debate update][error] %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage:
  sudo ./server/scripts/update_server.sh

Options:
  --pull-code       Pull origin/main with git pull --ff-only
  --update-ollama   Re-run the official Ollama installer
  --pull-model      Pull the configured Ollama model
  --help
USAGE
}

while (($# > 0)); do
  case "$1" in
    --pull-code)
      PULL_CODE=1
      shift
      ;;
    --update-ollama)
      UPDATE_OLLAMA=1
      shift
      ;;
    --pull-model)
      PULL_MODEL=1
      shift
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
[[ -d "${SERVER_DIR}/app" ]] || die "server/app was not found under ${PROJECT_DIR}"
[[ -f "${ENV_FILE}" ]] || die "${ENV_FILE} was not found; run setup_ubuntu.sh first"

env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key { print substr($0, index($0, "=") + 1); exit }' "$ENV_FILE"
}

set_env_value() {
  local key="$1"
  local value="$2"
  local escaped_value
  escaped_value="${value//\\/\\\\}"
  escaped_value="${escaped_value//&/\\&}"
  escaped_value="${escaped_value//|/\\|}"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${escaped_value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

CURRENT_MODEL="$(env_value OLLAMA_MODEL || true)"
MODEL="${OLLAMA_MODEL:-${CURRENT_MODEL:-gemma4:31b}}"
NUM_CTX="${OLLAMA_NUM_CTX:-32768}"

if [[ "$PULL_CODE" -eq 1 ]]; then
  command -v git >/dev/null 2>&1 || die "git is required for --pull-code"
  CURRENT_BRANCH="$(git -C "$PROJECT_DIR" branch --show-current)"
  [[ "$CURRENT_BRANCH" == "main" ]] || die "--pull-code requires the main branch (current: ${CURRENT_BRANCH:-detached})"
  git -C "$PROJECT_DIR" diff --quiet || die "working tree has unstaged changes"
  [[ -z "$(git -C "$PROJECT_DIR" status --porcelain)" ]] || die "working tree is not clean"
  log "pulling origin/main"
  git -C "$PROJECT_DIR" pull --ff-only origin main
fi

if [[ "$UPDATE_OLLAMA" -eq 1 ]]; then
  command -v curl >/dev/null 2>&1 || die "curl is required for --update-ollama"
  log "updating Ollama"
  curl -fsSL https://ollama.com/install.sh | sh
fi

systemctl start ollama

if [[ "$PULL_MODEL" -eq 1 ]]; then
  log "pulling model: $MODEL"
  if id ollama >/dev/null 2>&1; then
    runuser -u ollama -- env HOME=/usr/share/ollama ollama pull "$MODEL"
  else
    ollama pull "$MODEL"
  fi
fi

[[ -x "${SERVER_DIR}/.venv/bin/pip" ]] || die "Python virtual environment was not found"
log "installing Japanese PDF font"
apt-get update
apt-get install -y fonts-noto-cjk
log "installing Python dependencies"
"${SERVER_DIR}/.venv/bin/pip" install -r "${SERVER_DIR}/requirements.txt"

set_env_value OLLAMA_MODEL "$MODEL"
set_env_value OLLAMA_NUM_CTX "$NUM_CTX"
set_env_value DEBATE_PDF_FONT_PATH "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
chmod 0644 "$ENV_FILE"

log "restarting services"
systemctl daemon-reload
systemctl restart ollama
systemctl restart debate-api

PORT="$(env_value DEBATE_PORT || echo 8000)"
api_ready=0
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    api_ready=1
    break
  fi
  sleep 1
done
[[ "$api_ready" -eq 1 ]] || die "Debate API health check failed; inspect: journalctl -u debate-api"

log "update completed"
log "model: $MODEL"
log "num_ctx: $NUM_CTX"
log "health: http://127.0.0.1:$PORT/health"
