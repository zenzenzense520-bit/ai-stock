#!/usr/bin/env bash
# 测试入口：验证策略信号、次日成交和胜率口径。
set -e
cd "$(dirname "$0")/.."

[[ -d .venv ]] || uv sync
# 修改说明：不新增测试依赖，使用 Python 标准库 unittest。
uv run python -m unittest discover -s tests -v
