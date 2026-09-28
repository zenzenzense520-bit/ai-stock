# -*- coding: utf-8 -*-
"""用完整起始快照和有来源的调样事件重建成员区间。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ai_stock.universe import Membership, Universe


@dataclass(frozen=True)
class SeedMember:
    code: str
    published_at: pd.Timestamp
    source: str


@dataclass(frozen=True)
class AdjustmentEvent:
    code: str
    direction: str
    published_at: pd.Timestamp
    effective_after_close: pd.Timestamp
    source: str


def load_seed(path: str | Path) -> tuple[SeedMember, ...]:
    """修改说明：起始快照必须逐股带公告时间和可追溯来源。"""
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    if table.empty or not {"code", "published_at", "source"}.issubset(table):
        raise ValueError("起始快照需要 code,published_at,source 列")
    members: list[SeedMember] = []
    for row in table.itertuples(index=False):
        if not row.code or not row.source:
            raise ValueError("起始成员代码和来源不能为空")
        published = pd.Timestamp(row.published_at)
        if pd.isna(published):
            raise ValueError(f"起始成员公告日期无效: {row.code}")
        members.append(SeedMember(row.code, published, row.source))
    if len({member.code for member in members}) != len(members):
        raise ValueError("起始快照有重复成员")
    return tuple(members)


def load_events(path: str | Path) -> tuple[AdjustmentEvent, ...]:
    """修改说明：只读取明确列出方向、公布日及收盘后生效日的调样事件。"""
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {"code", "direction", "published_at", "effective_after_close", "source"}
    if table.empty or not required.issubset(table):
        raise ValueError("调样事件列不完整")
    events: list[AdjustmentEvent] = []
    for row in table.itertuples(index=False):
        if not row.code or row.direction not in {"in", "out"} or not row.source:
            raise ValueError(f"调样事件无效: {row.code}")
        published = pd.Timestamp(row.published_at)
        effective = pd.Timestamp(row.effective_after_close)
        if pd.isna(published) or pd.isna(effective) or published > effective:
            raise ValueError(f"调样日期无效: {row.code}")
        events.append(AdjustmentEvent(row.code, row.direction,
                                      published, effective, row.source))
    return tuple(events)


def reconstruct_universe(
    seed: tuple[SeedMember, ...],
    events: tuple[AdjustmentEvent, ...],
    calendar: pd.DatetimeIndex,
    expected_size: int = 50,
) -> Universe:
    """根据交易日历重建区间；不推断缺失的临时调样或行情。"""
    if calendar.empty or not calendar.is_monotonic_increasing or not calendar.is_unique:
        raise ValueError("交易日历必须非空、升序且无重复")
    if expected_size <= 0 or len(seed) != expected_size:
        raise ValueError(f"起始快照必须有 {expected_size} 个成员")
    start, end = calendar[0], calendar[-1]
    active: dict[str, Membership] = {}
    for member in seed:
        if member.code in active or not member.code or not member.source:
            raise ValueError("起始快照有重复或空成员")
        if pd.isna(member.published_at) or member.published_at > start:
            raise ValueError(f"起始成员在回测起点尚未公开: {member.code}")
        active[member.code] = Membership(member.code, start, end,
                                         member.published_at, member.source)
    completed: list[Membership] = []
    if any(event.direction not in {"in", "out"} or not event.code
           for event in events):
        raise ValueError("调样方向或代码无效")
    event_dates = sorted({event.effective_after_close for event in events})
    for date in event_dates:
        if date not in calendar or date >= end or date < start:
            raise ValueError(f"调样生效日不在可交易研究区间内: {date.date()}")
        day_events = [event for event in events if event.effective_after_close == date]
        additions = {event.code for event in day_events if event.direction == "in"}
        removals = {event.code for event in day_events if event.direction == "out"}
        if (len(additions) != len(removals) or len(day_events) !=
                len(additions) + len(removals) or additions & removals):
            raise ValueError(f"调样进出数量或代码不一致: {date.date()}")
        if not removals.issubset(active) or additions & active.keys():
            raise ValueError(f"调样与现有成员不一致: {date.date()}")
        next_date = calendar[calendar.get_loc(date) + 1]
        for event in day_events:
            if (pd.isna(event.published_at) or event.published_at > date
                    or not event.source):
                raise ValueError(f"调样公告时间或来源无效: {event.code}")
            if event.direction == "out":
                old = active.pop(event.code)
                completed.append(Membership(old.code, old.valid_from, date,
                                            old.published_at, old.source))
            else:
                active[event.code] = Membership(event.code, next_date, end,
                                                event.published_at, event.source)
        if len(active) != expected_size:
            raise ValueError(f"调样后成员数量错误: {date.date()}")
    return Universe(tuple(completed + list(active.values())))
