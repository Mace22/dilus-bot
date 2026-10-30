"use strict";
/* ============================================================
   Dilu's Bot · Panel — todo el front en un solo archivo, sin librerías.
   Los textos de personas (nombres, roles) siempre se insertan como texto, nunca como HTML.
   ============================================================ */

/* ---------- utilidades ---------- */
const SVGNS = "http://www.w3.org/2000/svg";
const $ = (sel, root = document) => root.querySelector(sel);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const fmt = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
const short = n => (n >= 1000 ? (n / 1000).toFixed(n % 1000 ? 1 : 0).replace(".", ",").replace(",0", "") + "K" : String(n));
const pct = c => (c / 37 * 100).toFixed(1).replace(".", ",") + "%";

function h(tag, props, ...kids) {
  const svg = tag.startsWith("svg:");
  const el = svg ? document.createElementNS(SVGNS, tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "style" && typeof v === "object") {
      for (const [sk, sv] of Object.entries(v)) sk.startsWith("--") ? el.style.setProperty(sk, sv) : (el.style[sk] = sv);
    } else if (k === "text") el.textContent = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const ICONS = {
  home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
  wheel: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/><line x1="12" y1="2" x2="12" y2="9"/><line x1="12" y1="15" x2="12" y2="22"/><line x1="2" y1="12" x2="9" y2="12"/><line x1="15" y1="12" x2="22" y2="12"/>',
  cards: '<rect x="3" y="4" width="13" height="17" rx="2"/><path d="M8 2h11a2 2 0 0 1 2 2v14"/><path d="M9.5 10.5c.8-1.5 3-1.2 3 .5 0 1.5-3 3-3 3s-3-1.5-3-3c0-1.7 2.2-2 3-.5z"/>',
  bag: '<path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/>',
  trophy: '<circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/>',
  gift: '<polyline points="20 12 20 22 4 22 4 12"/><rect x="2" y="7" width="20" height="5"/><line x1="12" y1="22" x2="12" y2="7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/>',
  work: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  chevron: '<polyline points="6 9 12 15 18 9"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
  undo: '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
};
function icon(name, cls = "ic") {
  const s = document.createElementNS(SVGNS, "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  for (const [k, v] of Object.entries({ fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round", class: cls })) s.setAttribute(k, v);
  s.innerHTML = ICONS[name] || "";   // iconos propios, texto fijo
  return s;
}
function coinIcon() {
  const s = document.createElementNS(SVGNS, "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("class", "coin");
  s.innerHTML = '<circle cx="12" cy="12" r="11" fill="#e8c35a"/><circle cx="12" cy="12" r="8.2" fill="none" stroke="#b8902b" stroke-width="1.6"/><text x="12" y="16.4" text-anchor="middle" font-size="11.5" font-weight="800" fill="#8a6414" font-family="Outfit, sans-serif">$</text>';
  return s;
}

/* ---------- estado ---------- */
const S = { user: null, guilds: [], gid: null, profile: null, offset: 0, routeToken: 0, cleanups: [] };
const now = () => Date.now() / 1000 + S.offset;
const fmtClock = sec => {
  sec = Math.max(0, Math.ceil(sec));
  const p = n => String(n).padStart(2, "0");
  return `${p(Math.floor(sec / 3600))}:${p(Math.floor(sec % 3600 / 60))}:${p(sec % 60)}`;
};
const fmtDur = sec => {
  const hrs = Math.floor(sec / 3600), min = Math.floor(sec % 3600 / 60);
  return hrs ? `${hrs} h ${min} min` : `${min} min`;
};
const guildName = () => (S.guilds.find(g => g.id === S.gid) || {}).name || "";

/* ---------- red ---------- */
class ApiError extends Error {
  constructor(msg, status, data) { super(msg); this.status = status; this.data = data || {}; }
}
async function api(path, { method = "GET", body, query } = {}) {
  const url = new URL(path, location.origin);
  for (const [k, v] of Object.entries(query || {})) url.searchParams.set(k, v);
  let res;
  try {
    res = await fetch(url, {
      method, credentials: "same-origin",
      headers: { "X-Requested-With": "fetch", ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch { throw new ApiError("No pude conectar con el servidor.", 0); }
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && path !== "/api/session") { S.user = null; render(); throw new ApiError(data.error || "Tu sesión venció.", 401, data); }
  if (!res.ok) throw new ApiError(data.error || "Algo salió mal.", res.status, data);
  return data;
}
const gget = (path, q = {}) => api(path, { query: { guild: S.gid, ...q } });
const gpost = (path, body = {}) => api(path, { method: "POST", body: { guild: S.gid, ...body } });

/* ---------- avisos y ventanas ---------- */
function toast(text, kind = "") {
  const t = h("div", { class: `toast ${kind}` }, text);
  $("#toasts").append(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 320); }, 3800);
}
function confirmBox({ title, text, ok = "Confirmar" }) {
  return new Promise(resolve => {
    const done = v => { ov.remove(); resolve(v); };
    const ov = h("div", { class: "overlay", onclick: e => e.target === ov && done(false) },
      h("div", { class: "modal", role: "dialog" },
        h("h3", { text: title }), h("p", { text }),
        h("div", { class: "row" },
          h("button", { class: "btn btn-ghost", text: "Cancelar", onclick: () => done(false) }),
          h("button", { class: "btn btn-primary", text: ok, onclick: () => done(true) }))));
    document.body.append(ov);
  });
}

/* ---------- saldo (se anima y se refleja en todos lados) ---------- */
let shownBal = 0, balRaf = 0;
function balSpan() { return h("span", { class: "js-bal", text: fmt(shownBal) }); }
function setBalance(n, animate = true) {
  S.profile.balance = n;
  cancelAnimationFrame(balRaf);
  const paint = v => document.querySelectorAll(".js-bal").forEach(e => { e.textContent = fmt(v); });
  if (!animate) { shownBal = n; paint(n); return; }
  const from = shownBal, t0 = performance.now();
  const tick = t => {
    const k = Math.min(1, (t - t0) / 700), e = 1 - Math.pow(1 - k, 3);
    shownBal = from + (n - from) * e; paint(shownBal);
    if (k < 1) balRaf = requestAnimationFrame(tick); else shownBal = n;
  };
  balRaf = requestAnimationFrame(tick);
}
function burst(host, text) {
  const f = h("div", { class: "floaty", text });
  host.append(f);
  setTimeout(() => f.remove(), 1600);
}

/* ============================================================
   Pantallas generales
   ============================================================ */
function mount(node) { $("#app").replaceChildren(node); }

function renderLogin(message) {
  const params = new URLSearchParams(location.search);
  const errs = { denied: "Cancelaste el inicio de sesión.", state: "El inicio de sesión venció. Probá de nuevo.", login: "No pude iniciar sesión con Discord. Probá de nuevo." };
  const err = message || errs[params.get("error")];
  mount(h("div", { class: "login" },
    h("div", { class: "card login-card" },
      h("div", { class: "logo", text: "D" }),
      h("h1", { text: "Dilu's Bot" }),
      h("p", { text: "Tu economía, tus estadísticas y los juegos del servidor, ahora en un solo lugar." }),
      err ? h("div", { class: "notice", text: err }) : null,
      h("div", { class: "features" },
        h("div", { text: "🪙 Saldo y recompensas" }), h("div", { text: "📊 Nivel y estadísticas" }),
        h("div", { text: "🎡 Ruleta en vivo" }), h("div", { text: "🃏 Blackjack" }),
        h("div", { text: "🛒 Tienda de roles" }), h("div", { text: "🏆 Rankings" })),
      h("a", { class: "btn btn-discord btn-lg", href: "/auth/login" }, icon("chat"), "Continuar con Discord"))));
}

function renderNoGuilds() {
  mount(h("div", { class: "login" }, h("div", { class: "card login-card" },
    h("div", { class: "logo", text: "D" }), h("h1", { text: "Sin servidores en común" }),
    h("p", { text: "No compartís ningún servidor con el bot. Entrá a un servidor donde esté Dilu's Bot y volvé a iniciar sesión." }),
    h("button", { class: "btn btn-primary btn-lg", text: "Cerrar sesión", onclick: logout }))));
}

async function logout() {
  try { await api("/auth/logout", { method: "POST", body: {} }); } catch { /* da igual */ }
  S.user = null; S.profile = null;
  history.replaceState(null, "", "/");
  renderLogin();
}

/* ---------- armazón: barra lateral + barra superior ---------- */
const NAV = [
  { id: "inicio", label: "Inicio", icon: "home" },
  { id: "ruleta", label: "Ruleta", icon: "wheel" },
  { id: "blackjack", label: "Blackjack", icon: "cards" },
  { id: "tienda", label: "Tienda", icon: "bag" },
  { id: "ranking", label: "Ranking", icon: "trophy" },
];

function guildIcon(g) {
  return h("span", { class: "guild-ic" }, g.icon ? h("img", { src: g.icon, alt: "" }) : (g.name || "?").trim().slice(0, 1).toUpperCase());
}

function renderShell() {
  const nav = h("nav", { class: "nav" }, NAV.map(n => h("a", { href: `#/${n.id}`, dataset: { id: n.id } }, icon(n.icon), h("span", { text: n.label }))));
  const side = h("aside", { class: "side" },
    h("div", { class: "brand" }, h("div", { class: "logo", text: "D" }), h("div", {}, h("b", { text: "Dilu's Bot" }), h("small", { text: "Panel web" }))),
    nav, h("div", { class: "side-foot", text: "Todo lo que ves acá es el mismo saldo y las mismas reglas que en Discord." }));

  /* selector de servidor */
  const gMenu = h("div", { class: "menu hide" }, S.guilds.map(g => h("button", {
    class: g.id === S.gid ? "on" : "", onclick: () => { gMenu.classList.add("hide"); switchGuild(g.id); },
  }, guildIcon(g), h("span", { text: g.name }))));
  const gBtn = h("button", { class: "guild-btn", onclick: e => { e.stopPropagation(); uMenu.classList.add("hide"); gMenu.classList.toggle("hide"); } },
    guildIcon(S.guilds.find(g => g.id === S.gid)), h("span", { text: guildName() }), icon("chevron"));

  /* menú de usuario */
  const uMenu = h("div", { class: "menu right hide" },
    h("button", { onclick: () => { uMenu.classList.add("hide"); refreshAll(); } }, icon("refresh"), "Actualizar datos"),
    h("button", { onclick: logout }, icon("logout"), "Cerrar sesión"));
  const uBtn = h("button", { class: "user-btn", "aria-label": "Cuenta", onclick: e => { e.stopPropagation(); gMenu.classList.add("hide"); uMenu.classList.toggle("hide"); } },
    h("img", { class: "avatar", src: S.user.avatar, alt: "" }));
  document.addEventListener("click", () => { gMenu.classList.add("hide"); uMenu.classList.add("hide"); });

  const top = h("header", { class: "top" },
    h("div", { class: "menu-wrap" }, gBtn, gMenu), h("div", { class: "grow" }),
    h("div", { class: "bal-chip", title: "Tu saldo" }, coinIcon(), balSpan()),
    h("div", { class: "menu-wrap" }, uBtn, uMenu));

  mount(h("div", { class: "shell" }, side, h("div", { class: "main" }, top, h("main", { id: "view" }))));
  setBalance(S.profile.balance, false);
}

async function loadProfile() {
  S.profile = await gget("/api/profile");
  S.offset = S.profile.now - Date.now() / 1000;
}
async function switchGuild(id) {
  if (id === S.gid) return;
  S.gid = id;
  try { localStorage.setItem("dilus_gid", id); } catch { /* sin almacenamiento */ }
  await loadProfile();
  renderShell(); route();
}
async function refreshAll() {
  await loadProfile(); setBalance(S.profile.balance, false); route(); toast("Datos actualizados", "ok");
}

/* ---------- router ---------- */
const VIEWS = {};
function route() {
  if (!S.user) return;
  const id = (location.hash.replace(/^#\/?/, "") || "inicio");
  const name = VIEWS[id] ? id : "inicio";
  S.cleanups.splice(0).forEach(fn => { try { fn(); } catch { /* ya no existe */ } });
  const token = ++S.routeToken;
  document.querySelectorAll(".nav a").forEach(a => a.classList.toggle("on", a.dataset.id === name));
  const view = $("#view");
  if (!view) return;
  view.replaceChildren(h("div", { class: "grid g3" }, [1, 2, 3].map(() => h("div", { class: "skeleton", style: { height: "150px" } }))));
  view.style.animation = "none"; void view.offsetWidth; view.style.animation = "";
  VIEWS[name](view, token).catch(e => {
    if (token !== S.routeToken) return;
    view.replaceChildren(h("div", { class: "card empty" }, h("div", { class: "big", text: "😵" }), h("p", { text: e.message || "No pude cargar esta sección." }),
      h("button", { class: "btn btn-primary", text: "Reintentar", onclick: route })));
  });
}
const alive = token => token === S.routeToken;
const sectionTitle = (title, sub) => h("div", { class: "page-title" }, h("h1", { text: title }), sub ? h("p", { text: sub }) : null);

/* ============================================================
   INICIO
   ============================================================ */
function claimCard(cfg) {
  const bar = h("i"), time = h("span", { class: "note" });
  const btn = h("button", { class: "btn btn-primary btn-lg" });
  const card = h("div", { class: "card claim" },
    h("div", { class: "claim-head" }, h("div", { class: "claim-ic" }, icon(cfg.icon)), h("div", {}, h("h3", { text: cfg.title }), h("p", { text: cfg.desc }))),
    cfg.extra || null, h("div", { class: "bar" }, bar), time, btn);

  function tick() {
    const left = cfg.readyAt() - now();
    if (left <= 0) {
      btn.disabled = false; btn.classList.add("ready"); btn.replaceChildren(icon("gift"), cfg.label());
      bar.style.width = "100%"; time.textContent = "¡Listo para reclamar!";
    } else {
      btn.disabled = true; btn.classList.remove("ready"); btn.textContent = `Disponible en ${fmtClock(left)}`;
      bar.style.width = Math.max(2, Math.min(100, (1 - left / cfg.total) * 100)) + "%"; time.textContent = "";
    }
  }
  tick();
  const timer = setInterval(tick, 1000);
  S.cleanups.push(() => clearInterval(timer));
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try { await cfg.claim(card); }
    catch (e) { toast(e.message, "err"); if (e.data && e.data.ready_at) cfg.setReady(e.data.ready_at); }
    tick();
  });
  return card;
}

VIEWS.inicio = async (root, token) => {
  await loadProfile();
  if (!alive(token)) return;
  setBalance(S.profile.balance, false);
  const p = S.profile, lv = p.level, d = p.daily;

  /* encabezado */
  const hero = h("section", { class: "card hero" },
    h("div", { class: "hero-user" },
      h("img", { class: "avatar", src: S.user.avatar, alt: "" }),
      h("div", { style: { minWidth: 0 } }, h("h1", { text: S.user.name }), h("p", { class: "muted", text: guildName() }),
        h("div", { class: "tags" },
          h("span", { class: "pill violet", text: `Nivel ${lv.level}` }),
          h("span", { class: "pill gold", text: `#${p.eco_rank} en economía` }),
          lv.rank ? h("span", { class: "pill", text: `#${lv.rank} en niveles` }) : null))),
    h("div", { class: "hero-bal" }, h("small", { text: "Tu saldo" }), h("div", { class: "big-num" }, coinIcon(), balSpan())));

  /* reclamos */
  const dots = h("div", { class: "streak" });
  const paintStreak = () => {
    dots.replaceChildren(h("span", { text: `🔥 Racha: ${d.streak} día${d.streak === 1 ? "" : "s"} · ` }),
      ...Array.from({ length: d.cap + 1 }, (_, i) => h("i", { class: i < d.streak ? "on" : "" })));
  };
  paintStreak();
  const daily = claimCard({
    icon: "gift", title: "Recompensa diaria", desc: `${fmt(d.base)} monedas + ${fmt(d.bonus)} por cada día de racha.`, total: 86400, extra: dots,
    readyAt: () => d.ready_at, setReady: t => { d.ready_at = t; },
    label: () => `Reclamar +${fmt(d.next_reward)}`,
    claim: async card => {
      const r = await gpost("/api/claim/daily");
      d.ready_at = r.ready_at; d.streak = r.streak; d.next_reward = d.base + Math.min(r.streak, d.cap) * d.bonus;
      setBalance(r.balance); burst(card, `+${fmt(r.reward)}`); paintStreak();
      toast(`¡Reclamaste ${fmt(r.reward)} monedas! Racha de ${r.streak} día${r.streak === 1 ? "" : "s"} 🔥`, "gold");
    },
  });
  const w = p.work;
  const work = claimCard({
    icon: "work", title: "Trabajar", desc: `Ganá entre ${fmt(w.min)} y ${fmt(w.max)} monedas cada ${fmtDur(w.cooldown)}.`, total: w.cooldown,
    readyAt: () => w.ready_at, setReady: t => { w.ready_at = t; },
    label: () => "Ir a trabajar",
    claim: async card => {
      const r = await gpost("/api/claim/work");
      w.ready_at = r.ready_at; setBalance(r.balance); burst(card, `+${fmt(r.reward)}`);
      toast(`${r.job} Ganaste ${fmt(r.reward)} monedas.`, "gold");
    },
  });

  /* estadísticas */
  const frac = lv.xp_need ? Math.min(1, lv.xp_in / lv.xp_need) : 0, C = 2 * Math.PI * 48;
  const ring = h("div", { class: "ring" });
  const rs = document.createElementNS(SVGNS, "svg");
  rs.setAttribute("viewBox", "0 0 112 112"); rs.setAttribute("width", "112"); rs.setAttribute("height", "112");
  rs.innerHTML = `<defs><linearGradient id="rg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8b5cf6"/><stop offset="1" stop-color="#d946ef"/></linearGradient></defs>
    <circle cx="56" cy="56" r="48" fill="none" stroke="rgba(255,255,255,.09)" stroke-width="9"/>
    <circle cx="56" cy="56" r="48" fill="none" stroke="url(#rg)" stroke-width="9" stroke-linecap="round" stroke-dasharray="${(frac * C).toFixed(1)} ${C.toFixed(1)}"/>`;
  ring.append(rs, h("div", { class: "c" }, h("div", {}, h("small", { text: "Nivel" }), String(lv.level))));
  const levelCard = h("div", { class: "card level-card" }, ring, h("div", {},
    h("h3", { text: "Tu progreso" }), h("p", { class: "muted", text: `${fmt(lv.xp_in)} / ${fmt(lv.xp_need)} XP para el nivel ${lv.level + 1}` }),
    h("div", { class: "bar gold", style: { margin: "12px 0 6px" } }, h("i", { style: { width: Math.round(frac * 100) + "%" } })),
    h("p", { class: "note", text: `${fmt(lv.xp_total)} XP en total` })));
  const stat = (label, value, sub) => h("div", { class: "card stat" }, h("small", { text: label }), h("b", { text: value }), sub ? h("em", { text: sub }) : null);
  const stats = h("div", { class: "grid g2" },
    stat("Mensajes enviados", fmt(lv.messages)), stat("Tiempo en voz", fmtDur(lv.voice_seconds), "en canales de voz"),
    stat("Puesto en economía", `#${p.eco_rank}`, "entre todo el servidor"), stat("Puesto en niveles", lv.rank ? `#${lv.rank}` : "—", lv.rank ? "por XP total" : "todavía sin XP"));

  /* casino */
  const casinoCard = (key, title, emoji) => {
    const c = p.casino[key], net = c ? c.returned - c.wagered : 0;
    return h("div", { class: "card" }, h("h3", { text: `${emoji} ${title}` }),
      c ? h("div", { class: "grid g2", style: { marginTop: "12px" } },
        h("div", { class: "stat" }, h("small", { text: "Partidas" }), h("b", { text: fmt(c.played) })),
        h("div", { class: "stat" }, h("small", { text: "Balance" }), h("b", { class: net >= 0 ? "pos" : "neg", text: (net > 0 ? "+" : "") + fmt(net) })),
        h("div", { class: "stat" }, h("small", { text: "Apostado" }), h("b", { text: fmt(c.wagered) })),
        h("div", { class: "stat" }, h("small", { text: "Mejor premio" }), h("b", { class: "gold", text: "+" + fmt(c.best) })))
        : h("p", { class: "muted", style: { marginTop: "8px" }, text: "Todavía no jugaste desde el panel. ¡Animate!" }));
  };
  const play = (id, big, title, text) => h("a", { class: "card tile-link", href: `#/${id}` }, h("div", { class: "big", text: big }), h("div", {}, h("h3", { text: title }), h("p", { class: "muted", text })));

  root.replaceChildren(hero,
    h("div", { class: "sec-title" }, h("h2", { text: "Recompensas" }), h("span", { text: "Reclamalas desde acá o con /daily y /trabajar" })),
    h("div", { class: "grid g2" }, daily, work),
    h("div", { class: "sec-title" }, h("h2", { text: "Tus estadísticas" }), h("span", { text: "Salen de tu actividad en Discord" })),
    h("div", { class: "grid g2", style: { gridTemplateColumns: "minmax(0,1.1fr) minmax(0,1fr)" } }, levelCard, stats),
    h("div", { class: "sec-title" }, h("h2", { text: "Casino" })),
    h("div", { class: "grid g2" }, casinoCard("roulette", "Ruleta", "🎡"), casinoCard("blackjack", "Blackjack", "🃏")),
    h("div", { class: "sec-title" }, h("h2", { text: "Jugá ahora" })),
    h("div", { class: "grid g2" }, play("ruleta", "🎡", "Ruleta europea", "Fichas, tablero y rueda animada"), play("blackjack", "🃏", "Blackjack", "Contra el dealer, paga 3 a 2")));
};

/* ============================================================
   TIENDA
   ============================================================ */
VIEWS.tienda = async (root, token) => {
  const data = await gget("/api/shop");
  if (!alive(token)) return;
  setBalance(data.balance, false);
  const items = data.items.map(it => {
    const poor = it.price > S.profile.balance;
    const btn = h("button", { class: `btn ${it.owned ? "btn-ghost" : "btn-primary"}`, disabled: it.owned || !it.available || poor, text: it.owned ? "Ya lo tenés ✓" : !it.available ? "No disponible" : poor ? "Saldo insuficiente" : "Comprar" });
    btn.addEventListener("click", async () => {
      if (!await confirmBox({ title: `Comprar ${it.name}`, text: `Se descontarán ${fmt(it.price)} monedas de tu saldo y recibirás el rol en Discord.`, ok: "Comprar" })) return;
      btn.disabled = true;
      try {
        const r = await gpost("/api/shop/buy", { role: it.id });
        setBalance(r.balance); toast(`¡Listo! Ahora tenés el rol ${r.role} 🎉`, "gold");
        VIEWS.tienda(root, token);
      } catch (e) { toast(e.message, "err"); btn.disabled = false; }
    });
    return h("div", { class: "card shop-card", style: it.color ? { "--rc": it.color } : {} },
      h("div", { class: "role-name" }, h("i"), h("span", { text: it.name })),
      h("div", { class: "price" }, coinIcon(), fmt(it.price)), btn);
  });
  root.replaceChildren(sectionTitle("Tienda de roles", "Cambiá tus monedas por roles exclusivos del servidor."),
    items.length ? h("div", { class: "grid g3" }, items)
      : h("div", { class: "card empty" }, h("div", { class: "big", text: "🛒" }), h("p", { text: "Este servidor todavía no tiene roles en la tienda." }),
        h("p", { class: "note", text: "Un admin puede agregarlos con /economia tienda_agregar." })));
};

/* ============================================================
   RANKING
   ============================================================ */
VIEWS.ranking = async (root, token, kind = "eco") => {
  const data = await gget("/api/leaderboard", { type: kind });
  if (!alive(token)) return;
  const tabs = h("div", { class: "tabs" },
    h("button", { class: kind === "eco" ? "on" : "", text: "🪙 Más ricos", onclick: () => VIEWS.ranking(root, token, "eco") }),
    h("button", { class: kind === "xp" ? "on" : "", text: "⭐ Niveles", onclick: () => VIEWS.ranking(root, token, "xp") }));
  const medals = ["🥇", "🥈", "🥉"];
  const rows = data.entries.map((e, i) => h("div", { class: `rank-row ${e.id === S.user.id ? "me" : ""}` },
    h("div", { class: "rank-pos", text: medals[i] || String(i + 1) }),
    e.avatar ? h("img", { class: "avatar", src: e.avatar, alt: "" }) : h("div", { class: "avatar" }),
    h("div", { class: "rank-name" }, e.name, e.sub ? h("small", { text: e.sub }) : null),
    h("div", { class: "rank-val", text: kind === "xp" ? `Nivel ${e.level} · ${fmt(e.value)} XP` : `${fmt(e.value)} 🪙` })));
  const me = data.me;
  root.replaceChildren(sectionTitle("Ranking", `Los mejores de ${guildName()}.`), tabs,
    rows.length ? h("div", { class: "card" }, rows) : h("div", { class: "card empty" }, h("div", { class: "big", text: "🏆" }), h("p", { text: "Todavía no hay nadie en este ranking." })),
    h("p", { class: "note", style: { marginTop: "14px", textAlign: "center" }, text: me.position ? `Tu puesto: #${me.position} · ${fmt(me.value)} ${kind === "xp" ? "XP" : "monedas"}` : "Todavía no figurás en este ranking." }));
};

/* ============================================================
   RULETA
   ============================================================ */
const RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);
const ORDER = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26];
const STEP = 360 / 37;
const colorOf = n => (n === 0 ? "green" : RED.has(n) ? "red" : "black");
const COLOR_ES = { red: "Rojo", black: "Negro", green: "Verde" };
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
  let grad = g.createRadialGradient(cx, cx * .8, R * .2, cx, cx, R); grad.addColorStop(0, "#7a4a2a"); grad.addColorStop(1, "#2b160b");
  circle(R, grad); circle(R * .965, "#5a3320"); circle(R * .945, null, "#e8c35a", px * .006);
  circle(R * .92, "#14151b"); circle(R * .88, null, "#464b5a", px * .003); circle(R * .80, "#aa965a");
  const rOut = R * .79, rIn = R * .56;
  ORDER.forEach((n, i) => {
    const a0 = (i * STEP - 90 - STEP / 2) * Math.PI / 180, a1 = a0 + STEP * Math.PI / 180;
    g.beginPath(); g.arc(cx, cx, rOut, a0, a1); g.arc(cx, cx, rIn, a1, a0, true); g.closePath();
    g.fillStyle = n === 0 ? "#0f7a4a" : RED.has(n) ? "#b91c2f" : "#15151d"; g.fill();
    g.strokeStyle = "#cdbe8c"; g.lineWidth = px * .0025; g.stroke();
  });
  circle(rIn, "#c8a546"); circle(rIn * .95, "#28190f");
  grad = g.createRadialGradient(cx * .95, cx * .9, 2, cx, cx, rIn * .55); grad.addColorStop(0, "#9a6a3f"); grad.addColorStop(1, "#4a2e1a");
  circle(rIn * .55, grad, "#e8c35a", px * .006);
  g.strokeStyle = "#e8c35a"; g.lineWidth = px * .012; g.lineCap = "round";
  for (let k = 0; k < 4; k++) { const a = k * Math.PI / 2; g.beginPath(); g.moveTo(cx, cx); g.lineTo(cx + rIn * .55 * Math.cos(a), cx + rIn * .55 * Math.sin(a)); g.stroke(); }
  circle(rIn * .14, "#f4e4a0", "#e8c35a", px * .003);
  g.fillStyle = "#fff"; g.font = `700 ${Math.round(px * .047)}px Outfit, Inter, sans-serif`; g.textAlign = "center"; g.textBaseline = "middle";
  ORDER.forEach((n, i) => {
    g.save(); g.translate(cx, cx); g.rotate((i * STEP - 90) * Math.PI / 180); g.translate(R * .675, 0); g.fillText(String(n), 0, 0); g.restore();
  });
  return c;
}

