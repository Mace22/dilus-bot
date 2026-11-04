"use strict";
/* ============================================================
   Juegos del panel: ruleta, blackjack y tragamonedas.
   Las reglas y los pagos los decide siempre el servidor; acá solo se anima y se suena.
   ============================================================ */

/* ---------- ayudas compartidas ---------- */
const CHIPS = [10, 50, 100, 500, 1000, 5000];
const tierOf = amount => [...CHIPS].reverse().find(v => v <= amount) || 10;
const centerOf = el => { const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; };
const smooth = x => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };

/* una ficha que vuela de un elemento a otro (con un arco y girando) */
function flyChip(fromEl, toEl, amount, { duration = 460, size = 34, scaleEnd = 0.8, fade = false, delay = 0, onEnd } = {}) {
  if (!fromEl || !toEl || !fromEl.isConnected || !toEl.isConnected) { if (onEnd) onEnd(); return; }
  const a = centerOf(fromEl), b = centerOf(toEl);
  const el = h("div", { class: `chip fly c${tierOf(amount)}`, text: short(amount), style: {
    position: "fixed", left: `${a.x - size / 2}px`, top: `${a.y - size / 2}px`, width: `${size}px`, height: `${size}px`, fontSize: "10px", margin: "0", zIndex: "170", pointerEvents: "none" } });
  document.body.append(el);
  const dx = b.x - a.x, dy = b.y - a.y;
  const anim = el.animate([
    { transform: "translate(0,0) scale(1.25) rotate(0deg)", opacity: 0.0 },
    { transform: "translate(0,0) scale(1.25) rotate(0deg)", opacity: 1, offset: 0.08 },
    { transform: `translate(${dx * 0.5}px, ${dy * 0.5 - 46}px) scale(1.05) rotate(180deg)`, opacity: 1, offset: 0.55 },
    { transform: `translate(${dx}px, ${dy}px) scale(${scaleEnd}) rotate(360deg)`, opacity: fade ? 0 : 1 },
  ], { duration, delay, easing: "cubic-bezier(.3,.7,.35,1)", fill: "backwards" });
  anim.onfinish = () => { el.remove(); if (onEnd) onEnd(); };
  anim.oncancel = () => el.remove();
}
function floatText(host, text, cls = "zfloat") {
  const f = h("div", { class: cls, text });
  host.append(f);
  setTimeout(() => f.remove(), 1500);
}
function chipRack(values, current, onPick) {
  const els = values.map(v => h("button", { class: `chip c${v} ${v === current ? "sel" : ""}`, "data-silent": "1", "aria-label": `Ficha de ${v}`, text: short(v),
    onclick: () => { els.forEach(e => e.classList.toggle("sel", e === els[values.indexOf(v)])); Sfx.chip(); onPick(v); } }));
  return els;
}
const howBox = items => h("details", { class: "how card" }, h("summary", {}, icon("help"), "¿Cómo se juega? (guía rápida)"),
  h("div", { class: "how-grid" }, items.map(([t, text]) => h("div", {}, h("b", { text: t }), text))));

/* ============================================================
   RULETA
   ============================================================ */
const RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);
const ORDER = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26];
const STEP = 360 / 37;
const colorOf = n => (n === 0 ? "green" : RED.has(n) ? "red" : "black");
const BETS = {
  red: { label: "Rojo", ratio: 1, count: 18, hint: "Salen los 18 números rojos" },
  black: { label: "Negro", ratio: 1, count: 18, hint: "Salen los 18 números negros" },
  even: { label: "Par", ratio: 1, count: 18, hint: "Números pares (el 0 no cuenta)" },
  odd: { label: "Impar", ratio: 1, count: 18, hint: "Números impares" },
  low: { label: "1-18", ratio: 1, count: 18, hint: "Del 1 al 18" },
  high: { label: "19-36", ratio: 1, count: 18, hint: "Del 19 al 36" },
  doc1: { label: "1ª docena", ratio: 2, count: 12, hint: "Del 1 al 12" },
  doc2: { label: "2ª docena", ratio: 2, count: 12, hint: "Del 13 al 24" },
  doc3: { label: "3ª docena", ratio: 2, count: 12, hint: "Del 25 al 36" },
  col1: { label: "Columna 1", ratio: 2, count: 12, hint: "1, 4, 7 … 34" },
  col2: { label: "Columna 2", ratio: 2, count: 12, hint: "2, 5, 8 … 35" },
  col3: { label: "Columna 3", ratio: 2, count: 12, hint: "3, 6, 9 … 36" },
};
const betInfo = key => key[0] === "n" ? { label: `Número ${key.slice(1)}`, ratio: 35, count: 1, hint: `Solo gana si sale el ${key.slice(1)}` } : BETS[key];
function wins(key, n) {
  if (key[0] === "n") return n === +key.slice(1);
  if (n === 0) return false;
  switch (key) {
    case "red": return RED.has(n); case "black": return !RED.has(n);
    case "even": return n % 2 === 0; case "odd": return n % 2 === 1;
    case "low": return n <= 18; case "high": return n >= 19;
    case "doc1": return n <= 12; case "doc2": return n >= 13 && n <= 24; case "doc3": return n >= 25;
    case "col1": return n % 3 === 1; case "col2": return n % 3 === 2; case "col3": return n % 3 === 0;
  }
  return false;
}

/* --- rueda dibujada en canvas --- */
function drawWheelBase(px) {
  const c = document.createElement("canvas"); c.width = c.height = px;
  const g = c.getContext("2d"), cx = px / 2, R = px / 2 - 2;
  const circle = (r, fill, stroke, lw) => {
    g.beginPath(); g.arc(cx, cx, r, 0, Math.PI * 2);
    if (fill) { g.fillStyle = fill; g.fill(); }
    if (stroke) { g.strokeStyle = stroke; g.lineWidth = lw; g.stroke(); }
  };
  let grad = g.createRadialGradient(cx, cx * 0.8, R * 0.2, cx, cx, R); grad.addColorStop(0, "#7a4a2a"); grad.addColorStop(1, "#2b160b");
  circle(R, grad); circle(R * 0.965, "#5a3320"); circle(R * 0.945, null, "#e8c35a", px * 0.006);
  circle(R * 0.92, "#14151b"); circle(R * 0.88, null, "#464b5a", px * 0.003); circle(R * 0.80, "#aa965a");
  const rOut = R * 0.79, rIn = R * 0.56;
  ORDER.forEach((n, i) => {
    const a0 = (i * STEP - 90 - STEP / 2) * Math.PI / 180, a1 = a0 + STEP * Math.PI / 180;
    g.beginPath(); g.arc(cx, cx, rOut, a0, a1); g.arc(cx, cx, rIn, a1, a0, true); g.closePath();
    g.fillStyle = n === 0 ? "#0f7a4a" : RED.has(n) ? "#b91c2f" : "#15151d"; g.fill();
    g.strokeStyle = "#cdbe8c"; g.lineWidth = px * 0.0025; g.stroke();
  });
  circle(rIn, "#c8a546"); circle(rIn * 0.95, "#28190f");
  grad = g.createRadialGradient(cx * 0.95, cx * 0.9, 2, cx, cx, rIn * 0.55); grad.addColorStop(0, "#9a6a3f"); grad.addColorStop(1, "#4a2e1a");
  circle(rIn * 0.55, grad, "#e8c35a", px * 0.006);
  g.strokeStyle = "#e8c35a"; g.lineWidth = px * 0.012; g.lineCap = "round";
  for (let k = 0; k < 4; k++) { const a = k * Math.PI / 2; g.beginPath(); g.moveTo(cx, cx); g.lineTo(cx + rIn * 0.55 * Math.cos(a), cx + rIn * 0.55 * Math.sin(a)); g.stroke(); }
  circle(rIn * 0.14, "#f4e4a0", "#e8c35a", px * 0.003);
  g.fillStyle = "#fff"; g.font = `700 ${Math.round(px * 0.047)}px Outfit, Inter, sans-serif`; g.textAlign = "center"; g.textBaseline = "middle";
  ORDER.forEach((n, i) => { g.save(); g.translate(cx, cx); g.rotate((i * STEP - 90) * Math.PI / 180); g.translate(R * 0.675, 0); g.fillText(String(n), 0, 0); g.restore(); });
  return c;
}

