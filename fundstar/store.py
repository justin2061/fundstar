"""以 DuckDB 合併資料並寫成 Parquet（資料放 GitHub Releases，不進 git 歷史）。"""
from __future__ import annotations

import pathlib

import duckdb

TABLES = {
    # 表名: 主鍵
    "nav_offshore": ["class_id", "date"],
    "nav_domestic": ["class_id", "date"],
    "div_offshore": ["class_id", "ex_date"],
    "funds_offshore": ["class_id"],
    "funds_domestic": ["class_id"],
    "div_domestic": ["class_id", "ex_date"],
    "fees_domestic": ["fund_id", "month"],
}


def merge(curated: pathlib.Path, table: str, rows: list[dict]) -> int:
    """新資料列併入既有 Parquet；主鍵重複時以新資料為準。回傳合併後筆數。"""
    if not rows:
        return -1
    curated.mkdir(parents=True, exist_ok=True)
    out = curated / f"{table}.parquet"
    keys = ", ".join(TABLES[table])
    con = duckdb.connect()
    con.execute("CREATE TABLE new AS SELECT * FROM (SELECT unnest($rows, recursive := true))",
                {"rows": rows})
    con.execute("ALTER TABLE new ADD COLUMN _src INTEGER DEFAULT 1")
    if out.exists():
        con.execute(f"CREATE TABLE old AS SELECT *, 0 AS _src FROM read_parquet('{out.as_posix()}')")
        con.execute("CREATE TABLE allrows AS SELECT * FROM old UNION ALL BY NAME SELECT * FROM new")
    else:
        con.execute("CREATE TABLE allrows AS SELECT * FROM new")
    tmp = out.with_suffix(".tmp.parquet")
    con.execute(f"""
        COPY (
          SELECT * EXCLUDE (_src, _rn) FROM (
            SELECT *, row_number() OVER (PARTITION BY {keys} ORDER BY _src DESC) AS _rn
            FROM allrows)
          WHERE _rn = 1 ORDER BY {keys}
        ) TO '{tmp.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)
    n = con.execute(f"SELECT count(*) FROM read_parquet('{tmp.as_posix()}')").fetchone()[0]
    con.close()
    tmp.replace(out)
    return n
