"""資料來源定義與抓取。

只抓開放授權（政府資料開放授權條款第 1 版）的來源。
規則：循序請求、每次間隔至少 MIN_INTERVAL 秒、失敗指數退避重試，不平行。
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import pathlib
import time
import urllib.error
import urllib.request

TZ_TAIPEI = dt.timezone(dt.timedelta(hours=8))
USER_AGENT = "fundstar-bot/0.1 (open-data pipeline; contact via GitHub repo)"
MIN_INTERVAL = 2.0  # 秒
TIMEOUT = 60

LICENSE = "政府資料開放授權條款-第1版 https://data.gov.tw/license"

SOURCES: dict[str, dict] = {
    "tdcc_offshore_basic": {
        "url": "https://openapi.tdcc.com.tw/v1/opendata/3-2",
        "ext": "json",
        "provider": "臺灣集中保管結算所",
        "title": "境外基金基本資料",
        "dataset": "https://data.gov.tw/dataset/11639",
    },
    "tdcc_offshore_nav": {
        "url": "https://openapi.tdcc.com.tw/v1/opendata/3-4",
        "ext": "json",
        "provider": "臺灣集中保管結算所",
        "title": "境外基金淨值",
        "dataset": "https://data.gov.tw/dataset/11641",
    },
    "tdcc_offshore_div": {
        "url": "https://openapi.tdcc.com.tw/v1/opendata/3-5",
        "ext": "json",
        "provider": "臺灣集中保管結算所",
        "title": "境外基金配息資訊",
        "dataset": "https://data.gov.tw/dataset/11642",
    },
    "fsc_domestic_nav": {
        "url": "https://www.sitca.org.tw/MemberK0000/F/03/nav.csv",
        "ext": "csv",
        "provider": "金融監督管理委員會證券期貨局",
        "title": "證券投資信託基金每日淨值",
        "dataset": "https://data.gov.tw/dataset/11109",
    },
    # 以下三個是投信投顧公會提供、由證期局上架的月資料（不定期更新，約每月中旬）
    "fsc_domestic_basic": {
        "url": "https://www.sitca.org.tw/MemberK0000/F/03/43476"
               "%E6%8A%95%E4%BF%A1%E6%8A%95%E9%A1%A7%E5%85%AC%E6%9C%83%E5%A2%83%E5%85%A7%E5%9F%BA%E9%87%91"
               "%E5%9F%BA%E6%9C%AC%E8%B3%87%E6%96%99.csv",
        "ext": "csv",
        "provider": "金融監督管理委員會證券期貨局",
        "title": "投信投顧公會境內基金基本資料",
        "dataset": "https://data.gov.tw/dataset/43476",
    },
    "fsc_domestic_div": {
        "url": "https://www.sitca.org.tw/MemberK0000/F/03/160547"
               "%E6%8A%95%E4%BF%A1%E6%8A%95%E9%A1%A7%E5%85%AC%E6%9C%83%E5%A2%83%E5%85%A7%E5%9F%BA%E9%87%91"
               "%E9%85%8D%E6%81%AF%E8%B3%87%E6%96%99.csv",
        "ext": "csv",
        "provider": "金融監督管理委員會證券期貨局",
        "title": "投信投顧公會境內基金配息資料",
        "dataset": "https://data.gov.tw/dataset/160547",
    },
    "fsc_domestic_fee": {
        "url": "https://www.sitca.org.tw/MemberK0000/F/03/46443"
               "%E6%8A%95%E4%BF%A1%E6%8A%95%E9%A1%A7%E5%85%AC%E6%9C%83%E5%A2%83%E5%85%A7%E5%9F%BA%E9%87%91"
               "%E5%90%84%E9%A0%85%E8%B2%BB%E7%94%A8%E8%B3%87%E6%96%99.csv",
        "ext": "csv",
        "provider": "金融監督管理委員會證券期貨局",
        "title": "投信投顧公會境內基金各項費用資料",
        "dataset": "https://data.gov.tw/dataset/46443",
    },
}

_last_request = 0.0


def http_get(url: str, retries: int = 4) -> bytes:
    """限速 + 指數退避的 GET。"""
    global _last_request
    delay = 5.0
    for attempt in range(retries + 1):
        wait = MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


def raw_path(root: pathlib.Path, name: str, day: dt.date) -> pathlib.Path:
    ext = SOURCES[name]["ext"]
    return root / "raw" / name / f"{day:%Y}" / f"{day:%Y%m%d}.{ext}.gz"


def archive(root: pathlib.Path, name: str, payload: bytes, day: dt.date) -> pathlib.Path:
    """原始檔壓縮存檔；同一天重抓且內容相同則不覆寫。"""
    path = raw_path(root, name, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = gzip.decompress(path.read_bytes())
        if hashlib.sha256(old).digest() == hashlib.sha256(payload).digest():
            return path
    path.write_bytes(gzip.compress(payload, mtime=0))
    return path


def fetch_all(root: pathlib.Path, names: list[str] | None = None,
              today: dt.date | None = None
              ) -> tuple[dict[str, pathlib.Path], dict[str, str]]:
    """回傳 (成功的原始檔路徑, 失敗原因)。單一來源失敗不影響其他來源。"""
    today = today or dt.datetime.now(TZ_TAIPEI).date()
    out, errors = {}, {}
    for name in names or list(SOURCES):
        try:
            payload = http_get(SOURCES[name]["url"])
            if len(payload) < 100:
                raise ValueError(f"payload too small: {len(payload)} bytes")
            out[name] = archive(root, name, payload, today)
        except Exception as e:
            errors[name] = repr(e)
    return out, errors
