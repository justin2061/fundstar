"""名稱正規化、類型判斷等文字工具（Python 與前端 search.js 規則需一致）。"""
from __future__ import annotations

import re
import unicodedata

CURRENCY_WORDS = [
    "新台幣", "新臺幣", "台幣", "臺幣", "美元", "美金", "歐元", "人民幣", "南非幣", "澳幣", "澳元",
    "日圓", "日幣", "紐幣", "紐西蘭幣", "英鎊", "加幣", "新加坡幣", "星幣", "港幣", "瑞士法郎",
]
CURRENCY_CODES = {
    "TWD": "新台幣", "USD": "美元", "EUR": "歐元", "CNY": "人民幣", "ZAR": "南非幣", "AUD": "澳幣",
    "JPY": "日圓", "NZD": "紐幣", "GBP": "英鎊", "CAD": "加幣", "SGD": "新加坡幣", "HKD": "港幣",
    "CHF": "瑞士法郎",
}
_PUNCT = re.compile(r"[\s\-_‧·・.,，、/／()（）\[\]【】「」:：;；*＊]+")
_PAREN = re.compile(r"[(（][^)）]*[)）]")
_CLASS_WORDS = re.compile(
    r"(避險|(?:月|季|半年|年)配(?:浮動|固定)|累積型?|配息型?|月配息?|季配息?|半年配息?|年配息?|穩定月配息|穩定月配|穩定配息|穩定配|收益股|累積股|分派股|"
    r"不配息|配息|類型|級別|類股|股份|TISA)"
)
_CLASS_TOKEN = re.compile(r"(?<![A-Za-z])[A-Z]{1,4}\d{0,2}[A-Z]{0,4}(?![A-Za-z])")

DIV_PATTERN = re.compile(r"配息|月配|季配|年配|半年配|收益股|派息|分派|穩定配")


def norm(s: str | None) -> str:
    """搜尋用正規化：全形轉半形、小寫、去符號與空白、去「基金」「證券投資信託」字樣。"""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("證券投資信託", "").replace("基金", "").replace("臺", "台")
    return _PUNCT.sub("", s)


def base_name(name: str | None) -> str:
    """去掉括號內容、幣別、級別字樣後的「基金本名」，用來找同一基金的其他級別。"""
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name)
    s = _PAREN.sub("", s)
    for w in CURRENCY_WORDS:
        s = s.replace(w, "")
    s = _CLASS_WORDS.sub("", s)
    s = _CLASS_TOKEN.sub("", s)
    return norm(s)


def is_div_name(name: str | None) -> bool:
    return bool(name and DIV_PATTERN.search(name)) and "不配息" not in name


def is_hedged(name: str | None) -> bool:
    return bool(name and "避險" in name)


def currency_label(code_or_name: str | None) -> str:
    if not code_or_name:
        return "資料不足"
    return CURRENCY_CODES.get(code_or_name.upper(), code_or_name)


def domestic_type_from_name(name: str | None) -> str | None:
    """境內基金沒有開放的類型欄位，只能依名稱粗分；判斷不出來回傳 None。"""
    if not name:
        return None
    rules = [
        ("貨幣市場", "貨幣市場型"), ("ETF連結", "ETF連結基金"), ("組合", "組合型"),
        ("ETF", "ETF"), ("多重資產", "多重資產型"), ("平衡", "平衡型"), ("保本", "保本型"),
        ("不動產", "不動產證券化型"), ("REIT", "不動產證券化型"), ("債", "債券型"),
        ("指數", "指數型"), ("股", "股票型"),
    ]
    for kw, t in rules:
        if kw in name:
            return t
    return None


def offshore_type(category: str | None) -> str | None:
    if not category:
        return None
    return category.split("-")[0].strip() or None


def offshore_region(region: str | None) -> str | None:
    if not region:
        return None
    return region.split("-")[0].strip() or None


TYPE_UNIFY = {"固定收益型": "債券型", "平衡型(混合型)": "平衡型", "其他型": "其他"}


def unify_type(t: str | None) -> str | None:
    """境外分類用語對齊境內，讓篩選選單一致。"""
    if not t:
        return None
    return TYPE_UNIFY.get(t, t)
