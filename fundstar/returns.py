"""含息報酬、年化波動、最大回撤。

含息報酬定義：配息在除息日以當日淨值再投資。
    index_t = index_{t-1} * (nav_t + d_t) / nav_{t-1}
d_t 為除息日在 t 的每單位配息（同幣別）。
除息日當天沒有淨值時，套用在除息日之後的第一個淨值日，並記錄警告。
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

MIN_POINTS_VOL = 60      # 年化波動至少需要的報酬筆數
MIN_POINTS_SERIES = 2


@dataclass
class TRSeries:
    dates: list[str]
    index: list[float]
    warnings: list[str] = field(default_factory=list)


def total_return_index(navs: list[tuple[str, float]],
                       dividends: dict[str, float] | None = None) -> TRSeries:
    navs = sorted((d, v) for d, v in navs if v is not None and v > 0)
    dates = [d for d, _ in navs]
    warnings: list[str] = []
    applied: dict[str, float] = {}
    for ex, amt in sorted((dividends or {}).items()):
        if not dates or ex <= dates[0] or ex > dates[-1]:
            warnings.append(f"dividend {ex} outside NAV range, ignored")
            continue
        i = bisect.bisect_left(dates, ex)
        if dates[i] != ex:
            warnings.append(f"no NAV on ex-date {ex}, applied on {dates[i]}")
        applied[dates[i]] = applied.get(dates[i], 0.0) + amt
    idx = [1.0] if navs else []
    for i in range(1, len(navs)):
        prev, cur = navs[i - 1][1], navs[i][1]
        idx.append(idx[-1] * (cur + applied.get(dates[i], 0.0)) / prev)
    return TRSeries(dates, idx, warnings)


def value_at(s: TRSeries, date: str) -> tuple[str, float] | None:
    """date 當天或之前最近的一點。"""
    i = bisect.bisect_right(s.dates, date) - 1
    return (s.dates[i], s.index[i]) if i >= 0 else None


def period_return(s: TRSeries, start: str, end: str) -> float | None:
    """區間含息報酬（小數）。起點早於資料起始則回傳 None（資料不足）。"""
    if not s.dates or start < s.dates[0]:
        return None
    a, b = value_at(s, start), value_at(s, end)
    if a is None or b is None or a[0] >= b[0]:
        return None
    return b[1] / a[1] - 1


def annualized_volatility(s: TRSeries, periods_per_year: int = 252) -> float | None:
    if len(s.index) < MIN_POINTS_VOL + 1:
        return None
    r = [math.log(s.index[i] / s.index[i - 1]) for i in range(1, len(s.index))]
    m = sum(r) / len(r)
    var = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    return math.sqrt(var) * math.sqrt(periods_per_year)


def max_drawdown(s: TRSeries) -> dict | None:
    """「最慘的時候從高點跌了多少」。回傳負數比例與高點、低點日期。"""
    if len(s.index) < MIN_POINTS_SERIES:
        return None
    peak_i, worst = 0, (0.0, 0, 0)
    for i, v in enumerate(s.index):
        if v > s.index[peak_i]:
            peak_i = i
        dd = v / s.index[peak_i] - 1
        if dd < worst[0]:
            worst = (dd, peak_i, i)
    dd, p, t = worst
    return {"drawdown": dd, "peak_date": s.dates[p], "trough_date": s.dates[t]}
