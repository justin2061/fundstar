import json
import pathlib

import pytest

from fundstar import site, store, textutil


def test_norm_and_base_name():
    assert textutil.norm("兆豐 ESG（台美）永續基金") == "兆豐esg台美永續"
    a = textutil.base_name("紐約梅隆美國股票收益基金-美元A配息")
    b = textutil.base_name("紐約梅隆美國股票收益基金-美元A累積")
    assert a == b == "紐約梅隆美國股票收益"
    assert textutil.base_name("兆豐ESG台美永續雙盈多重資產基金(新台幣)-累積型") == \
        textutil.base_name("兆豐ESG台美永續雙盈多重資產基金(美元)-配息型")


def test_div_and_type_from_name():
    assert textutil.is_div_name("某某收益基金-月配息") and not textutil.is_div_name("某某基金-不配息")
    assert textutil.domestic_type_from_name("兆豐美國企業優選投資級公司債ETF基金") == "ETF"
    assert textutil.domestic_type_from_name("某某貨幣市場基金") == "貨幣市場型"
    assert textutil.domestic_type_from_name("某某基金") is None   # 判斷不出 → 資料不足


def _curated(tmp_path):
    cur = tmp_path / "curated"
    navs = [{"market": "offshore", "class_id": "A1", "date": f"2026-{m:02d}-{d:02d}", "nav": 10 + (d % 5) * 0.1,
             "currency": "USD", "name": "測試全球收益基金-美元A配息", "isin": "LU1"}
            for m in (9, 10) for d in range(1, 29)]
    navs += [{"market": "offshore", "class_id": "A2", "date": "2026-11-10", "nav": 9.0, "currency": "EUR",
              "name": "測試全球收益基金-歐元A累積", "isin": "LU2"}]
    store.merge(cur, "nav_offshore", navs)
    store.merge(cur, "div_offshore", [{"market": "offshore", "class_id": "A1", "ex_date": "2026-10-15",
                                       "record_date": None, "pay_date": None, "dividend": 0.05, "currency": "美元",
                                       "frequency": "每月", "pct_from_income": 60.0, "pct_from_principal": 40.0,
                                       "name": "x"}])
    store.merge(cur, "nav_domestic", [
        {"market": "domestic", "class_id": "D1B", "date": "2026-11-13", "nav": 11.07, "currency": "TWD",
         "name": "測試多重資產基金(新台幣)-配息型", "fund_code": "X", "company": "測試投信", "type_code": "AJ2",
         "ticker": "T1"},
        {"market": "domestic", "class_id": "D2", "date": "2026-11-13", "nav": 20.0, "currency": "TWD",
         "name": "全球穩定月收益基金", "fund_code": "Y", "company": "測試投信", "type_code": "", "ticker": ""},
        {"market": "domestic", "class_id": "D3", "date": "2026-11-13", "nav": 21.0, "currency": "TWD",
         "name": "穩定月收益基金", "fund_code": "Z", "company": "測試投信", "type_code": "", "ticker": ""}])
    store.merge(cur, "funds_offshore", [{"class_id": "A1", "isin": "LU1", "name": "測試", "name_en": None,
                                         "category": "債券型-一般型", "region": "全球-已開發市場", "currency": "美元",
                                         "risk_level": "2", "agent": "測試總代理", "manager": None,
                                         "fund_aum_m": 100.0, "fund_aum_currency": "USD", "fund_aum_date": "2026-10-30",
                                         "class_aum_m": 1.0, "inception": "2010-01-01", "as_of": "2026-11-15"}])
    return cur


def test_build_site(tmp_path):
    out = tmp_path / "_site"
    meta = site.build_site(_curated(tmp_path), out, generated_at="test")
    assert meta["count"] == 5
    idx = json.loads((out / "data/index.json").read_text(encoding="utf-8"))
    ids = {f[0]: f for f in idx["funds"]}
    assert ids["o-A1"][6] == "RR2" and ids["o-A1"][8] == 1     # 風險等級、配息
    assert ids["o-A2"][6] == ""                                  # 沒有基本資料 → 空白
    a1 = (out / "f/o-A1.html").read_text(encoding="utf-8")
    assert "配息真相" in a1 and "40.0%" in a1 and "RR2" in a1
    assert "o-A2.html" in a1                                     # 同一基金其他級別（依名稱）
    assert "非投資建議" not in a1 and "不構成投資建議" in a1       # 固定警語
    d1 = (out / "f/d-D1B.html").read_text(encoding="utf-8")
    assert "境內配息型級別沒有開放的配息資料" in d1               # 含息報酬資料不足
    d3 = (out / "f/d-D3.html").read_text(encoding="utf-8")
    assert "名稱相近" in d3 and "d-D2.html" in d3                # 穩定月收益 vs 全球穩定月收益
    j = json.loads((out / "data/f/o-A1.json").read_text(encoding="utf-8"))
    assert j["div"]["n_principal"] == 1 and j["tr"] is not None
    for p in ("index.html", "compare.html", "glossary.html", "about.html", "assets/search.js", ".nojekyll"):
        assert (out / p).exists()


def test_chart_needs_enough_points():
    assert "資料不足" in site.svg_chart([("2026-01-01", 1.0)] * 3, "x")
    assert "<svg" in site.svg_chart([(f"2026-01-{i:02d}", 1.0 + i) for i in range(1, 25)], "x")
