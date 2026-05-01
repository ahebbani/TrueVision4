#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(uname -s)" == "Linux" ]]; then
  echo "[setup-pi] Linux detected. Install system packages before first hardware run:"
  echo "  sudo apt-get update"
  echo "  sudo apt-get install -y python3-venv python3-opencv libatlas-base-dev libjpeg-dev libopenjp2-7 libtiff5 libavcodec-dev libavformat-dev libswscale-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev"
  echo "[setup-pi] Enable UART and camera separately if not already configured."
else
  echo "[setup-pi] Non-Linux host detected; running portable setup only."
fi

"$ROOT/.venv/bin/python" "$ROOT/scripts/setup_pi.py"
