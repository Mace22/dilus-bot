"use strict";
/* ============================================================
   PANEL DE ADMIN (solo administradores; el servidor lo vuelve a comprobar en cada pedido)
   ============================================================ */

const MOD_ACTIONS = [
  { id: "warn", label: "⚠️ Advertir", need: "reason", btn: "Advertir", warn: false },
  { id: "timeout", label: "🔇 Timeout", need: "minutes", btn: "Aplicar timeout", warn: false },
  { id: "untimeout", label: "🔊 Quitar timeout", btn: "Quitar timeout", warn: false },
  { id: "clearwarns", label: "🧹 Borrar advertencias", btn: "Borrar advertencias", warn: false },
  { id: "kick", label: "👢 Expulsar", btn: "Expulsar", warn: true },
  { id: "ban", label: "🔨 Banear", btn: "Banear", warn: true },
];

function fmtWhen(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleString("es-AR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/* Selector de persona con búsqueda (reutilizable en las dos pestañas) */
function memberPicker(onChange) {
  const st = { target: null, timer: 0, seq: 0 };
  const search = h("input", { class: "txt", placeholder: "Buscá a alguien por nombre…", autocomplete: "off", maxlength: "32", "aria-label": "Buscar persona" });
  const results = h("div", { class: "pay-results" });
  const chosen = h("div", { class: "pay-chosen hide" });
  const box = h("div", { class: "field" }, h("label", { text: "Persona" }), chosen, search, results);

  function choose(m) {
    st.target = m; results.replaceChildren(); search.value = ""; search.classList.add("hide");
    chosen.classList.remove("hide");
    const extra = [`${fmt(m.balance)} monedas`, m.warns ? `${m.warns} advertencia(s)` : null, m.timed_out ? "en timeout" : null].filter(Boolean).join(" · ");
    chosen.replaceChildren(m.avatar ? h("img", { class: "avatar", src: m.avatar, alt: "" }) : h("div", { class: "avatar" }),
      h("div", { class: "grow" }, h("b", { text: m.name }), h("small", { class: "note", style: { display: "block" }, text: extra })),
      h("button", { class: "icon-btn sm", "aria-label": "Quitar", onclick: () => clear(true) }, icon("x")));
    onChange(m);
  }
  function clear(focus) {
    st.target = null; chosen.classList.add("hide"); search.classList.remove("hide");
    onChange(null); if (focus) search.focus();
  }
  search.addEventListener("input", () => {
    clearTimeout(st.timer);
    const q = search.value.trim();
    if (!q) return results.replaceChildren();
    st.timer = setTimeout(async () => {
      const mine = ++st.seq;
      try {
        const r = await gget("/api/admin/members", { q });
        if (mine !== st.seq) return;
        results.replaceChildren(...(r.members.length
          ? r.members.map(m => h("button", { class: "member-row", onclick: () => choose(m) },
            m.avatar ? h("img", { class: "avatar", src: m.avatar, alt: "" }) : h("div", { class: "avatar" }),
            h("span", { text: m.name }), h("small", { class: "note", style: { marginLeft: "auto" }, text: `${fmt(m.balance)} 🪙` })))
          : [h("p", { class: "note", style: { padding: "8px 4px" }, text: "No encontré a nadie con ese nombre." })]));
      } catch (e) { toast(e.message, "err"); }
    }, 220);
  });
  return { box, get target() { return st.target; }, reset: () => clear(false) };
}

const statTile = (label, value, sub) => h("div", { class: "card stat" }, h("small", { class: "note", text: label }), h("b", { class: "stat-n", text: value }), sub ? h("small", { class: "note", text: sub }) : null);

/* --- pestaña: economía --- */
function adminEconomy(ov, refreshStats) {
  const reason = h("input", { class: "txt", placeholder: "Motivo (opcional, queda en los logs)", maxlength: "200", "aria-label": "Motivo" });
  const amount = h("input", { class: "txt", type: "number", min: "1", max: String(ov.limits.coins_max), inputmode: "numeric", placeholder: `Monto (máx. ${fmt(ov.limits.coins_max)})`, "aria-label": "Monto" });
  const give = h("button", { class: "btn btn-primary", disabled: true }, "💰 Dar monedas");
  const take = h("button", { class: "btn btn-ghost", disabled: true }, "💸 Quitar monedas");
  const picker = memberPicker(() => update());
  const ok = () => !!picker.target && Number.isInteger(+amount.value) && +amount.value >= 1 && +amount.value <= ov.limits.coins_max;
  const update = () => { give.disabled = take.disabled = !ok(); };
  amount.addEventListener("input", update);

  const run = async sign => {
    if (!ok()) return;
    const n = +amount.value * sign, who = picker.target;
    const verb = sign > 0 ? `darle ${fmt(n)} monedas a` : `quitarle ${fmt(-n)} monedas a`;
    if (!await confirmBox({ title: sign > 0 ? "Dar monedas" : "Quitar monedas", text: `Vas a ${verb} ${who.name}. Esta acción queda registrada en los logs con tu nombre.`, ok: "Confirmar" })) return;
    give.disabled = take.disabled = true;
    try {
      const r = await gpost("/api/admin/coins", { target: who.id, amount: n, reason: reason.value });
      toast(`${r.target} ahora tiene ${fmt(r.balance)} monedas`, "gold");
      if (who.id === S.user.id) setBalance(r.balance);
      amount.value = ""; reason.value = ""; picker.reset(); refreshStats();
    } catch (e) { toast(e.message, "err"); update(); }
  };
  give.addEventListener("click", () => run(1));
  take.addEventListener("click", () => run(-1));
  return h("div", { class: "card admin-form" },
    h("h3", { text: "Dar o quitar monedas" }),
    h("p", { class: "note", text: "Los cambios quedan guardados en los logs: quién lo hizo, a quién, cuánto y por qué." }),
    picker.box,
    h("div", { class: "field" }, h("label", { text: "Monto" }), amount),
    h("div", { class: "field" }, h("label", { text: "Motivo" }), reason),
    h("div", { class: "row" }, take, give));
}

/* --- pestaña: moderación --- */
function adminModeration(ov, refreshStats) {
  let current = MOD_ACTIONS[0];
  const reason = h("input", { class: "txt", maxlength: "200", "aria-label": "Razón" });
  const minutes = h("input", { class: "txt", type: "number", min: "1", max: String(ov.limits.timeout_max), inputmode: "numeric", placeholder: `Minutos (1 a ${fmt(ov.limits.timeout_max)})`, "aria-label": "Minutos" });
  const minutesField = h("div", { class: "field" }, h("label", { text: "Duración" }), minutes);
  const reasonLabel = h("label");
  const go = h("button", { class: "btn btn-primary", disabled: true });
  const picker = memberPicker(() => update());
  const select = h("select", { class: "txt", "aria-label": "Acción" }, MOD_ACTIONS.map(a => h("option", { value: a.id, text: a.label })));

  const ok = () => {
    if (!picker.target) return false;
    if (current.need === "reason" && !reason.value.trim()) return false;
    if (current.need === "minutes" && !(Number.isInteger(+minutes.value) && +minutes.value >= 1 && +minutes.value <= ov.limits.timeout_max)) return false;
    return true;
  };
  function update() {
    current = MOD_ACTIONS.find(a => a.id === select.value);
    minutesField.classList.toggle("hide", current.need !== "minutes");
    reasonLabel.textContent = current.need === "reason" ? "Razón (obligatoria)" : "Razón (opcional)";
    reason.placeholder = current.need === "reason" ? "Por qué se advierte" : "Queda en los logs y en el registro de Discord";
    go.textContent = current.btn; go.className = `btn ${current.warn ? "btn-danger" : "btn-primary"}`;
    go.disabled = !ok();
  }
  [select, reason, minutes].forEach(el => el.addEventListener("input", update));

  go.addEventListener("click", async () => {
    if (!ok()) return;
    const who = picker.target;
    if (!await confirmBox({ title: current.btn, text: `${current.label.replace(/^\S+\s/, "")} a ${who.name}. Esta acción queda registrada en los logs.`, ok: "Confirmar" })) return;
    go.disabled = true;
    try {
      const r = await gpost("/api/admin/mod", { action: current.id, target: who.id, reason: reason.value, minutes: current.need === "minutes" ? +minutes.value : undefined });
      toast(r.message, "ok");
      reason.value = ""; minutes.value = ""; picker.reset(); refreshStats();
    } catch (e) { toast(e.message, "err"); }
    update();
  });
  update();
  return h("div", { class: "card admin-form" },
    h("h3", { text: "Moderación" }),
    h("p", { class: "note", text: `Respeta la jerarquía de roles. Con ${ov.warn_limit} advertencias la persona queda ${ov.auto_timeout} min en timeout automáticamente.` }),
    picker.box,
    h("div", { class: "field" }, h("label", { text: "Acción" }), select),
    minutesField,
    h("div", { class: "field" }, reasonLabel, reason),
    h("div", { class: "row" }, go));
}

/* --- pestaña: ajustes (canal de features, ingresos y rol Crew) --- */
function settingSelect(label, options, current, emptyText, onChange) {
  const select = h("select", { class: "txt", "aria-label": label },
    [h("option", { value: "", text: emptyText }), ...options.map(o => h("option", { value: o.id, text: o.text }))]);
  select.value = current || "";
  select.addEventListener("change", onChange);
  return { select, field: h("div", { class: "field" }, h("label", { text: label }), select) };
}

function featuresCard(data) {
  let saved = data.features_channel || "";
  const save = h("button", { class: "btn btn-primary", disabled: true }, "Guardar canal");
  const s = settingSelect("Canal", data.channels.map(c => ({ id: c.id, text: `#${c.name}${c.category ? ` · ${c.category}` : ""}` })),
    saved, "Sin restricción (en todos los canales)", () => { save.disabled = s.select.value === saved; });
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      const r = await gpost("/api/admin/features-channel", { channel: s.select.value || null });
      saved = r.features_channel || "";
      toast(r.name ? `Canal de features: #${r.name}` : "Quitaste la restricción de canal", "ok");
    } catch (e) { toast(e.message, "err"); save.disabled = s.select.value === saved; }
  });
  return h("div", { class: "card admin-form" },
    h("h3", { text: "Canal de features" }),
    h("p", { class: "note", text: "Blackjack, ruleta, slots, apostar y duelos de cara o cruz solo se pueden usar en este canal de Discord. En otro canal, el bot avisa dónde jugar. Los juegos del panel web no se ven afectados. También se puede cambiar con /config features." }),
    s.field, h("div", { class: "row" }, save));
}

