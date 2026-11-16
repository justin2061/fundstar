"""靜態網站產生器（M2）：搜尋、白話健檢、比較。

原則：
- 每個數字附一句白話解釋、資料日期與來源；沒有資料就寫「資料不足」並說明缺什麼。
- 只寫描述句，不寫判斷句（不推薦、不評論好壞、不說該不該買）。
"""
from __future__ import annotations

import datetime as dt
import html
import json
import math
import pathlib
import shutil
from collections import defaultdict

from . import returns, sources, textutil

MIN_CHART_POINTS = 20
ASSET_DIR = pathlib.Path(__file__).parent / "web"

DISCLAIMER = (
    "本站僅提供資訊與教育用途，不構成投資建議，也不推薦任何基金。"
    "過去績效不代表未來表現。配息率不代表報酬率，配息可能來自本金。"
    "資料來自政府開放資料，以基金公司公告為準。"
)
SRC_OFF = "臺灣集中保管結算所（開放資料）"
SRC_DOM = "金融監督管理委員會證券期貨局（開放資料）"

e = html.escape


# ---------------------------------------------------------------- 資料載入

def load(curated: pathlib.Path) -> dict:
    import duckdb
    con = duckdb.connect()

    def q(sql, path):
        p = curated / path
        return con.execute(sql.replace("{p}", f"read_parquet('{p.as_posix()}')")).fetchall() if p.exists() else []

    navs = defaultdict(list)
    meta = {}
    for cid, d, v, cur, name, isin in q(
            "SELECT class_id, date::VARCHAR, nav, currency, name, isin FROM {p} ORDER BY class_id, date",
            "nav_offshore.parquet"):
        key = f"o-{cid}"
        navs[key].append((d, v))
        meta[key] = {"market": "offshore", "class_id": cid, "currency": cur, "name": name, "isin": isin}
    for cid, d, v, cur, name, company, type_code, ticker in q(
            "SELECT class_id, date::VARCHAR, nav, currency, name, company, type_code, ticker "
            "FROM {p} ORDER BY class_id, date", "nav_domestic.parquet"):
        key = f"d-{cid}"
        navs[key].append((d, v))
        meta[key] = {"market": "domestic", "class_id": cid, "currency": cur, "name": name,
                     "company": company, "type_code": type_code, "ticker": ticker}

    divs = defaultdict(list)
    for cid, ex, amt, cur, freq, inc, pri in q(
            "SELECT class_id, ex_date::VARCHAR, dividend, currency, frequency, pct_from_income, "
            "pct_from_principal FROM {p} ORDER BY class_id, ex_date", "div_offshore.parquet"):
        divs[f"o-{cid}"].append({"ex_date": ex, "dividend": amt, "currency": cur, "frequency": freq,
                                 "pct_income": inc, "pct_principal": pri})

    basic = {}
    cols = ["class_id", "isin", "name", "category", "region", "currency", "risk_level", "agent",
            "manager", "fund_aum_m", "fund_aum_currency", "fund_aum_date", "class_aum_m", "inception", "as_of"]
    for row in q(f"SELECT {', '.join(cols)} FROM {{p}}", "funds_offshore.parquet"):
        r = dict(zip(cols, row))
        basic[f"o-{r['class_id']}"] = r
    return {"navs": navs, "meta": meta, "divs": divs, "basic": basic}


# ---------------------------------------------------------------- 計算

def _years_ago(date: str, years: int) -> str:
    d = dt.date.fromisoformat(date)
    try:
        return d.replace(year=d.year - years).isoformat()
    except ValueError:  # 2/29
        return d.replace(year=d.year - years, day=28).isoformat()


