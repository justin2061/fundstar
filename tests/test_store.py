import duckdb

from fundstar import store


def test_merge_dedupes_and_prefers_new(tmp_path):
    rows1 = [{"market": "offshore", "class_id": "A", "date": "2026-11-09", "nav": 1.0, "currency": "USD"},
             {"market": "offshore", "class_id": "A", "date": "2026-11-10", "nav": 2.0, "currency": "USD"}]
    rows2 = [{"market": "offshore", "class_id": "A", "date": "2026-11-10", "nav": 2.5, "currency": "USD"},
             {"market": "offshore", "class_id": "A", "date": "2026-11-11", "nav": 3.0, "currency": "USD"}]
    assert store.merge(tmp_path, "nav_offshore", rows1) == 2
    assert store.merge(tmp_path, "nav_offshore", rows2) == 3
    got = duckdb.sql(f"SELECT date, nav FROM read_parquet('{tmp_path}/nav_offshore.parquet') ORDER BY date").fetchall()
    assert [g[1] for g in got] == [1.0, 2.5, 3.0]