function crewCard(data) {
  const cur = data.crew;
  const saved = { channel: cur.channel || "", role: cur.role || "", staff_role: cur.staff_role || "" };
  const save = h("button", { class: "btn btn-primary", disabled: true }, "Guardar");
  const dirty = () => { save.disabled = ch.select.value === saved.channel && rl.select.value === saved.role && st.select.value === saved.staff_role; };
  const ch = settingSelect("Canal de ingresos", data.crew_channels.map(c => ({ id: c.id, text: `#${c.name}${c.category ? ` · ${c.category}` : ""}` })), saved.channel, "Desactivado", dirty);
  const rl = settingSelect("Rol Crew (el que se da con ✅)", data.assignable_roles.map(r => ({ id: r.id, text: r.name })), saved.role, "Ninguno", dirty);
  const st = settingSelect("Rol de staff (opcional)", data.all_roles.map(r => ({ id: r.id, text: r.name })), saved.staff_role, "Solo quienes tengan Gestionar roles", dirty);
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      const r = await gpost("/api/admin/crew-settings", { channel: ch.select.value || null, role: rl.select.value || null, staff_role: st.select.value || null });
      saved.channel = r.channel || ""; saved.role = r.role || ""; saved.staff_role = r.staff_role || "";
      toast("Ajustes de ingresos guardados", "ok");
    } catch (e) { toast(e.message, "err"); dirty(); }
  });
  return h("div", { class: "card admin-form" },
    h("h3", { text: "Ingresos y rol Crew" }),
    h("p", { class: "note", text: "Cuando alguien entra al servidor, el bot lo avisa en el canal de ingresos (conviene que lo vea solo el staff). Cualquier staff puede reaccionar con ✅ para darle el rol Crew. Staff = Administrador, Gestionar roles o el rol de staff que elijas. El rol Crew no puede tener permiso de Administrador. También se configura con /config ingresos, /config crew y /config crew_staff." }),
    ch.field, rl.field, st.field, h("div", { class: "row" }, save));
}

