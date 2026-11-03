"use strict";
/* ============================================================
   Cofres: sección del panel y animación de apertura.
   IMPORTANTE: el premio lo sortea y acredita el servidor ANTES de que empiece cualquier animación.
   Acá solo se muestra el resultado que ya existe; el navegador no puede cambiarlo.
   ============================================================ */

const RAR = ["common", "rare", "epic", "legendary"];
const RAR_PAL = {
  common: { body: "#6b7280", dark: "#2f3542", accent: "#d1d5db", glow: "#9ca3af", lid: "#7c8494" },
  rare: { body: "#2563eb", dark: "#14306f", accent: "#93c5fd", glow: "#3b82f6", lid: "#3b78f0" },
  epic: { body: "#7c3aed", dark: "#3f1d80", accent: "#c4b5fd", glow: "#8b5cf6", lid: "#9159f5" },
  legendary: { body: "#d4a017", dark: "#74500a", accent: "#fde68a", glow: "#f5b301", lid: "#e8b92e" },
};
let chestUid = 0;

/* cofre dibujado en SVG (cada rareza tiene su color y su adorno) */
function chestSvg(rarity, { open = false, cls = "" } = {}) {
  const p = RAR_PAL[rarity], id = `ch${++chestUid}`;
  const star = Array.from({ length: 10 }, (_, k) => { const a = (-90 + k * 36) * Math.PI / 180, r = k % 2 ? 9 : 21; return `${(120 + Math.cos(a) * r).toFixed(1)},${(166 + Math.sin(a) * r).toFixed(1)}`; }).join(" ");
  const deco = {
    common: "",
    rare: [[48, 124], [192, 124], [48, 182], [192, 182]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="4.5" fill="${p.accent}"/>`).join(""),
    epic: `<polygon points="120,146 140,166 120,190 100,166" fill="${p.accent}" stroke="#fff" stroke-opacity=".6" stroke-width="2"/><polygon points="120,146 140,166 120,166" fill="#fff" fill-opacity=".35"/>`,
    legendary: `<polygon points="${star}" fill="#fff1b8" stroke="#9a6a14" stroke-width="2"/>`,
  }[rarity];
  const sparkles = rarity === "common" || rarity === "rare" ? "" : [[28, 60], [214, 78], [186, 28]].map(([x, y]) => `<polygon class="tw" points="${x},${y - 9} ${x + 3},${y - 3} ${x + 9},${y} ${x + 3},${y + 3} ${x},${y + 9} ${x - 3},${y + 3} ${x - 9},${y} ${x - 3},${y - 3}" fill="#fff"/>`).join("");
  const svg = document.createElementNS(SVGNS, "svg");
  svg.setAttribute("viewBox", "0 0 240 220"); svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", `chest-svg r-${rarity} ${open ? "open" : ""} ${cls}`.trim());
  svg.innerHTML = `<defs>
    <linearGradient id="${id}b" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${p.body}"/><stop offset="1" stop-color="${p.dark}"/></linearGradient>
    <linearGradient id="${id}l" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${p.lid}"/><stop offset="1" stop-color="${p.body}"/></linearGradient>
    <radialGradient id="${id}g"><stop offset="0" stop-color="${p.glow}" stop-opacity=".8"/><stop offset="1" stop-color="${p.glow}" stop-opacity="0"/></radialGradient>
    <linearGradient id="${id}m" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="${p.glow}" stop-opacity=".95"/><stop offset="1" stop-color="${p.glow}" stop-opacity="0"/></linearGradient>
    <clipPath id="${id}c"><path d="M34 112 V86 C34 52 72 36 120 36 C168 36 206 52 206 86 V112 Z"/></clipPath></defs>
    <circle class="cg" cx="120" cy="124" r="116" fill="url(#${id}g)"/>
    <ellipse cx="120" cy="204" rx="94" ry="11" fill="#000" fill-opacity=".45"/>
    <polygon class="beam" points="66,112 174,112 232,-40 8,-40" fill="url(#${id}m)"/>
    <g class="body"><rect x="34" y="104" width="172" height="92" rx="12" fill="url(#${id}b)" stroke="${p.accent}" stroke-width="3"/>
      <rect x="34" y="112" width="172" height="12" fill="${p.dark}" fill-opacity=".8"/>
      <rect x="62" y="104" width="18" height="92" fill="${p.accent}" fill-opacity=".85"/><rect x="160" y="104" width="18" height="92" fill="${p.accent}" fill-opacity=".85"/>${deco}</g>
    <g class="lid"><path d="M34 112 V86 C34 52 72 36 120 36 C168 36 206 52 206 86 V112 Z" fill="url(#${id}l)" stroke="${p.accent}" stroke-width="3"/>
      <g clip-path="url(#${id}c)"><rect x="62" y="30" width="18" height="86" fill="${p.accent}" fill-opacity=".85"/><rect x="160" y="30" width="18" height="86" fill="${p.accent}" fill-opacity=".85"/></g>
      <path d="M46 72 C72 50 168 50 194 72" fill="none" stroke="#fff" stroke-opacity=".2" stroke-width="5" stroke-linecap="round"/></g>
    <g class="lock"><rect x="104" y="96" width="32" height="34" rx="6" fill="#e8c35a" stroke="#9a6a14" stroke-width="2.5"/><circle cx="120" cy="109" r="5" fill="#5b3d08"/><rect x="118" y="112" width="4" height="10" rx="2" fill="#5b3d08"/></g>${sparkles}`;
  return svg;
}

/* ---------- tarjeta chiquita para el inicio ---------- */
function chestTeaser(st) {
  const d = st.daily, rc = st.rarities[d.next_rarity];
  const time = h("span", { class: "note" });
  const card = h("div", { class: `card claim chest-teaser r-${d.next_rarity}` },
    h("div", { class: "claim-head" }, h("div", { class: "claim-ic" }, icon("chest")),
      h("div", {}, h("h3", { text: "Cofre diario" }), h("p", { text: `Racha de ${d.streak} día(s) · hoy toca el ${rc.name.toLowerCase()}` }))),
    h("div", { class: "teaser-art" }, chestSvg(d.next_rarity, { cls: "idle" })), time,
    h("a", { class: "btn btn-gold btn-lg", href: "#/cofres" }, icon("gift"), "Ir a los cofres"));
  const tick = () => { const left = d.ready_at - now(); time.textContent = left <= 0 ? "🎁 ¡Listo para abrir!" : `Próximo cofre en ${fmtClock(left)}`; };
  tick(); const t = setInterval(tick, 1000); S.cleanups.push(() => clearInterval(t));
  return card;
}

/* ============================================================
   ANIMACIÓN DE APERTURA (estilo "caja": chispas → se abre → ruleta que frena → premio)
   ============================================================ */
function playOpening(r, cfg) {
  return new Promise(resolve => {
    const rar = r.rarity, rc = cfg.rarities[rar], segs = rc.segments;
    let skipped = false, reelAnim = null, raf = 0, ended = false, sparkTimer = 0;
    const waiters = [];
    const wait = ms => skipped ? Promise.resolve() : new Promise(res => { const t = setTimeout(res, ms); waiters.push(() => { clearTimeout(t); res(); }); });
    const skip = () => { if (skipped) return; skipped = true; waiters.splice(0).forEach(f => f()); if (reelAnim) reelAnim.finish(); };

    /* ruleta: 60 premios de relleno según las probabilidades REALES; el ganador está en una posición fija y es el premio verdadero */
    const N = 60, WIN = 48, total = segs.reduce((a, s) => a + s.weight, 0);
    const pickSeg = () => { let x = Math.random() * total; for (const s of segs) { x -= s.weight; if (x < 0) return s; } return segs[segs.length - 1]; };
    const items = Array.from({ length: N }, (_, i) => {
      if (i === WIN) return { amount: r.reward, seg: segs[r.segment] };
      const s = pickSeg(); return { amount: Math.max(5, Math.round((s.lo + Math.random() * (s.hi - s.lo)) / 5) * 5), seg: s };
    });
    const itemEl = it => h("div", { class: "cs-item", style: { "--c": it.seg.color } }, coinIcon(), h("b", { class: "amt", text: fmt(it.amount) }), h("span", { class: "tag", text: it.seg.name.replace(/[¡!]/g, "") }));

    const wrapW = Math.min(1100, innerWidth - 32), iw = Math.max(92, Math.min(150, Math.floor(wrapW / 5.3))), step = iw + 10;
    const chest = chestSvg(rar, { cls: "cs-chest" });
    const track = h("div", { class: "cs-track" }, items.map(itemEl));
    const pointer = h("div", { class: "cs-pointer" });
    const reel = h("div", { class: "cs-reel" }, track, pointer);
    const reelWrap = h("div", { class: "cs-reel-wrap" }, reel);
    const flash = h("div", { class: "cs-flash" });
    const reveal = h("div", { class: "cs-reveal" });
    const skipBtn = h("button", { class: "btn btn-ghost btn-sm", "data-silent": "1", onclick: skip }, "Saltar ⏭");
    const ov = h("div", { class: `cs-ov r-${rar}`, style: { "--iw": `${iw}px` } }, flash,
      h("div", { class: "cs-top" }, h("div", { class: "cs-title" }, "Abriendo cofre ", h("span", { text: rc.name })), skipBtn),
      h("div", { class: "cs-body" }, chest, reelWrap), reveal);
    document.body.append(ov); document.body.classList.add("noscroll");
    const onKey = e => { if (e.key === "Escape") { ended ? close(false) : skip(); } };
    document.addEventListener("keydown", onKey);

    function close(again) {
      cancelAnimationFrame(raf); clearInterval(sparkTimer); document.removeEventListener("keydown", onKey);
      ov.remove(); document.body.classList.remove("noscroll"); resolve({ again });
    }

    function tickLoop() {                                   // un clic por cada premio que pasa bajo el indicador
      let lastIdx = -1, lastX = 0;
      const loop = () => {
        if (ended) return;
        const x = new DOMMatrix(getComputedStyle(track).transform).m41, idx = Math.floor((-x + reel.clientWidth / 2) / step);
        if (idx !== lastIdx) {
          lastIdx = idx; Sfx.reelTick(Math.min(1, Math.abs(x - lastX) / 55));
          pointer.classList.remove("bump"); void pointer.offsetWidth; pointer.classList.add("bump");
        }
        lastX = x; raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
    }

    (async () => {
      /* 1) el cofre se carga */
      Sfx.chestCharge(); chest.classList.add("charge");
      sparkTimer = setInterval(() => Fx.at(chest, "sparkle", 5), 170);
      await wait(950);
      clearInterval(sparkTimer); chest.classList.remove("charge");
      /* 2) se abre */
      Sfx.chestOpen(); chest.classList.add("open"); flash.classList.add("go"); Fx.at(chest, "sparkle", 26);
      await wait(560);
      chest.classList.add("gone"); reelWrap.classList.add("show");
      await wait(300);
      /* 3) la ruleta: arranca rápido y frena sobre el premio real */
      const jitter = (Math.random() * 0.6 - 0.3) * iw;
      const target = WIN * step + iw / 2 + jitter - reel.clientWidth / 2;
      reelAnim = track.animate([{ transform: "translateX(0)" }, { transform: `translateX(${-target}px)` }],
        { duration: 4300, easing: "cubic-bezier(.1,.65,.1,1)", fill: "forwards" });
      tickLoop();
      await reelAnim.finished.catch(() => {});
      ended = true; cancelAnimationFrame(raf);
      /* 4) premio */
      reel.classList.add("end"); track.children[WIN].classList.add("won");
      const tier = r.segment, seg = segs[tier];
      if (tier >= 4) Sfx.jackpot(); else Sfx.reveal(tier);
      const rect = track.children[WIN].getBoundingClientRect();
      Fx.confetti(rect.left + rect.width / 2, rect.top + rect.height / 2, [40, 70, 110, 160, 240][tier] || 60, 0.9 + tier * 0.12);
      if (tier >= 4 || (rar === "legendary" && tier >= 3)) Fx.rain(60);
      await wait(650);
      const amtEl = h("span", { text: "0" });
      const extra = r.source === "daily" ? `🔥 Racha: ${r.streak} día(s) · próximo cofre en 24 h` : `🎒 Te quedan ${r.inventory[rar]} ${rc.name.toLowerCase()}${r.inventory[rar] === 1 ? "" : "s"}`;
      const again = r.source === "bought" && r.inventory[rar] > 0;
      reveal.replaceChildren(
        h("div", { class: "cs-badge", style: { "--c": seg.color }, text: seg.name }),
        h("div", { class: "cs-reward" }, coinIcon(), amtEl), h("div", { class: "cs-extra", text: extra }),
        h("div", { class: "cs-actions" },
          again ? h("button", { class: "btn btn-primary btn-lg", onclick: () => close(true) }, icon("chest"), `Abrir otro (${r.inventory[rar]})`) : null,
          h("button", { class: "btn btn-gold btn-lg", onclick: () => close(false) }, "¡Genial!")));
      requestAnimationFrame(() => reveal.classList.add("show"));
      countUp(amtEl, r.reward, 1200);
      setBalance(r.balance);                                  // el saldo del panel sube (ya estaba acreditado en el servidor)
      Sfx.coins(6); setTimeout(() => flyChip(amtEl, $(".bal-chip"), r.reward, { duration: 900, size: 38, fade: true }), 900);
      skipBtn.classList.add("hide");
    })();
  });
}

/* ============================================================
   SECCIÓN "COFRES"
   ============================================================ */
const chestIds = {};                                          // un mismo "intento" reutiliza su id si falla la red (así nunca se cobra/abre doble)
const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 14)}xx`);

async function chestRequest(path, body, key) {
  chestIds[key] = chestIds[key] || newId();
  try {
    const r = await gpost(path, { ...body, request_id: chestIds[key] });
    delete chestIds[key];
    return r;
  } catch (e) {
    if (e.status !== 0) delete chestIds[key];                 // error "de verdad": el próximo intento es uno nuevo
    throw e;
  }
}

VIEWS.cofres = async (root, token) => {
  clearInterval(root.__chestTimer);
  const st = await gget("/api/chests");
  if (!alive(token)) return;
  S.offset = st.now - Date.now() / 1000;
  setBalance(st.balance, false);
  const cfg = st, d = st.daily, nextR = d.next_rarity, rc = cfg.rarities[nextR];
  const refresh = async () => { const y = scrollY; await VIEWS.cofres(root, token); scrollTo(0, y); };

  /* --- apertura (diario o comprado) --- */
  let busy = false;
  async function openFlow(kind, rarity) {
    if (busy) return;
    busy = true;
    try {
      let next = { kind, rarity };
      while (next) {
        let r;
        try {
          r = next.kind === "daily" ? await chestRequest("/api/chests/claim", {}, "daily") : await chestRequest("/api/chests/open", { rarity: next.rarity }, `open:${next.rarity}`);
        } catch (e) { toast(e.message, "err"); break; }
        const out = await playOpening(r, cfg);
        next = out.again ? { kind: "bought", rarity: r.rarity } : null;
      }
    } finally { busy = false; }
    if (alive(token)) refresh();
  }

  /* --- cofre diario --- */
  const claimBtn = h("button", { class: "btn btn-gold btn-lg claim-chest", "data-silent": "1", onclick: () => { Sfx.click(); openFlow("daily"); } });
  const sub = h("p", { class: "note" });
  const tick = () => {
    const t = now();
    if (t >= d.ready_at) {
      claimBtn.disabled = busy; claimBtn.classList.add("ready"); claimBtn.replaceChildren(icon("gift"), `Abrir cofre ${rc.name}`);
      const left = d.expires_at ? d.expires_at - t : null;
      sub.textContent = d.expires_at ? (left > 0 ? `⚠️ Tenés ${fmtClock(left)} para mantener tu racha de ${d.streak} día(s).` : "Se acabó el tiempo: tu racha se reinicia.")
        : d.streak_lost ? "💔 Perdiste tu racha por no reclamar a tiempo. ¡Empezá otra!" : "🎁 Tu primer cofre es gratis.";
    } else {
      claimBtn.disabled = true; claimBtn.classList.remove("ready"); claimBtn.textContent = `Disponible en ${fmtClock(d.ready_at - t)}`;
      sub.textContent = "Mientras esperás podés abrir los cofres que compraste.";
    }
  };
  tick(); root.__chestTimer = setInterval(tick, 1000); S.cleanups.push(() => clearInterval(root.__chestTimer));
  const shown = Math.min(d.next_streak, 7);
  const steps = h("div", { class: "steps" }, st.progression.map((r, i) => h("div", { class: `step r-${r} ${i + 1 < shown ? "done" : i + 1 === shown ? "cur" : ""}` },
    chestSvg(r), h("b", { text: `Día ${i + 1}` }), h("small", { text: i + 1 < shown ? "✓" : cfg.rarities[r].name }))));
  const hero = h("div", { class: `card chest-hero r-${nextR}` },
    h("div", { class: "chest-stage" }, chestSvg(nextR, { cls: "idle" })),
    h("div", {}, h("h2", { text: "Cofre diario" }),
      h("p", { class: "lead", text: `Gratis cada 24 horas. Cuantos más días seguidos, mejor el cofre: hoy te toca el ${rc.name.toLowerCase()} (de ${fmt(rc.min)} a ${fmt(rc.max)} monedas).` }),
      h("div", { class: "chest-stats" }, h("div", {}, h("small", { text: "Racha" }), h("b", { text: `${d.streak} 🔥` })), h("div", {}, h("small", { text: "Mejor racha" }), h("b", { text: String(d.best_streak) })),
        h("div", {}, h("small", { text: "Cofres abiertos" }), h("b", { text: String(d.claims) }))),
      steps, claimBtn, sub));

  /* --- tienda e inventario --- */
  const shop = RAR.map(r => {
    const c = cfg.rarities[r], owned = st.inventory[r];
    let qty = 1;
    const qtyEl = h("b", { text: "1" });
    const buy = h("button", { class: "btn btn-primary", "data-silent": "1" });
    const minus = h("button", { "aria-label": "Menos", text: "−" }), plus = h("button", { "aria-label": "Más", text: "+" });
    const paint = () => {
      qtyEl.textContent = String(qty); minus.disabled = qty <= 1; plus.disabled = qty >= cfg.max_buy;
      buy.replaceChildren(icon("bag"), `Comprar · ${fmt(c.price * qty)}`); buy.disabled = c.price * qty > S.profile.balance;
    };
    minus.addEventListener("click", () => { qty = Math.max(1, qty - 1); Sfx.click(); paint(); });
    plus.addEventListener("click", () => { qty = Math.min(cfg.max_buy, qty + 1); Sfx.click(); paint(); });
    buy.addEventListener("click", async () => {
      buy.disabled = true;
      try {
        const res = await chestRequest("/api/chests/buy", { rarity: r, qty }, `buy:${r}:${qty}`);
        setBalance(res.balance); Sfx.chips(3); Sfx.coins(4);
        toast(`Compraste ${res.qty} cofre${res.qty === 1 ? "" : "s"} ${c.name.toLowerCase()}${res.qty === 1 ? "" : "s"} 🎁`, "gold");
        refresh();
      } catch (e) { toast(e.message, "err"); paint(); }
    });
    const open = h("button", { class: "btn btn-ghost", disabled: owned < 1 || busy, "data-silent": "1", onclick: () => { Sfx.click(); openFlow("bought", r); } }, icon("chest"), owned ? `Abrir (${owned})` : "Abrir");
    paint();
    return h("div", { class: `card chest-card r-${r}` }, h("div", { class: "art" }, chestSvg(r)), h("h3", { text: `Cofre ${c.name}` }),
      h("div", { class: "range", text: `${fmt(c.min)} – ${fmt(c.max)} monedas` }), h("div", { class: `owned ${owned ? "has" : ""}`, text: `En inventario: ${owned}` }),
      h("div", { class: "qty" }, minus, qtyEl, plus), buy, open);
  });

  /* --- probabilidades (todo a la vista) --- */
  const probs = h("details", { class: "how card" }, h("summary", {}, icon("help"), "Probabilidades y premios de cada cofre"),
    h("p", { class: "note", style: { marginBottom: "12px" }, text: "Los cofres solo dan monedas. El premio se sortea en el servidor con estas probabilidades. Los cofres comprados devuelven en promedio menos de lo que cuestan." }),
    h("div", { class: "prob-grid" }, RAR.map(r => {
      const c = cfg.rarities[r];
      return h("div", { class: `r-${r}` }, h("h4", { text: `Cofre ${c.name} · ${fmt(c.price)} monedas` }),
        h("table", { class: "prob-table" }, c.segments.map(s => h("tr", {}, h("td", {}, h("span", { class: "dot", style: { "--c": s.color } }), s.name), h("td", { text: `${String(s.pct).replace(".", ",")}%` }), h("td", { text: `${fmt(s.lo)}–${fmt(s.hi)}` })))),
        h("div", { class: "avg", text: `Promedio: ${fmt(Math.round(c.ev))} monedas (${String(c.return_pct).replace(".", ",")}% del precio)` }));
    })));

  /* --- historial y ranking --- */
  const hist = st.history.length ? st.history.map(x => h("div", { class: `ch-row r-${x.rarity}` }, chestSvg(x.rarity),
    h("div", { class: "main" }, h("b", { text: `Cofre ${cfg.rarities[x.rarity].name}` }), h("small", { text: `${x.source === "daily" ? `Diario · racha ${x.streak}` : "Comprado"} · ${fmtAgo(x.ts)}` })),
    h("div", { class: "amt", text: `+${fmt(x.reward)}` })))
    : [h("p", { class: "muted", text: "Todavía no abriste ningún cofre." })];
  const medals = ["🥇", "🥈", "🥉"];
  const rank = st.ranking.length ? st.ranking.map((e, i) => h("div", { class: `rank-row ${e.id === S.user.id ? "me" : ""}` }, h("div", { class: "rank-pos", text: medals[i] || String(i + 1) }),
    e.avatar ? h("img", { class: "avatar", src: e.avatar, alt: "" }) : h("div", { class: "avatar" }),
    h("div", { class: "rank-name" }, e.name, h("small", { text: `Racha actual: ${e.streak} 🔥` })), h("div", { class: "rank-val", text: `${e.best} ${e.best === 1 ? "día" : "días"}` })))
    : [h("p", { class: "muted", text: "Nadie abrió un cofre diario todavía." })];

  root.replaceChildren(sectionTitle("Cofres", "Un cofre gratis por día, cofres que podés comprar y una apertura con ruleta. Solo dan monedas."), hero,
    h("div", { class: "sec-title" }, h("h2", { text: "Tienda e inventario" }), h("span", { text: "Los cofres comprados no afectan tu racha diaria" })),
    h("div", { class: "grid g4" }, shop), h("div", { style: { height: "16px" } }), probs,
    h("div", { class: "grid g2", style: { marginTop: "16px" } },
      h("div", { class: "card" }, h("h3", { text: "Historial de aperturas" }), h("div", { style: { marginTop: "12px" } }, hist)),
      h("div", { class: "card" }, h("h3", { text: "Ranking de rachas" }), h("div", { style: { marginTop: "12px" } }, rank))));
};
