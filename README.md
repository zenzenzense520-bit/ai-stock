# AI Stock：Python 股票策略回测练手项目

本项目从公开接口获取 A 股前复权日线数据，使用 pandas 实现基础技术策略和时间滚动多因子选股，并输出总收益率、最大回撤、胜率等回测指标。

> 仅用于编程和量化学习，不构成投资建议。公开接口可能调整或限流，生产用途应改用稳定、授权的数据源。

## 功能

- 公开数据：东方财富 A 股列表和历史 K 线，腾讯历史 K 线作为备用源
- 策略：双均线、20 日动量、布林带均值回归
- 多因子：20 日动量、低波动、成交量强度和 60 日趋势的横截面排名
- 验证：252 日滚动训练、63 日样本外测试，训练标签不会跨入测试窗口
- 回测：下一交易日开盘成交，模拟 A 股 100 股整数手、T+1、佣金、印花税和滑点
- 风控：单标的仓位上限、止损、止盈和最大回撤熔断
- 指标：总收益率、年化收益率、最大回撤、胜率、夏普比率和相对上证指数收益
- 输出：`output/report.csv` 与各策略净值图，运行日志写入 `logs/ai_stock.log`
- 因子输出：`output/factor_weights.csv` 与 `output/equity_factor_rank.png`

## 快速开始

需要 Python 3.12、[uv](https://docs.astral.sh/uv/) 和 Bash。

```bash
bash scripts/run.sh --pool-size 8 --years 5
```

默认风险参数为 80% 仓位上限、8% 止损、20% 止盈和 20% 最大回撤熔断，可按需覆盖：

```bash
bash scripts/run.sh --max-position 0.6 --stop-loss 0.06 --take-profit 0.15 --max-drawdown 0.15
```

多因子默认每 20 个交易日选择综合得分最高的 3 只股票，可调整持仓数量和滚动窗口：

```bash
bash scripts/run.sh --factor-top-n 3 --factor-train-days 252 --factor-test-days 63 --factor-rebalance-days 20
```

指定股票池时，CSV 至少包含 `code` 列，可选 `name` 列：

```csv
code,name
600519,贵州茅台
300750,宁德时代
```

```bash
bash scripts/run.sh --pool-file pool.csv --years 3
```

仓库提供可复现的示例股票池，可直接运行：

```bash
bash scripts/run.sh --pool-file data/sample_pool.csv --years 2 --factor-top-n 2
```

运行测试：

```bash
bash scripts/test.sh
```

## 策略说明

| 策略参数 | 持有条件 |
|---|---|
| `ma_cross` | 5 日均线高于 20 日均线 |
| `momentum` | 20 日收益为正且收盘价高于 20 日均线 |
| `bollinger` | 跌破 20 日布林下轨买入，回到中轨上方卖出 |
| `factor_rank` | 训练窗估计因子 IC 权重，测试窗持有综合排名 Top N |

所有信号在当日收盘后生成，并延迟到下一交易日开盘执行，以避免前视偏差。胜率按“盈利的已平仓交易数 ÷ 已平仓交易总数”计算。

自动选股使用运行当日的 PE 和市值，只适合演示完整流程，不能用于证明历史选股有效。严谨历史回测应使用 `--pool-file` 提供事先固定的股票池，后续版本再接入历史成分股和历史财务数据。

## 项目结构

```text
src/ai_stock/       数据、策略、回测与命令入口
scripts/run.sh      统一运行入口
scripts/test.sh     统一测试入口
tests/              回测口径测试
output/             回测报告与净值图
logs/               本地运行日志
```
