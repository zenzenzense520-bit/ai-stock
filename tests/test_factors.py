"""因子计算和时间滚动验证测试。"""
from __future__ import annotations

import unittest

import pandas as pd

from ai_stock.factors import (
    FactorConfig,
    build_factor_panel,
    generate_walk_forward_signals,
)


class FactorTest(unittest.TestCase):
    """修改说明：覆盖因子方向、训练边界和样本外信号。"""

    def setUp(self) -> None:
        index = pd.date_range("2024-01-01", periods=140, freq="B")
        self.frames: dict[str, pd.DataFrame] = {}
        for code, step in (("A", 1.0), ("B", 0.3), ("C", -0.1)):
            close = pd.Series(
                [100 + step * day for day in range(len(index))],
                index=index,
                dtype=float,
            )
            self.frames[code] = pd.DataFrame({
                "open": close,
                "close": close,
                "high": close + 1,
                "low": close - 1,
                "volume": 1_000 + pd.Series(range(len(index)), index=index),
            })

    def test_factor_panel_uses_expected_index(self) -> None:
        config = FactorConfig(train_days=80, test_days=20)
        panel = build_factor_panel(self.frames, config)
        self.assertEqual(panel.index.names, ["date", "code"])
        date = self.frames["A"].index[70]
        momentum = panel.loc[(date, "A"), "momentum"]
        self.assertGreater(momentum, 0)

    def test_signals_begin_after_training_window(self) -> None:
        config = FactorConfig(train_days=80, test_days=20,
                              rebalance_days=10, top_n=1)
        result = generate_walk_forward_signals(self.frames, config)
        first_test = self.frames["A"].index[80]
        self.assertEqual(result.first_test_date, first_test)
        for signal in result.signals.values():
            self.assertEqual(int(signal.loc[:first_test].iloc[:-1].sum()), 0)
        self.assertGreater(sum(int(signal.sum()) for signal in result.signals.values()), 0)

    def test_training_label_does_not_cross_test_boundary(self) -> None:
        config = FactorConfig(train_days=80, test_days=20, forward_window=10)
        result = generate_walk_forward_signals(self.frames, config)
        first_fold = result.folds[0]
        self.assertLess(first_fold.train_end, first_fold.test_start)
        self.assertEqual(first_fold.test_start, self.frames["A"].index[80])


if __name__ == "__main__":
    unittest.main()
