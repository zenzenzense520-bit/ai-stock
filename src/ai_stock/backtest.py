# -*- coding: utf-8 -*-
"""回测引擎：单标的回测 + 等权组合回测 + 绩效指标。

模拟 A 股规则：T+1、涨跌停不可成交、停牌跳过、佣金/印花税/滑点。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

COMMISSION = 2.5e-4   # 佣金 万2.5
STAMP_TAX = 5e-4      # 印花税 0.05%（卖出单边）
SLIPPAGE = 1e-3       # 滑点 0.1%


@dataclass(frozen=True)
class RiskConfig:
    """基础风险参数，比例均使用 0~1 小数。"""
    max_position_pct: float = 0.8
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.2
    max_drawdown_pct: float = 0.2

    def __post_init__(self) -> None:
        values = (
            self.max_position_pct,
            self.stop_loss_pct,
            self.take_profit_pct,
            self.max_drawdown_pct,
        )
        if not all(0 < value <= 1 for value in values):
            raise ValueError("风险参数必须位于 (0, 1] 区间")


@dataclass
class Trade:
    """一条已成交记录。"""
    date: pd.Timestamp
    side: str  # buy / sell
    price: float
    shares: int
    amount: float
    fee: float
    reason: str = "signal"


@dataclass
class BacktestResult:
    """单标的回测结果。"""
    code: str
    strategy: str
    equity: pd.Series  # 每日净值（初始 1.0）
    trades: list[Trade] = field(default_factory=list)
    buy_hold: Optional[pd.Series] = None
    risk_halted: bool = False


def run_backtest(
    df: pd.DataFrame,
    signal: pd.Series,
    initial_cash: float = 1_000_000.0,
    commission: float = COMMISSION,
    stamp_tax: float = STAMP_TAX,
    slippage: float = SLIPPAGE,
    risk: Optional[RiskConfig] = None,
) -> BacktestResult:
    """逐日模拟：昨日收盘信号 → 今日开盘成交。

    涨跌停判断基于今日开盘价相对昨收的幅度；
    T+1：当日买入的仓位次日才能卖出。
    初始资金默认 100 万：A股按手(100股)交易，高价股(如茅台~1600元/股)
    一手即 16 万，资金不足会永远买不进（曾因 10 万资金导致 0 交易）。
    """
    # 修改说明：增加仓位、止损止盈和回撤熔断，并为买入佣金预留现金。
    risk = risk or RiskConfig()
    executed_signal = signal.reindex(df.index).shift(1).fillna(0).astype(int)
    cash = initial_cash
    shares = 0
    buy_date: Optional[pd.Timestamp] = None
    trades: list[Trade] = []
    equity_list: list[float] = []
    prev_close: Optional[float] = None
    entry_price: Optional[float] = None
    peak_equity = initial_cash
    risk_halted = False

    for ts, row in df.iterrows():
        open_p = float(row["open"])
        high_p = float(row["high"])
        low_p = float(row["low"])
        close_p = float(row["close"])
        target = int(executed_signal.loc[ts])
        equity_at_open = cash + shares * open_p
        if equity_at_open / peak_equity - 1 <= -risk.max_drawdown_pct:
            risk_halted = True
        limit_up = limit_down = False
        if prev_close is not None and prev_close > 0:
            limit_up = open_p >= prev_close * 1.098  # 近似涨停(10%口径)
            limit_down = open_p <= prev_close * 0.902  # 近似跌停

        sold_today = False
        can_sell = shares > 0 and not limit_down and (buy_date is None or ts > buy_date)
        exit_price: Optional[float] = None
        exit_reason = "signal"
        if can_sell and risk_halted:
            exit_price = open_p
            exit_reason = "max_drawdown"
        elif can_sell and entry_price is not None:
            stop_price = entry_price * (1 - risk.stop_loss_pct)
            take_price = entry_price * (1 + risk.take_profit_pct)
            if low_p <= stop_price:
                exit_price = min(open_p, stop_price)
                exit_reason = "stop_loss"
            elif high_p >= take_price:
                exit_price = max(open_p, take_price)
                exit_reason = "take_profit"
        if can_sell and exit_price is None and target == 0:
            exit_price = open_p

        if exit_price is not None:
                px = exit_price * (1 - slippage)
                amount = px * shares
                fee = amount * (commission + stamp_tax)
                cash += amount - fee
                trades.append(Trade(ts, "sell", px, shares, amount, fee, exit_reason))
                shares = 0
                buy_date = None
                entry_price = None
                sold_today = True

        # ---- 买入：目标持仓且空仓，非涨停 ----
        if (target == 1 and shares == 0 and not limit_up and cash > 0
                and not risk_halted and not sold_today):
            px = open_p * (1 + slippage)
            position_budget = min(cash / (1 + commission),
                                  equity_at_open * risk.max_position_pct)
            buyable = int(position_budget / (px * 100)) * 100
            if buyable > 0:
                amount = px * buyable
                fee = amount * commission
                cash -= amount + fee
                shares = buyable
                buy_date = ts
                entry_price = px
                trades.append(Trade(ts, "buy", px, buyable, amount, fee, "entry"))

        equity = cash + shares * close_p
        equity_list.append(equity)
        peak_equity = max(peak_equity, equity)
        prev_close = close_p

    equity = pd.Series(equity_list, index=df.index) / initial_cash
    buy_hold = df["close"] / df["close"].iloc[0]
    return BacktestResult(code="", strategy="", equity=equity,
                          trades=trades, buy_hold=buy_hold,
                          risk_halted=risk_halted)


def portfolio_backtest(
    frames: dict[str, pd.DataFrame],
    signal_map: dict[str, pd.Series],
    risk: Optional[RiskConfig] = None,
) -> tuple[pd.Series, list[Trade]]:
    """等权组合：先对每只股票做资金归一化回测，再按日取均值。

    简化：每日组合净值 = 各标的自有策略净值均值（等权、每日再平衡）。
    """
    curves: list[pd.Series] = []
    trades: list[Trade] = []
    for code, df in frames.items():
        if code not in signal_map:
            continue
        res = run_backtest(df, signal_map[code], risk=risk)
        curves.append(res.equity)
        trades.extend(res.trades)
    if not curves:
        raise RuntimeError("组合回测无可用标的")
    merged = pd.concat(curves, axis=1, join="inner")
    return merged.mean(axis=1), trades


def trade_win_rate(trades: list[Trade]) -> float:
    """按已平仓交易计算胜率，未卖出的持仓不计入分母。"""
    buy_cost: Optional[float] = None
    wins = 0
    closed = 0
    for trade in trades:
        if trade.side == "buy":
            buy_cost = trade.amount + trade.fee
        elif trade.side == "sell" and buy_cost is not None:
            closed += 1
            wins += trade.amount - trade.fee > buy_cost
            buy_cost = None
    return round(wins / closed * 100, 2) if closed else 0.0


def performance(equity: pd.Series, benchmark: Optional[pd.Series] = None,
                risk_free: float = 0.02, trades: Optional[list[Trade]] = None,
                ) -> dict[str, float]:
    """绩效指标：总收益/年化/最大回撤/夏普/胜率/基准对比。"""
    eq = equity.dropna()
    if len(eq) < 2:
        return {"总收益率": 0.0, "年化收益率": 0.0, "最大回撤": 0.0,
                "胜率": 0.0, "夏普比率": 0.0, "基准收益率": 0.0,
                "超额收益率": 0.0}
    total = eq.iloc[-1] / eq.iloc[0] - 1
    days = len(eq)
    ann = (eq.iloc[-1] / eq.iloc[0]) ** (250 / days) - 1
    dd = (eq / eq.cummax() - 1).min()
    daily_ret = eq.pct_change().dropna()
    sharpe = 0.0
    if daily_ret.std() > 0:
        sharpe = (daily_ret.mean() * 250 - risk_free) / (daily_ret.std() * np.sqrt(250))
    bench_ret = 0.0
    if benchmark is not None and len(benchmark) > 1:
        bench_ret = benchmark.iloc[-1] / benchmark.iloc[0] - 1
    return {
        "总收益率": round(total * 100, 2),
        "年化收益率": round(ann * 100, 2),
        "最大回撤": round(dd * 100, 2),
        "胜率": trade_win_rate(trades or []),
        "夏普比率": round(sharpe, 2),
        "基准收益率": round(bench_ret * 100, 2),
        "超额收益率": round((total - bench_ret) * 100, 2),
    }
