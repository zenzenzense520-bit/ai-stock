#!/usr/bin/env bash
# Run & Debug 入口：A股选股+多策略回测
# 用法: bash scripts/run.sh [--pool-size 8] [--years 5] [--strategies ma_cross,momentum,bollinger] [--pool-file pool.csv]
set -e
cd "$(dirname "$0")/.."

POOL_SIZE=8
YEARS=5
STRATEGIES="ma_cross,momentum,bollinger"
POOL_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pool-size) POOL_SIZE="$2"; shift 2 ;;
    --years) YEARS="$2"; shift 2 ;;
    --strategies) STRATEGIES="$2"; shift 2 ;;
    --pool-file) POOL_FILE="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
done

ARGS="--pool-size $POOL_SIZE --years $YEARS --strategies $STRATEGIES"
if [[ -n "$POOL_FILE" ]]; then
  ARGS="$ARGS --pool-file $POOL_FILE"
fi

# 未安装依赖时自动安装
[[ -d .venv ]] || uv sync

# 修改说明：统一通过 uv 的项目命令运行，并保留 Python 文件日志。
uv run ai-stock $ARGS
