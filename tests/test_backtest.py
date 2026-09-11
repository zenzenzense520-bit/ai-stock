"""回测关键口径测试。"""
from __future__ import annotations

import unittest

import pandas as pd

from ai_stock.backtest import Trade, run_backtest, trade_win_rate
from ai_stock.strategy import bollinger, ma_cross, momentum


class BacktestTest(unittest.TestCase):
    """修改说明：覆盖信号延迟、胜率和三类策略输出。"""

    def setUp(self) -> None:
        index = pd.date_range("2026-01-01", periods=60, freq="B")
        close = pd.Series(range(100, 160), index=index, dtype=float)
        self.frame = pd.DataFrame({
            "open": close,
            "close": close,
            "high": close + 1,
            "low": close - 1,
            "volume": 1_000.0,
        })

    def test_signal_executes_next_day(self) -> None:
        signal = pd.Series(0, index=self.frame.index)
        signal.iloc[5:] = 1
        result = run_backtest(self.frame, signal, commission=0, slippage=0)
        self.assertEqual(result.trades[0].date, self.frame.index[6])

    def test_win_rate_uses_closed_trades(self) -> None:
        ts = self.frame.index[0]
        trades = [
            Trade(ts, "buy", 10, 100, 1_000, 1),
            Trade(ts, "sell", 12, 100, 1_200, 1),
            Trade(ts, "buy", 10, 100, 1_000, 1),
            Trade(ts, "sell", 9, 100, 900, 1),
        ]
        self.assertEqual(trade_win_rate(trades), 50.0)

    def test_all_strategies_return_binary_signal(self) -> None:
        for function in (ma_cross, momentum, bollinger):
            values = set(function(self.frame).unique())
            self.assertTrue(values <= {0, 1})


if __name__ == "__main__":
    unittest.main()
