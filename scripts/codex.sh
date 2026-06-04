#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PATH="$ROOT_DIR/.npm-global/bin:$ROOT_DIR/.tools/node-v22.22.3-linux-x64/bin:$PATH"

exec codex "$@"