function createWheel(canvas, size) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2), px = Math.round(size * dpr);
  canvas.width = canvas.height = px;
  const ctx = canvas.getContext("2d"), base = drawWheelBase(px), half = px / 2 - 2;
  const rTrack = half * 0.855, rPocket = half * 0.675, br = px * 0.017;
  let rot = Math.random() * 360, phi = null, ballR = rPocket, raf = 0, last = performance.now(), spinning = false, dead = false, trail = [];

  function render() {
    ctx.clearRect(0, 0, px, px);
    ctx.save(); ctx.translate(px / 2, px / 2); ctx.rotate(-rot * Math.PI / 180); ctx.drawImage(base, -px / 2, -px / 2); ctx.restore();
    if (phi == null) return;
    const th = (rot + phi) * Math.PI / 180, x = px / 2 + ballR * Math.cos(th), y = px / 2 - ballR * Math.sin(th);
    if (spinning) { trail.push({ x, y }); if (trail.length > 14) trail.shift(); } else trail.length = 0;
    trail.forEach((p, i) => {                                   // estela de la bola
      const k = i / trail.length;
      ctx.beginPath(); ctx.arc(p.x, p.y, br * (0.3 + 0.6 * k), 0, Math.PI * 2); ctx.fillStyle = `rgba(255,255,255,${(k * 0.3).toFixed(3)})`; ctx.fill();
    });
    ctx.beginPath(); ctx.arc(x + br * 0.3, y + br * 0.45, br, 0, Math.PI * 2); ctx.fillStyle = "rgba(0,0,0,.4)"; ctx.fill();
    const gr = ctx.createRadialGradient(x - br * 0.35, y - br * 0.35, br * 0.1, x, y, br); gr.addColorStop(0, "#fff"); gr.addColorStop(1, "#bfc3d0");
    ctx.beginPath(); ctx.arc(x, y, br, 0, Math.PI * 2); ctx.fillStyle = gr; ctx.fill();
  }
  function loop(t) {
    if (dead) return;
    if (!spinning) rot += (t - last) / 1000 * 4;               // gira despacito mientras espera
    last = t; render(); raf = requestAnimationFrame(loop);
  }
  raf = requestAnimationFrame(loop);

  return {
    destroy() { dead = true; cancelAnimationFrame(raf); },
    spinTo(number, ms = 6500, hooks = {}) {
      return new Promise(resolve => {
        spinning = true; trail = [];
        const pocket = 90 - ORDER.indexOf(number) * STEP, w0 = rot, lapsW = 0.6, lapsB = 3.6, t0 = performance.now();
        let lastK = null, lastTick = 0, dropped = false;
        const step = t => {
          if (dead) return resolve();
          const u = Math.min(1, (t - t0) / ms), p = 1 - Math.pow(1 - u, 3);
          rot = w0 + 360 * lapsW * p;
          phi = pocket + 360 * lapsB * (1 - p);
          const s = smooth((u - 0.60) / 0.34);
          ballR = rTrack + (rPocket - rTrack) * s;
          if (u > 0.60 && u < 0.97) ballR += Math.abs(Math.sin((u - 0.60) * 26)) * Math.pow(1 - s, 2) * half * 0.07;
          const k = Math.floor((90 - phi + STEP / 2) / STEP);   // casillero que está pisando la bola
          if (lastK !== null && k !== lastK && t - lastTick > 42 && u < 0.97) {
            lastTick = t;
            if (hooks.tick) hooks.tick(Math.min(1, 360 * lapsB * 3 * Math.pow(1 - u, 2) / (ms / 1000) / 500));
          }
          lastK = k;
          if (!dropped && u > 0.88) { dropped = true; if (hooks.drop) hooks.drop(); }
          if (u < 1) requestAnimationFrame(step); else { phi = pocket; ballR = rPocket; spinning = false; resolve(); }
        };
        requestAnimationFrame(step);
      });
    },
  };
}

/* --- tablero --- */
function buildBoard(onPick, onInfo) {
  const zones = new Map();
  const mk = (key, cls, grid, ...kids) => {
    const el = h("button", { class: `zone ${cls}`, dataset: { key }, style: grid, "data-silent": "1", "aria-label": betInfo(key).label,
      onclick: () => onPick(key), onmouseenter: () => onInfo(key), onfocus: () => onInfo(key), oncontextmenu: e => { e.preventDefault(); onPick(key, true); } }, ...kids);
    zones.set(key, el); return el;
  };
  const cells = [mk("n0", "green", { gridRow: "1 / 4", gridColumn: "1" }, "0")];
  for (let n = 1; n <= 36; n++) {
    const c = Math.floor((n - 1) / 3), r = 2 - (n - 1) % 3;
    cells.push(mk(`n${n}`, colorOf(n), { gridColumn: String(2 + c), gridRow: String(1 + r) }, String(n)));
  }
  [3, 2, 1].forEach((k, r) => cells.push(mk(`col${k}`, "out", { gridColumn: "14", gridRow: String(1 + r) }, "2:1")));
  [1, 2, 3].forEach(k => cells.push(mk(`doc${k}`, "out wide", { gridColumn: `${2 + (k - 1) * 4} / span 4`, gridRow: "4" }, `${k}ª docena`)));
  [["low", "1-18"], ["even", "PAR"], ["red", null], ["black", null], ["odd", "IMPAR"], ["high", "19-36"]].forEach(([key, label], i) =>
    cells.push(mk(key, "out wide", { gridColumn: `${2 + i * 2} / span 2`, gridRow: "5" }, label || h("span", { class: `dia ${key}` }))));
  return { el: h("div", { class: "board" }, cells), zones };
}

