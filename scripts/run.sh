#!/usr/bin/env bash
# Run & Debug 入口：A股选股+多策略回测
# 用法: bash scripts/run.sh [--pool-size 8] [--years 5] [--strategies ma_cross,momentum,bollinger] [--pool-file pool.csv]
set -e
cd "$(dirname "$0")/.."

POOL_SIZE=8
YEARS=5
STRATEGIES="ma_cross,momentum,bollinger"
POOL_FILE=""
MAX_POSITION=0.8
STOP_LOSS=0.08
TAKE_PROFIT=0.2
MAX_DRAWDOWN=0.2
FACTOR_TOP_N=3
FACTOR_TRAIN_DAYS=252
FACTOR_TEST_DAYS=63
FACTOR_REBALANCE_DAYS=20

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pool-size) POOL_SIZE="$2"; shift 2 ;;
    --years) YEARS="$2"; shift 2 ;;
    --strategies) STRATEGIES="$2"; shift 2 ;;
    --pool-file) POOL_FILE="$2"; shift 2 ;;
    --max-position) MAX_POSITION="$2"; shift 2 ;;
    --stop-loss) STOP_LOSS="$2"; shift 2 ;;
    --take-profit) TAKE_PROFIT="$2"; shift 2 ;;
    --max-drawdown) MAX_DRAWDOWN="$2"; shift 2 ;;
    --factor-top-n) FACTOR_TOP_N="$2"; shift 2 ;;
    --factor-train-days) FACTOR_TRAIN_DAYS="$2"; shift 2 ;;
    --factor-test-days) FACTOR_TEST_DAYS="$2"; shift 2 ;;
    --factor-rebalance-days) FACTOR_REBALANCE_DAYS="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
done

ARGS="--pool-size $POOL_SIZE --years $YEARS --strategies $STRATEGIES --max-position $MAX_POSITION --stop-loss $STOP_LOSS --take-profit $TAKE_PROFIT --max-drawdown $MAX_DRAWDOWN --factor-top-n $FACTOR_TOP_N --factor-train-days $FACTOR_TRAIN_DAYS --factor-test-days $FACTOR_TEST_DAYS --factor-rebalance-days $FACTOR_REBALANCE_DAYS"
if [[ -n "$POOL_FILE" ]]; then
  ARGS="$ARGS --pool-file $POOL_FILE"
fi

# 未安装依赖时自动安装
[[ -d .venv ]] || uv sync

# 修改说明：统一通过 uv 的项目命令运行，并保留 Python 文件日志。
uv run ai-stock $ARGS
