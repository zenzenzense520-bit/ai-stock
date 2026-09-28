# -*- coding: utf-8 -*-
"""不新增依赖的岭回归样本外选股基线。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ai_stock.factors import (
    FACTOR_COLUMNS, FactorConfig, FactorFold, FactorSignals, FactorWeights,
    build_factor_panel, walk_forward_windows,
)
from ai_stock.universe import Universe


def _fit_ridge(
    train: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """标准化与拟合均限定在训练样本，正则化强度固定为 1。"""
    data = train[[*FACTOR_COLUMNS, "forward_return"]].dropna()
    if len(data) < len(FACTOR_COLUMNS) + 2:
        raise ValueError("线性模型可用训练样本不足")
    x = data[list(FACTOR_COLUMNS)].to_numpy(dtype=float)
    y = data["forward_return"].to_numpy(dtype=float)
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale == 0] = 1.0
    standardized = (x - mean) / scale
    centered_y = y - y.mean()
    # 修改说明：岭回归只拟合训练窗，截距单独取训练标签均值。
    coefficients = np.linalg.solve(
        standardized.T @ standardized + np.eye(len(FACTOR_COLUMNS)),
        standardized.T @ centered_y,
    )
    return mean, scale, coefficients, float(y.mean())


def generate_ridge_signals(
    frames: dict[str, pd.DataFrame],
    config: FactorConfig,
    universe: Universe | None = None,
) -> FactorSignals:
    """与多因子排名使用同一滚动窗口、股票池和调仓日。"""
    panel = build_factor_panel(frames, config, universe)
    dates = pd.DatetimeIndex(sorted(panel.index.get_level_values("date").unique()))
    windows = walk_forward_windows(dates, config)
    signals = {code: pd.Series(0, index=frame.index, dtype=int)
               for code, frame in frames.items()}
    folds: list[FactorFold] = []
    for train_dates, test_dates in windows:
        eligible_dates = train_dates[:-config.forward_window]
        train = panel.loc[panel.index.get_level_values("date").isin(eligible_dates)]
        mean, scale, coefficients, intercept = _fit_ridge(train)
        folds.append(FactorFold(
            train_dates[0], train_dates[-1], test_dates[0], test_dates[-1],
            FactorWeights(*coefficients.tolist()),
        ))
        for offset in range(0, len(test_dates), config.rebalance_days):
            date = test_dates[offset]
            cross_section = panel.xs(date, level="date")[
                list(FACTOR_COLUMNS)].dropna()
            if cross_section.empty:
                continue
            features = cross_section.to_numpy(dtype=float)
            scores = pd.Series(
                ((features - mean) / scale) @ coefficients + intercept,
                index=cross_section.index,
            )
            selected = scores.nlargest(min(config.top_n, len(scores))).index
            holding_dates = test_dates[offset:offset + config.rebalance_days]
            for code in selected:
                # 修改说明：模型入选后仍逐日核对历史成员有效期。
                valid_dates = (holding_dates if universe is None else
                               pd.DatetimeIndex([day for day in holding_dates
                                                 if str(code) in universe.active(day)]))
                signals[str(code)].loc[valid_dates] = 1
    return FactorSignals(signals, folds, folds[0].test_start)