function adminSettings() {
  const box = h("div", { class: "grid" }, h("div", { class: "card admin-form" }, h("div", { class: "skeleton", style: { height: "120px" } })));
  (async () => {
    const data = await gget("/api/admin/settings");
    box.replaceChildren(crewCard(data), featuresCard(data));
  })().catch(e => box.replaceChildren(h("div", { class: "card empty" }, h("p", { text: e.message }))));
  return box;
}

/* --- eventos del servidor (entradas, salidas, mensajes, roles, perfil, voz...) --- */
function eventRow(it) {
  const x = it.extra || {};
  const imgs = [x.old_img, x.img].filter(Boolean).map(src => h("img", { class: "avatar", src, alt: "", style: { width: "38px", height: "38px" } }));
  const detail = it.kind === "message_delete" ? (it.detail || (x.attachments ? "(sin texto)" : "")) : (x.before == null ? it.detail : "");
  return h("div", { class: `log-row ${it.category}` },
    h("div", { class: "log-ic", text: it.emoji }),
    h("div", { class: "log-main" },
      h("div", {}, it.user ? h("b", { text: it.user }) : null, it.user ? " · " : null, it.title, it.channel ? ` en #${it.channel}` : null),
      detail ? h("small", { text: detail }) : null,
      x.before != null && it.kind === "message_edit" ? [h("small", { text: `Antes: ${x.before}` }), h("small", { text: `Después: ${x.after}` })] : null,
      x.attachments ? h("small", { text: `📎 ${x.attachments} adjunto(s)` }) : null,
      h("small", { text: fmtWhen(it.ts) })),
    imgs.length ? h("div", { style: { display: "flex", gap: "6px", alignItems: "center" } }, imgs.length > 1 ? [imgs[0], "→", imgs[1]] : imgs) : null);
}

