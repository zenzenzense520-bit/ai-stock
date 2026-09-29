# -*- coding: utf-8 -*-
"""只读审计国证指数历史调样文件，不生成可回测股票池。"""
from __future__ import annotations

import argparse
from datetime import date
import logging
import re
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import requests


URL = "https://www.cnindex.com.cn/sample-detail/download-adjustment"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class PeriodMember:
    start: str
    end: str
    code: str
    name: str
    change_type: str


def _read_rows(content: bytes) -> list[list[str]]:
    """修改说明：读取官方 XLSX 内的简单行表；格式变化时明确报错。"""
    try:
        with ZipFile(BytesIO(content)) as archive:
            xml = archive.read("xl/worksheets/sheet1.xml")
    except (BadZipFile, KeyError) as exc:
        raise ValueError("国证下载不是预期的 XLSX 工作表") from exc
    root = ElementTree.fromstring(xml)
    output: list[list[str]] = []
    for row in root.findall(f".//{NS}sheetData/{NS}row"):
        values: list[str] = []
        for column, cell in enumerate(row.findall(f"{NS}c")):
            label = cell.attrib.get("r", "")
            if label != f"{chr(65 + column)}{row.attrib.get('r', '')}" or column >= 6:
                raise ValueError("国证工作表列格式已变化")
            value = cell.find(f".//{NS}t")
            if value is None:
                value = cell.find(f"{NS}v")
            values.append((value.text or "") if value is not None else "")
        output.append(values)
    return output


def parse_adjustments(content: bytes) -> tuple[PeriodMember, ...]:
    rows = _read_rows(content)
    if not rows or rows[0] != ["开始日期", "结束日期", "样本代码", "样本简称", "所属行业", "调整类型"]:
        raise ValueError("国证历史调样表头已变化")
    members: list[PeriodMember] = []
    for row in rows[1:]:
        if (len(row) != 6 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[0])
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[1])
                or not re.fullmatch(r"\d{6}", row[2])
                or not row[3] or row[5] not in {"OLD", "+", "-", "备选"}):
            raise ValueError(f"国证历史调样记录格式无效: {row}")
        try:
            period_start = date.fromisoformat(row[0])
            period_end = date.fromisoformat(row[1])
        except ValueError as exc:
            raise ValueError(f"国证历史调样日期无效: {row}") from exc
        if period_end < period_start:
            raise ValueError(f"国证历史调样日期倒置: {row}")
        members.append(PeriodMember(row[0], row[1], row[2], row[3], row[5]))
    if not members:
        raise ValueError("国证历史调样文件为空")
    return tuple(members)


def fetch_adjustments(code: str = "399330") -> tuple[PeriodMember, ...]:
    """只读取国证官网；网络或结构失败时不回退到非官方名单。"""
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("指数代码必须是 6 位数字")
    response = requests.get(URL, params={"indexcode": code}, timeout=25)
    response.raise_for_status()
    return parse_adjustments(response.content)


def audit_periods(members: tuple[PeriodMember, ...], expected_size: int = 100,
                  start: str = "2024-01-01", end: str = "2025-12-31") -> list[str]:
    """修改说明：以 OLD 与调入组成的期次样本审计，调出和备选另列。"""
    if expected_size <= 0:
        raise ValueError("预期样本数必须为正数")
    counts = Counter(item.start for item in members)
    lines: list[str] = []
    for period_date, count in sorted(counts.items()):
        if start <= period_date <= end:
            cohort = [item for item in members if item.start == period_date]
            types = Counter(item.change_type for item in cohort)
            active = [item.code for item in cohort if item.change_type in {"OLD", "+"}]
            outgoing = [item.code for item in cohort if item.change_type == "-"]
            breakdown = ", ".join(f"{kind}={number}"
                                  for kind, number in sorted(types.items()))
            valid = (len(active) == expected_size and len(set(active)) == expected_size
                     and types["+"] == types["-"]
                     and len(set(outgoing)) == len(outgoing)
                     and not set(active).intersection(outgoing))
            status = "OK" if valid else "需核对"
            lines.append(f"{period_date}: {count} 行 / {len(set(active))} 个期次样本 "
                         f"({breakdown}) [{status}]")
    if not lines:
        raise ValueError("所选区间没有历史调样记录")
    return lines


def main() -> int:
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(filename="logs/cni_audit.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        encoding="utf-8")
    parser = argparse.ArgumentParser(description="国证指数历史调样只读审计")
    parser.add_argument("--code", default="399330", help="默认深证100：399330")
    parser.add_argument("--expected-size", type=int, default=100,
                        help="目标指数的期次样本数，默认 100")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2025-12-31")
    args = parser.parse_args()
    try:
        members = fetch_adjustments(args.code)
        lines = audit_periods(members, expected_size=args.expected_size,
                              start=args.start, end=args.end)
    except (requests.RequestException, ValueError) as exc:
        LOG.exception("国证历史调样审计失败")
        print(f"审计失败: {exc}")
        return 1
    LOG.info("指数 %s 下载 %s 行：%s", args.code, len(members), lines)
    print(f"指数 {args.code} 官方历史调样表共 {len(members)} 行；以下为所选期间：")
    for line in lines:
        print(line)
    print("仅检查调样表结构和期次样本数；公告发布时间、临时调样完整性和行情估值尚未核对。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
