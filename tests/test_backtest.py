"""回测关键口径测试。"""
from __future__ import annotations

import unittest

import pandas as pd

from ai_stock.backtest import RiskConfig, Trade, run_backtest, trade_win_rate
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

    def test_buy_reserves_commission_and_obeys_position_cap(self) -> None:
        signal = pd.Series(1, index=self.frame.index)
        risk = RiskConfig(max_position_pct=0.5)
        result = run_backtest(self.frame, signal, risk=risk, slippage=0)
        buy = result.trades[0]
        self.assertLessEqual(buy.amount, 500_000)
        self.assertLessEqual(buy.amount + buy.fee, 1_000_000)

    def test_stop_loss_closes_position(self) -> None:
        frame = self.frame.iloc[:4].copy()
        frame.loc[:, ["open", "close", "high", "low"]] = 100.0
        frame.iloc[2, frame.columns.get_loc("low")] = 90.0
        signal = pd.Series(1, index=frame.index)
        risk = RiskConfig(stop_loss_pct=0.05)
        result = run_backtest(frame, signal, risk=risk,
                              commission=0, stamp_tax=0, slippage=0)
        sells = [trade for trade in result.trades if trade.side == "sell"]
        self.assertEqual(sells[0].reason, "stop_loss")
        self.assertEqual(sells[0].price, 95.0)

    def test_take_profit_closes_position(self) -> None:
        frame = self.frame.iloc[:4].copy()
        frame.loc[:, ["open", "close", "high", "low"]] = 100.0
        frame.iloc[2, frame.columns.get_loc("high")] = 125.0
        signal = pd.Series(1, index=frame.index)
        risk = RiskConfig(take_profit_pct=0.2)
        result = run_backtest(frame, signal, risk=risk,
                              commission=0, stamp_tax=0, slippage=0)
        sells = [trade for trade in result.trades if trade.side == "sell"]
        self.assertEqual(sells[0].reason, "take_profit")
        self.assertEqual(sells[0].price, 120.0)

    def test_max_drawdown_halts_new_entries(self) -> None:
        frame = self.frame.iloc[:5].copy()
        frame.loc[:, ["open", "close", "high", "low"]] = 100.0
        frame.iloc[2, frame.columns.get_loc("open")] = 75.0
        frame.iloc[2, frame.columns.get_loc("close")] = 75.0
        frame.iloc[2, frame.columns.get_loc("high")] = 75.0
        frame.iloc[2, frame.columns.get_loc("low")] = 75.0
        frame.iloc[3, frame.columns.get_loc("open")] = 75.0
        frame.iloc[3, frame.columns.get_loc("close")] = 75.0
        frame.iloc[3, frame.columns.get_loc("high")] = 75.0
        frame.iloc[3, frame.columns.get_loc("low")] = 75.0
        signal = pd.Series(1, index=frame.index)
        risk = RiskConfig(max_drawdown_pct=0.15)
        result = run_backtest(frame, signal, risk=risk,
                              commission=0, stamp_tax=0, slippage=0)
        buys = [trade for trade in result.trades if trade.side == "buy"]
        sells = [trade for trade in result.trades if trade.side == "sell"]
        self.assertTrue(result.risk_halted)
        self.assertEqual(len(buys), 1)
        self.assertEqual(sells[0].reason, "max_drawdown")

    def test_invalid_risk_config_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RiskConfig(max_position_pct=0)


if __name__ == "__main__":
    unittest.main()