function adminEvents() {
  const st = { cat: "all", q: "", timer: 0, seq: 0 };
  const chips = h("div", { class: "tabs" });
  const search = h("input", { class: "txt", placeholder: "Buscar por persona, canal o texto…", maxlength: "40", autocomplete: "off", "aria-label": "Buscar en los eventos" });
  const list = h("div", {});
  const more = h("button", { class: "btn btn-ghost hide" }, "Cargar más");
  const note = h("p", { class: "note" });
  let cats = [], next = null;

  const paintChips = () => chips.replaceChildren(...[{ id: "all", name: "Todo", emoji: "📋" }, ...cats].map(c =>
    h("button", { class: c.id === st.cat ? "on" : "", text: `${c.emoji} ${c.name}`, onclick: () => { st.cat = c.id; paintChips(); load(true); } })));

  async function load(reset) {
    const mine = ++st.seq;
    if (reset) { list.replaceChildren(h("div", { class: "skeleton", style: { height: "120px" } })); next = null; }
    more.disabled = true;
    try {
      const r = await gget("/api/admin/events", { kind: st.cat, q: st.q, before: reset ? undefined : next });
      if (mine !== st.seq) return;
      if (!cats.length) { cats = r.categories; paintChips(); }
      note.textContent = `Se guardan los últimos ${r.retention_days} días. Incluye el contenido de mensajes borrados y editados, así que solo lo ven los administradores.`;
      const rows = r.items.map(eventRow);
      if (reset) {
        list.replaceChildren(rows.length ? h("div", { class: "card log-list", dataset: { events: "1" } }, rows)
          : h("div", { class: "card empty" }, h("div", { class: "big", text: "🧾" }), h("p", { text: st.q || st.cat !== "all" ? "No hay eventos con ese filtro." : "Todavía no hay eventos registrados." })));
      } else {
        list.querySelector("[data-events]")?.append(...rows);
      }
      next = r.next; more.classList.toggle("hide", !next);
    } catch (e) { if (mine === st.seq) list.replaceChildren(h("div", { class: "card empty" }, h("p", { text: e.message }))); }
    more.disabled = false;
  }
  more.addEventListener("click", () => load(false));
  search.addEventListener("input", () => { clearTimeout(st.timer); st.timer = setTimeout(() => { st.q = search.value.trim(); load(true); }, 300); });
  paintChips(); load(true);
  return h("div", {}, chips, h("div", { class: "field" }, search), note, list, h("div", { class: "row", style: { justifyContent: "center", marginTop: "12px" } }, more));
}

