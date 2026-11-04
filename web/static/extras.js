"use strict";
/* ============================================================
   Funciones extra: logros, historial con gráfico y envío de monedas.
   ============================================================ */

const GAME_NAME = { roulette: "Ruleta", blackjack: "Blackjack", slots: "Tragamonedas" };
const GAME_EMOJI = { roulette: "🎡", blackjack: "🃏", slots: "🎰" };
const OUT_TXT = { blackjack: "Blackjack", win: "Ganó", dealer_bust: "Dealer se pasó", lose: "Perdió", bust: "Se pasó", dealer_blackjack: "Blackjack del dealer", push: "Empate" };
const TIER_NAME = { bronze: "Bronce", silver: "Plata", gold: "Oro" };

function fmtAgo(ts) {
  const s = Math.max(0, now() - ts);
  if (s < 60) return "recién";
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
  return `hace ${Math.floor(s / 86400)} d`;
}
function playDetail(it) {
  if (it.game === "roulette") return `Salió el ${it.detail}`;
  if (it.game === "slots") return it.detail;
  return OUT_TXT[it.detail] || it.detail;
}

/* --- gráfico de línea (ganancia acumulada) --- */
function lineChart(series) {
  const W = 640, H = 210, pad = 16;
  const min = Math.min(0, ...series), max = Math.max(0, ...series), span = max - min || 1;
  const x = i => pad + (W - 2 * pad) * (series.length === 1 ? 0.5 : i / (series.length - 1));
  const y = v => pad + (H - 2 * pad) * (1 - (v - min) / span);
  const last = series[series.length - 1], up = last >= 0, col = up ? "#22c55e" : "#ef4444";
  const pts = series.map((v, i) => [x(i), y(v)]);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L${x(series.length - 1).toFixed(1)} ${(H - pad).toFixed(1)} L${x(0).toFixed(1)} ${(H - pad).toFixed(1)} Z`;
  const svg = document.createElementNS(SVGNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("class", "chart"); svg.setAttribute("preserveAspectRatio", "none");
  svg.innerHTML = `<defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${col}" stop-opacity=".42"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    <line x1="${pad}" y1="${y(0).toFixed(1)}" x2="${W - pad}" y2="${y(0).toFixed(1)}" stroke="rgba(255,255,255,.18)" stroke-dasharray="4 6"/>
    <path d="${area}" fill="url(#cg)" class="chart-area"/>
    <path d="${line}" fill="none" stroke="${col}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" pathLength="1" class="chart-line"/>
    <circle cx="${pts[pts.length - 1][0].toFixed(1)}" cy="${pts[pts.length - 1][1].toFixed(1)}" r="5.5" fill="${col}" stroke="#fff" stroke-width="2" class="chart-dot"/>`;
  return svg;
}

/* ============================================================
   LOGROS
   ============================================================ */
VIEWS.logros = async (root, token, filter = "all") => {
  const [ach, act] = await Promise.all([gget("/api/achievements"), gget("/api/activity")]);
  if (!alive(token)) return;

  /* resumen */
  const frac = ach.total ? ach.unlocked / ach.total : 0, C = 2 * Math.PI * 48;
  const ring = h("div", { class: "ring" });
  const rs = document.createElementNS(SVGNS, "svg");
  rs.setAttribute("viewBox", "0 0 112 112"); rs.setAttribute("width", "112"); rs.setAttribute("height", "112");
  rs.innerHTML = `<defs><linearGradient id="rg2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f3d57a"/><stop offset="1" stop-color="#b8902b"/></linearGradient></defs>
    <circle cx="56" cy="56" r="48" fill="none" stroke="rgba(255,255,255,.09)" stroke-width="9"/>
    <circle cx="56" cy="56" r="48" fill="none" stroke="url(#rg2)" stroke-width="9" stroke-linecap="round" class="ring-arc" stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${C.toFixed(1)}" data-to="${(C * (1 - frac)).toFixed(1)}"/>`;
  ring.append(rs, h("div", { class: "c" }, h("div", {}, h("small", { text: "Logros" }), `${ach.unlocked}/${ach.total}`)));
  const tiers = { bronze: 0, silver: 0, gold: 0 };
  ach.items.filter(a => a.unlocked).forEach(a => { tiers[a.tier]++; });
  const summary = h("div", { class: "card level-card" }, ring, h("div", {},
    h("h3", { text: "Tu colección" }), h("p", { class: "muted", text: ach.unlocked === ach.total ? "¡Lo conseguiste todo! 🏆" : `Te faltan ${ach.total - ach.unlocked} logros.` }),
    h("div", { class: "tier-row" }, ["bronze", "silver", "gold"].map(t => h("span", { class: `pill tier-${t}`, text: `${TIER_NAME[t]}: ${tiers[t]}` })))));

  /* gráfico */
  const chartCard = h("div", { class: "card" }, h("div", { class: "chart-head" },
    h("div", {}, h("h3", { text: "Tu evolución en el casino" }), h("p", { class: "note", text: `Ganancia acumulada en tus últimas ${act.series.length} jugadas del panel` })),
    act.series.length ? h("b", { class: `chart-total ${act.total_net >= 0 ? "pos" : "neg"}`, text: `${act.total_net > 0 ? "+" : act.total_net < 0 ? "−" : ""}${fmt(Math.abs(act.total_net))} 🪙` }) : null),
  act.series.length >= 2 ? lineChart(act.series) : h("div", { class: "empty small" }, h("div", { class: "big", text: "📈" }), h("p", { text: "Jugá unas manos o giros desde el panel y acá vas a ver cómo evoluciona tu saldo." })));

  /* historial */
  const rows = act.items.map(it => h("div", { class: "hist-row" },
    h("div", { class: "hist-ic", text: GAME_EMOJI[it.game] || "🎲" }),
    h("div", { class: "hist-main" }, h("b", { text: GAME_NAME[it.game] || it.game }), h("small", { text: `${playDetail(it)} · apostó ${fmt(it.bet)}` })),
    h("div", { class: "hist-end" }, h("b", { class: it.net > 0 ? "pos" : it.net < 0 ? "neg" : "muted", text: `${it.net > 0 ? "+" : it.net < 0 ? "−" : ""}${fmt(Math.abs(it.net))}` }), h("small", { text: fmtAgo(it.ts) }))));
  const history_ = h("div", { class: "card" }, h("h3", { text: "Últimas jugadas" }),
    rows.length ? h("div", { class: "hist-list" }, rows) : h("p", { class: "muted", style: { marginTop: "8px" }, text: "Todavía no jugaste desde el panel." }));

  /* tarjetas de logros */
  const tabs = h("div", { class: "tabs" }, [["all", "Todos"], ["done", "Conseguidos"], ["todo", "Pendientes"]].map(([k, label]) =>
    h("button", { class: filter === k ? "on" : "", text: label, onclick: () => VIEWS.logros(root, token, k) })));
  const items = ach.items.filter(a => filter === "all" || (filter === "done") === a.unlocked);
  const cards = items.map(a => {
    const p = Math.min(100, Math.round(a.value / a.goal * 100));
    return h("div", { class: `card ach ${a.unlocked ? "on" : "off"} tier-${a.tier}` },
      h("div", { class: "ach-ic", text: a.icon }),
      h("div", { class: "ach-body" }, h("b", { text: a.name }), h("small", { text: a.desc }),
        h("div", { class: `bar ${a.unlocked ? "gold" : ""}` }, h("i", { style: { width: `${p}%` } })),
        h("em", { text: a.unlocked ? `¡Conseguido! · ${TIER_NAME[a.tier]}` : `${fmt(Math.floor(a.value))} / ${fmt(a.goal)}` })),
      a.unlocked ? h("div", { class: "ach-badge" }, icon("star")) : null);
  });

  root.replaceChildren(sectionTitle("Logros", "Tus hitos en el servidor y un resumen de tu actividad en el casino."),
    h("div", { class: "grid g2 split-b" }, summary, chartCard),
    h("div", { class: "sec-title" }, h("h2", { text: "Medallas" }), tabs),
    cards.length ? h("div", { class: "grid g3" }, cards) : h("div", { class: "card empty" }, h("div", { class: "big", text: "🎯" }), h("p", { text: "No hay logros en esta categoría." })),
    h("div", { class: "sec-title" }, h("h2", { text: "Historial" })), history_);
  stagger(root);
  requestAnimationFrame(() => root.querySelectorAll(".ring-arc").forEach(a => { a.style.strokeDashoffset = a.dataset.to; }));
};

