# -*- coding: utf-8 -*-
"""按历史日期生效的股票池输入与校验。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Membership:
    code: str
    valid_from: pd.Timestamp
    valid_to: pd.Timestamp
    published_at: pd.Timestamp
    source: str


@dataclass(frozen=True)
class Universe:
    entries: tuple[Membership, ...]

    def codes(self) -> list[str]:
        return sorted({entry.code for entry in self.entries})

    def active(self, date: pd.Timestamp) -> set[str]:
        return {entry.code for entry in self.entries
                if entry.published_at <= date
                and entry.valid_from <= date <= entry.valid_to}


def validate_coverage(universe: Universe, frames: dict[str, pd.DataFrame],
                      calendar: pd.DatetimeIndex) -> None:
    """修改说明：历史模式要求有效交易日和全部行情均可对齐，缺口即拒绝。"""
    missing_codes = set(universe.codes()).difference(frames)
    if missing_codes:
        raise ValueError(f"历史成员行情缺失: {', '.join(sorted(missing_codes))}")
    eligible = pd.DatetimeIndex([day for day in calendar if universe.active(day)])
    if eligible.empty:
        raise ValueError("基准交易日内没有有效历史成员")
    for code, frame in frames.items():
        missing_dates = eligible.difference(frame.index)
        if not missing_dates.empty:
            raise ValueError(f"{code} 行情缺少历史交易日: {missing_dates[0].date()}")


def load_universe(path: str | Path) -> Universe:
    """修改说明：读取并严格校验带来源的历史成员区间。"""
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {"code", "valid_from", "valid_to", "published_at", "source"}
    if not required.issubset(table.columns) or table.empty:
        raise ValueError("历史股票池需要 code,valid_from,valid_to,published_at,source 列")
    entries: list[Membership] = []
    for row in table.itertuples(index=False):
        code = str(row.code).strip()
        source = str(row.source).strip()
        if not code or not source:
            raise ValueError("历史股票池的代码和来源不能为空")
        try:
            start = pd.Timestamp(row.valid_from)
            end = pd.Timestamp(row.valid_to)
            published = pd.Timestamp(row.published_at)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"历史股票池日期无效: {code}") from exc
        if (pd.isna(start) or pd.isna(end) or pd.isna(published)
                or start > end or published > start):
            raise ValueError(f"历史股票池日期区间无效: {code}")
        entries.append(Membership(code, start, end, published, source))
    by_code: dict[str, list[Membership]] = {}
    for entry in entries:
        by_code.setdefault(entry.code, []).append(entry)
    for code, periods in by_code.items():
        ordered = sorted(periods, key=lambda item: item.valid_from)
        if any(left.valid_to >= right.valid_from
               for left, right in zip(ordered, ordered[1:])):
            raise ValueError(f"历史股票池区间重叠: {code}")
    return Universe(tuple(entries))
