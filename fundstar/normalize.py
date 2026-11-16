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


def domestic_nav_rows(payload: bytes) -> list[dict]:
    """證期局／投信投顧公會 nav.csv。class_id 用「基金統編」（每個級別唯一）。"""
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = payload.decode("big5", errors="replace")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        r = {clean_key(k): clean_val(v) for k, v in r.items() if k}
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


PARSERS = {
    "tdcc_offshore_basic": offshore_basic_rows,
    "tdcc_offshore_nav": offshore_nav_rows,
    "tdcc_offshore_div": offshore_div_rows,
    "fsc_domestic_nav": domestic_nav_rows,
}
