#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${DEBATE_URL:-${1:-}}"

if [[ -z "$BASE_URL" ]]; then
  printf 'Usage: DEBATE_URL=http://127.0.0.1:8000 %s\n' "$0" >&2
  exit 2
fi

BASE_URL="${BASE_URL%/}"
printf 'Checking Debate API: %s/health\n' "$BASE_URL"
curl --fail --silent --show-error "$BASE_URL/health" >/dev/null

case "${OSTYPE:-}" in
  darwin*)
    open "$BASE_URL"
    ;;
  linux*)
    if command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$BASE_URL" >/dev/null 2>&1 &
    else
      printf 'Open this URL in a browser: %s\n' "$BASE_URL"
    fi
    ;;
  *)
    printf 'Open this URL in a browser: %s\n' "$BASE_URL"
    ;;
esac
