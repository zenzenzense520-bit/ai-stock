# -*- coding: utf-8 -*-
"""策略层：双均线 / 动量 / 布林带，输出目标持仓信号(0/1)。

约定：信号在 t 日收盘后计算，t+1 日开盘执行，避免前视偏差。
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

# 信号函数签名：输入日K，输出 0/1 持仓序列（与 df 对齐）
SignalFunc = Callable[[pd.DataFrame], pd.Series]


def ma_cross(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> pd.Series:
    """双均线：fast 上穿 slow 持有，下穿空仓。"""
    ma_fast = df["close"].rolling(fast).mean()
    ma_slow = df["close"].rolling(slow).mean()
    signal = (ma_fast > ma_slow).astype(int)
    return signal.fillna(0)


def momentum(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """动量：N 日收益为正且站上 N 日均线则持有。"""
    ret = df["close"].pct_change(lookback)
    above_ma = df["close"] > df["close"].rolling(lookback).mean()
    signal = ((ret > 0) & above_ma).astype(int)
    return signal.fillna(0)


def bollinger(df: pd.DataFrame, period: int = 20, width: float = 2.0) -> pd.Series:
    """布林带：收盘跌破下轨买入，回到中轨上方卖出。"""
    middle = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std(ddof=0)
    lower = middle - width * std

    # 修改说明：使用状态机保留开仓状态，避免中轨和下轨之间频繁切换。
    hold = pd.Series(0, index=df.index, dtype=int)
    state = 0
    for i in range(len(df)):
        close = df["close"].iloc[i]
        if state == 0 and close < lower.iloc[i]:
            state = 1
        elif state == 1 and close > middle.iloc[i]:
            state = 0
        hold.iloc[i] = state
    return hold


STRATEGIES: dict[str, SignalFunc] = {
    "ma_cross": ma_cross,
    "momentum": momentum,
    "bollinger": bollinger,
}
