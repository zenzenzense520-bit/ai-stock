# -*- coding: utf-8 -*-
"""入口：选股 → 拉K线 → 多策略单标的回测 + 组合回测 → 报告输出。"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ai_stock import backtest, fetch, strategy

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT_DIR = Path(os.environ.get("AI_STOCK_OUT", "output"))
LOG_DIR = Path("logs")


def _configure_logging() -> None:
    """修改说明：运行日志同时写入 logs/ai_stock.log。"""
    LOG_DIR.mkdir(exist_ok=True, parents=True)
    logging.basicConfig(
        filename=LOG_DIR / "ai_stock.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def _load_pool(args: argparse.Namespace) -> list:
    """股票池：手动 CSV 优先，否则东财选股。"""
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
                  strat_name: str, bench: pd.Series) -> dict:
    signal = strategy.STRATEGIES[strat_name](df)
    res = backtest.run_backtest(df, signal)
    res.code = code
    res.strategy = strat_name
    perf = backtest.performance(res.equity, bench, trades=res.trades)
    print(f"  [{strat_name}] {code} {name}: 总收益 {perf['总收益率']}% | "
          f"回撤 {perf['最大回撤']}% | 胜率 {perf['胜率']}% | "
          f"交易 {len(res.trades)} 次")
    return {"code": code, "name": name, "strategy": strat_name, **perf}


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
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True, parents=True)
    strat_list = [s.strip() for s in args.strategies.split(",") if s.strip()]
    for s in strat_list:
        if s not in strategy.STRATEGIES:
            print(f"未知策略: {s}，可选: {list(strategy.STRATEGIES)}")
            return 2

    pool = _load_pool(args)
    if not pool:
        print("股票池为空，退出")
        return 1

    print(f"[行情] 拉取 {len(pool)} 只股票近 {args.years} 年前复权日K...")
    frames = fetch.fetch_pool_kline(pool, years=args.years)
    if not frames:
        print("所有标的K线拉取失败，退出")
        return 1

    print("[基准] 拉取上证指数...")
    bench_df = fetch.fetch_index_kline(years=args.years)
    bench = bench_df["close"] / bench_df["close"].iloc[0]
    common_idx = None
    for df in frames.values():
        common_idx = df.index if common_idx is None else common_idx.intersection(df.index)
    bench = bench.loc[common_idx]
    # 对齐：截取各标的公共区间
    frames = {c: df.loc[common_idx] for c, df in frames.items()}

    rows: list[dict] = []
    best_curves: dict[str, pd.Series] = {}
    for strat_name in strat_list:
        print(f"\n=== 策略: {strat_name} ===")
        for code, df in frames.items():
            st = next((x for x in pool if x.code == code), None)
            name = st.name if st else code
            row = _run_strategy(code, name, df, strat_name, bench)
            rows.append(row)
        # 组合回测
        signal_map = {c: strategy.STRATEGIES[strat_name](df)
                      for c, df in frames.items()}
        port, port_trades = backtest.portfolio_backtest(frames, signal_map)
        perf_p = backtest.performance(port, bench, trades=port_trades)
        print(f"  [组合等权] 总收益 {perf_p['总收益率']}% | "
              f"回撤 {perf_p['最大回撤']}% | 胜率 {perf_p['胜率']}% | "
              f"基准 {perf_p['基准收益率']}% | 超额 {perf_p['超额收益率']}%")
        rows.append({"code": "组合", "name": "等权组合", "strategy": strat_name,
                     **perf_p})
        equity_map = {f"{c}": frames[c]["close"] / frames[c]["close"].iloc[0]
                      for c in frames}
        equity_map[f"[{strat_name}] 策略组合"] = port
        equity_map["基准 上证指数"] = bench
        _save_chart(equity_map, f"策略 {strat_name} 组合净值 vs 基准（近{args.years}年）",
                    OUT_DIR / f"equity_{strat_name}.png")

    # 汇总表
    df_report = pd.DataFrame(rows)
    report_path = OUT_DIR / "report.csv"
    df_report.to_csv(report_path, index=False, encoding="utf-8-sig")
    logging.info("回测完成，报告路径=%s，记录数=%s", report_path, len(df_report))
    print(f"\n[报告] 汇总已写入 {report_path}")
    print("\n=== 汇总（单标的按策略） ===")
    print(df_report.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
