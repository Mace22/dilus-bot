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
  palette: '<circle cx="13.5" cy="6.5" r=".8"/><circle cx="17.5" cy="10.5" r=".8"/><circle cx="8.5" cy="7.5" r=".8"/><circle cx="6.5" cy="12.5" r=".8"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.9 0 1.5-.7 1.5-1.5 0-.4-.2-.8-.4-1.1-.3-.3-.4-.7-.4-1.1 0-.8.7-1.5 1.5-1.5H16c3.3 0 6-2.7 6-6 0-4.9-4.5-9-10-9z"/>',
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
Object.assign(ICONS, {
  slots: '<rect x="2" y="5" width="20" height="14" rx="3"/><line x1="8.5" y1="5" x2="8.5" y2="19"/><line x1="15.5" y1="5" x2="15.5" y2="19"/><circle cx="5.2" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="18.8" cy="12" r="1"/>',
  volume: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>',
  volumeOff: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/>',
  send: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
  star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
  search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
});
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

function countUp(el, to, dur = 900) {
  const t0 = performance.now();
  const tick = t => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt(to * e);
    if (k < 1) requestAnimationFrame(tick); else el.textContent = fmt(to);
  };
  requestAnimationFrame(tick);
}
const stagger = view => view.querySelectorAll(".card, .sec-title, .page-title").forEach((el, i) => { el.classList.add("rise"); el.style.setProperty("--i", Math.min(i, 12)); });
document.addEventListener("click", e => {       // sonidito de clic en cualquier botón (salvo los que tienen su propio sonido)
  const t = e.target.closest("button, a.btn, .nav a");
  if (t && !t.disabled && !t.closest("[data-silent]")) Sfx.click();
}, true);

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
  if (kind === "err") Sfx.error();
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
  { id: "slots", label: "Slots", icon: "slots" },
  { id: "tienda", label: "Tienda", icon: "bag" },
  { id: "tags", label: "Tags", icon: "palette" },
  { id: "ranking", label: "Ranking", icon: "trophy" },
  { id: "logros", label: "Logros", icon: "star" },
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

  /* sonido */
  const paintSound = () => sBtn.replaceChildren(icon(Sfx.muted ? "volumeOff" : "volume"));
  const sBtn = h("button", { class: "icon-btn", "aria-label": "Sonido", title: "Sonido",
    onclick: e => { e.stopPropagation(); gMenu.classList.add("hide"); uMenu.classList.add("hide"); sMenu.classList.toggle("hide"); } });
  const slider = h("input", { type: "range", min: "0", max: "100", value: String(Math.round(Sfx.volume * 100)), class: "slider", "aria-label": "Volumen",
    oninput: e => Sfx.setVolume(e.target.value / 100), onchange: () => Sfx.chip() });
  const muteSw = h("button", { class: `switch ${Sfx.muted ? "" : "on"}`, role: "switch", "aria-label": "Activar sonido",
    onclick: () => { Sfx.setMuted(!Sfx.muted); muteSw.classList.toggle("on", !Sfx.muted); paintSound(); if (!Sfx.muted) Sfx.notify(); } }, h("i"));
  const sMenu = h("div", { class: "menu right sound-menu hide", onclick: e => e.stopPropagation() },
    h("div", { class: "sound-row" }, h("b", { text: "Sonido" }), muteSw), h("div", { class: "sound-row" }, icon("volume"), slider));
  paintSound();
  document.addEventListener("click", () => sMenu.classList.add("hide"));

  const top = h("header", { class: "top" },
    h("div", { class: "menu-wrap" }, gBtn, gMenu), h("div", { class: "grow" }),
    h("div", { class: "bal-chip", title: "Tu saldo" }, coinIcon(), balSpan()),
    h("div", { class: "menu-wrap" }, sBtn, sMenu),
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
  VIEWS[name](view, token).then(() => { if (alive(token)) stagger(view); }).catch(e => {
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
    h("div", { class: "hero-bal" }, h("small", { text: "Tu saldo" }), h("div", { class: "big-num" }, coinIcon(), balSpan()),
      h("button", { class: "btn btn-ghost btn-sm send-btn", onclick: () => openPay() }, icon("send"), "Enviar monedas")));

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
      setBalance(r.balance); burst(card, `+${fmt(r.reward)}`); paintStreak(); Sfx.coins(10); Fx.at(card.querySelector("button"), "coins", 20);
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
      w.ready_at = r.ready_at; setBalance(r.balance); burst(card, `+${fmt(r.reward)}`); Sfx.coins(6); Fx.at(card.querySelector("button"), "coins", 12);
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
  const stat = (label, value, sub, count) => h("div", { class: "card stat" }, h("small", { text: label }), h("b", { text: value, dataset: count != null ? { count } : {} }), sub ? h("em", { text: sub }) : null);
  const stats = h("div", { class: "grid g2" },
    stat("Mensajes enviados", fmt(lv.messages), null, lv.messages), stat("Tiempo en voz", fmtDur(lv.voice_seconds), "en canales de voz"),
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
    h("div", { class: "grid g2 split-a" }, levelCard, stats),
    h("div", { class: "sec-title" }, h("h2", { text: "Casino" })),
    h("div", { class: "grid g2" }, casinoCard("roulette", "Ruleta", "🎡"), casinoCard("blackjack", "Blackjack", "🃏")),
    h("div", { class: "sec-title" }, h("h2", { text: "Jugá ahora" })),
    h("div", { class: "grid g3" }, play("ruleta", "🎡", "Ruleta europea", "Fichas, tablero y rueda animada"), play("blackjack", "🃏", "Blackjack", "Contra el dealer, paga 3 a 2"), play("slots", "🎰", "Tragamonedas", "Tres iguales pagan hasta ×15")));
  root.querySelectorAll("[data-count]").forEach(el => countUp(el, +el.dataset.count));
  if (!S.intro) { S.intro = true; shownBal = 0; setBalance(S.profile.balance); }
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
if (document.readyState === "complete") boot(); else document.addEventListener("DOMContentLoaded", boot);   // los scripts con defer corren antes de este evento
