# -*- coding: utf-8 -*-
"""价格量能因子与时间滚动多因子选股。"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

FACTOR_COLUMNS = ("momentum", "low_volatility", "volume_strength", "trend")


@dataclass(frozen=True)
class FactorConfig:
    """多因子与滚动验证参数。"""
    momentum_window: int = 20
    volatility_window: int = 20
    volume_window: int = 20
    trend_window: int = 60
    forward_window: int = 20
    train_days: int = 252
    test_days: int = 63
    rebalance_days: int = 20
    top_n: int = 3

    def __post_init__(self) -> None:
        values = (
            self.momentum_window, self.volatility_window, self.volume_window,
            self.trend_window, self.forward_window, self.train_days,
            self.test_days, self.rebalance_days, self.top_n,
        )
        if any(value <= 0 for value in values):
            raise ValueError("因子窗口和选股数量必须为正整数")
        if self.train_days <= self.forward_window:
            raise ValueError("训练窗口必须大于未来收益窗口")


@dataclass(frozen=True)
class FactorWeights:
    """四个因子的标准化权重。"""
    momentum: float
    low_volatility: float
    volume_strength: float
    trend: float

    def values(self) -> tuple[float, float, float, float]:
        return (self.momentum, self.low_volatility,
                self.volume_strength, self.trend)


@dataclass(frozen=True)
class FactorFold:
    """一个时间滚动窗口及其训练所得权重。"""
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    weights: FactorWeights

    def values(self) -> tuple[object, ...]:
        return (self.train_start, self.train_end, self.test_start, self.test_end,
                *self.weights.values())


@dataclass
class FactorSignals:
    """多标的持仓信号及滚动窗口元数据。"""
    signals: dict[str, pd.Series]
    folds: list[FactorFold]
    first_test_date: pd.Timestamp


def build_factor_panel(
    frames: dict[str, pd.DataFrame],
    config: FactorConfig,
) -> pd.DataFrame:
    """按日期和股票构建因子面板，因子只使用当日及以前数据。"""
    panels: dict[str, pd.DataFrame] = {}
    for code, frame in frames.items():
        close = frame["close"]
        daily_return = close.pct_change()
        panel = pd.DataFrame(index=frame.index)
        panel["momentum"] = close.pct_change(config.momentum_window)
        panel["low_volatility"] = -daily_return.rolling(
            config.volatility_window).std()
        panel["volume_strength"] = (
            frame["volume"] / frame["volume"].rolling(config.volume_window).mean() - 1
        )
        panel["trend"] = close / close.rolling(config.trend_window).mean() - 1
        panel["forward_return"] = (
            close.shift(-config.forward_window) / close - 1
        )
        panels[code] = panel
    if not panels:
        raise ValueError("因子计算需要至少一个标的")
    result = pd.concat(panels, names=["code", "date"])
    return result.swaplevel().sort_index()


def _estimate_weights(
    panel: pd.DataFrame,
    train_dates: pd.DatetimeIndex,
    config: FactorConfig,
) -> FactorWeights:
    """使用训练窗横截面秩相关估计因子权重。"""
    eligible_dates = train_dates[:-config.forward_window]
    train = panel.loc[panel.index.get_level_values("date").isin(eligible_dates)]
    mean_ics: list[float] = []
    for column in FACTOR_COLUMNS:
        daily_ics: list[float] = []
        for _, group in train.groupby(level="date"):
            valid = group[[column, "forward_return"]].dropna()
            if (len(valid) >= 2 and valid[column].nunique() > 1
                    and valid["forward_return"].nunique() > 1):
                # 修改说明：先排名再算 Pearson，等价于 Spearman 且不依赖 SciPy。
                correlation = valid[column].rank().corr(
                    valid["forward_return"].rank())
                if pd.notna(correlation):
                    daily_ics.append(float(correlation))
        mean_ics.append(sum(daily_ics) / len(daily_ics) if daily_ics else 0.0)
    scale = sum(abs(value) for value in mean_ics)
    normalized = ([value / scale for value in mean_ics]
                  if scale > 0 else [0.25, 0.25, 0.25, 0.25])
    return FactorWeights(*normalized)


def _rank_stocks(
    panel: pd.DataFrame,
    date: pd.Timestamp,
    weights: FactorWeights,
    top_n: int,
) -> list[str]:
    """按当日横截面综合分数返回排名最高的股票代码。"""
    cross_section = panel.xs(date, level="date")[list(FACTOR_COLUMNS)].dropna()
    if cross_section.empty:
        return []
    ranks = cross_section.rank(pct=True)
    score = ranks.mul(weights.values(), axis=1).sum(axis=1)
    return [str(code) for code in score.nlargest(min(top_n, len(score))).index]


def generate_walk_forward_signals(
    frames: dict[str, pd.DataFrame],
    config: FactorConfig,
) -> FactorSignals:
    """滚动估计因子权重，并仅在后续测试窗生成持仓信号。"""
    panel = build_factor_panel(frames, config)
    dates = pd.DatetimeIndex(sorted(panel.index.get_level_values("date").unique()))
    if len(dates) <= config.train_days:
        raise ValueError("历史数据不足以形成一个训练窗口和测试窗口")
    signals = {
        code: pd.Series(0, index=frame.index, dtype=int)
        for code, frame in frames.items()
    }
    folds: list[FactorFold] = []
    test_start_position = config.train_days
    while test_start_position < len(dates):
        train_dates = dates[test_start_position - config.train_days:test_start_position]
        test_end_position = min(test_start_position + config.test_days, len(dates))
        test_dates = dates[test_start_position:test_end_position]
        weights = _estimate_weights(panel, train_dates, config)
        folds.append(FactorFold(
            train_start=train_dates[0], train_end=train_dates[-1],
            test_start=test_dates[0], test_end=test_dates[-1], weights=weights,
        ))
        for offset in range(0, len(test_dates), config.rebalance_days):
            rebalance_date = test_dates[offset]
            holding_dates = test_dates[offset:offset + config.rebalance_days]
            selected = _rank_stocks(panel, rebalance_date, weights, config.top_n)
            for code in selected:
                signals[code].loc[holding_dates] = 1
        test_start_position = test_end_position
    return FactorSignals(signals=signals, folds=folds,
                         first_test_date=folds[0].test_start)
