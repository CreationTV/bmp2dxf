#!/usr/bin/env bash
# bmp2dxf local web UI launcher for Linux / macOS.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "未找到虚拟环境，请先运行："
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/pip install -r requirements.txt"
  echo "  .venv/bin/pip install -e ."
  exit 1
fi

exec .venv/bin/python -m bmp2dxf.web --open "$@"
