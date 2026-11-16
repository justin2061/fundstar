"""命令列：python -m fundstar <fetch|build|rebuild|validate|status>"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import pathlib
import sys

from . import normalize, returns, sources

TABLE_OF = {
    "tdcc_offshore_basic": "funds_offshore",
    "tdcc_offshore_nav": "nav_offshore",
    "tdcc_offshore_div": "div_offshore",
    "fsc_domestic_nav": "nav_domestic",
}
TOLERANCE_PP = 0.05  # 與官方區間報酬的容許誤差（百分點）


def _today() -> dt.date:
    return dt.datetime.now(sources.TZ_TAIPEI).date()


def _ingest(root: pathlib.Path, files: dict[str, pathlib.Path]) -> dict[str, int]:
    from . import store  # duckdb 只在需要時載入
    counts = {}
    for name, path in files.items():
        rows = normalize.PARSERS[name](gzip.decompress(path.read_bytes()))
        counts[TABLE_OF[name]] = store.merge(root / "curated", TABLE_OF[name], rows)
    return counts


def cmd_fetch(a) -> int:
    ok, errors = sources.fetch_all(a.root, today=_today())
    print(json.dumps({"ok": {k: str(v) for k, v in ok.items()}, "errors": errors},
                     ensure_ascii=False, indent=1))
    return 1 if errors else 0


def cmd_build(a) -> int:
    day = dt.date.fromisoformat(a.day) if a.day else _today()
    files = {n: sources.raw_path(a.root, n, day) for n in sources.SOURCES}
    files = {n: p for n, p in files.items() if p.exists()}
    if not files:
        print(f"no raw files for {day}", file=sys.stderr)
        return 1
    print(json.dumps(_ingest(a.root, files), indent=1))
    return 0


def cmd_rebuild(a) -> int:
    """從所有原始檔依日期重建（災難復原用）。"""
    for name in sources.SOURCES:
        for path in sorted((a.root / "raw" / name).glob("*/*.gz")):
            print(path, _ingest(a.root, {name: path}))
    return 0


def _series(con, market: str, class_id: str) -> returns.TRSeries:
    navs = con.execute(f"SELECT date::VARCHAR, nav FROM read_parquet(?) WHERE class_id = ?",
                       [market["nav"], class_id]).fetchall()
    divs = {}
    if market.get("div"):
        divs = dict(con.execute("SELECT ex_date::VARCHAR, dividend FROM read_parquet(?) WHERE class_id = ?",
                                [market["div"], class_id]).fetchall())
    return returns.total_return_index(navs, divs)


def cmd_validate(a) -> int:
    """比對自算含息報酬與官方公布的區間報酬（官方數字只作內部核對，不對外顯示）。

    輸入 CSV 欄位：market,class_id,start,end,official_pct,source,collected_on
    """
    import duckdb
    cur = a.root / "curated"
    markets = {
        "offshore": {"nav": str(cur / "nav_offshore.parquet"), "div": str(cur / "div_offshore.parquet")},
        "domestic": {"nav": str(cur / "nav_domestic.parquet")},
    }
    con = duckdb.connect()
    results, fails = [], 0
    with open(a.official, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            s = _series(con, markets[r["market"]], r["class_id"])
            got = returns.period_return(s, r["start"], r["end"])
            if got is None:
                status, diff = "資料不足", None
            else:
                diff = got * 100 - float(r["official_pct"])
                status = "ok" if abs(diff) <= TOLERANCE_PP else "超出容許誤差"
                fails += status != "ok"
            results.append({**r, "computed_pct": None if got is None else round(got * 100, 4),
                            "diff_pp": None if diff is None else round(diff, 4),
                            "status": status, "warnings": s.warnings})
    print(json.dumps(results, ensure_ascii=False, indent=1))
    checked = sum(1 for x in results if x["diff_pp"] is not None)
    print(f"checked={checked} fail={fails} insufficient={len(results) - checked}", file=sys.stderr)
    return 1 if fails else 0


def cmd_status(a) -> int:
    """寫出 STATUS.json（小檔案，每日提交以維持 repo 活動）。"""
    import duckdb
    cur = a.root / "curated"
    con = duckdb.connect()
    status = {"generated_at": dt.datetime.now(sources.TZ_TAIPEI).isoformat(timespec="seconds"),
              "license": sources.LICENSE, "tables": {}}
    datecol = {"nav_offshore": "date", "nav_domestic": "date", "div_offshore": "ex_date",
               "funds_offshore": "as_of"}
    for t, c in datecol.items():
        p = cur / f"{t}.parquet"
        if p.exists():
            n, k, lo, hi = con.execute(
                f"SELECT count(*), count(DISTINCT class_id), min({c})::VARCHAR, max({c})::VARCHAR "
                f"FROM read_parquet(?)", [str(p)]).fetchone()
            status["tables"][t] = {"rows": n, "classes": k, "min": lo, "max": hi}
    out = a.root / "STATUS.json"
    out.write_text(json.dumps(status, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fundstar")
    p.add_argument("--root", type=pathlib.Path, default=pathlib.Path("data"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    b = sub.add_parser("build"); b.add_argument("--day"); b.set_defaults(fn=cmd_build)
    sub.add_parser("rebuild").set_defaults(fn=cmd_rebuild)
    v = sub.add_parser("validate"); v.add_argument("official"); v.set_defaults(fn=cmd_validate)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    a = p.parse_args(argv)
    return a.fn(a)
