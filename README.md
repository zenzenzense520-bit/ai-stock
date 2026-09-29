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
- 因子输出：`output/factor_rank_weights.csv` 与 `output/equity_factor_rank.png`
- 线性基线：在相同滚动窗口上训练岭回归，并与多因子排名比较

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

若有经核验的历史成分数据，可用 `--universe-file` 指定 CSV。字段为 `code,valid_from,valid_to,published_at,source`，其中公布日不得晚于生效日，`source` 应填写可核查的来源。它与 `--pool-file` 互斥。数据格式、边界和限制见 [历史股票池与线性模型数据协议](docs/历史股票池与线性模型数据协议.md)。

已按上交所公告整理 [2024—2025 年上证50调样事件](docs/上证50历史调样来源.md)。这仅是调入/调出记录，不是完整历史股票池，不能直接传给 `--universe-file`。

另提供[深证100历史调样只读审计](docs/深证100历史调样审计.md)，可通过 `bash scripts/audit-cni.sh` 直接检查国证官网调样表的期次样本数量。该表缺少可核验的逐期公告发布时间，因此审计结果不能直接用于回测。

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
| `ridge_rank` | 训练窗拟合岭回归，测试窗按预测未来收益持有 Top N |

所有信号在当日收盘后生成，并延迟到下一交易日开盘执行，以避免前视偏差。胜率按“盈利的已平仓交易数 ÷ 已平仓交易总数”计算。

自动选股使用运行当日的 PE 和市值，只适合演示完整流程，不能用于证明历史选股有效。`--pool-file` 可提供事先固定的股票池；`--universe-file` 已支持按日期过滤候选，但仍需自行提供可核验的历史成分、退市行情，并解决组合估值限制，才能开展更严谨的历史回测。

## 项目结构

```text
src/ai_stock/       数据、策略、回测与命令入口
scripts/run.sh      统一运行入口
scripts/test.sh     统一测试入口
scripts/audit-cni.sh 国证历史调样只读审计入口
tests/              回测口径测试
output/             回测报告与净值图
logs/               本地运行日志
```