VIEWS.ruleta = async (root, token) => {
  const lim = S.profile.limits;
  const chipVals = CHIPS.filter(v => v >= lim.rl_min && v <= lim.rl_max);
  const st = { chip: chipVals.includes(100) ? 100 : chipVals[0], bets: [], last: [], busy: false };
  let hist = [];
  try { hist = (await gget("/api/roulette/history")).history; } catch { /* sin historial */ }
  if (!alive(token)) return;

  const canvas = h("canvas"), pop = h("div", { class: "wheel-pop" }), histEl = h("div", { class: "hist" });
  const wheelBox = h("div", { class: "wheel-box" }, canvas, pop);
  const wheel = createWheel(canvas, 400);
  S.cleanups.push(() => wheel.destroy());
  const paintHistory = () => histEl.replaceChildren(...(hist.length ? hist.slice(-12).map(n => h("i", { class: colorOf(n), text: String(n) }))
    : [h("span", { class: "note", text: "Todavía no salió ningún número" })]));
  paintHistory();

  const infoBar = h("div", { class: "info-bar" }, "👆 Tocá una zona del tablero para apostar. Pasá el mouse (o tocá) para ver cuánto paga y qué chances tiene.");
  const showInfo = (key, amount = st.chip) => {
    const b = betInfo(key);
    infoBar.replaceChildren(h("b", { text: b.label }), h("span", { text: `paga ${b.ratio} a 1` }), h("span", { class: "muted", text: `· ${pct(b.count)} de chances (${b.count} de 37)` }),
      h("span", { class: "muted", text: `· ${b.hint}` }), h("span", { class: "gold", text: `· con ${fmt(amount)} cobrás ${fmt(amount * (b.ratio + 1))}` }));
  };

  const totals = () => { const m = new Map(); st.bets.forEach(b => m.set(b.key, (m.get(b.key) || 0) + b.amount)); return m; };
  const totalBet = () => st.bets.reduce((a, b) => a + b.amount, 0);
  const resultBox = h("div");
  const clearHighlight = () => { board.el.classList.remove("dim"); board.zones.forEach(z => z.classList.remove("win")); resultBox.replaceChildren(); pop.replaceChildren(); };

  const totalEl = h("b", { text: "0" }), zonesEl = h("span", { text: "0" });
  const spinBtn = h("button", { class: "btn btn-gold btn-lg", "data-silent": "1", onclick: spin }, icon("wheel"), "GIRAR");
  const undoBtn = h("button", { class: "btn btn-ghost btn-sm", onclick: () => { clearHighlight(); st.bets.pop(); Sfx.chip(); paintStacks(); refresh(); } }, icon("undo"), "Deshacer");
  const clearBtn = h("button", { class: "btn btn-ghost btn-sm", onclick: () => { clearHighlight(); st.bets = []; Sfx.chips(3); paintStacks(); refresh(); } }, icon("trash"), "Limpiar");
  const repeatBtn = h("button", { class: "btn btn-ghost btn-sm", onclick: () => { clearHighlight(); st.bets = st.last.map(b => ({ ...b })); fitToBalance(); Sfx.chips(4); paintStacks(); refresh(); } }, icon("refresh"), "Repetir");
  const doubleBtn = h("button", { class: "btn btn-ghost btn-sm", text: "×2", onclick: () => { clearHighlight(); st.bets.push(...st.bets.map(b => ({ ...b }))); fitToBalance(); Sfx.chips(4); paintStacks(); refresh(); } });

  function fitToBalance() {           // si no alcanza el saldo, se recortan las últimas fichas
    while (st.bets.length && totalBet() > S.profile.balance) { st.bets.pop(); toast("Quité fichas: no te alcanzaba el saldo.", "err"); }
  }
  function paintStacks() {
    const t = totals();
    board.zones.forEach((el, key) => {
      const v = t.get(key) || 0; let s = el.querySelector(".stack");
      if (v) { if (!s) { s = h("span", { class: "stack" }); el.append(s); } s.className = "stack"; s.textContent = short(v); } else if (s) s.remove();
    });
  }
  function refresh() {
    const t = totals();
    totalEl.textContent = fmt(totalBet()); zonesEl.textContent = String(t.size);
    spinBtn.disabled = st.busy || !st.bets.length;
    undoBtn.disabled = clearBtn.disabled = doubleBtn.disabled = st.busy || !st.bets.length;
    repeatBtn.disabled = st.busy || !st.last.length;
    allinBtn.disabled = st.busy;
  }
  function pick(key, remove = false) {
    if (st.busy) return;
    clearHighlight();
    if (remove) { st.bets = st.bets.filter(b => b.key !== key); Sfx.chip(); paintStacks(); return refresh(); }
    const t = totals(), cur = t.get(key) || 0;
    const allIn = st.allin, amount = allIn ? S.profile.balance - totalBet() : st.chip;      // all in = todo lo que te queda
    if (allIn && amount < lim.rl_min) return toast(`No te queda saldo para apostar (mínimo ${fmt(lim.rl_min)}).`, "err");
    if (cur + amount > lim.rl_max) return toast(`Máximo ${fmt(lim.rl_max)} por zona.`, "err");
    if (totalBet() + amount > S.profile.balance) return toast("No te alcanza el saldo para esa ficha.", "err");
    if (!t.has(key) && t.size >= 30) return toast("Máximo 30 zonas por tirada.", "err");
    st.bets.push({ key, amount }); showInfo(key, amount); refresh();
    Sfx.chip();
    flyChip(allIn ? allinBtn : chipEls[chipVals.indexOf(st.chip)], board.zones.get(key), amount, { duration: 380, onEnd: paintStacks });
    if (allIn) setAllin(false);                    // el all in se usa una sola vez
  }
  const board = buildBoard(pick, showInfo);
  const chipEls = chipRack(chipVals, st.chip, v => { st.chip = v; setAllin(false, false); });
  const allinBtn = h("button", { class: "btn btn-gold btn-sm btn-allin", "data-silent": "1", title: "Apostar todo tu saldo en la próxima zona que toques", text: "🔥 ALL IN",
    onclick: () => { if (st.busy) return; if (S.profile.balance - totalBet() < lim.rl_min) return toast(`No te queda saldo para apostar (mínimo ${fmt(lim.rl_min)}).`, "err"); Sfx.chip(); setAllin(!st.allin); } });
  function setAllin(on, restoreChip = true) {      // activa/desactiva el modo all in y deja marcada la ficha que corresponde
    st.allin = on; allinBtn.classList.toggle("sel", on);
    if (on) chipEls.forEach(e => e.classList.remove("sel"));
    else if (restoreChip) chipEls.forEach((e, i) => e.classList.toggle("sel", chipVals[i] === st.chip));
  }

  async function spin() {
    if (st.busy || !st.bets.length) return;
    st.busy = true; refresh(); clearHighlight();
    const merged = [...totals()].map(([key, amount]) => ({ key, amount })), total = totalBet(), before = S.profile.balance;
    setBalance(before - total);
    Sfx.spinStart();
    let r;
    try { r = await gpost("/api/roulette/spin", { bets: merged }); }
    catch (e) { toast(e.message, "err"); setBalance(before); st.busy = false; refresh(); return; }
    wheelBox.classList.add("spinning");
    pop.replaceChildren(h("div", { class: "nomas", text: "¡NO VA MÁS!" }));
    Sfx.whirr(5600);
    await wheel.spinTo(r.number, 6500, { tick: p => Sfx.tick(p), drop: () => Sfx.drop() });
    wheelBox.classList.remove("spinning");
    if (!alive(token)) return;

    /* resultado */
    hist = r.history; paintHistory();
    pop.replaceChildren(h("div", { class: `num ${r.color}`, text: String(r.number) }));
    board.el.classList.add("dim");
    const byKey = new Map(r.results.map(x => [x.key, x]));
    board.zones.forEach((z, key) => {
      z.classList.toggle("win", wins(key, r.number));
      const sk = z.querySelector(".stack"), x = byKey.get(key);
      if (!sk || !x) return;
      if (x.won) { sk.classList.add("won"); floatText(z, `+${fmt(x.payout - x.amount)}`); } else sk.classList.add("lost");
    });
    st.last = merged;
    const net = r.net;
    if (net > 0) {
      const big = net >= Math.max(3000, total * 8);
      Sfx.win(net >= total * 4); Fx.at(canvas, "confetti", big ? 160 : 90, big ? 1.25 : 1);
      if (big) { Fx.rain(70); Sfx.coins(14); }
    } else if (net < 0) Sfx.lose(); else Sfx.push();
    setBalance(r.balance);
    resultBox.replaceChildren(h("div", { class: "result-panel" },
      h("h3", {}, `Salió el ${r.number} `, h("span", { class: "muted", text: `· ${r.tags.join(" · ")}` })),
      h("p", { class: net >= 0 ? "pos" : "neg", style: { fontWeight: "700", marginTop: "4px", fontSize: "18px" },
        text: net > 0 ? `¡Ganaste +${fmt(net)} monedas! 🎉` : net === 0 ? "Recuperaste lo apostado." : `Perdiste ${fmt(-net)} monedas.` }),
      h("div", { class: "rows" }, r.results.map(x => h("div", { class: `r ${x.won ? "w" : ""}` },
        h("span", { text: `${x.label} · ${fmt(x.amount)}` }), h("b", { class: x.won ? "pos" : "muted", text: x.won ? `+${fmt(x.payout - x.amount)}` : `−${fmt(x.amount)}` }))))));
    await sleep(2100);                              // se ven las fichas ganar o irse
    if (!alive(token)) return;
    st.bets = []; paintStacks(); st.busy = false; refresh();
  }

  refresh();
  root.replaceChildren(sectionTitle("Ruleta europea", "Un solo cero, mismas reglas y pagos que el comando /ruleta del servidor."),
    h("div", { class: "rl" },
      h("div", { class: "card wheel-card" }, wheelBox, h("div", { class: "hist-label", text: "Últimos números" }), histEl),
      h("div", {},
        h("div", { class: "felt" }, h("div", { class: "board-wrap" }, board.el), infoBar),
        h("div", { class: "rl-actions" },
          h("div", { class: "left" }, h("div", { class: "chips" }, chipEls, allinBtn), h("div", { class: "chips" }, undoBtn, clearBtn, repeatBtn, doubleBtn)),
          h("div", { style: { display: "flex", flexDirection: "column", gap: "10px", alignItems: "flex-end" } },
            h("div", { class: "rl-total" }, "Apuesta total: ", totalEl, " · zonas: ", zonesEl), spinBtn)),
        resultBox)),
    howBox([
      ["1 · Elegí tu ficha", "Tocá una ficha y después las zonas del tablero donde querés apostar. Podés poner varias. Clic derecho en una zona la quita."],
      ["2 · Mirá los pagos", "Rojo/Negro, Par/Impar y 1-18/19-36 pagan 1 a 1. Docenas y columnas pagan 2 a 1. Un número pleno paga 35 a 1."],
      ["3 · ¡Girá!", "El 0 es verde: solo gana quien apostó a ese número. La casa tiene 2,7% de ventaja, así que jugá por diversión."]]));
};

/* ============================================================
   BLACKJACK
   ============================================================ */
const OUT = {
  blackjack: { t: "¡BLACKJACK!", cls: "bj" }, win: { t: "¡GANASTE!", cls: "win" }, dealer_bust: { t: "EL DEALER SE PASÓ", cls: "win" },
  lose: { t: "PERDISTE", cls: "lose" }, bust: { t: "TE PASASTE", cls: "lose" }, dealer_blackjack: { t: "BLACKJACK DEL DEALER", cls: "lose" }, push: { t: "EMPATE", cls: "push" },
};
function handValue(cards) {
  let total = 0, aces = 0;
  for (const c of cards) { if (!c) continue; const r = c[0]; if (r === "A") { total += 11; aces++; } else total += "JQK".includes(r) ? 10 : +r; }
  while (total > 21 && aces) { total -= 10; aces--; }
  return total;
}
function setFace(el, data) {                       // dibuja el frente de la carta
  const front = el.querySelector(".front");
  front.replaceChildren();
  front.classList.toggle("red", !!data && (data[1] === "♥" || data[1] === "♦"));
  if (!data) return;
  front.append(h("div", { class: "tl" }, data[0], h("small", { text: data[1] })), h("div", { class: "mid", text: data[1] }), h("div", { class: "br" }, data[0], h("small", { text: data[1] })));
}
function pcardEl(data) {                           // carta 3D: se crea boca abajo y se da vuelta con la clase "down"
  const el = h("div", { class: "pcard down" }, h("div", { class: "pc-in" }, h("div", { class: "pc-f front" }), h("div", { class: "pc-f back" })));
  setFace(el, data);
  return el;
}

