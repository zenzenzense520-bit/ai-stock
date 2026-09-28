# -*- coding: utf-8 -*-
"""入口：选股 → 拉K线 → 多策略单标的回测 + 组合回测 → 报告输出。"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ai_stock import backtest, factors, fetch, linear_model, strategy, universe

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT_DIR = Path(os.environ.get("AI_STOCK_OUT", "output"))
LOG_DIR = Path("logs")
REPORT_COLUMNS = (
    "code", "name", "strategy", "总收益率", "年化收益率", "最大回撤",
    "胜率", "夏普比率", "基准收益率", "超额收益率",
)
FACTOR_WEIGHT_COLUMNS = (
    "训练开始", "训练结束", "测试开始", "测试结束",
    "动量权重", "低波动权重", "成交量权重", "趋势权重",
)


@dataclass(frozen=True)
class ReportRow:
    """一行回测报告，替代未结构化字典。"""
    code: str
    name: str
    strategy_name: str
    metrics: backtest.PerformanceMetrics

    def values(self) -> tuple[object, ...]:
        return (self.code, self.name, self.strategy_name, *self.metrics.values())


def _configure_logging() -> None:
    """修改说明：运行日志同时写入 logs/ai_stock.log。"""
    LOG_DIR.mkdir(exist_ok=True, parents=True)
    logging.basicConfig(
        filename=LOG_DIR / "ai_stock.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def _load_pool(args: argparse.Namespace, historical: universe.Universe | None) -> list[fetch.Stock]:
    """股票池：手动 CSV 优先，否则东财选股。"""
    if historical is not None:
        return [fetch.Stock(code, code, 0.0, 0.0, 0.0, 0.0)
                for code in historical.codes()]
    if args.pool_file:
        pool = fetch.load_manual_pool(args.pool_file)
        print(f"[选股] 手动股票池: {len(pool)} 只 (来源 {args.pool_file})")
        return pool
    pool = fetch.pick_stocks(pe_max=args.pe_max, cap_min_yi=args.cap_min,
                             limit=args.pool_size)
    print(f"[选股] 东财条件选股: PE(0,{args.pe_max}) 市值>{args.cap_min}亿 "
          f"→ {len(pool)} 只")
    for s in pool:
        print(f"   {s.code} {s.name}  PE={s.pe:.1f} 市值={s.market_cap/1e8:.0f}亿")
    return pool


def _run_strategy(code: str, name: str, df: pd.DataFrame,
                  strat_name: str, bench: pd.Series,
                  risk: backtest.RiskConfig) -> ReportRow:
    signal = strategy.STRATEGIES[strat_name](df)
    res = backtest.run_backtest(df, signal, risk=risk)
    res.code = code
    res.strategy = strat_name
    perf = backtest.performance(res.equity, bench, trades=res.trades)
    print(f"  [{strat_name}] {code} {name}: 总收益 {perf.total_return}% | "
          f"回撤 {perf.max_drawdown}% | 胜率 {perf.win_rate}% | "
          f"交易 {len(res.trades)} 次")
    return ReportRow(code, name, strat_name, perf)


def _save_chart(equity_map: dict[str, pd.Series], title: str, path: Path) -> None:
    plt.figure(figsize=(11, 5))
    for label, curve in equity_map.items():
        plt.plot(curve.index, curve.values, label=label, linewidth=1.2)
    plt.legend()
    plt.title(title)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=130)
    plt.close()


def _run_factor_strategy(
    frames: dict[str, pd.DataFrame],
    bench: pd.Series,
    risk: backtest.RiskConfig,
    result: factors.FactorSignals,
    strategy_name: str,
) -> ReportRow:
    """修改说明：两种模型共享样本外组合、费用、风控与基准口径。"""
    factor_frames = {
        code: frame.loc[result.first_test_date:]
        for code, frame in frames.items()
    }
    factor_signals = {
        code: signal.loc[result.first_test_date:]
        for code, signal in result.signals.items()
    }
    factor_bench = bench.loc[result.first_test_date:]
    factor_bench = factor_bench / factor_bench.iloc[0]
    equity, trades = backtest.portfolio_backtest(
        factor_frames, factor_signals, risk=risk)
    metrics = backtest.performance(equity, factor_bench, trades=trades)
    weights = pd.DataFrame(
        [fold.values() for fold in result.folds], columns=FACTOR_WEIGHT_COLUMNS)
    weights.to_csv(OUT_DIR / f"{strategy_name}_weights.csv",
                   index=False, encoding="utf-8-sig")
    _save_chart(
        {strategy_name: equity, "基准 上证指数": factor_bench},
        f"{strategy_name} 时间滚动样本外净值 vs 基准",
        OUT_DIR / f"equity_{strategy_name}.png",
    )
    print(f"  [{strategy_name}] 总收益 {metrics.total_return}% | "
          f"回撤 {metrics.max_drawdown}% | 胜率 {metrics.win_rate}% | "
          f"滚动窗口 {len(result.folds)} 个")
    return ReportRow("组合", "样本外组合", strategy_name, metrics)


def main() -> int:
    _configure_logging()
    ap = argparse.ArgumentParser(description="A股选股+多策略回测（学习工具）")
    ap.add_argument("--pool-size", type=int, default=8, help="选股数量")
    ap.add_argument("--pe-max", type=float, default=50.0, help="PE上限")
    ap.add_argument("--cap-min", type=float, default=100.0, help="市值下限(亿)")
    ap.add_argument("--years", type=int, default=5, help="回测年限")
    ap.add_argument("--strategies", default="ma_cross,momentum,bollinger",
                    help="逗号分隔策略名")
    ap.add_argument("--pool-file", default="", help="手动股票池CSV(code,name)")
    ap.add_argument("--universe-file", default="", help="历史成员CSV，含公布日与来源")
    ap.add_argument("--max-position", type=float, default=0.8, help="单标的仓位上限")
    ap.add_argument("--stop-loss", type=float, default=0.08, help="止损比例")
    ap.add_argument("--take-profit", type=float, default=0.2, help="止盈比例")
    ap.add_argument("--max-drawdown", type=float, default=0.2, help="最大回撤熔断比例")
    ap.add_argument("--factor-top-n", type=int, default=3, help="多因子持仓数量")
    ap.add_argument("--factor-train-days", type=int, default=252, help="因子训练窗口")
    ap.add_argument("--factor-test-days", type=int, default=63, help="因子测试窗口")
    ap.add_argument("--factor-rebalance-days", type=int, default=20, help="因子调仓周期")
    args = ap.parse_args()
    if args.pool_file and args.universe_file:
        print("--pool-file 和 --universe-file 不能同时指定")
        return 2

    try:
        risk = backtest.RiskConfig(
            max_position_pct=args.max_position,
            stop_loss_pct=args.stop_loss,
            take_profit_pct=args.take_profit,
            max_drawdown_pct=args.max_drawdown,
        )
    except ValueError as exc:
        print(f"风险参数错误: {exc}")
        return 2

    OUT_DIR.mkdir(exist_ok=True, parents=True)
    strat_list = [s.strip() for s in args.strategies.split(",") if s.strip()]
    for s in strat_list:
        if s not in strategy.STRATEGIES:
            print(f"未知策略: {s}，可选: {list(strategy.STRATEGIES)}")
            return 2

    try:
        historical = (universe.load_universe(args.universe_file)
                      if args.universe_file else None)
        pool = _load_pool(args, historical)
    except (RuntimeError, OSError, ValueError) as exc:
        logging.exception("股票池加载失败")
        print(f"股票池加载失败: {exc}")
        return 1
    if not pool:
        print("股票池为空，退出")
        return 1
    if not args.pool_file and historical is None:
        print("[提示] 自动筛选使用当前 PE/市值，仅适合演示；严谨历史回测请传入固定股票池。")
    if historical is not None:
        # 修改说明：历史成员模式只比较会逐日过滤成员的两种排名策略。
        strat_list = []
        print("[提示] 历史成员模式仅运行 factor_rank 与 ridge_rank")

    print(f"[行情] 拉取 {len(pool)} 只股票近 {args.years} 年前复权日K...")
    frames = fetch.fetch_pool_kline(pool, years=args.years)
    if not frames:
        print("所有标的K线拉取失败，退出")
        return 1
    print("[基准] 拉取上证指数...")
    bench_df = fetch.fetch_index_kline(years=args.years)
    if historical is not None:
        try:
            universe.validate_coverage(historical, frames, bench_df.index)
        except ValueError as exc:
            print(f"历史股票池无法完整回测: {exc}")
            return 1
    bench = bench_df["close"] / bench_df["close"].iloc[0]
    common_idx = None
    for df in frames.values():
        common_idx = df.index if common_idx is None else common_idx.intersection(df.index)
    common_idx = common_idx.intersection(bench_df.index)
    if common_idx.empty:
        print("标的与基准没有共同交易日")
        return 1
    if historical is not None and common_idx[-1] != bench_df.index[-1]:
        print("历史股票池含提前结束的行情；当前回测器尚不能处理退市/摘牌后的组合估值")
        return 1
    bench = bench.loc[common_idx]
    # 对齐：截取各标的公共区间
    frames = {c: df.loc[common_idx] for c, df in frames.items()}

    rows: list[ReportRow] = []
    for strat_name in strat_list:
        print(f"\n=== 策略: {strat_name} ===")
        for code, df in frames.items():
            st = next((x for x in pool if x.code == code), None)
            name = st.name if st else code
            row = _run_strategy(code, name, df, strat_name, bench, risk)
            rows.append(row)
        # 组合回测
        signal_map = {c: strategy.STRATEGIES[strat_name](df)
                      for c, df in frames.items()}
        port, port_trades = backtest.portfolio_backtest(frames, signal_map, risk=risk)
        perf_p = backtest.performance(port, bench, trades=port_trades)
        print(f"  [组合等权] 总收益 {perf_p.total_return}% | "
              f"回撤 {perf_p.max_drawdown}% | 胜率 {perf_p.win_rate}% | "
              f"基准 {perf_p.benchmark_return}% | 超额 {perf_p.excess_return}%")
        rows.append(ReportRow("组合", "等权组合", strat_name, perf_p))
        equity_map = {f"{c}": frames[c]["close"] / frames[c]["close"].iloc[0]
                      for c in frames}
        equity_map[f"[{strat_name}] 策略组合"] = port
        equity_map["基准 上证指数"] = bench
        _save_chart(equity_map, f"策略 {strat_name} 组合净值 vs 基准（近{args.years}年）",
                    OUT_DIR / f"equity_{strat_name}.png")

    print("\n=== 策略: factor_rank（时间滚动样本外） ===")
    try:
        factor_config = factors.FactorConfig(
            train_days=args.factor_train_days,
            test_days=args.factor_test_days,
            rebalance_days=args.factor_rebalance_days,
            top_n=args.factor_top_n,
        )
        factor_result = factors.generate_walk_forward_signals(
            frames, factor_config, historical)
        ridge_result = linear_model.generate_ridge_signals(
            frames, factor_config, historical)
        rows.append(_run_factor_strategy(frames, bench, risk,
                                         factor_result, "factor_rank"))
        rows.append(_run_factor_strategy(frames, bench, risk,
                                         ridge_result, "ridge_rank"))
    except ValueError as exc:
        print(f"  [SKIP] 多因子策略未运行: {exc}")

    # 汇总表
    df_report = pd.DataFrame(
        [row.values() for row in rows], columns=REPORT_COLUMNS)
    report_path = OUT_DIR / "report.csv"
    df_report.to_csv(report_path, index=False, encoding="utf-8-sig")
    logging.info("回测完成，报告路径=%s，记录数=%s", report_path, len(df_report))
    print(f"\n[报告] 汇总已写入 {report_path}")
    print("\n=== 汇总（单标的按策略） ===")
    print(df_report.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
