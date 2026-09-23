"""公开行情主备数据源测试。"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from ai_stock import fetch


class FakeResponse:
    """测试用腾讯行情响应。"""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "data": {
                "sh601398": {
                    "qfqday": [
                        ["2026-09-21", "7.10", "7.20", "7.30", "7.00", "1000"],
                        ["2026-09-22", "7.20", "7.25", "7.35", "7.10", "1200"],
                    ]
                }
            }
        }


class FetchTest(unittest.TestCase):
    """修改说明：验证主源网络失败后确实调用备用源。"""

    def test_primary_failure_uses_tencent_fallback(self) -> None:
        side_effects = [requests.ConnectionError("primary down"), FakeResponse()]
        with patch.object(fetch._SESSION, "get", side_effect=side_effects) as mocked:
            frame = fetch.fetch_kline("601398", years=1)
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(len(frame), 2)
        self.assertEqual(float(frame.iloc[-1]["close"]), 7.25)


if __name__ == "__main__":
    unittest.main()