VIEWS.blackjack = async (root, token) => {
  const lim = S.profile.limits;
  const chipVals = CHIPS.filter(v => v >= lim.bj_min && v <= lim.bj_max);
  const st = { bet: chipVals.includes(100) ? 100 : chipVals[0], game: null, busy: false, finished: false, spotAmount: 0 };
  const data = await gget("/api/blackjack");
  if (!alive(token)) return;
  setBalance(data.balance, false);

  const dealerHand = h("div", { class: "hand" }), playerHand = h("div", { class: "hand" });
  const dealerVal = h("span", { class: "val hide" }), playerVal = h("span", { class: "val hide" });
  const shoe = h("div", { class: "shoe" }, h("i"), h("i"), h("i"));
  const spotStack = h("div", { class: "spot-stack" }), spotAmt = h("small", { class: "spot-amt" });
  const spot = h("div", { class: "spot" }, h("div", { class: "spot-ring" }, spotStack), spotAmt);
  const mid = h("div", { class: "bj-mid" });
  const table = h("div", { class: "bj-table" }, shoe,
    h("div", { class: "seat" }, h("div", { class: "seat-label" }, "Dealer", dealerVal), dealerHand), mid,
    h("div", { class: "seat" }, h("div", { class: "seat-label" }, "Tu mano", playerVal), playerHand), spot);
  const controls = h("div", { class: "bj-controls" });

  const setVal = (el, v, bust) => {
    const prev = el.textContent;
    el.textContent = v == null ? "" : String(v);
    el.classList.toggle("bust", !!bust); el.classList.toggle("hide", v == null);
    if (v != null && String(v) !== prev) { el.classList.remove("pop"); void el.offsetWidth; el.classList.add("pop"); }
  };

  /* reparte una carta desde el mazo (con arco, giro y sonido) */
  async function dealCard(hand, data, { down = false, instant = false } = {}) {
    const el = pcardEl(data);
    const before = [...hand.children].map(c => c.getBoundingClientRect().left);
    hand.append(el);
    [...hand.children].slice(0, -1).forEach((c, i) => {      // las cartas que ya estaban se acomodan suavemente
      const dx = before[i] - c.getBoundingClientRect().left;
      if (Math.abs(dx) > 1) c.animate([{ transform: `translateX(${dx}px)` }, { transform: "none" }], { duration: 340, easing: "cubic-bezier(.3,.7,.3,1)" });
    });
    if (instant) { if (!down) el.classList.remove("down"); return el; }
    const a = centerOf(shoe), b = centerOf(el);
    Sfx.deal();
    const anim = el.animate([
      { transform: `translate(${a.x - b.x}px, ${a.y - b.y}px) rotate(-24deg) scale(.55)`, opacity: 0 },
      { opacity: 1, offset: 0.18 }, { transform: "none", opacity: 1 }],
    { duration: 520, easing: "cubic-bezier(.2,.8,.25,1)", fill: "backwards" });
    await anim.finished.catch(() => {});
    if (!down) { await sleep(70); el.classList.remove("down"); Sfx.flip(); await sleep(420); }
    return el;
  }
  async function syncPlayer(cards) {
    while (playerHand.children.length < cards.length) { await dealCard(playerHand, cards[playerHand.children.length]); if (!alive(token)) return; }
    setVal(playerVal, handValue(cards), handValue(cards) > 21);
  }
  function clearTable() {
    dealerHand.replaceChildren(); playerHand.replaceChildren(); mid.replaceChildren(); spotStack.replaceChildren(); spotAmt.textContent = "";
    setVal(dealerVal, null); setVal(playerVal, null); st.spotAmount = 0;
  }
  const showSpot = amount => {
    st.spotAmount = amount;
    spotStack.replaceChildren(h("div", { class: `chip big c${tierOf(amount)}`, text: short(amount) }));
    spotAmt.textContent = `${fmt(amount)} 🪙`;
  };
  function placeBet(amount, fromEl) {
    Sfx.chips(2);
    if (st.spotAmount && st.spotAmount !== amount) spotStack.replaceChildren();
    flyChip(fromEl, spot.querySelector(".spot-ring"), amount, { duration: 420, size: 40, scaleEnd: 1.1, onEnd: () => showSpot(amount) });
  }
  function settleChips(kind) {                    // las fichas se van con quien corresponde
    const chip = spotStack.firstChild; if (!chip) return;
    const amt = st.spotAmount;
    if (kind === "win") {
      Sfx.coins(8);
      [0, 110, 220].forEach(d => flyChip(chip, $(".bal-chip"), amt, { duration: 760, size: 36, delay: d, fade: true }));
    } else if (kind === "lose") flyChip(chip, dealerHand, amt, { duration: 700, size: 40, fade: true });
    else flyChip(chip, controls, amt, { duration: 600, size: 36, fade: true });
    setTimeout(() => { spotStack.replaceChildren(); spotAmt.textContent = ""; }, 140);
  }

  async function reveal(g) {                      // fin de la mano: el dealer da vuelta su carta y juega
    st.busy = true; renderControls();
    await syncPlayer(g.player);
    if (!alive(token)) return;
    const d = g.dealer, hole = dealerHand.children[1];
    await sleep(g.player.length > 2 ? 500 : 800);
    if (!alive(token) || !hole) return;
    setFace(hole, d[1]); hole.classList.remove("down"); Sfx.flip(); setVal(dealerVal, handValue(d.slice(0, 2)), false);
    await sleep(750);
    for (let i = 2; i < d.length; i++) {
      await dealCard(dealerHand, d[i]); if (!alive(token)) return;
      const v = handValue(d.slice(0, i + 1)); setVal(dealerVal, v, v > 21); await sleep(380);
    }
    await sleep(250); if (!alive(token)) return;
    const o = OUT[g.outcome];
    const banner = h("div", { class: `banner ${o.cls}` }, o.t,
      h("small", { text: g.net > 0 ? `+${fmt(g.net)} monedas` : g.net < 0 ? `−${fmt(-g.net)} monedas` : "Te devuelvo tu apuesta" }));
    mid.replaceChildren(banner);
    if (g.outcome === "blackjack") { Sfx.blackjack(); Fx.at(banner, "confetti", 170, 1.3); Fx.rain(50); }
    else if (o.cls === "win") { Sfx.win(g.net >= 1000); Fx.at(banner, "confetti", 90); }
    else if (g.outcome === "push") Sfx.push();
    else { Sfx.lose(); if (g.outcome === "bust") { playerHand.classList.add("shake"); setTimeout(() => playerHand.classList.remove("shake"), 600); } }
    settleChips(o.cls === "win" || o.cls === "bj" ? "win" : g.outcome === "push" ? "push" : "lose");
    setBalance(g.balance);
    if (g.net > 0) toast(`¡Ganaste ${fmt(g.net)} monedas en el blackjack! 🃏`, "gold");
    st.game = null; st.finished = true; st.busy = false; renderControls();
  }

  async function act(action) {
    if (st.busy) return;
    st.busy = true; renderControls();
    const g0 = st.game;
    if (action === "double") { setBalance(S.profile.balance - g0.base_bet); Sfx.chip(); showSpot(g0.base_bet * 2); }
    try {
      const r = await gpost("/api/blackjack/action", { action });
      st.game = r.game;
      await syncPlayer(r.game.player);
      if (!alive(token)) return;
      if (r.game.active) { setBalance(r.balance); st.busy = false; renderControls(); } else await reveal(r.game);
    } catch (e) {
      toast(e.message, "err"); st.busy = false; setBalance(S.profile.balance + (action === "double" ? g0.base_bet : 0));
      if (g0) showSpot(g0.bet);
      if (e.status === 404) { st.game = null; clearTable(); }
      renderControls();
    }
  }

  async function deal() {
    if (st.busy) return;
    if (st.bet > S.profile.balance) return toast("No te alcanza el saldo para esa apuesta.", "err");
    const from = controls.querySelector(".chip.sel") || controls.querySelector(".btn-gold");
    st.busy = true; st.finished = false; renderControls(); clearTable();
    const before = S.profile.balance;
    setBalance(before - st.bet); placeBet(st.bet, from);
    try {
      const r = await gpost("/api/blackjack/deal", { bet: st.bet });
      const g = r.game; st.game = g;
      await sleep(260);
      const order = [[playerHand, g.player[0], false], [dealerHand, g.dealer[0], false], [playerHand, g.player[1], false], [dealerHand, g.dealer[1], true]];
      for (const [hand, c, down] of order) {
        await dealCard(hand, c, { down }); if (!alive(token)) return;
        setVal(playerVal, handValue(g.player.slice(0, playerHand.children.length)), false);
        if (dealerHand.children.length) setVal(dealerVal, handValue([g.dealer[0]]), false);
        await sleep(120);
      }
      if (g.active) { st.busy = false; renderControls(); } else await reveal(g);
    } catch (e) {
      toast(e.message, "err"); st.busy = false; setBalance(before); clearTable();
      if (e.status === 409) await restore();
      renderControls();
    }
  }
  async function restore() {                      // si había una mano abierta, se retoma tal cual
    const d = await gget("/api/blackjack");
    if (!(d.game && d.game.active)) return;
    const g = d.game; st.game = g; clearTable();
    for (const c of g.player) await dealCard(playerHand, c, { instant: true });
    await dealCard(dealerHand, g.dealer[0], { instant: true }); await dealCard(dealerHand, g.dealer[1], { down: true, instant: true });
    setVal(playerVal, g.player_value, g.player_value > 21); setVal(dealerVal, g.dealer_value, false);
    showSpot(g.bet); setBalance(d.balance, false);
  }

  const btn = (cls, label, fn, disabled) => h("button", { class: `btn ${cls} btn-lg`, disabled: disabled || st.busy, onclick: fn }, label);
  function renderControls() {
    const g = st.game;
    if (g && g.active) {
      controls.replaceChildren(
        btn("btn-primary", "🃏 Pedir", () => act("hit")), btn("btn-ghost", "✋ Plantarse", () => act("stand")),
        btn("btn-gold", `💰 Doblar (${fmt(g.base_bet)})`, () => act("double"), !g.can_double || S.profile.balance < g.base_bet));
      return;
    }
    const input = h("input", { class: "num-input", type: "number", inputmode: "numeric", min: lim.bj_min, max: lim.bj_max, value: st.bet, "aria-label": "Apuesta",
      oninput: e => { st.bet = Math.max(0, Math.min(lim.bj_max, parseInt(e.target.value || "0", 10) || 0)); chips.forEach(c => c.classList.remove("sel")); } });
    const chips = chipRack(chipVals, st.bet, v => { st.bet = v; input.value = v; dealBtn.textContent = label(); });
    chips.forEach(c => { c.disabled = st.busy; });
    const label = () => st.finished ? `Otra mano · ${fmt(st.bet)}` : `Repartir · ${fmt(st.bet)}`;
    const dealBtn = h("button", { class: "btn btn-gold btn-lg", disabled: st.busy, onclick: deal, text: label() });
    input.addEventListener("input", () => { dealBtn.textContent = label(); dealBtn.disabled = st.busy || st.bet < lim.bj_min; });
    const x2Btn = h("button", { class: "btn btn-ghost btn-bet-x2", "data-silent": "1", disabled: st.busy, title: "Duplicar la apuesta", "aria-label": "Duplicar la apuesta", text: "×2",
      onclick: () => {
        const cap = S.profile.balance >= lim.bj_min ? Math.min(lim.bj_max, S.profile.balance) : lim.bj_max;   // no pasar del máximo ni del saldo
        const next = Math.min(cap, Math.max(lim.bj_min, st.bet * 2));
        if (next === st.bet) return toast("No te alcanza el saldo para duplicar.", "err");
        st.bet = next; input.value = next; chips.forEach(c => c.classList.remove("sel")); Sfx.chip();
        dealBtn.textContent = label(); dealBtn.disabled = st.busy || st.bet < lim.bj_min;
      } });
    const allinBtn = h("button", { class: "btn btn-gold btn-allin", "data-silent": "1", disabled: st.busy, title: "Apostar todo tu saldo", text: "🔥 ALL IN",
      onclick: () => {
        if (S.profile.balance < lim.bj_min) return toast(`Necesitás al menos ${fmt(lim.bj_min)} monedas para apostar.`, "err");
        st.bet = Math.min(lim.bj_max, S.profile.balance); input.value = st.bet; chips.forEach(c => c.classList.remove("sel")); Sfx.chips(4);
        dealBtn.textContent = label(); dealBtn.disabled = st.busy || st.bet < lim.bj_min;
      } });
    controls.replaceChildren(h("div", { class: "bj-bet" }, h("div", { class: "row" }, chips, input, x2Btn, allinBtn), h("div", { class: "row" }, dealBtn),
      h("p", { class: "note", text: `Apuesta mínima: ${fmt(lim.bj_min)} monedas · sin máximo.` })));
  }

  if (data.game && data.game.active) await restore();
  if (data.expired) {
    const o = OUT[data.expired.outcome];
    toast(`Tu mano anterior se cerró por inactividad (me planté por vos): ${o ? o.t.toLowerCase() : ""}.`);
  }
  renderControls();
  root.replaceChildren(sectionTitle("Blackjack", "Mismas reglas que /blackjack: mazo de 6, el dealer se planta en 17."), h("div", { class: "bj" }, table, controls),
    howBox([
      ["Objetivo", "Acercate a 21 sin pasarte y ganale al dealer. Las figuras valen 10 y el As vale 11 u 1, lo que más te convenga."],
      ["Tus opciones", "Pedir suma una carta. Plantarse termina tu turno. Doblar duplica la apuesta, te da una sola carta y te planta."],
      ["Pagos", "Ganar paga 1 a 1, el Blackjack natural (21 con dos cartas) paga 3 a 2 y el empate devuelve la apuesta. El dealer se planta en 17."]]));
  if (st.game) { await sleep(0); showSpot(st.game.bet); }
};

