"use strict";
/* ============================================================
   Blackjack multijugador: mesas en vivo de hasta 5 personas.
   El servidor reparte, decide los turnos y paga; acá solo se muestra la mesa y se anima.
   Usa lo que define games.js (h, S, CHIPS, chipRack, pcardEl, setFace, handValue, howBox, bjTabs, Sfx, Fx...).
   ============================================================ */

const BJM_SEATS = 5;
const BJM_RESULT = {            // etiqueta y color por resultado
  blackjack: ["¡BLACKJACK!", "bj"], win: ["¡Ganó!", "win"], dealer_bust: ["¡Ganó!", "win"],
  lose: ["Perdió", "lose"], bust: ["Se pasó", "lose"], dealer_blackjack: ["Perdió", "lose"], push: ["Empate", "push"],
};
const BJM_MINE = {              // el mismo resultado, dicho en segunda persona
  blackjack: "¡BLACKJACK!", win: "¡GANASTE!", dealer_bust: "EL DEALER SE PASÓ", lose: "PERDISTE", bust: "TE PASASTE", dealer_blackjack: "BLACKJACK DEL DEALER", push: "EMPATE",
};
const bjmNet = n => (n > 0 ? `+${fmt(n)}` : n < 0 ? `−${fmt(-n)}` : "±0");
const bjmVal = (el, v, bust) => { el.textContent = v == null ? "" : String(v); el.classList.toggle("bust", !!bust); el.classList.toggle("hide", v == null); };

