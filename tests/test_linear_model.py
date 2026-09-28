"""历史成员过滤和线性模型时间边界测试。"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from ai_stock.factors import FactorConfig, build_factor_panel, generate_walk_forward_signals
from ai_stock.linear_model import generate_ridge_signals
from ai_stock.universe import Membership, Universe, load_universe, validate_coverage


class LinearModelTest(unittest.TestCase):
    """修改说明：验证成员日期与样本外预测无标签泄漏。"""

    def setUp(self) -> None:
        dates = pd.date_range("2024-01-01", periods=150, freq="B")
        self.frames: dict[str, pd.DataFrame] = {}
        for code, multiplier in (("A", 1.0), ("B", 0.4), ("C", -0.2)):
            close = pd.Series(
                [100 + multiplier * day + (day % 7) for day in range(150)],
                index=dates, dtype=float,
            )
            self.frames[code] = pd.DataFrame({
                "close": close, "volume": 1_000 + close * 2,
                "open": close, "high": close + 1, "low": close - 1,
            })
        self.config = FactorConfig(train_days=90, test_days=30,
                                   forward_window=10, top_n=1)

    def test_membership_excludes_inactive_stock(self) -> None:
        dates = self.frames["A"].index
        membership = Universe((Membership("A", dates[80], dates[-1],
                                           dates[70], "fixture"),))
        panel = build_factor_panel(self.frames, self.config, membership)
        self.assertTrue(pd.isna(panel.loc[(dates[70], "A"), "momentum"]))
        self.assertTrue(pd.notna(panel.loc[(dates[100], "A"), "momentum"]))
        self.assertTrue(pd.isna(panel.loc[(dates[100], "B"), "momentum"]))

    def test_future_prices_do_not_change_first_model(self) -> None:
        baseline = generate_ridge_signals(self.frames, self.config)
        altered = {code: frame.copy() for code, frame in self.frames.items()}
        # 修改说明：只改首个测试窗以后的价格，训练标签和标准化参数必须不变。
        altered["A"].loc[altered["A"].index[90]:, "close"] *= 1.3
        candidate = generate_ridge_signals(altered, self.config)
        self.assertEqual(baseline.folds[0].weights.values(),
                         candidate.folds[0].weights.values())
        self.assertEqual(baseline.first_test_date, candidate.first_test_date)

    def test_overlapping_memberships_are_rejected(self) -> None:
        table = pd.DataFrame([
            {"code": "600001", "valid_from": "2024-01-01",
             "valid_to": "2024-12-31", "published_at": "2023-12-01",
             "source": "fixture"},
            {"code": "600001", "valid_from": "2024-12-31",
             "valid_to": "2025-12-31", "published_at": "2024-12-01",
             "source": "fixture"},
        ])
        with patch("ai_stock.universe.pd.read_csv", return_value=table):
            with self.assertRaisesRegex(ValueError, "区间重叠"):
                load_universe("unused.csv")

    def test_valid_membership_is_parsed(self) -> None:
        table = pd.DataFrame([{
            "code": "600001", "valid_from": "2024-01-01",
            "valid_to": "2024-12-31", "published_at": "2023-12-15",
            "source": "fixture",
        }])
        with patch("ai_stock.universe.pd.read_csv", return_value=table):
            membership = load_universe("unused.csv")
        self.assertEqual(membership.codes(), ["600001"])
        self.assertEqual(membership.active(pd.Timestamp("2024-06-01")), {"600001"})
        self.assertEqual(membership.active(pd.Timestamp("2025-01-01")), set())

    def test_late_publication_is_rejected(self) -> None:
        table = pd.DataFrame([{
            "code": "600001", "valid_from": "2024-01-01",
            "valid_to": "2024-12-31", "published_at": "2024-01-02",
            "source": "fixture",
        }])
        with patch("ai_stock.universe.pd.read_csv", return_value=table):
            with self.assertRaisesRegex(ValueError, "日期区间无效"):
                load_universe("unused.csv")

    def test_historical_price_gap_is_rejected(self) -> None:
        dates = self.frames["A"].index
        membership = Universe((Membership("A", dates[0], dates[-1],
                                           dates[0], "fixture"),))
        with self.assertRaisesRegex(ValueError, "行情缺少历史交易日"):
            validate_coverage(membership, {"A": self.frames["A"].drop(dates[12])}, dates)

    def test_signals_stop_after_member_exits(self) -> None:
        dates = self.frames["A"].index
        membership = Universe(tuple(
            Membership(code, dates[0], dates[95], dates[0], "fixture")
            for code in self.frames
        ))
        for generator in (generate_walk_forward_signals, generate_ridge_signals):
            result = generator(self.frames, self.config, membership)
            for signal in result.signals.values():
                self.assertEqual(int(signal.loc[dates[96]:].sum()), 0)


if __name__ == "__main__":
    unittest.main()