/* ============================================================
   TRAGAMONEDAS
   ============================================================ */
VIEWS.slots = async (root, token) => {
  const lim = S.profile.limits, sl = S.profile.slots;
  const chipVals = CHIPS.filter(v => v >= lim.sl_min && v <= lim.sl_max);
  const st = { bet: chipVals.includes(100) ? 100 : chipVals[0], busy: false };
  const randSym = () => sl.symbols[(Math.random() * sl.symbols.length) | 0];
  const symDiv = s => h("div", { class: "sym", text: s });

  const reels = [0, 1, 2].map(() => h("div", { class: "reel" }, h("div", { class: "strip" }, symDiv(randSym()), symDiv(randSym()), symDiv(randSym()))));
  const display = h("div", { class: "led", text: "¡Probá tu suerte!" });
  const lights = h("div", { class: "marquee" }, Array.from({ length: 18 }, (_, i) => h("i", { style: { "--d": `${i * 0.08}s` } })));
  const knob = h("div", { class: "knob" }), lever = h("button", { class: "lever", "data-silent": "1", "aria-label": "Palanca", onclick: spin }, h("div", { class: "rod" }, knob));
  const win = h("div", { class: "payline" });
  const window_ = h("div", { class: "reels" }, reels, win);
  const machine = h("div", { class: "machine" }, lights, h("div", { class: "machine-title", text: "TRAGAMONEDAS" }), h("div", { class: "reels-frame" }, window_, lever), display);

  const payRows = new Map();
  const payRow = (key, syms, label) => { const r = h("div", { class: "pay-row" }, h("span", { class: "syms", text: syms }), h("b", { text: label })); payRows.set(key, r); return r; };
  const paytable = h("div", { class: "card paytable" }, h("h3", { text: "Tabla de pagos" }), h("p", { class: "note", text: "Tres iguales o dos iguales." }),
    sl.symbols.map(s => payRow(s, s.repeat(3), `×${sl.mult[s]}`)), payRow("pair", "🍒🍒 ➜", `×${String(sl.pair).replace(".", ",")}`));

  const spinBtn = h("button", { class: "btn btn-gold btn-lg", "data-silent": "1", onclick: spin }, icon("slots"), `GIRAR · ${fmt(st.bet)}`);
  const input = h("input", { class: "num-input", type: "number", inputmode: "numeric", min: lim.sl_min, max: lim.sl_max, value: st.bet, "aria-label": "Apuesta",
    oninput: e => { st.bet = Math.max(0, Math.min(lim.sl_max, parseInt(e.target.value || "0", 10) || 0)); chips.forEach(c => c.classList.remove("sel")); relabel(); } });
  const relabel = () => { spinBtn.replaceChildren(icon("slots"), `GIRAR · ${fmt(st.bet)}`); spinBtn.disabled = st.busy || st.bet < lim.sl_min; };
  const chips = chipRack(chipVals, st.bet, v => { st.bet = v; input.value = v; relabel(); });
  const allinBtn = h("button", { class: "btn btn-gold btn-allin", "data-silent": "1", title: "Apostar todo tu saldo", text: "🔥 ALL IN",
    onclick: () => {
      if (st.busy) return;
      if (S.profile.balance < lim.sl_min) return toast(`Necesitás al menos ${fmt(lim.sl_min)} monedas para apostar.`, "err");
      st.bet = Math.min(lim.sl_max, S.profile.balance); input.value = st.bet; chips.forEach(c => c.classList.remove("sel")); Sfx.chips(4); relabel();
    } });

  let lastTick = 0;
  function spinReel(i, finalSym, dur) {
    const reel = reels[i], strip = reel.querySelector(".strip"), symH = reel.clientHeight / 3;
    const current = [...strip.children].map(c => c.textContent), n = 16 + i * 8;
    const seq = [...current, ...Array.from({ length: n }, randSym), randSym(), finalSym, randSym()];
    strip.replaceChildren(...seq.map(symDiv));
    const total = seq.length - 3;
    reel.classList.add("fast");
    const anim = strip.animate([{ transform: "translateY(0)" }, { transform: `translateY(${-total * symH}px)` }], { duration: dur, easing: "cubic-bezier(.22,.6,.2,1)", fill: "forwards" });
    setTimeout(() => reel.classList.remove("fast"), dur * 0.72);
    for (let k = 1; k < total; k++) {                                    // un "tic" por cada símbolo que pasa
      const t = dur * (1 - Math.pow(1 - k / total, 1 / 3));
      setTimeout(() => { const now_ = performance.now(); if (now_ - lastTick > 38) { lastTick = now_; Sfx.tick(0.22); } }, t);
    }
    return anim.finished.catch(() => {}).then(() => {
      anim.cancel();
      strip.replaceChildren(...seq.slice(-3).map(symDiv));
      strip.animate([{ transform: "translateY(9px)" }, { transform: "none" }], { duration: 260, easing: "ease-out" });
      Sfx.reelStop();
    });
  }

  async function spin() {
    if (st.busy) return;
    if (st.bet < lim.sl_min) return toast(`La apuesta mínima es ${fmt(lim.sl_min)} monedas.`, "err");
    if (st.bet > S.profile.balance) return toast("No te alcanza el saldo para esa apuesta.", "err");
    st.busy = true; relabel(); chips.forEach(c => { c.disabled = true; });
    machine.classList.remove("jackpot", "pairwin"); reels.forEach(r => r.classList.remove("win")); payRows.forEach(r => r.classList.remove("hit"));
    display.textContent = "Girando…"; knob.classList.add("pull"); Sfx.lever(); setTimeout(() => knob.classList.remove("pull"), 600);
    const before = S.profile.balance; setBalance(before - st.bet);
    let r;
    try { r = await gpost("/api/slots/spin", { bet: st.bet }); }
    catch (e) { toast(e.message, "err"); setBalance(before); st.busy = false; chips.forEach(c => { c.disabled = false; }); relabel(); display.textContent = "¡Probá tu suerte!"; return; }
    Sfx.spinStart();
    await Promise.all(r.reels.map((s, i) => spinReel(i, s, 1700 + i * 650)));
    if (!alive(token)) return;

    if (r.kind === "jackpot") {
      reels.forEach(x => x.classList.add("win")); payRows.get(r.reels[0]).classList.add("hit"); machine.classList.add("jackpot");
      display.textContent = `¡JACKPOT! ×${r.mult} · +${fmt(r.net)}`; Sfx.jackpot(); Fx.rain(100); Fx.at(machine, "confetti", 180, 1.3);
    } else if (r.kind === "pair") {
      const sym = r.reels.find(s => r.reels.filter(x => x === s).length === 2);
      r.reels.forEach((s, i) => { if (s === sym) reels[i].classList.add("win"); }); payRows.get("pair").classList.add("hit"); machine.classList.add("pairwin");
      display.textContent = `Dos iguales ×${String(r.mult).replace(".", ",")} · ${r.net >= 0 ? "+" : "−"}${fmt(Math.abs(r.net))}`; Sfx.win(false); Fx.at(machine, "coins", 14);
    } else { display.textContent = "Nada esta vez… ¡otra!"; Sfx.lose(); }
    setBalance(r.balance);
    if (r.net > 0) toast(`¡Ganaste ${fmt(r.net)} monedas en los slots! 🎰`, "gold");
    st.busy = false; chips.forEach(c => { c.disabled = false; }); relabel();
  }

  relabel();
  root.replaceChildren(sectionTitle("Tragamonedas", "Mismas reglas y pagos que el comando /slots. Tres iguales pagan hasta ×15."),
    h("div", { class: "slots-layout" },
      h("div", { class: "slots-main" }, machine,
        h("div", { class: "bj-bet slots-bet" }, h("div", { class: "row" }, chips, input, allinBtn), h("div", { class: "row" }, spinBtn),
          h("p", { class: "note", text: `Apuesta mínima: ${fmt(lim.sl_min)} monedas · sin máximo.` }))),
      paytable),
    howBox([
      ["Cómo se juega", "Elegí cuánto apostar y tirá de la palanca (o tocá GIRAR). Se detienen los tres carretes uno por uno."],
      ["Qué paga", "Tres símbolos iguales pagan según la tabla (hasta ×15). Dos iguales pagan ×1,4. Si no hay iguales, perdés la apuesta."],
      ["A tener en cuenta", "Cada giro es independiente: no hay rachas ni «momentos» para jugar. Jugá por diversión."]]));
};


