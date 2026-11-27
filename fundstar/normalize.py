"""把各來源原始檔轉成統一格式的資料列。

已知資料問題（2026-11-16 實測）：
- 集保 JSON 的第一個欄位名稱帶 BOM（\\ufeff資料日期、\\ufeff基金代碼）
- 部分值前面帶 tab（例如 "\\tA-1"）
- 缺值寫成 "N/A"
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json

MISSING = {"", "N/A", "NA", "-", "--", "null", "None"}


def clean_key(k: str) -> str:
    return k.replace("﻿", "").strip()


def clean_val(v):
    if isinstance(v, str):
        v = v.replace("﻿", "").strip()
        return None if v in MISSING else v
    return v


def to_float(v) -> float | None:
    v = clean_val(v)
    if v is None:
        return None
    return float(str(v).replace(",", ""))


def to_date(v) -> str | None:
    """'YYYYMMDD' -> 'YYYY-MM-DD'；無效則 None。"""
    v = clean_val(v)
    if v is None:
        return None
    v = str(v)
    if len(v) != 8 or not v.isdigit():
        return None
    try:
        return dt.datetime.strptime(v, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def parse_json_records(payload: bytes) -> list[dict]:
    data = json.loads(payload.decode("utf-8-sig"))
    if isinstance(data, dict):  # 防禦：若日後改成包一層
        data = data.get("data") or data.get("result") or []
    return [{clean_key(k): clean_val(v) for k, v in r.items()} for r in data]


def offshore_basic_rows(payload: bytes) -> list[dict]:
    rows = []
    for r in parse_json_records(payload):
        rows.append({
            "class_id": r.get("基金代碼"),
            "isin": r.get("基金ISIN_CODE"),
            "name": r.get("基金名稱"),
            "name_en": r.get("基金英文名稱"),
            "category": r.get("基金種類"),
            "region": r.get("投資區域"),
            "currency": r.get("計價幣別"),
            "risk_level": r.get("風險收益等級"),
            "agent": r.get("基金總代理名稱"),
            "manager": r.get("基金管理機構"),
            "fund_aum_m": to_float(r.get("基金規模(百萬)")),
            "fund_aum_currency": r.get("基金規模幣別"),
            "fund_aum_date": to_date(r.get("基金規模日期")),
            "class_aum_m": to_float(r.get("基金類股規模(百萬)")),
            "inception": to_date(r.get("基金成立日")),
            "as_of": to_date(r.get("資料日期")),
        })
    return [r for r in rows if r["class_id"]]


def offshore_nav_rows(payload: bytes) -> list[dict]:
    rows = []
    for r in parse_json_records(payload):
        rows.append({
            "market": "offshore",
            "class_id": r.get("基金代碼"),
            "date": to_date(r.get("日期")),
            "nav": to_float(r.get("基金淨值(金額)")),
            "currency": r.get("計價幣別"),
            "name": r.get("基金名稱"),
            "isin": r.get("ISINCODE"),
        })
    return [r for r in rows if r["class_id"] and r["date"] and r["nav"] is not None]


def offshore_div_rows(payload: bytes) -> list[dict]:
    """單位數 = 每單位配息金額；本金/配息 與 可分配淨利益/配息 為百分比。"""
    rows = []
    for r in parse_json_records(payload):
        rows.append({
            "market": "offshore",
            "class_id": r.get("基金代碼"),
            "ex_date": to_date(r.get("除息日")),
            "record_date": to_date(r.get("配息基準日")),
            "pay_date": to_date(r.get("配息發放日")),
            "dividend": to_float(r.get("單位數")),
            "currency": r.get("基金幣別"),
            "frequency": r.get("配息頻率"),
            "pct_from_income": to_float(r.get("可分配淨利益/配息")),
            "pct_from_principal": to_float(r.get("本金/配息")),
            "name": r.get("基金名稱"),
        })
    return [r for r in rows if r["class_id"] and r["ex_date"] and r["dividend"] is not None]


def parse_csv_records(payload: bytes) -> list[dict]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = payload.decode("big5", errors="replace")
    return [{clean_key(k): clean_val(v) for k, v in r.items() if k}
            for r in csv.DictReader(io.StringIO(text))]


def to_month(v) -> str | None:
    """'YYYYMM' -> 'YYYY-MM'。"""
    v = clean_val(v)
    if v is None or len(str(v)) != 6 or not str(v).isdigit():
        return None
    return f"{str(v)[:4]}-{str(v)[4:]}"


def domestic_nav_rows(payload: bytes) -> list[dict]:
    """證期局／投信投顧公會 nav.csv。class_id 用「基金統編」（每個級別唯一）。"""
    rows = []
    for r in parse_csv_records(payload):
        rows.append({
            "market": "domestic",
            "class_id": r.get("基金統編"),
            "date": to_date(r.get("日期")),
            "nav": to_float(r.get("基金淨值")),
            "currency": r.get("幣別"),
            "name": r.get("基金名稱"),
            "fund_code": r.get("基金代號"),
            "company": r.get("公司名稱"),
            "type_code": r.get("類型代號"),
            "ticker": r.get("受益憑證代號"),
        })
    return [r for r in rows if r["class_id"] and r["date"] and r["nav"] is not None]


def domestic_basic_rows(payload: bytes) -> list[dict]:
    """境內基金基本資料（月資料，每列一個級別）。規模單位為元。"""
    rows = []
    for r in parse_csv_records(payload):
        rows.append({
            "class_id": r.get("統編"),
            "month": to_month(r.get("年月")),
            "name": r.get("基金名稱"),
            "company": r.get("公司名稱"),
            "inception": to_date(r.get("基金/級別成立日期")),
            "aum_date": to_date(r.get("基金規模日期")),
            "aum_currency": r.get("基金規模幣別"),
            "class_aum": to_float(r.get("基金級別規模_金額")),
            "fund_aum": to_float(r.get("基金規模(依基金別)_金額")),
            "category": r.get("基金類型別"),
            "region": r.get("投資地區"),
            "div_policy": r.get("基金配息規定(基金收益分配規定)"),
            "isin": r.get("基金ISIN Code"),
            "currency": r.get("基金計價幣別"),
        })
    return [r for r in rows if r["class_id"]]


def domestic_div_rows(payload: bytes) -> list[dict]:
    """境內基金配息（只有每單位金額，沒有本金／收益組成）。"""
    rows = []
    for r in parse_csv_records(payload):
        rows.append({
            "market": "domestic",
            "class_id": r.get("基金統編"),
            "ex_date": to_date(r.get("除息日")),
            "record_date": to_date(r.get("配息基準日")),
            "pay_date": to_date(r.get("收益分配發放日")),
            "dividend": to_float(r.get("每單位分派金額")),
            "currency": r.get("配息幣別"),
            "type_code": r.get("基金類型"),
            "name": r.get("基金名稱"),
        })
    return [r for r in rows if r["class_id"] and r["ex_date"] and r["dividend"] is not None]


FEE_ITEMS = {"手續費": "trade", "交易稅": "tax", "經理費": "mgmt", "保管費": "custody",
             "保證費": "guarantee", "其他費用": "other"}


def domestic_fee_rows(payload: bytes) -> list[dict]:
    """境內基金各項費用（月資料，整檔基金層級）。*_pct 為占基金淨資產的百分比（單月）。"""
    rows = []
    for r in parse_csv_records(payload):
        row = {
            "fund_id": r.get("基金統編"),
            "month": to_month(r.get("年月")),
            "name": r.get("基金名稱"),
            "company": r.get("公司名稱"),
            "type_code": r.get("類型代號"),
            "total_amount": to_float(r.get("合計")),
            "total_pct": to_float(r.get("合計_比率")),
        }
        for zh, en in FEE_ITEMS.items():
            row[f"{en}_pct"] = to_float(r.get(f"月{zh}_比率"))
        rows.append(row)
    return [r for r in rows if r["fund_id"] and r["month"]]


PARSERS = {
    "tdcc_offshore_basic": offshore_basic_rows,
    "tdcc_offshore_nav": offshore_nav_rows,
    "tdcc_offshore_div": offshore_div_rows,
    "fsc_domestic_nav": domestic_nav_rows,
    "fsc_domestic_basic": domestic_basic_rows,
    "fsc_domestic_div": domestic_div_rows,
    "fsc_domestic_fee": domestic_fee_rows,
}
