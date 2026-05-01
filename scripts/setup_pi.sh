#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

venv_uses_system_site_packages() {
  local cfg="$ROOT/.venv/pyvenv.cfg"
  [[ -f "$cfg" ]] && grep -Eiq '^include-system-site-packages = true$' "$cfg"
}

rebuild_pi_venv() {
  echo "[setup-pi] Rebuilding .venv with --system-site-packages so Picamera2 and apt-installed OpenCV are visible."
  rm -rf "$ROOT/.venv"
  python3 -m venv --system-site-packages "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install --upgrade pip
  (
    cd "$ROOT"
    "$ROOT/.venv/bin/pip" install -e '.[dev]'
  )
}

if [[ "$(uname -s)" == "Linux" ]]; then
  echo "[setup-pi] Linux detected. Install system packages before first hardware run:"
  echo "  sudo apt-get update"
  echo "  sudo apt-get install -y python3-venv python3-opencv python3-picamera2 python3-libcamera libatlas-base-dev libjpeg-dev libopenjp2-7 libtiff5 libavcodec-dev libavformat-dev libswscale-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev"
  echo "[setup-pi] Enable UART and camera separately if not already configured."
  if ! venv_uses_system_site_packages; then
    rebuild_pi_venv
  fi
else
  echo "[setup-pi] Non-Linux host detected; running portable setup only."
fi

"$ROOT/.venv/bin/python" "$ROOT/scripts/setup_pi.py"