/* ============================================================
   CARA O CRUZ (mismas reglas que /apostar: acertás y duplicás)
   ============================================================ */
const ccTabs = (root, token, mode) => h("div", { class: "tabs" },
  h("button", { class: mode === "casa" ? "on" : "", text: "🪙 Contra la casa", onclick: () => VIEWS.caracruz(root, token, "casa") }),
  h("button", { class: mode === "duel" ? "on" : "", text: "⚔️ Duelo contra alguien", onclick: () => VIEWS.caracruz(root, token, "duel") }));

VIEWS.caracruz = async (root, token, mode = "casa") => {
  clearInterval(S.duelTimer);
  if (mode === "duel") return caracruzDuel(root, token);
  const lim = S.profile.limits;
  const chipVals = CHIPS.filter(v => v >= lim.cf_min && v <= lim.cf_max);
  const st = { bet: chipVals.includes(100) ? 100 : chipVals[0], side: "cara", busy: false, rot: 0, hist: [] };
  const FACE = { cara: "😎", cruz: "✖" };

  const coin = h("div", { class: "coin3d" },
    h("div", { class: "coin-face front" }, h("span", { text: FACE.cara }), h("small", { text: "CARA" })),
    h("div", { class: "coin-face back" }, h("span", { text: FACE.cruz }), h("small", { text: "CRUZ" })));
  const toss = h("div", { class: "coin-toss" }, coin);
  const stage = h("div", { class: "coin-stage" }, toss, h("div", { class: "coin-shadow" }));
  const display = h("div", { class: "led coin-led", text: "Elegí un lado y lanzá" });
  const histEl = h("div", { class: "hist" });
  const paintHist = () => histEl.replaceChildren(...(st.hist.length
    ? st.hist.slice(-12).map(x => h("i", { class: x.won ? "green" : "red", title: x.won ? "Ganaste" : "Perdiste", text: x.result === "cara" ? "C" : "X" }))
    : [h("span", { class: "note", text: "Todavía no lanzaste" })]));
  paintHist();

  const sideBtns = ["cara", "cruz"].map(k => h("button", { class: `side-btn ${k === st.side ? "on" : ""}`, "data-silent": "1", "aria-pressed": String(k === st.side),
    onclick: () => { if (st.busy) return; st.side = k; Sfx.chip(); sideBtns.forEach(b => { b.classList.toggle("on", b.dataset.k === k); b.setAttribute("aria-pressed", String(b.dataset.k === k)); }); } },
    h("span", { text: FACE[k] }), k === "cara" ? "Cara" : "Cruz"));
  sideBtns.forEach((b, i) => { b.dataset.k = ["cara", "cruz"][i]; });

  const flipBtn = h("button", { class: "btn btn-gold btn-lg", "data-silent": "1", onclick: flip });
  const input = h("input", { class: "num-input", type: "number", inputmode: "numeric", min: lim.cf_min, max: lim.cf_max, value: st.bet, "aria-label": "Apuesta",
    oninput: e => { st.bet = Math.max(0, Math.min(lim.cf_max, parseInt(e.target.value || "0", 10) || 0)); chips.forEach(c => c.classList.remove("sel")); relabel(); } });
  const relabel = () => { flipBtn.replaceChildren(icon("coin"), `LANZAR · ${fmt(st.bet)}`); flipBtn.disabled = st.busy || st.bet < lim.cf_min; };
  const chips = chipRack(chipVals, st.bet, v => { st.bet = v; input.value = v; relabel(); });
  const setBet = n => { st.bet = n; input.value = n; chips.forEach(c => c.classList.remove("sel")); Sfx.chips(4); relabel(); };
  const x2Btn = h("button", { class: "btn btn-ghost btn-bet-x2", "data-silent": "1", title: "Duplicar la apuesta", "aria-label": "Duplicar la apuesta", text: "×2",
    onclick: () => {
      if (st.busy) return;
      const cap = S.profile.balance >= lim.cf_min ? Math.min(lim.cf_max, S.profile.balance) : lim.cf_max;
      const next = Math.min(cap, Math.max(lim.cf_min, st.bet * 2));
      if (next === st.bet) return toast("No te alcanza el saldo para duplicar.", "err");
      setBet(next);
    } });
  const allinBtn = h("button", { class: "btn btn-gold btn-allin", "data-silent": "1", title: "Apostar todo tu saldo", text: "🔥 ALL IN",
    onclick: () => {
      if (st.busy) return;
      if (S.profile.balance < lim.cf_min) return toast(`Necesitás al menos ${fmt(lim.cf_min)} monedas para apostar.`, "err");
      setBet(Math.min(lim.cf_max, S.profile.balance));
    } });
  const lock = on => { st.busy = on; chips.forEach(c => { c.disabled = on; }); sideBtns.forEach(b => { b.disabled = on; }); x2Btn.disabled = allinBtn.disabled = input.disabled = on; relabel(); };

  async function flip() {
    if (st.busy) return;
    if (st.bet < lim.cf_min) return toast(`La apuesta mínima es ${fmt(lim.cf_min)} monedas.`, "err");
    if (st.bet > S.profile.balance) return toast("No te alcanza el saldo para esa apuesta.", "err");
    lock(true); stage.classList.remove("win", "lose");
    display.textContent = "Lanzando…";
    const before = S.profile.balance; setBalance(before - st.bet);
    let r;
    try { r = await gpost("/api/coinflip", { bet: st.bet, side: st.side }); }
    catch (e) { toast(e.message, "err"); setBalance(before); lock(false); display.textContent = "Elegí un lado y lanzá"; return; }
    Sfx.spinStart();
    const turns = 5 + Math.floor(Math.random() * 3), target = turns * 360 + (r.result === "cara" ? 0 : 180), dur = 1700;
    const spin = coin.animate([{ transform: `rotateY(${st.rot}deg)` }, { transform: `rotateY(${target}deg)` }], { duration: dur, easing: "cubic-bezier(.2,.7,.25,1)", fill: "forwards" });
    const up = toss.animate([{ transform: "translateY(0) scale(1)" }, { transform: "translateY(-150px) scale(1.18)", offset: 0.5 }, { transform: "translateY(0) scale(1)" }], { duration: dur, easing: "ease-in-out" });
    await Promise.all([spin.finished, up.finished].map(p => p.catch(() => {})));
    if (!alive(token)) return;
    st.rot = target % 360; coin.style.transform = `rotateY(${st.rot}deg)`; spin.cancel();
    toss.animate([{ transform: "translateY(6px) scaleY(.95)" }, { transform: "none" }], { duration: 240, easing: "ease-out" });

    st.hist.push(r); paintHist();
    stage.classList.add(r.won ? "win" : "lose");
    if (r.won) {
      display.textContent = `¡Salió ${r.result}! +${fmt(r.net)}`; Sfx.win(r.net >= 5000); Fx.at(stage, "coins", 14);
      toast(`¡Ganaste ${fmt(r.net)} monedas en cara o cruz! 🪙`, "gold");
    } else { display.textContent = `Salió ${r.result}… perdiste ${fmt(st.bet)}`; Sfx.lose(); }
    setBalance(r.balance);
    lock(false);
  }

  relabel();
  root.replaceChildren(sectionTitle("Cara o cruz", "Mismas reglas que el comando /apostar: si acertás, duplicás lo apostado."), ccTabs(root, token, "casa"),
    h("div", { class: "card coin-card" }, stage, display, h("div", { class: "hist-label", text: "Últimos lanzamientos" }), histEl,
      h("div", { class: "side-pick" }, sideBtns),
      h("div", { class: "bj-bet slots-bet" }, h("div", { class: "row" }, chips, input, x2Btn, allinBtn), h("div", { class: "row" }, flipBtn),
        h("p", { class: "note", text: `Apuesta mínima: ${fmt(lim.cf_min)} monedas · sin máximo. Si acertás cobrás ×2.` }))),
    howBox([
      ["Cómo se juega", "Elegí cara o cruz, poné cuánto apostás y lanzá la moneda."],
      ["Qué paga", "Si acertás, recibís el doble de lo apostado (ganás lo mismo que pusiste). Si no, perdés la apuesta."],
      ["A tener en cuenta", "Cada lanzamiento es 50/50 e independiente: que haya salido cara varias veces seguidas no cambia nada. Jugá por diversión."]]));
};


