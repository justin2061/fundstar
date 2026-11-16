// 2～4 檔並排比較。只描述事實，不下判斷。
(function () {
  const MIN_RET = 60; // 相關係數至少需要的共同報酬筆數（與 returns.MIN_POINTS_VOL 一致）
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const NA = (why) => `<span class="na">資料不足</span>${why ? `<span class="why">${esc(why)}</span>` : ""}`;
  const pct = (x, sign = true) => x == null ? null : (sign && x > 0 ? "+" : "") + (x * 100).toFixed(1) + "%";

  const ids = (new URLSearchParams(location.search).get("ids") || "").split(",").filter(Boolean).slice(0, 4);
  if (!ids.length) {
    $("table").innerHTML = '<p>還沒有選擇基金。請到<a href="index.html">搜尋頁</a>勾選 2～4 檔。</p>';
    return;
  }
  Promise.all(ids.map((id) => fetch(`data/f/${encodeURIComponent(id)}.json`).then((r) => r.ok ? r.json() : null)))
    .then((list) => draw(list.filter(Boolean)))
    .catch(() => { $("table").innerHTML = "<p>資料載入失敗，請重新整理。</p>"; });

  function series(f) {
    return f.tr || (f.nav || []).map(([d, v]) => [d, v]);
  }
  function corr(a, b) {
    const ma = new Map(series(a)), mb = new Map(series(b));
    const dates = [...ma.keys()].filter((d) => mb.has(d)).sort();
    const ra = [], rb = [];
    for (let i = 1; i < dates.length; i++) {
      ra.push(ma.get(dates[i]) / ma.get(dates[i - 1]) - 1);
      rb.push(mb.get(dates[i]) / mb.get(dates[i - 1]) - 1);
    }
    if (ra.length < MIN_RET) return { n: ra.length, r: null };
    const m = (x) => x.reduce((s, v) => s + v, 0) / x.length;
    const xa = m(ra), xb = m(rb);
    let num = 0, da = 0, db = 0;
    for (let i = 0; i < ra.length; i++) { num += (ra[i] - xa) * (rb[i] - xb); da += (ra[i] - xa) ** 2; db += (rb[i] - xb) ** 2; }
    return { n: ra.length, r: da && db ? num / Math.sqrt(da * db) : null };
  }

  function draw(fs) {
    if (fs.length < 1) { $("table").innerHTML = "<p>找不到所選基金的資料。</p>"; return; }
    const head = fs.map((f) => `<th><a href="f/${encodeURIComponent(f.id)}.html">${esc(f.name)}</a>
      <br><a href="#" data-rm="${esc(f.id)}" class="meta">移除</a></th>`).join("");
    const hist = (f) => `本站只有 ${f.n_nav} 個淨值日`;
    const rows = [
      ["市場", (f) => f.market === "offshore" ? "境外" : "境內"],
      ["計價幣別", (f) => esc(f.currency) + (f.hedged ? "（避險）" : "")],
      ["類型", (f) => f.type ? esc(f.type) : NA()],
      ["投資區域", (f) => f.region ? esc(f.region) : NA()],
      ["風險等級", (f) => f.risk ? esc(f.risk) : NA()],
      ["最新淨值", (f) => `${esc(f.latest_nav)}<span class="why">${esc(f.latest_date)}</span>`],
      ["資料期間", (f) => `${esc(f.first_date)} ～ ${esc(f.latest_date)}<span class="why">${f.n_nav} 個淨值日</span>`],
      ["近 1 年含息報酬", (f) => !f.tr_available ? NA("沒有開放的配息資料") : f.ret_1y == null ? NA(hist(f)) : `<b>${pct(f.ret_1y)}</b>`],
      ["近 3 年含息報酬", (f) => !f.tr_available ? NA("沒有開放的配息資料") : f.ret_3y == null ? NA(hist(f)) : `<b>${pct(f.ret_3y)}</b>`],
      ["年化波動", (f) => f.vol == null ? NA(hist(f)) : pct(f.vol, false)],
      ["最大回撤", (f) => f.mdd ? `${pct(f.mdd.drawdown)}<span class="why">${esc(f.mdd.peak_date)} → ${esc(f.mdd.trough_date)}</span>` : NA(hist(f))],
      ["配息紀錄", (f) => f.div ? `${f.div.n} 次<span class="why">${f.div.n_with_source ? `標示來源的 ${f.div.n_with_source} 次中，${f.div.n_principal} 次含本金` : "未標示配息來源"}</span>` : (f.market === "domestic" ? NA("境內基金沒有開放的配息資料") : "資料期間內沒有配息")],
      ["持股", () => NA("沒有開放授權的持股資料")],
    ];
    const body = rows.map(([label, fn]) => `<tr><th>${esc(label)}</th>${fs.map((f) => `<td>${fn(f)}</td>`).join("")}</tr>`).join("");
    $("table").innerHTML = `<table class="tbl"><thead><tr><th></th>${head}</tr></thead><tbody>${body}</tbody></table>`;
    $("table").querySelectorAll("[data-rm]").forEach((a) => a.addEventListener("click", (ev) => {
      ev.preventDefault();
      const left = ids.filter((x) => x !== a.dataset.rm);
      location.search = left.length ? "?ids=" + left.map(encodeURIComponent).join(",") : "";
    }));

    const notes = [];
    const curs = [...new Set(fs.map((f) => f.currency))];
    if (curs.length > 1) {
      notes.push(`<div class="warn"><p>這幾檔的計價幣別不同（${curs.map(esc).join("、")}），報酬包含匯率漲跌，不能直接相比。
        可以到各基金頁的「同一基金的其他級別」找相同幣別的級別再比較。</p></div>`);
    }
    if (fs.some((f) => f.hedged) && fs.some((f) => !f.hedged)) {
      notes.push(`<div class="warn"><p>有些是避險級別、有些不是：避險級別會降低匯率影響，但有避險成本，兩者報酬不能直接相比。</p></div>`);
    }
    if (fs.length >= 2) {
      const pairs = [];
      for (let i = 0; i < fs.length; i++) for (let j = i + 1; j < fs.length; j++) pairs.push([fs[i], fs[j], corr(fs[i], fs[j])]);
      const ok = pairs.filter((p) => p[2].r != null);
      if (ok.length) {
        notes.push("<p>" + ok.map(([a, b, c]) => `近 ${c.n} 個共同淨值日，${esc(a.name)} 與 ${esc(b.name)} 的每日漲跌相關係數為 <b>${c.r.toFixed(2)}</b>。`).join("<br>") +
          "<br><span class=\"why\">相關係數越接近 1，代表兩檔過去每天的漲跌越同步。這只描述過去的走勢。</span></p>");
      }
      const short = pairs.filter((p) => p[2].r == null);
      if (short.length) {
        const n = Math.min(...short.map((p) => p[2].n));
        notes.push(`<p>漲跌相關係數：${NA(`共同淨值日的報酬只有 ${n} 筆，至少需要 ${MIN_RET} 筆。本站從 2026-11-16 起每日累積。`)}</p>`);
      }
      notes.push(`<p>共同持股：${NA("沒有開放授權的持股資料，無法比較這幾檔是否買了相同的公司")}</p>`);
    }
    $("summary").innerHTML = notes.join("");
  }
})();