/* --- pestaña: logs --- */
async function adminLogs(box, kind) {
  box.replaceChildren(h("div", { class: "skeleton", style: { height: "120px" } }));
  const data = await gget("/api/admin/logs", { kind });
  const rows = data.items.map(it => h("div", { class: `log-row ${it.category}` },
    h("div", { class: "log-ic", text: it.emoji }),
    h("div", { class: "log-main" },
      h("div", {}, h("b", { text: it.actor }), ` · ${it.title}`, it.target ? [" → ", h("b", { text: it.target })] : null),
      it.detail ? h("small", { text: it.detail }) : null,
      h("small", { text: `${fmtWhen(it.ts)} · ${it.source === "web" ? "🌐 panel web" : "💬 Discord"}` })),
    it.amount != null && it.category === "economy" && it.action.startsWith("coins")
      ? h("div", { class: `log-amt ${it.amount >= 0 ? "pos" : "neg"}`, text: `${it.amount >= 0 ? "+" : "−"}${fmt(Math.abs(it.amount))} 🪙` }) : null));
  box.replaceChildren(rows.length ? h("div", { class: "card log-list" }, rows)
    : h("div", { class: "card empty" }, h("div", { class: "big", text: "📜" }), h("p", { text: "Todavía no hay acciones registradas." })));
}

VIEWS.admin = async (root, token) => {
  if (!S.profile.is_admin) throw new Error("Esta sección es solo para administradores del servidor.");
  const ov = await gget("/api/admin/overview");
  if (!alive(token)) return;
  const stats = h("div", { class: "grid g4 admin-stats" });
  const paintStats = o => stats.replaceChildren(
    statTile("Miembros", fmt(o.members)), statTile("Monedas en circulación", fmt(o.coins), `${fmt(o.players)} jugadores`),
    statTile("Advertencias activas", fmt(o.warns)), statTile("Acciones (24 h)", fmt(o.actions_24h), `${fmt(o.given_24h)} monedas dadas`));
  paintStats(ov);
  const refreshStats = async () => { try { paintStats(await gget("/api/admin/overview")); } catch { /* se actualiza en la próxima */ } if (tab === "logs") show("logs"); };

  const body = h("div", {});
  let tab = "eco", kind = "all", source = "events";
  const tabsEl = h("div", { class: "tabs" });
  function show(id) {
    tab = id;
    tabsEl.replaceChildren(...[["eco", "💰 Economía"], ["mod", "🛡️ Moderación"], ["settings", "⚙️ Ajustes"], ["logs", "📜 Logs"]].map(([k, label]) => h("button", { class: k === tab ? "on" : "", text: label, onclick: () => show(k) })));
    if (id === "eco") body.replaceChildren(adminEconomy(ov, refreshStats));
    else if (id === "mod") body.replaceChildren(adminModeration(ov, refreshStats));
    else if (id === "settings") body.replaceChildren(adminSettings());
    else {
      const sources = h("div", { class: "tabs" }, [["events", "📋 Eventos del servidor"], ["staff", "🛡️ Acciones de staff"]].map(([k, label]) =>
        h("button", { class: k === source ? "on" : "", text: label, onclick: () => { source = k; show("logs"); } })));
      if (source === "events") body.replaceChildren(sources, adminEvents());
      else {
        const list = h("div", {});
        const chips = h("div", { class: "tabs" }, [["all", "Todo"], ["economy", "🪙 Economía"], ["moderation", "🛡️ Moderación"]].map(([k, label]) =>
          h("button", { class: k === kind ? "on" : "", text: label, onclick: () => { kind = k; show("logs"); } })));
        body.replaceChildren(sources, chips, list);
        adminLogs(list, kind).catch(e => list.replaceChildren(h("div", { class: "card empty" }, h("p", { text: e.message }))));
      }
    }
  }
  show("eco");
  root.replaceChildren(sectionTitle("Panel de Admin", `Herramientas de administración de ${guildName()}. Todo queda registrado.`), stats, tabsEl, body);
};