/* ============================================================
   ENVIAR MONEDAS (mismas reglas que /pay)
   ============================================================ */
function openPay() {
  const st = { target: null, timer: 0, seq: 0 };
  const maxAmount = Math.min(S.profile.balance, S.profile.limits.pay_max);
  const search = h("input", { class: "txt", placeholder: "Buscá a alguien por nombre…", autocomplete: "off", maxlength: "32", "aria-label": "Buscar persona" });
  const results = h("div", { class: "pay-results" });
  const chosen = h("div", { class: "pay-chosen hide" });
  const amount = h("input", { class: "txt", type: "number", min: "1", max: String(maxAmount), inputmode: "numeric", placeholder: `Monto (máx. ${fmt(maxAmount)})`, "aria-label": "Monto" });
  const send = h("button", { class: "btn btn-primary", disabled: true }, icon("send"), "Enviar");
  const close = () => { ov.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = e => { if (e.key === "Escape") close(); };

  const valid = () => !!st.target && Number.isInteger(+amount.value) && +amount.value >= 1 && +amount.value <= maxAmount;
  const update = () => { send.disabled = !valid(); };
  amount.addEventListener("input", update);

  function choose(m) {
    st.target = m; results.replaceChildren(); search.value = "";
    chosen.classList.remove("hide");
    chosen.replaceChildren(m.avatar ? h("img", { class: "avatar", src: m.avatar, alt: "" }) : h("div", { class: "avatar" }), h("b", { text: m.name }),
      h("button", { class: "icon-btn sm", "aria-label": "Quitar", onclick: () => { st.target = null; chosen.classList.add("hide"); update(); search.focus(); } }, icon("x")));
    update(); amount.focus();
  }
  search.addEventListener("input", () => {
    clearTimeout(st.timer);
    const q = search.value.trim();
    if (!q) return results.replaceChildren();
    st.timer = setTimeout(async () => {
      const mine = ++st.seq;
      try {
        const r = await gget("/api/members", { q });
        if (mine !== st.seq) return;
        results.replaceChildren(...(r.members.length
          ? r.members.map(m => h("button", { class: "member-row", onclick: () => choose(m) }, m.avatar ? h("img", { class: "avatar", src: m.avatar, alt: "" }) : h("div", { class: "avatar" }), h("span", { text: m.name })))
          : [h("p", { class: "note", style: { padding: "8px 4px" }, text: "No encontré a nadie con ese nombre." })]));
      } catch (e) { toast(e.message, "err"); }
    }, 220);
  });

  send.addEventListener("click", async () => {
    if (!valid()) return;
    send.disabled = true;
    try {
      const r = await gpost("/api/pay", { target: st.target.id, amount: +amount.value });
      close(); setBalance(r.balance);
      Sfx.coins(10); Fx.at($(".bal-chip"), "coins", 16);
      toast(`Le mandaste ${fmt(r.amount)} monedas a ${r.to} 💸`, "gold");
    } catch (e) { toast(e.message, "err"); update(); }
  });

  const ov = h("div", { class: "overlay", onclick: e => e.target === ov && close() },
    h("div", { class: "modal pay-modal", role: "dialog", "aria-label": "Enviar monedas" },
      h("h3", { text: "Enviar monedas" }), h("p", { text: `Mandale monedas a otra persona del servidor. Tenés ${fmt(S.profile.balance)} disponibles.` }),
      h("div", { class: "field" }, h("label", { text: "Para" }), chosen, search, results),
      h("div", { class: "field" }, h("label", { text: "Monto" }), amount),
      h("div", { class: "row" }, h("button", { class: "btn btn-ghost", text: "Cancelar", onclick: close }), send)));
  document.body.append(ov);
  document.addEventListener("keydown", onKey);
  search.focus();
}


/* ============================================================
   TAGS DE COLORES
   ============================================================ */
VIEWS.tags = async (root, token) => {
  const data = await gget("/api/tags");
  if (!alive(token)) return;
  setBalance(data.balance, false);
  const reload = () => VIEWS.tags(root, token);
  const run = async (btn, path, body, msg) => {
    btn.disabled = true;
    try {
      const r = await gpost(path, { ...body });
      setBalance(r.balance);
      toast(msg(r), "gold");
      reload();
    } catch (e) { toast(e.message, "err"); btn.disabled = false; }
  };
  const cards = data.items.map(it => {
    const poor = !it.owned && it.price > data.balance;
    let btn;
    if (it.equipped) {
      btn = h("button", { class: "btn btn-ghost", text: "Sacar tag" });
      btn.addEventListener("click", () => run(btn, "/api/tags/equip", { tag: null }, () => "Te saqué el tag."));
    } else if (it.owned) {
      btn = h("button", { class: "btn btn-primary", text: "Usar" });
      btn.addEventListener("click", () => run(btn, "/api/tags/equip", { tag: it.key }, () => `Ahora llevás el tag ${it.name} ${it.emoji}`));
    } else {
      btn = h("button", { class: "btn btn-primary", disabled: poor, text: poor ? "Saldo insuficiente" : "Comprar" });
      btn.addEventListener("click", async () => {
        if (!await confirmBox({ title: `Comprar tag ${it.name}`, text: `Se descontarán ${fmt(it.price)} monedas y el bot te va a dar el rol de color en Discord. Es tuyo para siempre: después podés cambiar de color gratis.`, ok: "Comprar" })) return;
        run(btn, "/api/tags/buy", { tag: it.key }, () => `¡Tag ${it.name} comprado! ${it.emoji}`);
      });
    }
    const glow = it.key === "negro" ? "#8a8a9c" : it.color;      // el negro puro no se ve sobre fondo oscuro
    const status = it.equipped ? h("span", { class: "tag-state on", text: "Puesto" }) : it.owned ? h("span", { class: "tag-state", text: "Comprado" }) : null;
    return h("div", { class: `card shop-card tag-card ${it.equipped ? "worn" : ""}`, style: { "--rc": glow } },
      h("div", { class: "role-name" }, h("i", { class: "swatch", style: { background: it.color } }), h("span", { text: `Tag ${it.name}` }), status),
      h("div", { class: "tag-preview" }, h("span", { style: { color: it.key === "negro" ? "#fff" : it.color, textShadow: it.key === "negro" ? "0 0 0 #000" : "none" }, class: it.key === "negro" ? "name-black" : "", text: S.user.name })),
      it.owned ? h("div", { class: "note", text: "Ya es tuyo" }) : h("div", { class: "price" }, coinIcon(), fmt(it.price)), btn);
  });
  root.replaceChildren(
    sectionTitle("Tags de colores", "Comprá un tag y el bot te da un rol con ese color en Discord. Una vez comprado, cambiás entre tus tags gratis."),
    h("div", { class: "grid g3" }, cards));
};
