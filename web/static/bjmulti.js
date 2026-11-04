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
    tid: null, v: null, t: null, ui: null, listSig: "", ctlSig: "", deadlineAt: 0, shownRound: -1, celebrated: 0, wasMyTurn: false,
  };
  const holder = h("div", { class: "bjm" });

  /* ---------- apuesta (se comparte entre la lista y la mesa) ---------- */
  const setBet = v => { st.bet = v; betInput.value = v; chipEls.forEach(c => c.classList.remove("sel")); };
  const betInput = h("input", { class: "num-input", type: "number", inputmode: "numeric", min: lim.bj_min, value: st.bet, "aria-label": "Tu apuesta",
    oninput: e => { st.bet = Math.max(0, Math.min(lim.bj_max, parseInt(e.target.value || "0", 10) || 0)); chipEls.forEach(c => c.classList.remove("sel")); } });
  const chipEls = chipRack(chipVals, st.bet, v => { st.bet = v; betInput.value = v; });
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
  const pendingResults = t => !!t && !t.seats.length && !!t.last && t.last.round !== st.celebrated;   // resultados que todavía no se mostraron
  function betOk() {
    if (st.bet < lim.bj_min) { toast(`La apuesta mínima es ${fmt(lim.bj_min)} monedas.`, "err"); return false; }
    if (st.bet > S.profile.balance) { toast("No te alcanza el saldo para esa apuesta.", "err"); return false; }
    return true;
  }

  /* ---------- pantalla 1: lista de mesas ---------- */
  const listBox = h("div", { class: "bjm-list" });
  const lobby = h("div", { class: "bjm-lobby" },
    h("div", { class: "card bjm-new" },
      h("h3", { text: "Tu apuesta" }),
      h("p", { class: "note", text: `Cada jugador apuesta lo suyo (mínimo ${fmt(lim.bj_min)} monedas, sin máximo). Se descuenta al sentarte y te la devuelvo entera si te vas o si la mesa se cierra antes de repartir.` }),
      betBox,
      h("div", { class: "bjm-actions" }, h("button", { class: "btn btn-gold btn-lg", text: "➕ Abrir una mesa nueva", onclick: createTable }))),
    h("h3", { class: "bjm-sub", text: "Mesas del servidor" }), listBox);

  function renderList(d) {
    const sig = JSON.stringify(d.tables.map(x => [x.id, x.status, x.players.map(p => [p.id, p.bet])]));
    if (sig === st.listSig) return;
    st.listSig = sig;
    if (!d.tables.length) {
      listBox.replaceChildren(h("p", { class: "note", text: "No hay mesas abiertas ahora mismo. ¡Abrí la primera y avisale a tus amigos del servidor!" }));
      return;
    }
    listBox.replaceChildren(...d.tables.map(x => {
      const full = x.count >= x.max, playing = x.status === "playing";
      return h("div", { class: "card bjm-tcard" },
        h("div", { class: "bjm-thead" }, h("b", { text: `Mesa ${x.id}` }),
          h("span", { class: `bjm-pill ${playing ? "play" : "open"}`, text: playing ? "En juego" : full ? "Llena" : "Abierta" }),
          h("span", { class: "note", text: `${x.count}/${x.max} jugadores` })),
        h("div", { class: "bjm-players" }, x.players.length
          ? x.players.map(p => h("span", { class: "bjm-peep" }, p.avatar ? h("img", { class: "avatar", src: p.avatar, alt: "" }) : null, p.name, h("small", { text: ` ${short(p.bet)} 🪙` })))
          : h("span", { class: "note", text: "Vacía · esperando jugadores" })),
        h("div", { class: "duel-btns" },
          h("button", { class: "btn btn-primary btn-sm", disabled: playing || full, text: "🪑 Sentarme", onclick: () => joinTable(x.id) }),
          h("button", { class: "btn btn-ghost btn-sm", text: "👀 Mirar", onclick: () => openTable(x.id) })));
    }));
  }

  async function createTable() {
    if (st.busy || !betOk()) return;
    st.busy = true;
    try {
      const r = await gpost("/api/bjtable/create", { bet: st.bet });
      if (!live()) return;
      Sfx.chips(2); setBalance(r.balance);
      await openTable(r.table.id, r.table);
    } catch (e) { toast(e.message, "err"); } finally { st.busy = false; if (live() && st.ui) renderControls(true); }
  }
  async function joinTable(id) {
    if (st.busy || !betOk()) return;
    st.busy = true;
    try {
      const r = await gpost("/api/bjtable/join", { id, bet: st.bet });
      if (!live()) return;
      Sfx.chips(2); setBalance(r.balance);
      await openTable(id, r.table);
    } catch (e) { toast(e.message, "err"); st.listSig = ""; } finally { st.busy = false; if (live() && st.ui) renderControls(true); }
  }
  function backToList() {
    st.tid = null; st.t = null; st.ui = null; st.v = null; st.pending = null; st.listSig = ""; st.shownRound = -1;
    holder.replaceChildren(lobby);
    poll();
  }

  /* ---------- pantalla 2: la mesa ---------- */
  function slotEl() {
    const avatar = h("img", { class: "avatar bjm-av", alt: "" }), name = h("span", { class: "bjm-name" }), val = h("span", { class: "val hide" });
    const hand = h("div", { class: "hand" }), bet = h("div", { class: "bjm-bet" }), tag = h("div", { class: "bjm-tag" });
    const bar = h("i"), timer = h("div", { class: "bjm-timer" }, bar);
    const el = h("div", { class: "bjm-seat empty" }, h("div", { class: "bjm-who" }, avatar, name, val), hand, bet, tag, timer);
    return { el, avatar, name, val, hand, bet, tag, bar, timer, uid: null };
  }
  function buildTable() {
    const u = st.ui = { slots: [] };
    u.title = h("b", { class: "bjm-title" });
    u.sub = h("span", { class: "note" });
    u.back = h("button", { class: "btn btn-ghost btn-sm", text: "← Mesas", onclick: backToList });
    u.dealerHand = h("div", { class: "hand" });
    u.dealerVal = h("span", { class: "val hide" });
    u.shoe = h("div", { class: "shoe" }, h("i"), h("i"), h("i"));
    u.mid = h("div", { class: "bjm-mid" });
    u.seats = h("div", { class: "bjm-seats" });
    for (let i = 0; i < BJM_SEATS; i++) { const s = slotEl(); u.slots.push(s); u.seats.append(s.el); }
    u.controls = h("div", { class: "bj-controls bjm-controls" });
    u.table = h("div", { class: "bj-table bjm-table" }, u.shoe,
      h("div", { class: "seat" }, h("div", { class: "seat-label" }, "Dealer", u.dealerVal), u.dealerHand), u.mid, u.seats);
    u.wrap = h("div", { class: "bj bjm-wrap" }, h("div", { class: "bjm-head" }, u.back, u.title, u.sub), u.table, u.controls);
  }

  async function openTable(tid, initial) {
    st.tid = tid; st.v = null; st.t = null; st.ctlSig = ""; st.shownRound = -1; st.celebrated = 0; st.wasMyTurn = false; st.pending = null;
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

  function paintSeat(sl, r, t, reveal) {
    sl.el.classList.toggle("empty", !r);
    sl.el.classList.toggle("turn", !!r && r.status === "turn");
    sl.el.classList.toggle("me", !!r && r.id === me);
    for (const c of ["win", "lose", "push", "bj"]) sl.el.classList.remove("res-" + c);
    if (!r) {
      sl.name.textContent = "Asiento libre"; sl.avatar.style.display = "none"; sl.bet.textContent = ""; sl.tag.textContent = ""; sl.tag.className = "bjm-tag";
      bjmVal(sl.val, null); sl.timer.classList.remove("on"); return;
    }
    sl.name.textContent = r.id === me ? `${r.name} (vos)` : r.name;
    if (r.avatar) { sl.avatar.src = r.avatar; sl.avatar.style.display = ""; } else sl.avatar.style.display = "none";
    sl.bet.textContent = `🪙 ${fmt(r.bet)}${r.doubled ? " · doblada" : ""}`;
    let text = "", cls = "";
    if (r.status === "done" && reveal) {
      const [label, c] = BJM_RESULT[r.outcome] || ["", ""];
      text = `${label} ${bjmNet(r.net)}`; cls = c; sl.el.classList.add("res-" + c);
    } else if (r.status === "done") {
      text = r.value > 21 ? "💥 Se pasó" : (r.cards.length === 2 && r.value === 21) ? "★ Blackjack" : "✋ Plantado";
    } else if (r.status === "turn") text = "🎯 Jugando…";
    else if (r.status === "wait") text = t.status === "playing" ? "⏳ Esperando turno" : "✅ Apuesta lista";
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
    const showLast = !t.seats.length && !!t.last;
    const rows = showLast ? t.last.seats : t.seats;
    const dealer = showLast ? t.last.dealer : t.dealer;
    const dealerValue = showLast ? t.last.dealer_value : t.dealer_value;
    const rnd = showLast ? t.last.round : t.round;
    const fresh = st.shownRound !== rnd;               // otra ronda: se limpia la mesa
    st.shownRound = rnd;
    const myRow = rows.find(r => r.id === me);

    u.title.textContent = `Mesa ${t.id}`;
    u.sub.textContent = t.status === "playing" ? `Ronda ${t.round} · en juego` : t.seats.length ? "Abierta · esperando jugadores" : "Libre";
    u.back.style.display = t.me.seated ? "none" : "";
    if (!first && t.me.my_turn && !st.wasMyTurn) { toast("¡Es tu turno en el blackjack! 🃏", "gold"); Sfx.push(); }
    st.wasMyTurn = t.me.my_turn;
    if (t.turn_left != null) st.deadlineAt = performance.now() + t.turn_left * 1000;

    if (fresh) {
      u.dealerHand.replaceChildren(); bjmVal(u.dealerVal, null);
      u.slots.forEach(sl => { sl.hand.replaceChildren(); sl.uid = null; bjmVal(sl.val, null); });
    }
    u.slots.forEach((sl, i) => {                       // quién está sentado dónde
      const r = rows[i] || null, id = r ? r.id : null;
      if (sl.uid !== id || (r && r.cards.length < sl.hand.children.length)) { sl.hand.replaceChildren(); bjmVal(sl.val, null); }
      sl.uid = id;
      paintSeat(sl, r, t, false);
    });
    if (dealer.length < u.dealerHand.children.length) { u.dealerHand.replaceChildren(); bjmVal(u.dealerVal, null); }
    paintMid(t, false, myRow);
    renderControls();

    /* reparto inicial: una carta a cada uno, otra al dealer, y vuelta */
    if (fresh && !calm && t.status === "playing") {
      for (let k = 0; k < 2; k++) {
        for (let i = 0; i < rows.length; i++) {
          await dealTo(u, u.slots[i].hand, rows[i].cards[k], { seat: true });
          if (!live() || st.ui !== u) return;
          bjmVal(u.slots[i].val, handValue(rows[i].cards.slice(0, k + 1)), false);
        }
        await dealTo(u, u.dealerHand, dealer[k], { down: dealer[k] === null });
        if (!live() || st.ui !== u) return;
        if (dealer[k]) bjmVal(u.dealerVal, handValue(dealer.slice(0, 1)), false);
      }
    }
    for (let i = 0; i < rows.length; i++) {            // cartas nuevas de cada mano (pedir, doblar)
      const sl = u.slots[i], cards = rows[i].cards;
      while (sl.hand.children.length < cards.length) {
        await dealTo(u, sl.hand, cards[sl.hand.children.length], { instant: calm, seat: true });
        if (!live() || st.ui !== u) return;
        bjmVal(sl.val, handValue(cards.slice(0, sl.hand.children.length)), handValue(cards.slice(0, sl.hand.children.length)) > 21);
      }
      sl.hand.style.setProperty("--ov", `${ovFor(cards.length)}px`);
      bjmVal(sl.val, rows[i].value, rows[i].value > 21);
    }
    if (dealer.length) {
      await syncDealer(u, dealer, dealerValue, !calm);
      if (!live() || st.ui !== u) return;
    }

    /* terminó la ronda: se muestran los resultados */
    if (showLast) {
      await sleep(calm ? 0 : 250);
      if (!live() || st.ui !== u) return;
      rows.forEach((r, i) => paintSeat(u.slots[i], r, t, true));
      paintMid(t, true, myRow);
      if (st.celebrated !== t.last.round) {
        st.celebrated = t.last.round;
        if (myRow) {
          setBet(Math.max(lim.bj_min, Math.min(lim.bj_max, myRow.base_bet)));    // la revancha arranca con tu misma apuesta
          if (!first) celebrate(myRow, u);
        }
        setBalance(t.balance, !first);
      }
      renderControls(true);
    }
  }

  function celebrate(r, u) {
    const banner = u.mid.querySelector(".banner");
    if (r.outcome === "blackjack") { Sfx.blackjack(); if (banner) Fx.at(banner, "confetti", 170, 1.3); Fx.rain(50); }
    else if (r.net > 0) { Sfx.win(r.net >= 1000); if (banner) Fx.at(banner, "confetti", 90); }
    else if (r.outcome === "push") Sfx.push();
    else Sfx.lose();
    if (r.net > 0) toast(`¡Ganaste ${fmt(r.net)} monedas en la mesa! 🃏`, "gold");
  }

  function paintMid(t, final, myRow) {
    const u = st.ui, showLast = !t.seats.length && !!t.last;
    if (final && showLast && myRow && BJM_RESULT[myRow.outcome]) {
      const [label, cls] = BJM_RESULT[myRow.outcome];
      const mine = { blackjack: "¡BLACKJACK!", win: "¡GANASTE!", dealer_bust: "EL DEALER SE PASÓ", lose: "PERDISTE", bust: "TE PASASTE", dealer_blackjack: "BLACKJACK DEL DEALER", push: "EMPATE" }[myRow.outcome] || label;
      u.mid.replaceChildren(h("div", { class: `banner ${cls}` }, mine,
        h("small", { text: myRow.net > 0 ? `+${fmt(myRow.net)} monedas` : myRow.net < 0 ? `−${fmt(-myRow.net)} monedas` : "Te devuelvo tu apuesta" })));
      return;
    }
    let main, sub = "";
    if (t.status === "playing") {
      const cur = t.seats.find(s => s.id === t.turn);
      main = cur ? (cur.id === me ? "🎯 ¡Es tu turno!" : `Turno de ${cur.name}`) : "Repartiendo…";
    } else if (showLast) {
      main = final ? `Ronda ${t.last.round} terminada` : "El dealer juega…";
      sub = final ? "Sentate de nuevo para jugar otra" : "";
    } else if (t.seats.length) {
      main = `Esperando jugadores · ${t.seats.length}/${t.max_seats}`;
      const host = t.seats.find(s => s.id === t.host);
      sub = t.seats.length < t.min_players ? `Hacen falta al menos ${t.min_players} para repartir`
        : t.host === me ? "Repartí cuando estén todos" : `Esperando que reparta ${host ? host.name : "quien abrió la mesa"}`;
    } else main = "Mesa libre · sentate para empezar";
    u.midSub = h("small", { class: "bjm-midsub", text: sub });
    u.mid.replaceChildren(h("div", { class: "bjm-midtext", text: main }), u.midSub);
  }

  /* cuenta regresiva del turno (solo visual: el servidor es quien planta a quien no juega) */
  function tick() {
    const t = st.t, u = st.ui;
    if (!t || !u || t.status !== "playing" || t.turn == null) return;
    const left = Math.max(0, (st.deadlineAt - performance.now()) / 1000);
    const sl = u.slots.find(s => s.uid === t.turn);
    if (sl) { sl.bar.style.width = `${Math.min(100, left / t.turn_time * 100)}%`; sl.timer.classList.toggle("low", left < 10); }
    if (u.midSub && u.midSub.isConnected) u.midSub.textContent = `${Math.ceil(left)} s`;
  }

  /* ---------- controles ---------- */
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
  async function sit() { if (betOk() && await call("/api/bjtable/join", { bet: st.bet })) Sfx.chips(2); }
  async function start() { await call("/api/bjtable/start", {}); }
  async function leave() {
    const r = await call("/api/bjtable/leave", {});
    if (r && r.left) { Sfx.chips(2); toast("Saliste de la mesa. Te devolví tu apuesta.", ""); backToList(); }
  }

  function renderControls(force) {
    const u = st.ui;
    if (!u) return;
    const t = st.t, seated = !!t && t.me.seated;
    const sig = JSON.stringify([!!t, t && t.status, seated, t && t.me.my_turn, t && t.me.can_double, t && t.seats.length, t && t.host, st.busy, !!t && S.profile.balance >= t.me.base_bet]);
    if (!force && sig === st.ctlSig) return;
    st.ctlSig = sig;
    const btn = (cls, label, fn, disabled) => h("button", { class: `btn ${cls} btn-lg`, disabled: disabled || st.busy, onclick: fn }, label);
    const note = text => h("p", { class: "note bjm-note", text });
    if (!t) { u.controls.replaceChildren(note("Cargando la mesa…")); return; }
    if (t.status === "playing") {
      if (seated && t.me.my_turn) {
        u.controls.replaceChildren(btn("btn-primary", "🃏 Pedir", () => act("hit")), btn("btn-ghost", "✋ Plantarse", () => act("stand")),
          btn("btn-gold", `💰 Doblar (${fmt(t.me.base_bet)})`, () => act("double"), !t.me.can_double || S.profile.balance < t.me.base_bet));
      } else u.controls.replaceChildren(note(seated ? "Esperá tu turno: los demás están jugando. Si alguien no juega a tiempo, se planta solo." : "Estás mirando la mesa. Cuando termine la ronda podés sentarte."));
      return;
    }
    if (seated) {
      const isHost = t.host === me, host = t.seats.find(s => s.id === t.host);
      u.controls.replaceChildren(
        isHost ? (t.seats.length >= t.min_players ? btn("btn-gold", `🃏 Repartir (${t.seats.length} jugadores)`, start) : note(`Falta al menos un jugador más para repartir (mínimo ${t.min_players}).`))
          : note(`Esperando a que reparta ${host ? host.name : "quien abrió la mesa"}.`),
        h("div", { class: "bjm-leave" }, btn("btn-ghost", "🚪 Salir de la mesa", leave), note("Si salís antes de repartir te devuelvo tu apuesta.")));
      return;
    }
    if (t.seats.length >= t.max_seats) { u.controls.replaceChildren(note("La mesa está llena. Esperá a que termine la ronda o buscá otra.")); return; }
    u.controls.replaceChildren(h("div", { class: "bjm-betwrap" }, betBox, h("div", { class: "bjm-row" }, btn("btn-primary", "🪑 Sentarme con esta apuesta", sit)),
      note(t.last ? "¿Revancha? Sentate de nuevo con la misma apuesta o cambiala." : `Apuesta mínima: ${fmt(lim.bj_min)} monedas · sin máximo.`)));
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
      if (e.status === 404 && st.tid != null && live()) { toast("La mesa se cerró.", ""); backToList(); }
    } finally { st.polling = false; }
  }

  clearInterval(S.bjmTimer); clearInterval(S.bjmTick);
  S.bjmTimer = setInterval(poll, 1300);
  S.bjmTick = setInterval(tick, 250);
  S.cleanups.push(() => { clearInterval(S.bjmTimer); clearInterval(S.bjmTick); S.bjmRun = null; });

  root.replaceChildren(sectionTitle("Blackjack", "Mesas en vivo: jugá con hasta 5 personas del servidor contra el dealer. Mismas reglas que contra la casa."),
    bjTabs(root, token, "multi"), holder,
    howBox([
      ["Armá la mesa", "Abrí una mesa o sentate en una abierta con tu apuesta. Pueden sentarse hasta 5 jugadores; quien abrió la mesa reparte cuando haya al menos 2."],
      ["Por turnos", "Cada uno juega su mano de izquierda a derecha: pedir, plantarse o doblar. Si no jugás a tiempo, tu mano se planta sola."],
      ["Pagos", "Ganar paga 1 a 1, el blackjack natural paga 3 a 2 y el empate devuelve la apuesta. Cada uno juega contra el dealer, no contra los demás; el dealer se planta en 17."]]));
  holder.replaceChildren(lobby);
  await poll();
};
