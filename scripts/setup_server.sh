#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(uname -s)" == "Linux" ]]; then
  echo "[setup-server] Linux detected. Recommended packages:"
  echo "  sudo apt-get update"
  echo "  sudo apt-get install -y python3-venv ffmpeg build-essential"
  echo "[setup-server] Install Ollama and optional CUDA libraries separately if GPU offload is required."
else
  echo "[setup-server] Non-Linux host detected; running portable setup only."
fi

"$ROOT/.venv/bin/python" "$ROOT/scripts/setup_server.py"
