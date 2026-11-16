// 配息真相：各級別配息來源查詢表（全部在瀏覽器計算）
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const norm = (s) => !s ? "" : s.normalize("NFKC").toLowerCase().replace(/證券投資信託/g, "").replace(/基金/g, "")
    .replace(/臺/g, "台").replace(/[\s\-_‧·・.,，、/／()（）\[\]【】「」:：;；*＊]+/g, "");
  const MAX = 100;
  // 欄位：0 id,1 名稱,2 幣別,3 次數,4 有標示,5 含本金次數,6 平均本金%,7 合計占淨值%,8 最近除息日,9 最近一次本金%,10 總代理
  const COLS = [
    ["基金級別", 1, (r) => `<a href="f/${encodeURIComponent(r[0])}.html">${esc(r[1])}</a><span class="why">${esc(r[10])}</span>`],
    ["幣別", 2, (r) => esc(r[2])],
    ["配息次數", 3, (r) => r[3]],
    ["含本金次數", 5, (r) => r[4] ? `${r[5]} / ${r[4]}` : '<span class="na">資料不足</span>'],
    ["平均本金占比", 6, (r) => r[6] == null ? '<span class="na">資料不足</span>' : r[6].toFixed(1) + "%"],
    ["最近一次本金占比", 9, (r) => r[9] == null ? '<span class="na">資料不足</span>' : r[9].toFixed(1) + "%"],
    ["配息合計占淨值", 7, (r) => r[7] == null ? "資料不足" : r[7].toFixed(2) + "%"],
    ["最近除息日", 8, (r) => esc(r[8])],
  ];
  let rows = [], prepared = [], sortCol = 1, asc = true;

  function draw() {
    const q = norm($("dq").value.trim());
    let hit = rows.filter((r, i) => !q || prepared[i].includes(q));
    hit.sort((a, b) => {
      const x = a[sortCol], y = b[sortCol];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      const c = typeof x === "number" ? x - y : String(x).localeCompare(String(y), "zh-Hant");
      return asc ? c : -c;
    });
    $("dcount").textContent = hit.length ? `${hit.length} 個有配息紀錄的級別${hit.length > MAX ? `，顯示前 ${MAX} 個` : ""}` : "找不到符合的級別。";
    const head = COLS.map(([t, idx]) => `<th><a href="#" data-sort="${idx}">${esc(t)}${idx === sortCol ? (asc ? " ▲" : " ▼") : ""}</a></th>`).join("");
    const body = hit.slice(0, MAX).map((r) => `<tr>${COLS.map(([, , fn]) => `<td>${fn(r)}</td>`).join("")}</tr>`).join("");
    $("dtable").innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;
  }
  $("dtable").addEventListener("click", (ev) => {
    const a = ev.target.closest("[data-sort]");
    if (!a) return;
    ev.preventDefault();
    const c = Number(a.dataset.sort);
    asc = c === sortCol ? !asc : true;
    sortCol = c;
    draw();
  });
  let t;
  $("dq").addEventListener("input", () => { clearTimeout(t); t = setTimeout(draw, 120); });
  fetch("data/dividends.json").then((r) => r.json()).then((d) => {
    rows = d.rows;
    prepared = rows.map((r) => norm(r[1]));
    draw();
  }).catch(() => { $("dcount").textContent = "資料載入失敗，請重新整理。"; });
})();