VIEWS.bjmulti = async (root, token) => {
  const run = S.bjmRun = {};
  const live = () => alive(token) && S.bjmRun === run;
  const lim = S.profile.limits;
  const me = String(S.user.id);
  const chipVals = CHIPS.filter(v => v >= lim.bj_min && v <= lim.bj_max);
  const st = {
    bet: chipVals.includes(100) ? 100 : chipVals[0], busy: false, polling: false, rendering: false, pending: null,
    tid: null, v: null, t: null, ui: null, listSig: "", ctlSig: "", cd: null, subBase: "", shownRound: -1, celebrated: 0,
    wasMyTurn: false, wasSeated: false, sideAmt: {},
  };
  const holder = h("div", { class: "bjm" });

  /* ---------- apuesta (se comparte entre las rondas) ---------- */
  const setBet = v => { st.bet = v; betInput.value = v; chipEls.forEach(c => c.classList.remove("sel")); refreshPlace(); };
  function refreshPlace() {                            // el botón "Apostar" refleja el monto elegido
    const b = st.placeBtn, t = st.t;
    if (!b || !t) return;
    const mine = t.me.bet > 0;
    b.textContent = mine ? `Cambiar apuesta a ${fmt(st.bet)}` : `Apostar ${fmt(st.bet)}`;
    b.disabled = st.busy || (mine && st.bet === t.me.bet);
  }
  const betInput = h("input", { class: "num-input", type: "number", inputmode: "numeric", min: lim.bj_min, value: st.bet, "aria-label": "Tu apuesta",
    oninput: e => { st.bet = Math.max(0, Math.min(lim.bj_max, parseInt(e.target.value || "0", 10) || 0)); chipEls.forEach(c => c.classList.remove("sel")); refreshPlace(); } });
  const chipEls = chipRack(chipVals, st.bet, v => { st.bet = v; betInput.value = v; refreshPlace(); });
  const x2Btn = h("button", { class: "btn btn-ghost btn-bet-x2", "data-silent": "1", title: "Duplicar la apuesta", "aria-label": "Duplicar la apuesta", text: "×2",
    onclick: () => {
      const cap = S.profile.balance >= lim.bj_min ? Math.min(lim.bj_max, S.profile.balance) : lim.bj_max;
      const next = Math.min(cap, Math.max(lim.bj_min, st.bet * 2));
      if (next === st.bet) return toast("No te alcanza el saldo para duplicar.", "err");
      setBet(next); Sfx.chip();
    } });
  const allInBtn = h("button", { class: "btn btn-gold btn-allin", "data-silent": "1", title: "Apostar todo tu saldo", text: "🔥 ALL IN",
    onclick: () => {
      if (S.profile.balance < lim.bj_min) return toast(`Necesitás al menos ${fmt(lim.bj_min)} monedas para apostar.`, "err");
      setBet(Math.min(lim.bj_max, S.profile.balance)); Sfx.chips(4);
    } });
  const betBox = h("div", { class: "bjm-betbox" }, h("div", { class: "bjm-row" }, chipEls, betInput, x2Btn, allInBtn));
  // resultados de una ronda que todavía no se mostraron (el saldo se actualiza cuando se ven)
  const pendingResults = t => !!t && t.status === "betting" && t.dealer.length > 0 && t.round !== st.celebrated;

  /* ---------- pantalla 1: lista de mesas ---------- */
  const listBox = h("div", { class: "bjm-list" });
  const lobby = h("div", { class: "bjm-lobby" },
    h("div", { class: "card bjm-new" },
      h("h3", { text: "Jugá con otros del servidor" }),
      h("p", { class: "note", text: "Abrí una mesa o sentate en una abierta (hasta 5 personas). Sentarte no cuesta nada: apostás en cada ronda y te quedás en la mesa entre ronda y ronda." }),
      h("div", { class: "bjm-actions" }, h("button", { class: "btn btn-gold btn-lg", text: "➕ Abrir una mesa nueva", onclick: createTable }))),
    h("h3", { class: "bjm-sub", text: "Mesas del servidor" }), listBox);

  function renderList(d) {
    const sig = JSON.stringify([d.admin, d.tables.map(x => [x.id, x.status, x.can_delete, x.players.map(p => [p.id, p.bet])])]);
    if (sig === st.listSig) return;
    st.listSig = sig;
    if (!d.tables.length) {
      listBox.replaceChildren(h("p", { class: "note", text: "No hay mesas abiertas ahora mismo. ¡Abrí la primera y avisale a tus amigos del servidor!" }));
      return;
    }
    listBox.replaceChildren(...d.tables.map(x => {
      const full = x.count >= x.max, playing = x.status === "playing";
      const adminDel = d.admin && x.owner !== me;
      return h("div", { class: "card bjm-tcard" },
        h("div", { class: "bjm-thead" }, h("b", { text: `Mesa ${x.id}` }),
          h("span", { class: `bjm-pill ${playing ? "play" : "open"}`, text: playing ? "En juego" : "Apuestas abiertas" }),
          h("span", { class: "note", text: `${x.count}/${x.max} jugadores` })),
        h("div", { class: "bjm-players" }, x.players.length
          ? x.players.map(p => h("span", { class: "bjm-peep" }, p.avatar ? h("img", { class: "avatar", src: p.avatar, alt: "" }) : null, p.name, p.bet ? h("small", { text: ` ${short(p.bet)} 🪙` }) : null))
          : h("span", { class: "note", text: "Vacía · esperando jugadores" })),
        h("div", { class: "duel-btns bjm-tbtns" },
          h("button", { class: "btn btn-primary btn-sm", disabled: full, text: full ? "Llena" : "🪑 Sentarme", onclick: () => joinTable(x.id) }),
          h("button", { class: "btn btn-ghost btn-sm", text: "👀 Mirar", onclick: () => openTable(x.id) }),
          x.can_delete ? h("button", { class: "btn btn-ghost btn-sm bjm-del", text: adminDel ? "🛡️ Admin: borrar" : "🗑️ Borrar", onclick: () => deleteFromList(x.id) }) : null));
    }));
  }

  async function createTable() {
    if (st.busy) return;
    st.busy = true;
    try {
      const r = await gpost("/api/bjtable/create", {});
      if (!live()) return;
      Sfx.chips(2); setBalance(r.balance);
      await openTable(r.table.id, r.table);
    } catch (e) { toast(e.message, "err"); } finally { st.busy = false; if (live() && st.ui) renderControls(true); }
  }
  async function joinTable(id) {
    if (st.busy) return;
    st.busy = true;
    try {
      const r = await gpost("/api/bjtable/join", { id });
      if (!live()) return;
      Sfx.chip(); setBalance(r.balance);
      await openTable(id, r.table);
    } catch (e) { toast(e.message, "err"); st.listSig = ""; } finally { st.busy = false; if (live() && st.ui) renderControls(true); }
  }
  async function deleteFromList(id) {
    if (!await confirmBox({ title: `Borrar la mesa ${id}`, text: "Se cierra la mesa para todos y se devuelven todas las apuestas.", ok: "Borrar" })) return;
    try { await gpost("/api/bjtable/delete", { id }); toast("Mesa borrada. Devolví las apuestas.", "ok"); } catch (e) { toast(e.message, "err"); }
    st.listSig = ""; poll();
  }
  function backToList() {
    st.tid = null; st.t = null; st.ui = null; st.v = null; st.pending = null; st.listSig = ""; st.shownRound = -1; st.cd = null; st.wasSeated = false;
    holder.replaceChildren(lobby);
    poll();
  }

  /* ---------- pantalla 2: la mesa ---------- */
  function slotEl() {
    const avatar = h("img", { class: "avatar bjm-av", alt: "" }), name = h("span", { class: "bjm-name" }), val = h("span", { class: "val hide" });
    const hand = h("div", { class: "hand" }), bet = h("div", { class: "bjm-bet" }), side = h("div", { class: "bjm-side" }), tag = h("div", { class: "bjm-tag" });
    const bar = h("i"), timer = h("div", { class: "bjm-timer" }, bar);
    const el = h("div", { class: "bjm-seat hide" }, h("div", { class: "bjm-who" }, avatar, name, val), hand, bet, side, tag, timer);
    return { el, avatar, name, val, hand, bet, side, tag, bar, timer, uid: null };
  }
  function buildTable() {
    const u = st.ui = { slots: [] };
    st.midKey = "";
    u.title = h("b", { class: "bjm-title" });
    u.sub = h("span", { class: "note" });
    u.back = h("button", { class: "btn btn-ghost btn-sm", text: "← Mesas", onclick: backToList });
    u.del = h("button", { class: "btn btn-ghost btn-sm bjm-del hide", text: "🗑️ Borrar mesa", onclick: deleteTable });
    u.dealerHand = h("div", { class: "hand" });
    u.dealerVal = h("span", { class: "val hide" });
    u.shoe = h("div", { class: "shoe" }, h("i"), h("i"), h("i"));
    u.mid = h("div", { class: "bjm-mid" });
    u.seats = h("div", { class: "bjm-seats" });
    for (let i = 0; i < BJM_SEATS; i++) { const s = slotEl(); u.slots.push(s); u.seats.append(s.el); }
    u.controls = h("div", { class: "bj-controls bjm-controls" });
    u.table = h("div", { class: "bj-table bjm-table" }, u.shoe,
      h("div", { class: "seat" }, h("div", { class: "seat-label" }, "Dealer", u.dealerVal), u.dealerHand), u.mid, u.seats);
    u.wrap = h("div", { class: "bj bjm-wrap" }, h("div", { class: "bjm-head" }, u.back, u.title, u.sub, u.del), u.table, u.controls);
  }

  async function openTable(tid, initial) {
    st.tid = tid; st.v = null; st.t = null; st.ctlSig = ""; st.shownRound = -1; st.celebrated = 0; st.wasMyTurn = false; st.wasSeated = false; st.pending = null; st.cd = null;
    buildTable();
    holder.replaceChildren(st.ui.wrap);
    renderControls(true);
    try {
      const t = initial || await gget("/api/bjtable", { id: tid });
      if (!live() || st.tid !== tid) return;
      setBalance(t.balance, false);
      await receive(t);
    } catch (e) { toast(e.message, "err"); if (live()) backToList(); }
  }

  async function receive(t) {          // si llega otro estado mientras se anima, se queda el más nuevo
    st.v = t.v; st.pending = t;
    if (st.rendering) return;
    st.rendering = true;
    try {
      while (st.pending && live()) { const x = st.pending; st.pending = null; await render(x); }
    } finally { st.rendering = false; }
  }

  /* reparte una carta desde el mazo (con arco, giro y sonido) */
  const ovFor = n => (n <= 3 ? 20 : n === 4 ? 24 : n === 5 ? 27 : 30);
  async function dealTo(u, hand, data, { down = false, instant = false, seat = false } = {}) {
    const el = pcardEl(data);
    hand.append(el);
    if (seat) hand.style.setProperty("--ov", `${ovFor(hand.children.length)}px`);
    if (instant) { if (!down) el.classList.remove("down"); return el; }
    const a = centerOf(u.shoe), b = centerOf(el);
    Sfx.deal();
    const anim = el.animate([
      { transform: `translate(${a.x - b.x}px, ${a.y - b.y}px) rotate(-24deg) scale(.5)`, opacity: 0 },
      { opacity: 1, offset: 0.18 }, { transform: "none", opacity: 1 }],
    { duration: 480, easing: "cubic-bezier(.2,.8,.25,1)", fill: "backwards" });
    await anim.finished.catch(() => {});
    if (!down) { await sleep(60); el.classList.remove("down"); Sfx.flip(); await sleep(300); }
    return el;
  }

  function paintSeat(sl, r, reveal) {
    sl.el.classList.toggle("hide", !r);
    if (!r) return;
    const res = r.status === "done" ? r.result : null;
    sl.el.classList.toggle("turn", r.status === "turn");
    sl.el.classList.toggle("me", r.id === me);
    sl.el.classList.toggle("out", r.status === "idle" || r.status === "watch");
    for (const c of ["win", "lose", "push", "bj"]) sl.el.classList.remove("res-" + c);
    sl.name.textContent = r.id === me ? `${r.name} (vos)` : r.name;
    if (r.avatar) { sl.avatar.src = r.avatar; sl.avatar.style.display = ""; } else sl.avatar.style.display = "none";
    const shown = res ? res.bet : r.bet;
    sl.bet.textContent = shown ? `🪙 ${fmt(shown)}${r.doubled && shown ? " · doblada" : ""}` : "";
    const sides = res && reveal ? r.side_result : r.sides;                   // apuestas por vecinos
    sl.side.replaceChildren(...sides.map(x => h("div", { text: `🤝 ${x.name}: ${fmt(x.amount)}${x.net != null ? ` (${bjmNet(x.net)})` : ""}` })));
    let text = "", cls = "";
    if (res && reveal) {
      const [label, c] = BJM_RESULT[res.outcome] || ["", ""];
      text = `${label} ${bjmNet(res.net)}`; cls = c; sl.el.classList.add("res-" + c);
    } else if (r.status === "done") text = r.value > 21 ? "💥 Se pasó" : (r.cards.length === 2 && r.value === 21) ? "★ Blackjack" : "✋ Plantado";
    else if (r.status === "ready") text = "✅ Apuesta lista";
    else if (r.status === "idle") text = "💤 Sin apuesta";
    else if (r.status === "watch") text = "👀 Mirando esta ronda";
    else if (r.status === "turn") text = "🎯 Jugando…";
    else if (r.status === "wait") text = "⏳ Esperando turno";
    else if (r.status === "stand") text = "✋ Plantado";
    else if (r.status === "bust") text = "💥 Se pasó";
    else if (r.status === "blackjack") text = "★ Blackjack";
    sl.tag.textContent = text; sl.tag.className = `bjm-tag ${cls}`;
    sl.timer.classList.toggle("on", r.status === "turn");
  }

  async function syncDealer(u, cards, value, anim) {
    const hand = u.dealerHand, hole = hand.children[1];
    if (hole && hole.classList.contains("down") && cards[1]) {          // el dealer da vuelta su carta tapada
      if (anim) await sleep(500);
      setFace(hole, cards[1]); hole.classList.remove("down");
      if (anim) { Sfx.flip(); await sleep(700); }
      bjmVal(u.dealerVal, handValue(cards.slice(0, 2)), false);
    }
    while (hand.children.length < cards.length) {
      if (st.ui !== u) return;
      const i = hand.children.length, c = cards[i];
      await dealTo(u, hand, c, { down: c === null, instant: !anim });
      if (c) { const v = handValue(cards.slice(0, i + 1)); bjmVal(u.dealerVal, v, v > 21); if (anim) await sleep(380); }
    }
    bjmVal(u.dealerVal, cards.length ? value : null, value > 21);
  }

  async function render(t) {
    const u = st.ui;
    if (!u || st.tid !== t.id) return;
    const prev = st.t, first = !prev, calm = first || document.hidden;
    st.t = t;
    const rows = t.seats, dealer = t.dealer, myRow = rows.find(r => r.id === me) || null;
    const fresh = st.shownRound !== t.round;           // se repartió otra ronda: se limpia la mesa
    st.shownRound = t.round;
    const resolved = t.status === "betting" && dealer.length > 0;       // hay una ronda terminada para mostrar
    const pending = resolved && st.celebrated !== t.round;              // ...y todavía no se mostró

    u.title.textContent = `Mesa ${t.id}`;
    st.subBase = t.status === "playing" ? `Ronda ${t.round} · en juego`
      : t.round ? `Ronda ${t.round + 1} · apuestas abiertas` : "Mesa nueva · esperando apuestas";
    u.sub.textContent = st.subBase;
    u.back.style.display = t.me.seated ? "none" : "";
    u.del.classList.toggle("hide", !t.can_delete);
    u.del.textContent = t.admin ? "🛡️ Admin: borrar mesa" : "🗑️ Borrar mesa";
    st.cd = t.turn_left != null ? { kind: "turn", at: performance.now() + t.turn_left * 1000 }
      : t.deal_left != null ? { kind: "deal", at: performance.now() + t.deal_left * 1000 }
      : t.bet_left != null ? { kind: "bet", at: performance.now() + t.bet_left * 1000 } : null;
    if (!first && t.me.my_turn && !st.wasMyTurn) { toast("¡Es tu turno en el blackjack! 🃏", "gold"); Sfx.push(); }
    st.wasMyTurn = t.me.my_turn;
    if (st.wasSeated && !t.me.seated && !first) toast("Te levantaron de la mesa por pasar varias rondas sin apostar.", "");
    st.wasSeated = t.me.seated;

    if (fresh) {
      u.dealerHand.replaceChildren(); bjmVal(u.dealerVal, null);
      u.slots.forEach(sl => { sl.hand.replaceChildren(); sl.uid = null; bjmVal(sl.val, null); });
    }
    const moved = u.slots.map((sl, i) => {             // quién está sentado en cada lugar (si cambió, se redibuja sin animar)
      const r = rows[i] || null, id = r ? r.id : null;
      const changed = sl.uid !== id || (r && r.cards.length < sl.hand.children.length);
      if (changed) { sl.hand.replaceChildren(); bjmVal(sl.val, null); }
      sl.uid = id;
      paintSeat(sl, r, !pending);
      return changed;
    });
    if (dealer.length < u.dealerHand.children.length) { u.dealerHand.replaceChildren(); bjmVal(u.dealerVal, null); }
    paintMid(t, !pending, myRow, resolved);
    renderControls();

    /* reparto inicial: una carta a cada uno, otra al dealer, y vuelta */
    if (fresh && !calm && t.status === "playing") {
      for (let k = 0; k < 2; k++) {
        for (let i = 0; i < rows.length; i++) {
          if (!rows[i].cards.length) continue;
          await dealTo(u, u.slots[i].hand, rows[i].cards[k], { seat: true });
          if (!live() || st.ui !== u) return;
          bjmVal(u.slots[i].val, handValue(rows[i].cards.slice(0, k + 1)), false);
        }
        await dealTo(u, u.dealerHand, dealer[k], { down: dealer[k] === null });
        if (!live() || st.ui !== u) return;
        if (dealer[k]) bjmVal(u.dealerVal, handValue(dealer.slice(0, 1)), false);
      }
    }
    for (let i = 0; i < rows.length; i++) {            // cartas nuevas de cada mano (repartir, pedir, doblar)
      const sl = u.slots[i], cards = rows[i].cards;
      while (sl.hand.children.length < cards.length) {
        await dealTo(u, sl.hand, cards[sl.hand.children.length], { instant: calm || moved[i], seat: true });
        if (!live() || st.ui !== u) return;
        const v = handValue(cards.slice(0, sl.hand.children.length));
        bjmVal(sl.val, v, v > 21);
      }
      sl.hand.style.setProperty("--ov", `${ovFor(cards.length)}px`);
      bjmVal(sl.val, rows[i].value, rows[i].value > 21);
    }
    if (dealer.length) {
      await syncDealer(u, dealer, t.dealer_value, !calm);
      if (!live() || st.ui !== u) return;
    }

    /* terminó la ronda: se muestran los resultados (una sola vez por ronda) */
    if (pending) {
      await sleep(calm ? 0 : 250);
      if (!live() || st.ui !== u) return;
      t.seats.forEach((r, i) => paintSeat(u.slots[i], r, true));
      paintMid(t, true, myRow, true);
      st.celebrated = t.round;
      if (myRow && myRow.result) {
        if (myRow.base_bet) setBet(Math.max(lim.bj_min, Math.min(lim.bj_max, myRow.base_bet)));   // la revancha arranca con tu misma apuesta
        if (!first) celebrate(myRow, u);
      }
      setBalance(t.balance, !first);
      renderControls(true);
    }
  }

  function celebrate(r, u) {
    const res = r.result, total = res.net + res.side_net;
    const banner = u.mid.querySelector(".banner");
    if (res.outcome === "blackjack") { Sfx.blackjack(); if (banner) Fx.at(banner, "confetti", 170, 1.3); Fx.rain(50); }
    else if (total > 0) { Sfx.win(total >= 1000); if (banner) Fx.at(banner, "confetti", 90); }
    else if (res.outcome === "push" && total === 0) Sfx.push();
    else Sfx.lose();
    if (total > 0) toast(`¡Ganaste ${fmt(total)} monedas en la mesa! 🃏`, "gold");
  }

  function paintMid(t, final, myRow, resolved) {
    const u = st.ui;
    if (resolved && final && myRow && myRow.result && !myRow.bet) {          // tu resultado, hasta que apostés de nuevo
      const res = myRow.result, cls = (BJM_RESULT[res.outcome] || ["", ""])[1], total = res.net + res.side_net;
      const parts = [`Mano ${bjmNet(res.net)}`];
      if (myRow.side_result.length) parts.push(`Vecinos ${bjmNet(res.side_net)}`, `Total ${bjmNet(total)}`);
      const key = `banner:${t.round}:${res.outcome}:${res.net}:${res.side_net}`;
      if (st.midKey === key) return;
      st.midKey = key;
      u.mid.replaceChildren(h("div", { class: `banner ${cls}` }, BJM_MINE[res.outcome] || "",
        h("small", { text: res.net === 0 && !myRow.side_result.length ? "Te devuelvo tu apuesta" : parts.join(" · ") })));
      return;
    }
    let main, sub = "";
    if (t.status === "playing") {
      const cur = t.seats.find(s => s.id === t.turn);
      main = cur ? (cur.id === me ? "🎯 ¡Es tu turno!" : `Turno de ${cur.name}`) : "Repartiendo…";
    } else if (resolved && !final) main = "El dealer juega…";
    else {
      const n = t.seats.filter(s => s.bet).length;
      main = "💰 Hagan sus apuestas";
      sub = n < t.need ? `Hace falta${t.need > 1 ? "n" : ""} ${t.need} jugador${t.need > 1 ? "es" : ""} con apuesta para repartir (${n} por ahora)` : `${n} de ${t.seats.length} ya apostaron`;
    }
    const key = `text:${main}:${sub}`;
    if (st.midKey === key) return;
    st.midKey = key;
    u.mid.replaceChildren(h("div", { class: "bjm-midtext", text: main }), h("small", { class: "bjm-midsub", text: sub }));
  }

  /* cuenta regresiva (solo visual: el servidor es quien planta o reparte cuando se acaba el tiempo) */
  function tick() {
    const t = st.t, u = st.ui;
    if (!t || !u) return;
    const left = st.cd ? Math.max(0, (st.cd.at - performance.now()) / 1000) : 0;
    if (st.cd && st.cd.kind === "turn") {
      const sl = u.slots.find(s => s.uid === t.turn);
      if (sl) { sl.bar.style.width = `${Math.min(100, left / t.turn_time * 100)}%`; sl.timer.classList.toggle("low", left < 10); }
    }
    const suffix = !st.cd ? "" : st.cd.kind === "turn" ? ` · ${Math.ceil(left)} s` : st.cd.kind === "deal" ? ` · repartimos en ${Math.ceil(left)} s` : ` · se reparte en ${Math.ceil(left)} s`;
    const text = st.subBase + suffix;
    if (u.sub.textContent !== text) u.sub.textContent = text;
  }

  /* ---------- acciones ---------- */
  async function call(path, body) {
    if (st.busy) return null;
    st.busy = true; renderControls(true);
    try {
      const r = await gpost(path, { id: st.tid, ...body });
      if (!live()) return null;
      if (r.balance != null && !pendingResults(r.table)) setBalance(r.balance);
      if (r.table) await receive(r.table);
      return r;
    } catch (e) {
      toast(e.message, "err");
      if (e.status === 404 && live()) backToList();
      return null;
    } finally { st.busy = false; if (live()) renderControls(true); }
  }
  const act = action => call("/api/bjtable/action", { action });
  const have = () => S.profile.balance + (st.t ? st.t.me.bet : 0);
  async function placeBet() {
    if (st.bet < lim.bj_min) return toast(`La apuesta mínima es ${fmt(lim.bj_min)} monedas.`, "err");
    if (st.bet > have()) return toast("No te alcanza el saldo para esa apuesta.", "err");
    if (await call("/api/bjtable/bet", { bet: st.bet })) Sfx.chips(2);
  }
  async function withdraw() { if (await call("/api/bjtable/bet", { bet: 0 })) { Sfx.chip(); toast("Retiraste tu apuesta.", ""); } }
  async function sideBet(n, amount) {
    if (amount && amount < lim.bj_min) return toast(`La apuesta mínima es ${fmt(lim.bj_min)} monedas.`, "err");
    if (amount > S.profile.balance + n.mine) return toast("No te alcanza el saldo para esa apuesta.", "err");
    if (await call("/api/bjtable/side", { target: n.id, amount })) Sfx.chips(1);
  }
  async function sit() { if (await call("/api/bjtable/join", {})) Sfx.chip(); }
  async function start() { await call("/api/bjtable/start", {}); }
  async function leave() {
    const r = await call("/api/bjtable/leave", {});
    if (r && r.left) { Sfx.chips(2); toast("Te levantaste de la mesa. Te devolví lo que tenías apostado.", ""); backToList(); }
  }
  async function deleteTable() {
    const t = st.t;
    if (!t || !await confirmBox({ title: `Borrar la mesa ${t.id}`, text: "Se cierra la mesa para todos y se devuelven todas las apuestas, incluso si hay una ronda en marcha.", ok: "Borrar" })) return;
    const r = await call("/api/bjtable/delete", {});
    if (r && r.deleted) { toast("Mesa borrada. Devolví las apuestas.", "ok"); backToList(); }
  }

  function renderControls(force) {
    const u = st.ui;
    if (!u) return;
    const t = st.t, seated = !!t && t.me.seated;
    const mySeat = t && t.seats.find(s => s.id === me);
    const sig = JSON.stringify([!!t, t && t.status, seated, t && t.me.my_turn, t && t.me.can_double, t && t.me.bet, t && t.me.neighbors, t && t.can_deal,
      t && t.host === me, t && t.seats.length >= t.max_seats, st.busy, !!t && S.profile.balance >= t.me.base_bet, mySeat && mySeat.playing]);
    if (!force && sig === st.ctlSig) return;
    st.ctlSig = sig;
    const mk = (cls, label, fn, disabled) => h("button", { class: `btn ${cls}`, disabled: disabled || st.busy, onclick: fn }, label);
    const btn = (cls, label, fn, disabled) => mk(`${cls} btn-lg`, label, fn, disabled);
    const note = text => h("p", { class: "note bjm-note", text });
    if (!t) { u.controls.replaceChildren(note("Cargando la mesa…")); return; }
    const sitBtn = () => (t.seats.length >= t.max_seats
      ? note("La mesa está llena. Esperá a que se libere un lugar o buscá otra.")
      : h("div", { class: "bjm-leave" }, btn("btn-primary", "🪑 Sentarme en esta mesa", sit), note("Sentarte es gratis: apostás en cada ronda y seguís en la mesa.")));

    if (t.status === "playing") {
      if (seated && t.me.my_turn) {
        u.controls.replaceChildren(btn("btn-primary", "🃏 Pedir", () => act("hit")), btn("btn-ghost", "✋ Plantarse", () => act("stand")),
          btn("btn-gold", `💰 Doblar (${fmt(t.me.base_bet)})`, () => act("double"), !t.me.can_double || S.profile.balance < t.me.base_bet));
      } else if (seated) {
        u.controls.replaceChildren(note(mySeat && mySeat.playing ? "Esperá tu turno: los demás están jugando. Si alguien no juega a tiempo, se planta solo."
          : "Estás sentado pero esta ronda no apostaste: mirás y apostás en la próxima."));
      } else u.controls.replaceChildren(note("Estás mirando la mesa."), sitBtn());
      return;
    }

    /* fase de apuestas */
    if (!seated) { u.controls.replaceChildren(sitBtn()); return; }
    const mine = t.me.bet > 0;
    const placeBtn = btn("btn-gold", "", placeBet);
    st.placeBtn = placeBtn; refreshPlace();
    const betPanel = h("div", { class: "bjm-panel" },
      h("b", { text: mine ? `Tu apuesta: ${fmt(t.me.bet)} 🪙` : "Hacé tu apuesta" }),
      betBox,
      h("div", { class: "bjm-row" },
        placeBtn,
        mine ? mk("btn-ghost", "Retirar apuesta", withdraw) : null),
      note(`Mínimo ${fmt(lim.bj_min)} monedas, sin máximo. Si no apostás a tiempo, se reparte sin vos (seguís sentado).`));
    const sideRow = n => {
      const label = n.side === "left" ? "⬅️ A tu izquierda" : "A tu derecha ➡️";
      const input = h("input", { class: "num-input bjm-sideinput", type: "number", inputmode: "numeric", min: lim.bj_min, "aria-label": `Apuesta por ${n.name}`,
        value: st.sideAmt[n.id] != null ? st.sideAmt[n.id] : Math.max(lim.bj_min, Math.floor(st.bet / 2)),
        oninput: e => { st.sideAmt[n.id] = Math.max(0, parseInt(e.target.value || "0", 10) || 0); } });
      const ok = n.bet > 0;
      return h("div", { class: "bjm-siderow" },
        h("div", { class: "bjm-sidewho" }, h("b", { text: `${label} · ${n.name}` }), h("small", { text: ok ? `su mano: ${fmt(n.bet)} 🪙` : "esperá a que apueste" })),
        h("div", { class: "bjm-row" }, input,
          mk("btn-primary btn-sm", n.mine ? `Cambiar (${fmt(n.mine)})` : "Apostar por él/ella", () => sideBet(n, parseInt(input.value || "0", 10) || 0), !ok),
          n.mine ? mk("btn-ghost btn-sm", "Quitar", () => sideBet(n, 0)) : null));
    };
    const panels = [betPanel];
    if (mine && t.me.neighbors.length) {
      panels.push(h("div", { class: "bjm-panel" }, h("b", { text: "Apostar por tus vecinos" }),
        note("Ganás según le vaya a esa mano contra el dealer (1 a 1; 3 a 2 si hace blackjack; el empate se devuelve)."),
        ...t.me.neighbors.map(sideRow)));
    }
    const row = [];
    if (t.can_deal && t.host === me) row.push(btn("btn-primary", "🃏 Repartir ya", start));
    row.push(btn("btn-ghost", "🚪 Levantarme de la mesa", leave));
    panels.push(h("div", { class: "bjm-leave" }, h("div", { class: "bjm-row bjm-center" }, row), note("Si te levantás, te devuelvo todo lo que tengas apostado.")));
    u.controls.replaceChildren(...panels);
  }

  /* ---------- actualización en vivo ---------- */
  async function poll() {
    if (!live() || st.polling || st.busy) return;
    st.polling = true;
    try {
      if (st.tid == null) {
        const d = await gget("/api/bjtable/list");
        if (!live() || st.tid != null) return;
        setBalance(d.balance, false);
        if (d.mine != null) { await openTable(d.mine); return; }      // ya estabas sentado (por ejemplo, si recargaste la página)
        renderList(d);
      } else {
        const tid = st.tid, d = await gget("/api/bjtable", { id: tid, v: st.v ?? "" });
        if (!live() || st.tid !== tid) return;
        if (d.same || !pendingResults(d)) setBalance(d.balance, false);
        if (!d.same) await receive(d);
      }
    } catch (e) {
      if (e.status === 404 && st.tid != null && live()) { toast("La mesa se cerró (la borraron o quedó inactiva).", ""); backToList(); }
    } finally { st.polling = false; }
  }

  clearInterval(S.bjmTimer); clearInterval(S.bjmTick);
  S.bjmTimer = setInterval(poll, 1300);
  S.bjmTick = setInterval(tick, 250);
  S.cleanups.push(() => { clearInterval(S.bjmTimer); clearInterval(S.bjmTick); S.bjmRun = null; });

  root.replaceChildren(sectionTitle("Blackjack", "Mesas en vivo: jugá con hasta 5 personas del servidor contra el dealer. Mismas reglas que contra la casa."),
    bjTabs(root, token, "multi"), holder,
    howBox([
      ["Armá la mesa", "Abrí una mesa o sentate en una abierta (hasta 5). Sentarte es gratis: te quedás en la mesa ronda tras ronda y apostás cuando empieza cada una. Quien abrió la mesa puede borrarla."],
      ["Apuestas y reparto", "Todos apuestan su mano. Se reparte cuando todos apostaron, cuando quien abrió la mesa aprieta Repartir o cuando se acaba el tiempo: quien no apostó se queda mirando esa ronda (tras 3 seguidas sin apostar te levantan)."],
      ["Apostar por tus vecinos", "Si ya apostaste, también podés apostar por el jugador de tu izquierda y/o de tu derecha. Cobrás según le vaya a su mano contra el dealer."],
      ["Pagos", "Ganar paga 1 a 1, el blackjack natural paga 3 a 2 y el empate devuelve la apuesta. Cada uno juega por turnos contra el dealer, que se planta en 17."]]));
  holder.replaceChildren(lobby);
  await poll();
};