def build_record(key: str, data: dict) -> dict:
    m = data["meta"][key]
    b = data["basic"].get(key, {})
    navs = data["navs"][key]
    divs = data["divs"].get(key, [])
    name = m["name"] or b.get("name")
    market = m["market"]
    div_name = textutil.is_div_name(name)

    rec = {
        "id": key, "name": name, "market": market, "class_id": m["class_id"],
        "currency": textutil.currency_label(m.get("currency") or b.get("currency")),
        "hedged": textutil.is_hedged(name),
        "isin": m.get("isin") or b.get("isin"),
        "latest_nav": navs[-1][1], "latest_date": navs[-1][0],
        "first_date": navs[0][0], "n_nav": len(navs),
        "has_div_record": bool(divs), "div_name": div_name,
        "base": textutil.base_name(name),
        "source": SRC_OFF if market == "offshore" else SRC_DOM,
    }
    if market == "offshore":
        rec.update({
            "type": textutil.unify_type(textutil.offshore_type(b.get("category"))), "type_detail": b.get("category"),
            "type_basis": "基本資料" if b.get("category") else None,
            "region": textutil.offshore_region(b.get("region")), "region_detail": b.get("region"),
            "risk": f"RR{b['risk_level']}" if b.get("risk_level") else None,
            "company": b.get("agent"), "company_label": "總代理",
            "manager": b.get("manager"), "inception": b.get("inception"),
            "region_filter": b.get("region"),
            "fund_aum_m": b.get("fund_aum_m"), "fund_aum_currency": b.get("fund_aum_currency"),
            "fund_aum_date": b.get("fund_aum_date"), "basic_as_of": b.get("as_of"),
        })
    else:
        t = textutil.domestic_type_from_name(name)
        rec.update({
            "type": t, "type_detail": None, "type_basis": "依基金名稱判斷" if t else None,
            "region": None, "region_detail": None, "region_filter": None, "risk": None,
            "company": m.get("company"), "company_label": "投信",
            "ticker": m.get("ticker"), "type_code": m.get("type_code"),
        })

    # 含息報酬：境內配息型沒有開放的配息資料 → 資料不足
    tr_ok = not (market == "domestic" and div_name)
    series = returns.total_return_index(navs, {d["ex_date"]: d["dividend"] for d in divs}) if tr_ok else None
    rec["tr_available"] = tr_ok
    rec["tr_warnings"] = series.warnings if series else []
    end = rec["latest_date"]
    for y in (1, 3, 5):
        rec[f"ret_{y}y"] = returns.period_return(series, _years_ago(end, y), end) if series else None
    rec["vol"] = returns.annualized_volatility(series) if series else None
    mdd = returns.max_drawdown(series) if series and len(series.index) >= MIN_CHART_POINTS else None
    rec["mdd"] = mdd

    if divs:
        withp = [d for d in divs if d["pct_principal"] is not None]
        rec["div"] = {
            "n": len(divs), "first_ex": divs[0]["ex_date"], "last_ex": divs[-1]["ex_date"],
            "sum": sum(d["dividend"] for d in divs), "frequency": divs[-1]["frequency"],
            "n_with_source": len(withp),
            "n_principal": sum(1 for d in withp if d["pct_principal"] > 0),
            "avg_principal": (sum(d["pct_principal"] for d in withp) / len(withp)) if withp else None,
            "recent": divs[-12:][::-1],
        }
        rec["div"]["sum_pct_of_nav"] = rec["div"]["sum"] / rec["latest_nav"] if rec["latest_nav"] else None
    else:
        rec["div"] = None
    rec["_series"] = series
    return rec


def group_key(r: dict) -> str:
    """同一檔基金的分組鍵。
    境內：基金統編前 8 碼（同一基金各級別共用，2026-10 共 1,105 組，接近公會統計的 1,103 檔）。
    境外：管理機構＋基金規模＋規模日期（整檔基金規模為各級別共用）；沒有基本資料時退回用名稱。
    """
    if r["market"] == "domestic":
        return "d:" + r["class_id"][:8]
    if r.get("fund_aum_m") is not None:
        return f"o:{r.get('manager')}|{r['fund_aum_m']}|{r.get('fund_aum_currency')}|{r.get('fund_aum_date')}"
    return "o-name:" + r["base"]


def _strip_ascii(s: str) -> str:
    return "".join(ch for ch in s if not ch.isascii())


LOOKALIKE_MIN_LEN = 5
GROUP_NOTE = {
    "domestic": "依基金統編判斷為同一檔基金。",
    "offshore": "依整檔基金規模與管理機構判斷為同一檔基金；沒有基本資料的級別依名稱判斷。",
}


