import math

import pytest

from fundstar import returns as r


def test_no_dividend_equals_nav_ratio():
    s = r.total_return_index([("2026-01-01", 10.0), ("2026-01-02", 11.0), ("2026-01-03", 9.9)])
    assert s.index == pytest.approx([1.0, 1.1, 0.99])


def test_dividend_reinvested_at_ex_date():
    # 淨值 10 → 除息後 9.5，配 0.5：含息報酬 0%（高配息但沒賺錢的情況）
    s = r.total_return_index([("2026-01-01", 10.0), ("2026-01-02", 9.5)], {"2026-01-02": 0.5})
    assert s.index[-1] == pytest.approx(1.0)
    # 淨值 10 → 9.6，配 0.5：含息 +1%
    s = r.total_return_index([("2026-01-01", 10.0), ("2026-01-02", 9.6)], {"2026-01-02": 0.5})
    assert s.index[-1] == pytest.approx(1.01)


def test_reinvested_units_compound():
    # 再投資後的單位數會吃到之後的漲幅
    s = r.total_return_index([("d1", 10.0), ("d2", 9.0), ("d3", 9.9)], {"d2": 1.0})
    assert s.index[-1] == pytest.approx(1.0 * 1.1)


def test_ex_date_without_nav_applied_next_day_with_warning():
    s = r.total_return_index([("2026-01-01", 10.0), ("2026-01-05", 9.5)], {"2026-01-03": 0.5})
    assert s.index[-1] == pytest.approx(1.0)
    assert "applied on 2026-01-05" in s.warnings[0]


def test_dividend_outside_range_ignored():
    s = r.total_return_index([("2026-01-01", 10.0), ("2026-01-02", 10.0)], {"2025-12-01": 1.0})
    assert s.index[-1] == 1.0 and s.warnings


def test_period_return_insufficient_history():
    s = r.total_return_index([("2026-01-01", 10.0), ("2026-06-01", 12.0)])
    assert r.period_return(s, "2025-01-01", "2026-06-01") is None   # 資料不足
    assert r.period_return(s, "2026-01-01", "2026-06-01") == pytest.approx(0.2)


def test_max_drawdown():
    s = r.total_return_index([("a", 10), ("b", 12), ("c", 9), ("d", 13), ("e", 11.7)])
    mdd = r.max_drawdown(s)
    assert mdd["drawdown"] == pytest.approx(-0.25)
    assert (mdd["peak_date"], mdd["trough_date"]) == ("b", "c")


def test_volatility_needs_enough_points():
    short = r.total_return_index([(f"{i:03d}", 10 + i % 2) for i in range(30)])
    assert r.annualized_volatility(short) is None
    # 每日 +1%/-1% 交替：日對數報酬標準差約 0.01
    navs, v = [], 10.0
    for i in range(200):
        navs.append((f"{i:03d}", v)); v *= 1.01 if i % 2 == 0 else 1 / 1.01
    vol = r.annualized_volatility(r.total_return_index(navs))
    assert vol == pytest.approx(math.log(1.01) * math.sqrt(252), rel=0.02)
