"""核对公开公告转录的上证50历史调样事件。"""
from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from ai_stock.universe_events import (
    AdjustmentEvent, SeedMember, load_events, reconstruct_universe,
)


EVENTS = Path(__file__).resolve().parents[1] / "data" / "sse50_adjustments_2024_2025.csv"


class IndexEventsTest(unittest.TestCase):
    def test_official_adjustments_have_balanced_unique_rows(self) -> None:
        # 修改说明：固定核验四份官方附件的行数、方向和出处，防止误当成完整股票池。
        events = pd.read_csv(EVENTS, dtype=str)
        self.assertEqual(len(events), 36)
        expected = {
            "2024-06-14": ("2024-05-31", 5),
            "2024-12-13": ("2024-11-29", 5),
            "2025-06-13": ("2025-05-30", 4),
            "2025-12-12": ("2025-11-28", 4),
        }
        self.assertFalse(events.duplicated(["code", "direction", "effective_after_close"]).any())
        self.assertTrue(events["code"].str.fullmatch(r"\d{6}").all())
        self.assertTrue(events["source"].str.startswith(
            "https://www.sse.com.cn/market/sseindex/diclosure/").all())
        for effective, (published, count) in expected.items():
            group = events[events["effective_after_close"] == effective]
            self.assertEqual(len(group), count * 2)
            self.assertEqual(set(group["published_at"]), {published})
            self.assertEqual(int((group["direction"] == "in").sum()), count)
            self.assertEqual(int((group["direction"] == "out").sum()), count)
            self.assertEqual(group["source"].nunique(), 1)

    def test_official_events_are_parseable(self) -> None:
        self.assertEqual(len(load_events(EVENTS)), 36)

    def test_reconstructs_members_only_after_effective_close(self) -> None:
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        seed = (SeedMember("600001", dates[0], "snapshot"),
                SeedMember("600002", dates[0], "snapshot"))
        events = (
            AdjustmentEvent("600001", "out", dates[1], dates[2], "notice"),
            AdjustmentEvent("600003", "in", dates[1], dates[2], "notice"),
        )
        # 修改说明：收盘后调样在次一交易日生效，调出股的区间含调样当日。
        result = reconstruct_universe(seed, events, dates, expected_size=2)
        self.assertEqual(result.active(dates[2]), {"600001", "600002"})
        self.assertEqual(result.active(dates[3]), {"600002", "600003"})

    def test_reconstruction_rejects_missing_seed_and_bad_exit(self) -> None:
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        seed = (SeedMember("600001", dates[0], "snapshot"),)
        with self.assertRaisesRegex(ValueError, "起始快照"):
            reconstruct_universe(seed, (), dates, expected_size=2)
        bad = (AdjustmentEvent("600099", "out", dates[1], dates[2], "notice"),
               AdjustmentEvent("600003", "in", dates[1], dates[2], "notice"))
        with self.assertRaisesRegex(ValueError, "现有成员不一致"):
            reconstruct_universe(seed, bad, dates, expected_size=1)

    def test_reconstruction_rejects_future_announcement(self) -> None:
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        seed = (SeedMember("600001", dates[0], "snapshot"),)
        events = (
            AdjustmentEvent("600001", "out", dates[3], dates[2], "notice"),
            AdjustmentEvent("600002", "in", dates[1], dates[2], "notice"),
        )
        with self.assertRaisesRegex(ValueError, "公告时间"):
            reconstruct_universe(seed, events, dates, expected_size=1)

    def test_reconstruction_rejects_duplicate_or_nontrading_event(self) -> None:
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        seed = (SeedMember("600001", dates[0], "snapshot"),)
        repeated = (
            AdjustmentEvent("600001", "out", dates[0], dates[2], "notice"),
            AdjustmentEvent("600001", "out", dates[0], dates[2], "notice"),
            AdjustmentEvent("600002", "in", dates[0], dates[2], "notice"),
        )
        with self.assertRaisesRegex(ValueError, "进出数量"):
            reconstruct_universe(seed, repeated, dates, expected_size=1)
        weekend = (
            AdjustmentEvent("600001", "out", dates[0], pd.Timestamp("2024-01-06"), "notice"),
            AdjustmentEvent("600002", "in", dates[0], pd.Timestamp("2024-01-06"), "notice"),
        )
        with self.assertRaisesRegex(ValueError, "可交易研究区间"):
            reconstruct_universe(seed, weekend, dates, expected_size=1)


if __name__ == "__main__":
    unittest.main()
