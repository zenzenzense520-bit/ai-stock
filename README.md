# AI Stock：Python 股票策略回测练手项目

本项目从公开接口获取 A 股前复权日线数据，使用 pandas 实现双均线、动量和布林带三种简单策略，并输出总收益率、最大回撤、胜率等回测指标。

> 仅用于编程和量化学习，不构成投资建议。公开接口可能调整或限流，生产用途应改用稳定、授权的数据源。

## 功能

- 公开数据：东方财富 A 股列表和历史 K 线，腾讯历史 K 线作为备用源
- 策略：双均线、20 日动量、布林带均值回归
- 回测：下一交易日开盘成交，模拟 A 股 100 股整数手、T+1、佣金、印花税和滑点
- 指标：总收益率、年化收益率、最大回撤、胜率、夏普比率和相对上证指数收益
- 输出：`output/report.csv` 与各策略净值图，运行日志写入 `logs/ai_stock.log`

## 快速开始

需要 Python 3.12、[uv](https://docs.astral.sh/uv/) 和 Bash。

```bash
bash scripts/run.sh --pool-size 8 --years 5
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

所有信号在当日收盘后生成，并延迟到下一交易日开盘执行，以避免前视偏差。胜率按“盈利的已平仓交易数 ÷ 已平仓交易总数”计算。

## 项目结构

```text
src/ai_stock/       数据、策略、回测与命令入口
scripts/run.sh      统一运行入口
scripts/test.sh     统一测试入口
tests/              回测口径测试
output/             回测报告与净值图
logs/               本地运行日志
```
