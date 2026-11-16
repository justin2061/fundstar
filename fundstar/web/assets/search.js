// 基金搜尋：口語簡稱與錯字容忍（子字串＋雙字重疊），全部在瀏覽器計算。
(function () {
  const F = { id: 0, name: 1, market: 2, type: 3, region: 4, cur: 5, risk: 6, co: 7, div: 8, nav: 9, date: 10, look: 11, hedged: 12, code: 13 };
  const MAX = 60, MAX_CMP = 4;
  const $ = (id) => document.getElementById(id);
  let funds = [], prepared = [], picked = [];

  // 與 fundstar/textutil.py norm() 規則一致
  function norm(s) {
    if (!s) return "";
    s = s.normalize("NFKC").toLowerCase().replace(/證券投資信託/g, "").replace(/基金/g, "").replace(/臺/g, "台");
    return s.replace(/[\s\-_‧·・.,，、/／()（）\[\]【】「」:：;；*＊]+/g, "");
  }
  function grams(s) {
    const g = new Set();
    if (s.length === 1) g.add(s);
    for (let i = 0; i < s.length - 1; i++) g.add(s.slice(i, i + 2));
    return g;
  }
  function score(qn, tokens, p) {
    if (!qn) return 1;
    const n = p.n;
    let i = n.indexOf(qn);
    if (i >= 0) return 1000 - i - n.length * 0.01;
    if (p.code && p.code.startsWith(qn)) return 950;
    if (tokens.length > 1 && tokens.every((t) => n.includes(t))) return 800 - n.length * 0.01;
    const qg = grams(qn);
    let hit = 0;
    qg.forEach((g) => { if (p.g.has(g)) hit++; });
    const ratio = hit / qg.size;
    return ratio >= 0.5 && hit >= 2 ? 500 * ratio - n.length * 0.01 : 0;
  }
  function esc(s) {
    return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  }
  // 篩選選單：數字依「其他已選條件」即時計算，0 筆的選項不顯示（目前選中的除外）
  const FACETS = [["f-type", F.type, "type"], ["f-region", F.region, "region"], ["f-risk", F.risk, "risk"],
    ["f-cur", F.cur, "cur"], ["f-co", F.co, "co"]];
  function facets() {
    const c = filters();
    FACETS.forEach(([selId, idx, key]) => {
      const sel = $(selId), cur = sel.value, others = { ...c, [key]: "" };
      const counts = {};
      funds.forEach((f) => { if (f[idx] && pass(f, others)) counts[f[idx]] = (counts[f[idx]] || 0) + 1; });
      if (cur && !counts[cur]) counts[cur] = 0;
      const first = sel.options[0];
      sel.innerHTML = "";
      sel.appendChild(first);
      Object.keys(counts).sort().forEach((k) => {
        const o = document.createElement("option");
        o.value = k; o.textContent = `${k}（${counts[k]}）`;
        sel.appendChild(o);
      });
      sel.value = cur;
    });
  }
  function filters() {
    return { market: $("f-market").value, type: $("f-type").value, region: $("f-region").value, risk: $("f-risk").value,
      cur: $("f-cur").value, div: $("f-div").value, co: $("f-co").value };
  }
  function pass(f, c) {
    return (!c.market || f[F.market] === c.market) && (!c.type || f[F.type] === c.type) &&
      (!c.region || f[F.region] === c.region) && (!c.risk || f[F.risk] === c.risk) &&
      (!c.cur || f[F.cur] === c.cur) && (c.div === "" || String(f[F.div]) === c.div) && (!c.co || f[F.co] === c.co);
  }
  function render() {
    facets();
    const q = $("q").value.trim();
    const qn = norm(q), tokens = q.split(/\s+/).map(norm).filter(Boolean);
    const c = filters();
    const hits = [];
    for (let i = 0; i < funds.length; i++) {
      const f = funds[i];
      if (!pass(f, c)) continue;
      const s = score(qn, tokens, prepared[i]);
      if (s > 0) hits.push([s, f]);
    }
    hits.sort((a, b) => b[0] - a[0] || a[1][F.name].localeCompare(b[1][F.name], "zh-Hant"));
    $("count").textContent = hits.length
      ? `找到 ${hits.length} 個級別${hits.length > MAX ? `，顯示前 ${MAX} 個` : ""}`
      : "找不到符合的基金。可以試試較短的關鍵字，或放寬篩選條件。";
    $("results").innerHTML = hits.slice(0, MAX).map(([, f]) => {
      const id = f[F.id], on = picked.includes(id);
      const b = [`<span class="badge cur">${esc(f[F.cur])}${f[F.hedged] ? "・避險" : ""}</span>`,
        `<span class="badge">${f[F.market] === "offshore" ? "境外" : "境內"}</span>`];
      if (f[F.type]) b.push(`<span class="badge">${esc(f[F.type])}</span>`);
      if (f[F.region]) b.push(`<span class="badge">${esc(f[F.region])}</span>`);
      if (f[F.risk]) b.push(`<span class="badge">${esc(f[F.risk])}</span>`);
      if (f[F.div]) b.push(`<span class="badge">配息</span>`);
      if (f[F.look]) b.push(`<span class="badge look">名稱相近</span>`);
      return `<div class="result"><input type="checkbox" data-id="${esc(id)}" ${on ? "checked" : ""} aria-label="加入比較">
        <div><a class="name" href="f/${encodeURIComponent(id)}.html">${esc(f[F.name])}</a>
        <div class="badges">${b.join("")}</div>
        <div class="meta">淨值 ${esc(f[F.nav])}（${esc(f[F.date])}）${f[F.co] ? "・" + esc(f[F.co]) : ""}</div></div></div>`;
    }).join("");
  }
  function tray() {
    $("tray").classList.toggle("on", picked.length > 0);
    $("tray-text").textContent = `已選 ${picked.length} 檔（最多 ${MAX_CMP} 檔）`;
    $("tray-go").href = "compare.html?ids=" + picked.map(encodeURIComponent).join(",");
    try { localStorage.setItem("fundstar.picked", JSON.stringify(picked)); } catch (e) { /* 無痕模式 */ }
  }
  let timer;
  $("q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(render, 120); });
  document.querySelectorAll(".filters select").forEach((s) => s.addEventListener("change", render));
  $("results").addEventListener("change", (ev) => {
    const id = ev.target.dataset && ev.target.dataset.id;
    if (!id) return;
    if (ev.target.checked) {
      if (picked.length >= MAX_CMP) { ev.target.checked = false; alertTray(); return; }
      picked.push(id);
    } else picked = picked.filter((x) => x !== id);
    tray();
  });
  function alertTray() { $("tray-text").textContent = `最多比較 ${MAX_CMP} 檔，請先取消其他勾選`; }
  $("tray-clear").addEventListener("click", () => { picked = []; tray(); render(); });

  try { picked = JSON.parse(localStorage.getItem("fundstar.picked") || "[]").slice(0, MAX_CMP); } catch (e) { picked = []; }
  fetch("data/index.json").then((r) => r.json()).then((d) => {
    funds = d.funds;
    prepared = funds.map((f) => { const n = norm(f[F.name]); return { n, g: grams(n), code: norm(f[F.code]) }; });
    const params = new URLSearchParams(location.search);
    if (params.get("q")) $("q").value = params.get("q");
    render(); tray();
    const m = d.meta;
    document.querySelector(".sub").insertAdjacentHTML("beforeend",
      `<br><span class="meta">資料更新：境外 ${esc(m.latest.offshore)}、境內 ${esc(m.latest.domestic)}，共 ${m.count} 個級別</span>`);
  }).catch(() => { $("count").textContent = "資料載入失敗，請重新整理。"; });
})();