def link_names(recs: list[dict]) -> None:
    """siblings：同一基金的其他級別；lookalikes：名稱互相包含、但屬於不同基金。"""
    groups = defaultdict(list)
    for r in recs:
        r["group"] = group_key(r)
    # 沒有基本資料的境外級別：若名稱本名與某個已分組級別相同，併入該組
    base_to_group = {}
    for r in recs:
        if r["group"].startswith("o:") and r["base"]:
            base_to_group.setdefault(r["base"], r["group"])
    for r in recs:
        if r["group"].startswith("o-name:") and r["base"] in base_to_group:
            r["group"] = base_to_group[r["base"]]
        groups[r["group"]].append(r["id"])
    for r in recs:
        r["siblings"] = [i for i in groups[r["group"]] if i != r["id"]][:30]

    # 每個（本名去英數）對應到哪些分組
    base_groups = defaultdict(set)
    rep = {}
    for r in recs:
        b = _strip_ascii(r["base"])
        if len(b) >= LOOKALIKE_MIN_LEN:
            base_groups[b].add(r["group"])
            rep.setdefault((b, r["group"]), r["id"])
    bases = sorted(base_groups, key=len)
    related = defaultdict(set)
    for i, a in enumerate(bases):
        for bb in bases[i + 1:]:
            if len(bb) - len(a) >= 2 and a in bb:
                related[a].add(bb)
                related[bb].add(a)
    for r in recs:
        b = _strip_ascii(r["base"])
        out = []
        for other in sorted(related.get(b, ())):
            for g in sorted(base_groups[other]):
                if g != r["group"]:
                    out.append(rep[(other, g)])
        r["lookalikes"] = out[:10]


# ---------------------------------------------------------------- 格式化

def pct(x, digits=1, sign=True):
    if x is None:
        return None
    s = f"{x * 100:+.{digits}f}%" if sign else f"{x * 100:.{digits}f}%"
    return s


def num(x, digits=4):
    if x is None:
        return "資料不足"
    s = f"{x:,.{digits}f}".rstrip("0").rstrip(".")
    return s


def insufficient(what: str) -> str:
    return f'<span class="na">資料不足</span><span class="why">{e(what)}</span>'