function createWheel(canvas, size) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2), px = Math.round(size * dpr);
  canvas.width = canvas.height = px;
  const ctx = canvas.getContext("2d"), base = drawWheelBase(px), half = px / 2 - 2;
  const rTrack = half * .855, rPocket = half * .675, br = px * .017;
  let rot = Math.random() * 360, phi = null, ballR = rPocket, raf = 0, last = performance.now(), spinning = false, dead = false;

  function render() {
    ctx.clearRect(0, 0, px, px);
    ctx.save(); ctx.translate(px / 2, px / 2); ctx.rotate(-rot * Math.PI / 180); ctx.drawImage(base, -px / 2, -px / 2); ctx.restore();
    if (phi == null) return;
    const th = (rot + phi) * Math.PI / 180, x = px / 2 + ballR * Math.cos(th), y = px / 2 - ballR * Math.sin(th);
    ctx.beginPath(); ctx.arc(x + br * .3, y + br * .45, br, 0, Math.PI * 2); ctx.fillStyle = "rgba(0,0,0,.4)"; ctx.fill();
    const gr = ctx.createRadialGradient(x - br * .35, y - br * .35, br * .1, x, y, br); gr.addColorStop(0, "#fff"); gr.addColorStop(1, "#bfc3d0");
    ctx.beginPath(); ctx.arc(x, y, br, 0, Math.PI * 2); ctx.fillStyle = gr; ctx.fill();
  }
  function loop(t) {
    if (dead) return;
    if (!spinning) rot += (t - last) / 1000 * 4;          // gira despacito mientras espera
    last = t; render(); raf = requestAnimationFrame(loop);
  }
  raf = requestAnimationFrame(loop);

  const smooth = x => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  return {
    destroy() { dead = true; cancelAnimationFrame(raf); },
    spinTo(number, ms = 6500) {
      return new Promise(resolve => {
        spinning = true;
        const pocket = 90 - ORDER.indexOf(number) * STEP, w0 = rot, lapsW = .6, lapsB = 3.6, t0 = performance.now();
        const step = t => {
          if (dead) return resolve();
          const u = Math.min(1, (t - t0) / ms), p = 1 - Math.pow(1 - u, 3);
          rot = w0 + 360 * lapsW * p;
          phi = pocket + 360 * lapsB * (1 - p);
          const s = smooth((u - .60) / .34);
          ballR = rTrack + (rPocket - rTrack) * s;
          if (u > .60 && u < .97) ballR += Math.abs(Math.sin((u - .60) * 26)) * Math.pow(1 - s, 2) * half * .07;
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
    const el = h("button", { class: `zone ${cls}`, dataset: { key }, style: grid, "aria-label": betInfo(key).label, onclick: () => onPick(key), onmouseenter: () => onInfo(key), onfocus: () => onInfo(key),
      oncontextmenu: e => { e.preventDefault(); onPick(key, true); } }, ...kids);
    zones.set(key, el); return el;
  };
  const cells = [mk("n0", "green", { gridRow: "1 / 4", gridColumn: "1" }, "0")];
  for (let n = 1; n <= 36; n++) {
    const c = Math.floor((n - 1) / 3), r = 2 - (n - 1) % 3;
    cells.push(mk(`n${n}`, colorOf(n), { gridColumn: String(2 + c), gridRow: String(1 + r) }, String(n)));
  }
  [3, 2, 1].forEach((k, r) => cells.push(mk(`col${k}`, "out", { gridColumn: "14", gridRow: String(1 + r) }, "2:1")));
  [1, 2, 3].forEach(k => cells.push(mk(`doc${k}`, "out wide", { gridColumn: `${2 + (k - 1) * 4} / span 4`, gridRow: "4" }, `${k}ª docena`)));
  const outs = [["low", "1-18"], ["even", "PAR"], ["red", null], ["black", null], ["odd", "IMPAR"], ["high", "19-36"]];
  outs.forEach(([key, label], i) => cells.push(mk(key, "out wide", { gridColumn: `${2 + i * 2} / span 2`, gridRow: "5" }, label || h("span", { class: `dia ${key}` }))));
  const el = h("div", { class: "board" }, cells);
  return { el, zones };
}

VIEWS.ruleta = async (root, token) => {
  const lim = S.profile.limits;
  const chipVals = [10, 50, 100, 500, 1000, 5000].filter(v => v >= lim.rl_min && v <= lim.rl_max);
  const st = { chip: chipVals.includes(100) ? 100 : chipVals[0], bets: [], last: [], busy: false };
  let history = [];
  try { history = (await gget("/api/roulette/history")).history; } catch { /* sin historial */ }
  if (!alive(token)) return;

  const canvas = h("canvas"), pop = h("div", { class: "wheel-pop" }), histEl = h("div", { class: "hist" });
  const wheel = createWheel(canvas, 400);
  S.cleanups.push(() => wheel.destroy());
  const paintHistory = () => histEl.replaceChildren(...(history.length ? history.slice(-12).map(n => h("i", { class: colorOf(n), text: String(n) }))
    : [h("span", { class: "note", text: "Todavía no salió ningún número" })]));
  paintHistory();

  const infoBar = h("div", { class: "info-bar" }, "👆 Tocá una zona del tablero para apostar. Pasá el mouse (o tocá) para ver cuánto paga y qué chances tiene.");
  const showInfo = key => {
    const b = betInfo(key);
    infoBar.replaceChildren(h("b", { text: b.label }), h("span", { text: `paga ${b.ratio} a 1` }), h("span", { class: "muted", text: `· ${pct(b.count)} de chances (${b.count} de 37)` }), h("span", { class: "muted", text: `· ${b.hint}` }),
      h("span", { class: "gold", text: `· con ${fmt(st.chip)} cobrás ${fmt(st.chip * (b.ratio + 1))}` }));
  };

  const totals = () => { const m = new Map(); st.bets.forEach(b => m.set(b.key, (m.get(b.key) || 0) + b.amount)); return m; };
  const totalBet = () => st.bets.reduce((a, b) => a + b.amount, 0);
  const clearHighlight = () => { board.el.classList.remove("dim"); board.zones.forEach(z => z.classList.remove("win")); resultBox.replaceChildren(); pop.replaceChildren(); };

  const totalEl = h("b", { text: "0" }), zonesEl = h("span", { text: "0" });
  const spinBtn = h("button", { class: "btn btn-gold btn-lg", onclick: spin }, icon("wheel"), "GIRAR");
  const undoBtn = h("button", { class: "btn btn-ghost btn-sm", onclick: () => { st.bets.pop(); refresh(); } }, icon("undo"), "Deshacer");
  const clearBtn = h("button", { class: "btn btn-ghost btn-sm", onclick: () => { st.bets = []; refresh(); } }, icon("trash"), "Limpiar");
  const repeatBtn = h("button", { class: "btn btn-ghost btn-sm", onclick: () => { clearHighlight(); st.bets = st.last.map(b => ({ ...b })); fitToBalance(); refresh(); } }, icon("refresh"), "Repetir");
  const doubleBtn = h("button", { class: "btn btn-ghost btn-sm", text: "×2", onclick: () => { clearHighlight(); const extra = st.bets.map(b => ({ ...b })); st.bets.push(...extra); fitToBalance(); refresh(); } });

  function fitToBalance() {           // si no alcanza el saldo, se recortan las últimas fichas
    while (st.bets.length && totalBet() > S.profile.balance) { st.bets.pop(); toast("Quité fichas: no te alcanzaba el saldo.", "err"); }
  }
  function refresh() {
    const t = totals();
    board.zones.forEach((el, key) => {
      const v = t.get(key) || 0; let s = el.querySelector(".stack");
      if (v) { if (!s) { s = h("span", { class: "stack" }); el.append(s); } s.textContent = short(v); } else if (s) s.remove();
    });
    totalEl.textContent = fmt(totalBet()); zonesEl.textContent = String(t.size);
    spinBtn.disabled = st.busy || !st.bets.length;
    undoBtn.disabled = clearBtn.disabled = doubleBtn.disabled = st.busy || !st.bets.length;
    repeatBtn.disabled = st.busy || !st.last.length;
  }
  function pick(key, remove = false) {
    if (st.busy) return;
    clearHighlight();
    if (remove) { st.bets = st.bets.filter(b => b.key !== key); return refresh(); }
    const t = totals(), cur = t.get(key) || 0;
    if (cur + st.chip > lim.rl_max) return toast(`Máximo ${fmt(lim.rl_max)} por zona.`, "err");
    if (totalBet() + st.chip > S.profile.balance) return toast("No te alcanza el saldo para esa ficha.", "err");
    if (!t.has(key) && t.size >= 30) return toast("Máximo 30 zonas por tirada.", "err");
    st.bets.push({ key, amount: st.chip }); showInfo(key); refresh();
  }
  const board = buildBoard(pick, showInfo);
  const resultBox = h("div");

  const chipEls = chipVals.map(v => h("button", { class: `chip c${v} ${v === st.chip ? "sel" : ""}`, "aria-label": `Ficha de ${v}`, text: short(v),
    onclick: () => { st.chip = v; chipEls.forEach(c => c.classList.toggle("sel", c === chipEls[chipVals.indexOf(v)])); } }));

  async function spin() {
    if (st.busy || !st.bets.length) return;
    st.busy = true; refresh();
    const merged = [...totals()].map(([key, amount]) => ({ key, amount })), total = totalBet(), before = S.profile.balance;
    setBalance(before - total);
    let r;
    try { r = await gpost("/api/roulette/spin", { bets: merged }); }
    catch (e) { toast(e.message, "err"); setBalance(before); st.busy = false; refresh(); return; }
    await wheel.spinTo(r.number);
    if (!alive(token)) return;
    history = r.history; paintHistory();
    pop.replaceChildren(h("div", { class: `num ${r.color}`, text: String(r.number) }));
    board.el.classList.add("dim");
    board.zones.forEach((z, key) => z.classList.toggle("win", wins(key, r.number)));
    st.last = merged; st.bets = [];
    setBalance(r.balance);
    const net = r.net;
    resultBox.replaceChildren(h("div", { class: "result-panel" },
      h("h3", {}, `Salió el ${r.number} `, h("span", { class: "muted", text: `· ${r.tags.join(" · ")}` })),
      h("p", { class: net >= 0 ? "pos" : "neg", style: { fontWeight: "700", marginTop: "4px", fontSize: "18px" },
        text: net > 0 ? `¡Ganaste +${fmt(net)} monedas! 🎉` : net === 0 ? "Recuperaste lo apostado." : `Perdiste ${fmt(-net)} monedas.` }),
      h("div", { class: "rows" }, r.results.map(x => h("div", { class: `r ${x.won ? "w" : ""}` },
        h("span", { text: `${x.label} · ${fmt(x.amount)}` }), h("b", { class: x.won ? "pos" : "muted", text: x.won ? `+${fmt(x.payout - x.amount)}` : `−${fmt(x.amount)}` }))))));
    if (net > 0) toast(`¡Ganaste ${fmt(net)} monedas en la ruleta! 🎡`, "gold");
    st.busy = false; refresh();
  }

  const how = h("details", { class: "how card" }, h("summary", {}, icon("help"), "¿Cómo se juega? (guía rápida)"),
    h("div", { class: "how-grid" },
      h("div", {}, h("b", { text: "1 · Elegí tu ficha" }), "Tocá una ficha y después las zonas del tablero donde querés apostar. Podés poner varias. Clic derecho en una zona la quita."),
      h("div", {}, h("b", { text: "2 · Mirá los pagos" }), "Rojo/Negro, Par/Impar y 1-18/19-36 pagan 1 a 1. Docenas y columnas pagan 2 a 1. Un número pleno paga 35 a 1."),
      h("div", {}, h("b", { text: "3 · ¡Girá!" }), "El 0 es verde: solo gana quien apostó a ese número. La casa tiene 2,7% de ventaja, así que jugá por diversión.")));

  refresh();
  root.replaceChildren(sectionTitle("Ruleta europea", "Un solo cero, mismas reglas y pagos que el comando /ruleta del servidor."),
    h("div", { class: "rl" },
      h("div", { class: "card wheel-card" }, h("div", { class: "wheel-box" }, canvas, pop), h("div", { class: "hist-label", text: "Últimos números" }), histEl),
      h("div", {},
        h("div", { class: "felt" }, h("div", { class: "board-wrap" }, board.el), infoBar),
        h("div", { class: "rl-actions" },
          h("div", { class: "left" }, h("div", { class: "chips" }, chipEls),
            h("div", { class: "chips" }, undoBtn, clearBtn, repeatBtn, doubleBtn)),
          h("div", { style: { display: "flex", flexDirection: "column", gap: "10px", alignItems: "flex-end" } },
            h("div", { class: "rl-total" }, "Apuesta total: ", totalEl, " · zonas: ", zonesEl), spinBtn)),
        resultBox)),
    how);
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
function cardEl(c, extra = "", delay = 0) {
  const attrs = { class: `pcard ${c ? (c[1] === "♥" || c[1] === "♦" ? "red" : "") : "back"} ${extra}`, style: delay ? { animationDelay: delay + "ms" } : {} };
  if (!c) return h("div", attrs);
  return h("div", attrs, h("div", { class: "tl" }, c[0], h("small", { text: c[1] })), h("div", { class: "mid", text: c[1] }), h("div", { class: "br" }, c[0], h("small", { text: c[1] })));
}

VIEWS.blackjack = async (root, token) => {
  const lim = S.profile.limits;
  const chipVals = [10, 50, 100, 500, 1000, 5000].filter(v => v >= lim.bj_min && v <= lim.bj_max);
  const st = { bet: chipVals.includes(100) ? 100 : chipVals[0], game: null, busy: false, shown: { player: 0, dealer: 0 }, finished: false };
  const data = await gget("/api/blackjack");
  if (!alive(token)) return;
  setBalance(data.balance, false);

  const dealerHand = h("div", { class: "hand" }), playerHand = h("div", { class: "hand" });
  const dealerVal = h("span", { class: "val", text: "" }), playerVal = h("span", { class: "val", text: "" });
  const mid = h("div", { class: "bj-mid" });
  const table = h("div", { class: "bj-table" },
    h("div", { class: "seat" }, h("div", { class: "seat-label" }, "Dealer", dealerVal), dealerHand), mid,
    h("div", { class: "seat" }, h("div", { class: "seat-label" }, "Tu mano", playerVal), playerHand));
  const controls = h("div", { class: "bj-controls" });

  const setVal = (el, v, bust) => { el.textContent = v == null ? "" : String(v); el.classList.toggle("bust", !!bust); el.classList.toggle("hide", v == null); };
  const drawHand = (el, cards, from) => el.replaceChildren(...cards.map((c, i) => cardEl(c, i >= from ? "deal" : "", Math.max(0, i - from) * 140)));
  const clearBanner = () => mid.replaceChildren();

  function paintActive(g) {
    drawHand(playerHand, g.player, st.shown.player); st.shown.player = g.player.length;
    drawHand(dealerHand, g.dealer, st.shown.dealer); st.shown.dealer = g.dealer.length;
    setVal(playerVal, g.player_value, g.player_value > 21); setVal(dealerVal, g.dealer_value, false);
  }

  async function reveal(g) {                         // fin de la mano: el dealer da vuelta su carta y juega
    st.busy = true; renderControls();
    drawHand(playerHand, g.player, st.shown.player); st.shown.player = g.player.length;
    setVal(playerVal, g.player_value, g.player_value > 21);
    const d = g.dealer;
    if (!dealerHand.children.length) { drawHand(dealerHand, [d[0], null], 0); setVal(dealerVal, handValue([d[0]]), false); }
    await sleep(g.player.length > 2 ? 650 : 900);
    if (!alive(token)) return;
    dealerHand.children[1].replaceWith(cardEl(d[1], "flip")); setVal(dealerVal, handValue(d.slice(0, 2)), false);
    for (let i = 2; i < d.length; i++) {
      await sleep(800); if (!alive(token)) return;
      dealerHand.append(cardEl(d[i], "deal")); setVal(dealerVal, handValue(d.slice(0, i + 1)), handValue(d.slice(0, i + 1)) > 21);
    }
    st.shown.dealer = d.length;
    await sleep(550); if (!alive(token)) return;
    const o = OUT[g.outcome];
    mid.append(h("div", { class: `banner ${o.cls}` }, o.t,
      h("small", { text: g.net > 0 ? `+${fmt(g.net)} monedas` : g.net < 0 ? `−${fmt(-g.net)} monedas` : "Te devuelvo tu apuesta" })));
    setBalance(g.balance);
    if (g.net > 0) toast(`¡Ganaste ${fmt(g.net)} monedas en el blackjack! 🃏`, "gold");
    st.game = null; st.finished = true; st.busy = false; renderControls();
  }

  async function act(action) {
    if (st.busy) return;
    st.busy = true; renderControls();
    const g0 = st.game;
    if (action === "double") setBalance(S.profile.balance - g0.base_bet);
    try {
      const r = await gpost("/api/blackjack/action", { action });
      st.game = r.game; st.busy = false;
      if (r.game.active) { paintActive(r.game); setBalance(r.balance); renderControls(); } else await reveal(r.game);
    } catch (e) {
      toast(e.message, "err"); st.busy = false; setBalance(g0 ? S.profile.balance + (action === "double" ? g0.base_bet : 0) : S.profile.balance);
      if (e.status === 404) { st.game = null; clearTable(); }
      renderControls();
    }
  }

  function clearTable() { dealerHand.replaceChildren(); playerHand.replaceChildren(); setVal(dealerVal, null); setVal(playerVal, null); st.shown = { player: 0, dealer: 0 }; clearBanner(); }

  async function deal() {
    if (st.busy) return;
    if (st.bet > S.profile.balance) return toast("No te alcanza el saldo para esa apuesta.", "err");
    st.busy = true; st.finished = false; renderControls(); clearTable();
    const before = S.profile.balance;
    try {
      const r = await gpost("/api/blackjack/deal", { bet: st.bet });
      st.game = r.game;
      if (r.game.active) { setBalance(r.balance); paintActive(r.game); st.busy = false; renderControls(); }
      else { setBalance(before - st.bet); drawHand(dealerHand, [r.game.dealer[0], null], 0); drawHand(playerHand, r.game.player, 0); await reveal(r.game); }
    } catch (e) { toast(e.message, "err"); st.busy = false; if (e.status === 409) await restore(); renderControls(); }
  }
  async function restore() {
    const d = await gget("/api/blackjack");
    if (d.game && d.game.active) { st.game = d.game; clearTable(); paintActive(d.game); setBalance(d.balance, false); }
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
    const chips = chipVals.map(v => h("button", { class: `chip c${v} ${v === st.bet ? "sel" : ""}`, disabled: st.busy, text: short(v),
      onclick: () => { st.bet = v; input.value = v; chips.forEach(c => c.classList.toggle("sel", c.textContent === short(v))); } }));
    controls.replaceChildren(h("div", { class: "bj-bet" },
      h("div", { class: "row" }, chips, input),
      h("div", { class: "row" }, h("button", { class: "btn btn-gold btn-lg", disabled: st.busy || st.bet < lim.bj_min, onclick: deal, text: st.finished ? `Otra mano · ${fmt(st.bet)}` : `Repartir · ${fmt(st.bet)}` })),
      h("p", { class: "note", text: `Apuesta de ${fmt(lim.bj_min)} a ${fmt(lim.bj_max)} monedas.` })));
  }

  if (data.game && data.game.active) { st.game = data.game; paintActive(data.game); } else { setVal(dealerVal, null); setVal(playerVal, null); }
  if (data.expired) {
    const o = OUT[data.expired.outcome];
    toast(`Tu mano anterior se cerró por inactividad (me planté por vos): ${o ? o.t.toLowerCase() : ""}.`);
  }
  renderControls();

  const how = h("details", { class: "how card" }, h("summary", {}, icon("help"), "¿Cómo se juega? (guía rápida)"),
    h("div", { class: "how-grid" },
      h("div", {}, h("b", { text: "Objetivo" }), "Acercate a 21 sin pasarte y ganale al dealer. Las figuras valen 10 y el As vale 11 u 1, lo que más te convenga."),
      h("div", {}, h("b", { text: "Tus opciones" }), "Pedir suma una carta. Plantarse termina tu turno. Doblar duplica la apuesta, te da una sola carta y te planta."),
      h("div", {}, h("b", { text: "Pagos" }), "Ganar paga 1 a 1, el Blackjack natural (21 con dos cartas) paga 3 a 2 y el empate devuelve la apuesta. El dealer se planta en 17.")));
  root.replaceChildren(sectionTitle("Blackjack", "Mismas reglas que /blackjack: mazo de 6, el dealer se planta en 17."), h("div", { class: "bj" }, table, controls), how);
};

/* ============================================================
   Arranque
   ============================================================ */
window.addEventListener("hashchange", route);
async function boot() {
  let sess;
  try { sess = await api("/api/session"); } catch { return renderLogin("No pude conectar con el servidor. Probá de nuevo en un momento."); }
  if (!sess.logged_in) return renderLogin();
  S.user = sess.user;
  try { S.guilds = (await api("/api/guilds")).guilds; } catch { return renderLogin(); }
  if (!S.guilds.length) return renderNoGuilds();
  let saved = null;
  try { saved = localStorage.getItem("dilus_gid"); } catch { /* sin almacenamiento */ }
  S.gid = (S.guilds.find(g => g.id === saved) || S.guilds[0]).id;
  try { await loadProfile(); } catch (e) { return renderLogin(e.message); }
  history.replaceState(null, "", location.pathname + location.hash);
  renderShell(); route();
}
boot();
