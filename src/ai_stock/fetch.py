# -*- coding: utf-8 -*-
"""数据抓取层：东财选股器(选股) + 腾讯K线(历史行情)。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      " (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": UA})


@dataclass(frozen=True)
class Stock:
    """选股结果中的一只股票。"""
    code: str
    name: str
    pe: float  # 动态市盈率
    market_cap: float  # 总市值（元）
    price: float
    pct: float  # 当日涨跌幅 %


def _em_request(page: int, page_size: int) -> list[dict]:
    """拉取一页东财沪深A股列表（按市值降序）。"""
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        f"pn={page}&pz={page_size}&po=1&np=1&fltt=2&invt=2&fid=f20"
        "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:0+t:81"
        "&fields=f12,f14,f2,f3,f9,f20"
    )
    r = _SESSION.get(url, timeout=15)
    r.raise_for_status()
    data = r.json().get("data")
    if not data or not data.get("diff"):
        return []
    diff = data["diff"]
    return diff if isinstance(diff, list) else list(diff.values())


def pick_stocks(
    pe_max: float = 50.0,
    cap_min_yi: float = 100.0,
    limit: int = 8,
    sleep: float = 0.3,
) -> list[Stock]:
    """按 0<PE<pe_max 且 总市值>cap_min_yi(亿) 过滤，返回市值最大的 limit 只。

    注意：问财(iwencai)在本网络环境被 IP 风控(403)，此处用东财 clist 接口
    做客户端过滤，功能等价（同花顺选股在脚本中保留 CSV 手动导入兜底）。
    """
    cap_min = cap_min_yi * 1e8
    picked: list[Stock] = []
    page = 1
    while len(picked) < limit and page <= 20:
        for it in _em_request(page, 100):
            code = str(it.get("f12", ""))
            name = str(it.get("f14", ""))
            pe = it.get("f9")
            cap = it.get("f20")
            price = it.get("f2")
            pct = it.get("f3")
            if not code or not name or not isinstance(pe, (int, float)):
                continue
            if not (0 < pe < pe_max):
                continue
            if not isinstance(cap, (int, float)) or cap < cap_min:
                continue
            picked.append(Stock(code=code, name=name, pe=float(pe),
                                market_cap=float(cap), price=float(price or 0),
                                pct=float(pct or 0)))
        page += 1
        time.sleep(sleep)
    return picked[:limit]


def _market_prefix(code: str) -> str:
    """6开头=沪(sh)，0/3开头=深(sz)；北交所直接抛异常。"""
    if code.startswith(("sh", "sz")):
        return code
    if code.startswith(("6", "9")):
        return "sh" + code
    if code.startswith(("0", "3")):
        return "sz" + code
    raise ValueError(f"不支持的代码前缀: {code}")


def _secid(code: str) -> str:
    """东财 secid：沪 1.xxxxxx，深 0.xxxxxx。"""
    symbol = _market_prefix(code)
    return ("1." if symbol.startswith("sh") else "0.") + symbol[2:]


def fetch_kline(code: str, years: int = 5) -> pd.DataFrame:
    """拉取前复权日K。

    主源：东财 push2his（beg/end 指定区间，无 641 根上限，前复权 fqt=1）；
    兜底：腾讯 fqkline（免费接口 qfq 最多返回最近 641 根 ≈ 2.6 年）。
    """
    from datetime import date, timedelta

    end = date.today()
    beg = end - timedelta(days=int(years * 365.25) + 30)
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        f"secid={_secid(code)}&klt=101&fqt=1&beg={beg:%Y%m%d}&end={end:%Y%m%d}"
        "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56"
    )
    r = _SESSION.get(url, timeout=15)
    r.raise_for_status()
    klines = r.json().get("data", {}).get("klines")
    if klines:
        rows = [k.split(",") for k in klines]
        df = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
        for col in ("open", "close", "high", "low", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["close"]).set_index("date").sort_index()
        return df[["open", "close", "high", "low", "volume"]].astype(float)

    # ---- 腾讯兜底 ----
    symbol = _market_prefix(code)
    datalen = max(300, int(years * 250) + 30)
    url2 = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={symbol},day,,,{datalen},qfq"
    )
    r2 = _SESSION.get(url2, timeout=15)
    r2.raise_for_status()
    data = r2.json().get("data", {}).get(symbol, {})
    rows = data.get("qfqday") or data.get("day")
    if not rows:
        raise RuntimeError(f"K线无数据: {code}")
    # 腾讯字段序: [日期, 开, 收, 高, 低, 量(, 额外字段)]，长区间可能多出1列
    df = pd.DataFrame(rows).iloc[:, :6]
    df.columns = ["date", "open", "close", "high", "low", "volume"]
    for col in ("open", "close", "high", "low"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["close"]).set_index("date").sort_index()
    return df[["open", "close", "high", "low", "volume"]].astype(float)


def fetch_index_kline(index_symbol: str = "000001", years: int = 5) -> pd.DataFrame:
    """上证指数(000001)K线，作为基准。"""
    return fetch_kline("sh" + index_symbol if not index_symbol.startswith("sh")
                       else index_symbol, years)


def load_manual_pool(path: str) -> list[Stock]:
    """手动股票池 CSV 兜底：列 code,name(可选)。"""
    df = pd.read_csv(path, dtype={"code": str})
    out: list[Stock] = []
    for _, row in df.iterrows():
        out.append(Stock(code=row["code"], name=str(row.get("name", row["code"])),
                         pe=float(row.get("pe", 0)) if pd.notna(row.get("pe")) else 0.0,
                         market_cap=0.0, price=0.0, pct=0.0))
    return out


def fetch_pool_kline(pool: list[Stock], years: int = 5,
                     sleep: float = 0.4) -> dict[str, pd.DataFrame]:
    """批量拉取股票池K线，失败自动跳过，返回 {code: DataFrame}。"""
    result: dict[str, pd.DataFrame] = {}
    for st in pool:
        try:
            result[st.code] = fetch_kline(st.code, years)
            print(f"  [OK] {st.code} {st.name}  {len(result[st.code])} 根K线")
        except Exception as exc:  # 单只失败不阻断整体
            print(f"  [SKIP] {st.code} {st.name}: {exc}")
        time.sleep(sleep)
    return result