def svg_chart(points: list[tuple[str, float]], label: str) -> str:
    if len(points) < MIN_CHART_POINTS:
        return (f'<div class="chart-na">資料不足：目前只有 {len(points)} 個淨值日，'
                f'至少需要 {MIN_CHART_POINTS} 個才畫圖。本站從 2026-11-16 起每日累積。</div>')
    w, h, pad = 640, 220, 36
    vals = [v for _, v in points]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(points)
    xy = [(pad + (w - 2 * pad) * i / (n - 1), h - pad - (h - 2 * pad) * (v - lo) / span)
          for i, (_, v) in enumerate(points)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    return (
        f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{e(label)}">'
        f'<polyline fill="none" stroke="currentColor" stroke-width="1.6" points="{poly}"/>'
        f'<text x="{pad}" y="{h - 10}" class="ax">{points[0][0]}</text>'
        f'<text x="{w - pad}" y="{h - 10}" class="ax" text-anchor="end">{points[-1][0]}</text>'
        f'<text x="4" y="{pad}" class="ax">{num(hi)}</text>'
        f'<text x="4" y="{h - pad}" class="ax">{num(lo)}</text></svg>'
    )


# ---------------------------------------------------------------- 頁面

def page(title: str, body: str, depth: int = 0, desc: str = "") -> str:
    up = "../" * depth
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}｜基金白話通</title>
<meta name="description" content="{e(desc or DISCLAIMER)}">
<link rel="icon" href="data:,">
<link rel="stylesheet" href="{up}assets/style.css"></head>
<body><header class="top"><a class="brand" href="{up}index.html">基金白話通</a>
<nav><a href="{up}index.html">搜尋</a><a href="{up}compare.html">比較</a>
<a href="{up}glossary.html">名詞小辭典</a><a href="{up}about.html">資料來源</a></nav></header>
<main>{body}</main>
<footer class="disclaimer"><p>{e(DISCLAIMER)}</p></footer></body></html>
"""


def row(label: str, value: str, explain: str, meta: str = "") -> str:
    m = f'<div class="meta">{e(meta)}</div>' if meta else ""
    return (f'<div class="row"><div class="label">{e(label)}</div><div class="value">{value}</div>'
            f'<div class="explain">{e(explain)}</div>{m}</div>')


def fund_page(r: dict, by_id: dict) -> str:
    src = f"來源：{r['source']}"
    cur = r["currency"] + ("（避險級別）" if r["hedged"] else "")
    parts = [f'<h1>{e(r["name"] or r["class_id"])}</h1>',
             f'<p class="sub">{"境外基金" if r["market"] == "offshore" else "境內基金"}・'
             f'{e(cur)}計價・{e(r["company_label"])}：{e(r.get("company") or "資料不足")}</p>',
             f'<p><a class="btn" href="../compare.html?ids={e(r["id"])}">加入比較</a></p>']

    # 這是什麼級別
    cls = []
    cls.append(f"這是用{r['currency']}計價的級別，淨值和配息都以{r['currency']}計算；換回台幣時會有匯率漲跌。")
    if r["hedged"]:
        cls.append("名稱標示「避險」：基金會用避險工具降低匯率影響，但會有避險成本，也不能完全消除匯率風險。")
    if r["div_name"]:
        cls.append("名稱標示配息：配息會發給投資人，淨值會在除息日下降相同金額。")
    elif r["has_div_record"]:
        cls.append("這個級別有配息紀錄。")
    if r["siblings"]:
        cls.append(f"同一檔基金還有其他 {len(r['siblings'])} 個級別，列在本頁下方。")
    parts.append('<section><h2>這是什麼級別</h2><ul>' + "".join(f"<li>{e(x)}</li>" for x in cls) + "</ul></section>")

    # 基本資料
    rows = [
        row("最新淨值", f'{num(r["latest_nav"])} {e(r["currency"])}',
            "每一單位基金現在值多少錢。淨值高低本身不代表好壞。", f"資料日期 {r['latest_date']}｜{src}"),
        row("類型", e(r["type"]) if r["type"] else insufficient("開放資料沒有這檔的類型欄位"),
            "基金主要投資什麼，例如股票、債券。",
            (f"判斷依據：{r['type_basis']}" + (f"（{r['type_detail']}）" if r.get("type_detail") else ""))
            if r["type"] else ""),
        row("投資區域", e(r["region_detail"] or r["region"]) if r["region"] else
            insufficient("境內基金沒有開放的投資區域資料" if r["market"] == "domestic" else "開放資料沒有這檔的區域欄位"),
            "基金的錢主要投到哪些國家或地區。", src if r["region"] else ""),
        row("風險等級", e(r["risk"]) if r["risk"] else
            insufficient("境內基金沒有開放的風險等級資料" if r["market"] == "domestic" else "開放資料沒有這檔的基本資料"),
            "RR1 到 RR5，數字越大代表價格可能上下波動越大。這是基金公司依規定標示的等級，不是本站的評價。",
            f"資料日期 {r.get('basic_as_of')}｜{src}" if r["risk"] else ""),
    ]
    if r["market"] == "offshore" and r.get("fund_aum_m") is not None:
        rows.append(row("基金規模", f'{num(r["fund_aum_m"], 2)} 百萬 {e(r.get("fund_aum_currency") or "")}',
                        "整檔基金（所有級別合計）管理多少錢。", f"資料日期 {r.get('fund_aum_date')}｜{src}"))
    parts.append('<section><h2>基本資料</h2>' + "".join(rows) + "</section>")

    # 走勢與風險
    hist = f"本站目前有 {r['n_nav']} 個淨值日（{r['first_date']} 到 {r['latest_date']}）"
    perf = []
    for y in (1, 3, 5):
        v = r[f"ret_{y}y"]
        if not r["tr_available"]:
            val = insufficient("境內配息型級別沒有開放的配息資料，無法計算含息報酬")
        elif v is None:
            val = insufficient(f"需要至少 {y} 年的淨值資料；{hist}")
        else:
            val = f'<b>{pct(v)}</b>'
        perf.append(row(f"近 {y} 年含息報酬", val,
                        f"假設 {y} 年前投入，並把每次配息都在除息日買回同一檔基金，到現在的漲跌幅度。",
                        f"本站依官方淨值與配息計算｜{src}" if v is not None else ""))
    vol = r["vol"]
    perf.append(row("年化波動", f"<b>{pct(vol, sign=False)}</b>" if vol is not None else
                    insufficient(f"至少需要 {returns.MIN_POINTS_VOL + 1} 個淨值日；{hist}"),
                    "一年內價格大概會上下晃動多少。數字越大，短期起伏越大。"))
    mdd = r["mdd"]
    perf.append(row("最大回撤", f'<b>{pct(mdd["drawdown"])}</b>（{mdd["peak_date"]} 高點 → {mdd["trough_date"]} 低點）'
                    if mdd else insufficient(f"至少需要 {MIN_CHART_POINTS} 個淨值日；{hist}"),
                    "在資料期間內，最慘的時候從高點跌了多少。"))
    parts.append('<section><h2>走勢與風險</h2>' +
                 svg_chart(by_id[r["id"]]["_navs"], f"{r['name']} 淨值走勢") + "".join(perf) + "</section>")

    # 配息真相
    d = r["div"]
    if d:
        def pv(v):
            return "資料不足" if v is None else f"{v:.1f}%"
        recent = "".join(
            f"<tr><td>{x['ex_date']}</td><td>{num(x['dividend'], 6)}</td>"
            f"<td>{pv(x['pct_principal'])}</td><td>{pv(x['pct_income'])}</td></tr>"
            for x in d["recent"])
        principal_line = (f"有標示來源的 {d['n_with_source']} 次配息中，{d['n_principal']} 次有部分來自本金。"
                          if d["n_with_source"] else "配息來源：資料不足（官方資料未標示）。")
        body = [
            f"<p>本站資料期間（除息日 {d['first_ex']} 到 {d['last_ex']}）共配息 {d['n']} 次，"
            f"每單位合計 {num(d['sum'], 6)} {e(r['currency'])}，約為目前淨值的 {pct(d['sum_pct_of_nav'], 2, False)}。</p>",
            f"<p>{e(principal_line)}</p>",
            '<p class="explain">「來自本金」的意思是：這部分配息其實是把你投入的錢還給你，'
            "不是基金賺來的。配息金額看起來高，不代表有賺錢；要看「含息報酬」才知道。</p>",
            '<table class="tbl"><thead><tr><th>除息日</th><th>每單位配息</th><th>來自本金</th>'
            f"<th>來自可分配收益</th></tr></thead><tbody>{recent}</tbody></table>",
            f'<p class="meta">最近 {len(d["recent"])} 次｜{SRC_OFF}</p>',
        ]
        if r["ret_1y"] is None:
            body.append(f"<p>配息率和含息報酬對照：{insufficient('含息報酬需要至少 1 年的淨值資料')}</p>")
        parts.append('<section><h2>配息真相</h2>' + "".join(body) + "</section>")
    elif r["div_name"] and r["market"] == "domestic":
        parts.append('<section><h2>配息真相</h2><p>' + insufficient(
            "境內基金的配息紀錄沒有開放授權的資料來源，本站無法顯示配息金額與來源") + "</p></section>")

    # 持股
    parts.append('<section><h2>買了哪些公司</h2><p>' + insufficient(
        "持股、產業與國家配置沒有開放授權的資料來源") + "</p></section>")

    # 同基金其他級別 / 名稱相近
    if r["siblings"]:
        items = "".join(f'<li><a href="{e(s)}.html">{e(by_id[s]["name"])}</a>（{e(by_id[s]["currency"])}）</li>'
                        for s in r["siblings"] if s in by_id)
        parts.append(f'<section><h2>同一基金的其他級別</h2><p class="meta">{e(GROUP_NOTE[r["market"]])}</p><ul>{items}</ul></section>')
    if r["lookalikes"]:
        items = "".join(f'<li><a href="{e(s)}.html">{e(by_id[s]["name"])}</a></li>'
                        for s in r["lookalikes"] if s in by_id)
        parts.append('<section class="warn"><h2>注意：名稱相近、但可能是不同基金</h2>'
                     f"<p>下面這些基金名稱和本基金很像，投資內容可能不同，查詢時請確認全名。</p><ul>{items}</ul></section>")
    desc = f"{r['name']}：最新淨值 {num(r['latest_nav'])}（{r['latest_date']}）、配息、風險等級的白話說明。"
    return page(r["name"] or r["class_id"], "".join(parts), depth=1, desc=desc)


# ---------------------------------------------------------------- 匯出

def index_entry(r: dict) -> list:
    """搜尋用的精簡陣列，欄位順序與 search.js 的 F 對應。"""
    return [r["id"], r["name"], r["market"], r["type"] or "", r.get("region_filter") or "", r["currency"],
            r["risk"] or "", r.get("company") or "", 1 if (r["div_name"] or r["has_div_record"]) else 0,
            r["latest_nav"], r["latest_date"], 1 if r["lookalikes"] else 0, 1 if r["hedged"] else 0,
            r.get("ticker") or r.get("isin") or ""]


def fund_json(r: dict) -> dict:
    keep = ["id", "name", "market", "currency", "hedged", "type", "region", "risk", "company",
            "latest_nav", "latest_date", "first_date", "n_nav", "ret_1y", "ret_3y", "ret_5y", "vol",
            "mdd", "tr_available", "source", "base"]
    out = {k: r.get(k) for k in keep}
    out["nav"] = r["_navs"]
    s = r["_series"]
    out["tr"] = [[d, round(v, 8)] for d, v in zip(s.dates, s.index)] if s else None
    if r["div"]:
        out["div"] = {k: r["div"][k] for k in ("n", "first_ex", "last_ex", "sum", "sum_pct_of_nav",
                                              "n_with_source", "n_principal", "avg_principal")}
    else:
        out["div"] = None
    return out


def build_site(curated: pathlib.Path, out: pathlib.Path, generated_at: str | None = None) -> dict:
    data = load(curated)
    recs = []
    for key in sorted(data["meta"]):
        r = build_record(key, data)
        r["_navs"] = data["navs"][key]
        recs.append(r)
    link_names(recs)
    by_id = {r["id"]: r for r in recs}

    if out.exists():
        shutil.rmtree(out)
    (out / "f").mkdir(parents=True)
    (out / "data" / "f").mkdir(parents=True)
    shutil.copytree(ASSET_DIR / "assets", out / "assets")
    for name in ("index.html", "compare.html", "glossary.html", "about.html"):
        body = (ASSET_DIR / name).read_text(encoding="utf-8")
        title = {"index.html": "搜尋基金", "compare.html": "基金比較", "glossary.html": "名詞小辭典",
                 "about.html": "資料來源與使用說明"}[name]
        (out / name).write_text(page(title, body), encoding="utf-8")

    for r in recs:
        (out / "f" / f"{r['id']}.html").write_text(fund_page(r, by_id), encoding="utf-8")
        (out / "data" / "f" / f"{r['id']}.json").write_text(
            json.dumps(fund_json(r), ensure_ascii=False, separators=(",", ":"), default=_json_default),
            encoding="utf-8")

    meta = {
        "generated_at": generated_at or dt.datetime.now(sources.TZ_TAIPEI).isoformat(timespec="minutes"),
        "count": len(recs),
        "latest": {mk: max((r["latest_date"] for r in recs if r["market"] == mk), default=None)
                   for mk in ("offshore", "domestic")},
    }
    (out / "data" / "index.json").write_text(
        json.dumps({"meta": meta, "funds": [index_entry(r) for r in recs]}, ensure_ascii=False,
                   separators=(",", ":"), default=_json_default), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    return meta


def _json_default(o):
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    raise TypeError(type(o))
