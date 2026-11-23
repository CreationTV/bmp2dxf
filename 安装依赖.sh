#!/usr/bin/env bash
# Install bmp2dxf dependencies into a local virtual environment.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -e .
echo "安装完成。运行 ./启动工具.sh 启动网页界面。"
