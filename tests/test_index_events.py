"""核对公开公告转录的上证50历史调样事件。"""
from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd


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


if __name__ == "__main__":
    unittest.main()