/* ---------- Cara o cruz: duelo contra otra persona ---------- */
const DUEL_END = { declined: "rechazó el duelo", cancelled: "canceló el duelo", expired: "no respondió a tiempo" };
async function caracruzDuel(root, token) {
  const lim = S.profile.limits, me = S.user.id;
  const chipVals = CHIPS.filter(v => v >= lim.cf_min && v <= lim.cf_max);
  const st = { bet: chipVals.includes(100) ? 100 : chipVals[0], side: "cara", target: null, busy: false, seen: null, seq: 0, timer: 0 };
  const FACE = { cara: "😎", cruz: "✖" }, OTHER = { cara: "cruz", cruz: "cara" };
  const cap = s => s[0].toUpperCase() + s.slice(1);

  /* --- quién --- */
  const search = h("input", { class: "txt", placeholder: "Buscá a quién desafiar…", autocomplete: "off", maxlength: "32", "aria-label": "Buscar persona" });
  const results = h("div", { class: "pay-results" }), chosen = h("div", { class: "pay-chosen hide" });
  const avatarOf = m => m.avatar ? h("img", { class: "avatar", src: m.avatar, alt: "" }) : h("div", { class: "avatar" });
  function choose(m) {
    st.target = m; results.replaceChildren(); search.value = ""; search.classList.add("hide"); chosen.classList.remove("hide");
    chosen.replaceChildren(avatarOf(m), h("b", { text: m.name }),
      h("button", { class: "icon-btn sm", "aria-label": "Quitar", onclick: () => { st.target = null; chosen.classList.add("hide"); search.classList.remove("hide"); relabel(); search.focus(); } }, icon("x")));
    relabel();
  }
  search.addEventListener("input", () => {
    clearTimeout(st.qt);
    const q = search.value.trim();
    if (!q) return results.replaceChildren();
    st.qt = setTimeout(async () => {
      const mine = ++st.seq;
      try {
        const r = await gget("/api/members", { q });
        if (mine !== st.seq) return;
        results.replaceChildren(...(r.members.length ? r.members.map(m => h("button", { class: "member-row", onclick: () => choose(m) }, avatarOf(m), h("span", { text: m.name })))
          : [h("p", { class: "note", style: { padding: "8px 4px" }, text: "No encontré a nadie con ese nombre." })]));
      } catch (e) { toast(e.message, "err"); }
    }, 220);
  });

  /* --- lado y apuesta --- */
  const sideBtns = ["cara", "cruz"].map(k => h("button", { class: `side-btn ${k === st.side ? "on" : ""}`, "data-silent": "1", dataset: { k },
    onclick: () => { if (st.busy) return; st.side = k; Sfx.chip(); sideBtns.forEach(b => b.classList.toggle("on", b.dataset.k === k)); sideNote.textContent = sideText(); } },
    h("span", { text: FACE[k] }), cap(k)));
  const sideText = () => `Vos elegís ${st.side}. ${st.target ? st.target.name : "La otra persona"} se queda con ${OTHER[st.side]}.`;
  const sideNote = h("p", { class: "note", text: sideText() });

  const sendBtn = h("button", { class: "btn btn-gold btn-lg", "data-silent": "1", onclick: send });
  const input = h("input", { class: "num-input", type: "number", inputmode: "numeric", min: lim.cf_min, max: lim.cf_max, value: st.bet, "aria-label": "Apuesta",
    oninput: e => { st.bet = Math.max(0, Math.min(lim.cf_max, parseInt(e.target.value || "0", 10) || 0)); chips.forEach(c => c.classList.remove("sel")); relabel(); } });
  const relabel = () => { sendBtn.replaceChildren(icon("coin"), `DESAFIAR · ${fmt(st.bet)}`); sendBtn.disabled = st.busy || st.bet < lim.cf_min || !st.target; sideNote.textContent = sideText(); };
  const chips = chipRack(chipVals, st.bet, v => { st.bet = v; input.value = v; relabel(); });
  const setBet = n => { st.bet = n; input.value = n; chips.forEach(c => c.classList.remove("sel")); Sfx.chips(4); relabel(); };
  const x2Btn = h("button", { class: "btn btn-ghost btn-bet-x2", "data-silent": "1", title: "Duplicar la apuesta", text: "×2", onclick: () => {
    const c = S.profile.balance >= lim.cf_min ? Math.min(lim.cf_max, S.profile.balance) : lim.cf_max, next = Math.min(c, Math.max(lim.cf_min, st.bet * 2));
    if (next === st.bet) return toast("No te alcanza el saldo para duplicar.", "err"); setBet(next); } });
  const allinBtn = h("button", { class: "btn btn-gold btn-allin", "data-silent": "1", title: "Apostar todo tu saldo", text: "🔥 ALL IN", onclick: () => {
    if (S.profile.balance < lim.cf_min) return toast(`Necesitás al menos ${fmt(lim.cf_min)} monedas para apostar.`, "err"); setBet(Math.min(lim.cf_max, S.profile.balance)); } });

  async function send() {
    if (st.busy || !st.target) return;
    if (st.bet > S.profile.balance) return toast("No te alcanza el saldo para esa apuesta.", "err");
    if (!await confirmBox({ title: `Desafiar a ${st.target.name}`, text: `Tu apuesta de ${fmt(st.bet)} monedas queda en custodia hasta que responda (o se devuelve si rechaza o pasan 2 minutos). Elegiste ${st.side}.`, ok: "Desafiar" })) return;
    st.busy = true; relabel();
    try {
      const r = await gpost("/api/duel/create", { target: st.target.id, bet: st.bet, side: st.side });
      setBalance(r.balance); Sfx.chips(3);
      toast(r.dm ? `Desafío enviado a ${r.opponent} 🪙 (le avisé por mensaje privado)` : `Desafío enviado a ${r.opponent} 🪙 (no pude avisarle por privado: tiene que entrar al panel o mirar el servidor)`, "gold");
      await refresh();
    } catch (e) { toast(e.message, "err"); }
    st.busy = false; relabel();
  }

  /* --- listas --- */
  const incomingBox = h("div"), outgoingBox = h("div"), recentBox = h("div");
  const left = ts => { const s = Math.max(0, Math.round(ts - now())); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  async function act(path, id, ok) {
    try {
      const r = await gpost(path, { id }); st.seen && st.seen.add(id); setBalance(r.balance);
      if (r.result) {
        r.won ? (Sfx.win(false), Fx.at($(".bal-chip"), "coins", 14)) : Sfx.lose();
        toast(r.won ? `¡Salió ${r.result} y ganaste ${fmt(r.bet)} monedas! 🏆` : `Salió ${r.result}… perdiste ${fmt(r.bet)} monedas`, r.won ? "gold" : "err");
      } else toast(ok, "ok");
    } catch (e) { toast(e.message, "err"); }
    refresh();
  }
  function paint(d) {
    incomingBox.replaceChildren(d.incoming.length ? h("div", { class: "card" }, h("h3", { text: "⚔️ Te desafiaron" }), d.incoming.map(x => h("div", { class: "duel-row" },
      h("div", { class: "duel-main" }, h("b", { text: x.challenger }), ` te desafía por ${fmt(x.bet)} 🪙`,
        h("small", { text: `Eligió ${x.side} · vos te quedás con ${OTHER[x.side]} · ganás ${fmt(x.bet * 2)} · vence en ${left(x.expires)}` })),
      h("div", { class: "duel-btns" },
        h("button", { class: "btn btn-primary btn-sm", disabled: x.bet > S.profile.balance, title: x.bet > S.profile.balance ? "No te alcanza el saldo" : "", text: "Aceptar", onclick: async () => {
          if (await confirmBox({ title: `Aceptar el duelo de ${x.challenger}`, text: `Ponés ${fmt(x.bet)} monedas. Si sale ${OTHER[x.side]} ganás ${fmt(x.bet * 2)}; si sale ${x.side}, las perdés.`, ok: "Aceptar" })) act("/api/duel/accept", x.id); } }),
        h("button", { class: "btn btn-ghost btn-sm", text: "Rechazar", onclick: () => act("/api/duel/decline", x.id, "Rechazaste el duelo") })))))
      : null);
    outgoingBox.replaceChildren(d.outgoing.length ? h("div", { class: "card" }, h("h3", { text: "⏳ Esperando respuesta" }), d.outgoing.map(x => h("div", { class: "duel-row" },
      h("div", { class: "duel-main" }, "Desafiaste a ", h("b", { text: x.opponent }), ` por ${fmt(x.bet)} 🪙`, h("small", { text: `Elegiste ${x.side} · vence en ${left(x.expires)}` })),
      h("div", { class: "duel-btns" }, h("button", { class: "btn btn-ghost btn-sm", text: "Cancelar", onclick: () => act("/api/duel/cancel", x.id, "Desafío cancelado, te devolví la apuesta") })))))
      : null);
    recentBox.replaceChildren(h("div", { class: "card" }, h("h3", { text: "Últimos duelos" }), d.recent.length ? d.recent.map(x => {
      const mineC = x.challenger_id === me, other = mineC ? x.opponent : x.challenger;
      if (x.status !== "done") return h("div", { class: "duel-row" }, h("div", { class: "duel-main" }, h("span", { class: "note", text: mineC ? `${other} ${DUEL_END[x.status] || "no respondió"} · apuesta devuelta` : `Duelo de ${other}: ${x.status === "declined" ? "lo rechazaste" : x.status === "cancelled" ? "lo canceló" : "venció"}` })));
      const won = x.winner_id === me;
      return h("div", { class: "duel-row" }, h("div", { class: "duel-main" }, `${won ? "🏆 Ganaste" : "💸 Perdiste"} contra `, h("b", { text: other }), h("small", { text: `Salió ${x.result}` })),
        h("div", { class: `log-amt ${won ? "pos" : "neg"}`, text: `${won ? "+" : "−"}${fmt(x.bet)} 🪙` }));
    }) : h("p", { class: "note", text: "Todavía no jugaste ningún duelo." })));
  }
  async function refresh() {
    const d = await gget("/api/duel/list");
    if (!alive(token)) return;
    if (d.balance !== S.profile.balance) setBalance(d.balance);
    const first = st.seen === null; if (first) st.seen = new Set();
    for (const x of d.recent) {                                      // avisos de lo que pasó mientras mirabas otra cosa
      if (st.seen.has(x.id)) continue; st.seen.add(x.id);
      if (first || x.challenger_id !== me) continue;                  // lo que me toca a mí como retador
      if (x.status === "done") { const won = x.winner_id === me; won ? Sfx.win(false) : Sfx.lose(); toast(won ? `¡Salió ${x.result} y le ganaste a ${x.opponent}! +${fmt(x.bet)} 🏆` : `Salió ${x.result}… perdiste contra ${x.opponent} (−${fmt(x.bet)})`, won ? "gold" : "err"); }
      else toast(`${x.opponent} ${DUEL_END[x.status] || "no respondió"}. Te devolví la apuesta.`, "ok");
    }
    paint(d);
  }

  relabel();
  root.replaceChildren(sectionTitle("Cara o cruz", "Desafiá a alguien del servidor: cada uno pone la misma apuesta y el ganador se lleva todo."), ccTabs(root, token, "duel"),
    h("div", { class: "grid g2 duel-grid" },
      h("div", { class: "card duel-form" }, h("h3", { text: "Nuevo desafío" }),
        h("div", { class: "field" }, h("label", { text: "Contra quién" }), chosen, search, results),
        h("div", { class: "field" }, h("label", { text: "Tu lado" }), h("div", { class: "side-pick" }, sideBtns), sideNote),
        h("div", { class: "field" }, h("label", { text: "Apuesta de cada uno" }), h("div", { class: "bj-bet" }, h("div", { class: "row" }, chips, input, x2Btn, allinBtn))),
        h("div", { class: "row" }, sendBtn),
        h("p", { class: "note", text: `Mínimo ${fmt(lim.cf_min)} monedas, sin máximo. La otra persona tiene 2 minutos para aceptar desde acá o desde Discord (también podés usar /caracruz duelo).` })),
      h("div", { class: "duel-side" }, incomingBox, outgoingBox, recentBox)));
  await refresh();
  S.duelTimer = setInterval(() => { refresh().catch(() => {}); }, 3000);
  S.cleanups.push(() => clearInterval(S.duelTimer));
}
