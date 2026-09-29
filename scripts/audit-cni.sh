#!/usr/bin/env bash
# 修改说明：统一从 scripts/ 运行只读国证历史调样审计，并保留文件日志。
set -e
cd "$(dirname "$0")/.."
[[ -d .venv ]] || uv sync
uv run python -m ai_stock.cni_audit "$@"
