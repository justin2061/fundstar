import pathlib

from fundstar import normalize as n

FX = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return (FX / name).read_bytes()


def test_bom_and_tab_cleaned():
    rows = n.offshore_basic_rows(load("tdcc_3-2.json"))
    assert rows[0]["as_of"] == "2026-11-15"          # BOM 欄位名稱
    assert rows[0]["risk_level"] == "4"
    assert rows[0]["fund_aum_m"] == 1144.63
    assert rows[0]["class_id"] == "00BD5M6702"


def test_offshore_nav_drops_missing():
    rows = n.offshore_nav_rows(load("tdcc_3-4.json"))
    assert len(rows) == 1                              # N/A 淨值被排除
    assert rows[0] == {"market": "offshore", "class_id": "000AMEEBEI", "date": "2026-11-09",
                       "nav": 31.1516, "currency": "EUR",
                       "name": "天利(盧森堡)-歐洲策略債券基金(歐元)", "isin": "LU0096353940"}


def test_offshore_div_source_pct():
    rows = n.offshore_div_rows(load("tdcc_3-5.json"))
    hsbc, eur = rows
    assert hsbc["ex_date"] == "2026-07-31" and hsbc["dividend"] == 0.029622
    assert hsbc["pct_from_income"] == 100.0 and hsbc["pct_from_principal"] == 0.0
    assert eur["pct_from_principal"] is None           # N/A → 資料不足，不是 0


def test_domestic_csv():
    rows = n.domestic_nav_rows(load("nav.csv"))
    assert [r["class_id"] for r in rows] == ["00512527", "00526748B"]
    assert rows[1]["nav"] == 11.07 and rows[1]["date"] == "2026-11-13"
    assert rows[0]["ticker"] == "00957B"


def test_domestic_basic():
    rows = n.domestic_basic_rows(load("sitca_basic.csv"))
    assert [r["class_id"] for r in rows] == ["00512527", "00526748A"]     # 缺統編的列被排除
    etf = rows[0]
    assert etf["month"] == "2026-10" and etf["aum_date"] == "2026-10-31"
    assert etf["fund_aum"] == 2422735021 and etf["category"] == "(AH22) 跨國投資指數股票型_債券型"
    assert etf["div_policy"] == "月配息" and etf["isin"] == "TW00000957B0"


def test_domestic_div():
    rows = n.domestic_div_rows(load("sitca_div.csv"))                    # BOM 欄位、缺金額的列被排除
    assert len(rows) == 1
    assert rows[0]["class_id"] == "31968075B" and rows[0]["ex_date"] == "2026-10-01"
    assert rows[0]["dividend"] == 0.0326 and rows[0]["pay_date"] == "2026-10-08"


def test_domestic_fee():
    (r,) = n.domestic_fee_rows(load("sitca_fee.csv"))
    assert r["fund_id"] == "00965469" and r["month"] == "2026-10"
    assert r["mgmt_pct"] == 0.1274 and r["total_pct"] == 0.17944 and r["guarantee_pct"] == 0.0


def test_to_date_invalid():
    assert n.to_date("2026131") is None
    assert n.to_date("N/A") is None
