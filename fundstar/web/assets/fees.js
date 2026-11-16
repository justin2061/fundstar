// 費用試算：純計算，使用者自行輸入所有數字。
// 模型：每年先依假設報酬成長，再扣（經理費＋保管費）×年末資產；與「沒有任何費用」比較。
(function () {
  const $ = (id) => document.getElementById(id);
  const fmt = (x) => Math.round(x).toLocaleString("zh-TW");
  const val = (id, lo, hi) => {
    const v = parseFloat($(id).value);
    return Number.isFinite(v) && v >= lo && v <= hi ? v : null;
  };

  function calc(p) {
    const r = p.ret / 100, fee = (p.mgmt + p.cust) / 100;
    const frontFee = p.amount * p.front / 100;
    const invested = p.feeIn ? p.amount - frontFee : p.amount;
    const paid = p.feeIn ? p.amount : p.amount + frontFee; // 你總共拿出的錢
    let v = invested, noFee = paid, annualTotal = 0;
    const rows = [];
    for (let y = 1; y <= p.years; y++) {
      const grown = v * (1 + r);
      const f = grown * fee;
      v = grown - f;
      annualTotal += f;
      noFee *= 1 + r;
      rows.push({ y, v, f, noFee });
    }
    return { frontFee, invested, paid, end: v, noFee, annualTotal, direct: frontFee + annualTotal, lost: noFee - v, rows };
  }

  function draw() {
    const p = {
      amount: val("amount", 1, 1e12), years: val("years", 1, 50), front: val("front", 0, 10),
      mgmt: val("mgmt", 0, 10), cust: val("cust", 0, 5), ret: val("ret", -50, 50), feeIn: $("feeIn").checked,
    };
    const bad = Object.entries(p).filter(([, v]) => v === null).map(([k]) => k);
    if (bad.length) {
      $("feeout").innerHTML = '<p class="na">請確認輸入：金額要大於 0、年數 1～50、費率 0～10%、報酬 -50%～50%。</p>';
      return;
    }
    p.years = Math.round(p.years);
    const c = calc(p);
    const perYear100k = 100000 * (p.mgmt + p.cust) / 100;
    const share = c.lost / (c.noFee || 1);
    $("feeout").innerHTML = `
      <section><h2>結果</h2>
      <p class="big">${p.years} 年下來，費用讓你少了大約 <b>${fmt(c.lost)} 元</b>。</p>
      <div class="row"><div class="label">直接付掉的費用</div><div class="value"><b>${fmt(c.direct)} 元</b></div>
        <div class="explain">申購手續費 ${fmt(c.frontFee)} 元＋經理費與保管費累計 ${fmt(c.annualTotal)} 元。</div></div>
      <div class="row"><div class="label">少賺的錢</div><div class="value"><b>${fmt(c.lost)} 元</b></div>
        <div class="explain">和「完全沒有費用」相比少了多少，包含被扣掉的錢沒辦法繼續滾的部分。約占沒有費用時資產的 ${(share * 100).toFixed(1)}%。</div></div>
      <div class="row"><div class="label">期末資產</div><div class="value">${fmt(c.end)} 元</div>
        <div class="explain">你總共拿出 ${fmt(c.paid)} 元；若完全沒有費用，期末會是 ${fmt(c.noFee)} 元。</div></div>
      <div class="row"><div class="label">換個方式看</div><div class="value">每 10 萬元一年約 ${fmt(perYear100k)} 元</div>
        <div class="explain">經理費加保管費 ${(p.mgmt + p.cust).toFixed(2)}%，以 10 萬元資產計算的一年費用。</div></div>
      </section>
      <section><h2>逐年明細</h2><div class="cmp"><table class="tbl"><thead><tr><th>第幾年</th><th>當年經理費＋保管費</th><th>年末資產</th><th>沒有費用時</th></tr></thead><tbody>
      ${c.rows.map((x) => `<tr><td>${x.y}</td><td>${fmt(x.f)}</td><td>${fmt(x.v)}</td><td>${fmt(x.noFee)}</td></tr>`).join("")}
      </tbody></table></div><p class="meta">假設每年報酬 ${p.ret}%（自行假設，不是預測）。數字四捨五入到元。</p></section>`;
  }
  $("fee").addEventListener("input", draw);
  draw();
  window.__feeCalc = calc; // 測試用
})();
