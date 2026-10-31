"use strict";
/* ============================================================
   Sonidos del panel — se sintetizan en el navegador con Web Audio:
   no hay archivos de audio, no se descarga nada y no hay derechos de autor.
   ============================================================ */
const Sfx = (() => {
  let ctx = null, master = null, noise = null;
  const prefs = { muted: false, volume: 0.6 };
  try { Object.assign(prefs, JSON.parse(localStorage.getItem("dilus_sfx") || "{}")); } catch { /* sin almacenamiento */ }
  const save = () => { try { localStorage.setItem("dilus_sfx", JSON.stringify(prefs)); } catch { /* ok */ } };

  function ensure() {
    if (ctx) return ctx;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = prefs.muted ? 0 : prefs.volume;
    const comp = ctx.createDynamicsCompressor();        // evita que varios sonidos juntos "revienten"
    comp.threshold.value = -16; comp.ratio.value = 5;
    master.connect(comp); comp.connect(ctx.destination);
    noise = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
    const d = noise.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    return ctx;
  }
  function ready() {
    const c = ensure();
    if (!c || prefs.muted) return null;
    if (c.state === "suspended") c.resume();
    return c;
  }
  ["pointerdown", "keydown", "touchstart"].forEach(ev => addEventListener(ev, () => {
    const c = ensure();
    if (c && c.state === "suspended") c.resume();
  }, { passive: true }));

  /* nota: oscilador con envolvente */
  function tone({ f = 440, to = null, type = "sine", dur = 0.15, vol = 0.25, at = 0, attack = 0.004 }) {
    const c = ready(); if (!c) return;
    const t0 = c.currentTime + at, o = c.createOscillator(), g = c.createGain();
    o.type = type;
    o.frequency.setValueAtTime(f, t0);
    if (to) o.frequency.exponentialRampToValueAtTime(Math.max(1, to), t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(vol, t0 + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g); g.connect(master);
    o.start(t0); o.stop(t0 + dur + 0.03);
  }
  /* soplido / chasquido: ruido filtrado con envolvente */
  function hiss({ dur = 0.1, vol = 0.2, at = 0, type = "bandpass", f = 2000, to = null, q = 1, attack = 0.003 }) {
    const c = ready(); if (!c) return;
    const t0 = c.currentTime + at, s = c.createBufferSource(), flt = c.createBiquadFilter(), g = c.createGain();
    s.buffer = noise; s.loop = true;
    flt.type = type; flt.Q.value = q;
    flt.frequency.setValueAtTime(f, t0);
    if (to) flt.frequency.exponentialRampToValueAtTime(Math.max(20, to), t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(vol, t0 + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    s.connect(flt); flt.connect(g); g.connect(master);
    s.start(t0, Math.random() * 0.5); s.stop(t0 + dur + 0.03);
  }

  const S = {
    click() { tone({ f: 900, to: 640, type: "triangle", dur: 0.06, vol: 0.07 }); },
    chip() {
      hiss({ f: 4200, q: 2, dur: 0.045, vol: 0.2 });
      tone({ f: 2300, to: 1700, type: "triangle", dur: 0.07, vol: 0.08 });
      tone({ f: 3100, dur: 0.05, vol: 0.04, at: 0.02 });
    },
    chips(n = 3) { for (let i = 0; i < n; i++) { hiss({ f: 4000 + i * 200, q: 2, dur: 0.045, vol: 0.16, at: i * 0.06 }); tone({ f: 2200 + i * 150, to: 1600, type: "triangle", dur: 0.07, vol: 0.06, at: i * 0.06 }); } },
    deal() {
      hiss({ f: 1400, to: 5200, q: 0.8, dur: 0.16, vol: 0.18 });
      tone({ f: 150, to: 90, dur: 0.06, vol: 0.09, at: 0.13 });
    },
    flip() { hiss({ f: 2600, q: 1.2, dur: 0.1, vol: 0.13 }); tone({ f: 420, to: 260, type: "triangle", dur: 0.09, vol: 0.05 }); },
    tick(power = 0.5) {
      tone({ f: 1500 + power * 900, to: 900, type: "square", dur: 0.02, vol: 0.02 + power * 0.035 });
      hiss({ f: 3500, q: 3, dur: 0.015, vol: 0.04 });
    },
    drop() {                                           // la bola rebota y se acomoda
      [0, 0.11, 0.2, 0.27, 0.32].forEach((d, i) => {
        tone({ f: 700 - i * 70, to: 380, type: "triangle", dur: 0.07, vol: 0.16 - i * 0.025, at: d });
        hiss({ f: 2800, q: 2, dur: 0.03, vol: 0.07, at: d });
      });
    },
    spinStart() {
      hiss({ type: "lowpass", f: 300, to: 2600, dur: 0.7, vol: 0.2, attack: 0.08 });
      tone({ f: 180, to: 520, type: "sawtooth", dur: 0.6, vol: 0.04 });
    },
    whirr(ms = 5000) { hiss({ type: "bandpass", f: 900, to: 260, q: 0.6, dur: ms / 1000, vol: 0.06, attack: 0.35 }); },
    win(big = false) {
      const notes = big ? [523, 659, 784, 1047, 1319, 1568] : [523, 659, 784, 1047];
      notes.forEach((f, i) => { tone({ f, type: "triangle", dur: 0.38, vol: 0.14, at: i * 0.085 }); tone({ f: f * 2, dur: 0.26, vol: 0.045, at: i * 0.085 }); });
      if (big) S.coins(10);
    },
    lose() {
      tone({ f: 330, to: 220, type: "sawtooth", dur: 0.35, vol: 0.05 });
      tone({ f: 247, to: 147, type: "sawtooth", dur: 0.5, vol: 0.05, at: 0.18 });
    },
    push() { tone({ f: 440, type: "triangle", dur: 0.18, vol: 0.09 }); tone({ f: 440, type: "triangle", dur: 0.24, vol: 0.07, at: 0.18 }); },
    blackjack() {
      [523, 659, 784, 1047, 784, 1047, 1319].forEach((f, i) => { tone({ f, type: "triangle", dur: 0.3, vol: 0.15, at: i * 0.1 }); tone({ f: f / 2, type: "sine", dur: 0.3, vol: 0.08, at: i * 0.1 }); });
      S.coins(14);
    },
    jackpot() {
      for (let k = 0; k < 3; k++) [523, 659, 784, 1047, 1319].forEach((f, i) => tone({ f: f * (1 + k * 0.5), type: "triangle", dur: 0.28, vol: 0.12, at: k * 0.5 + i * 0.07 }));
      S.coins(26);
    },
    coins(n = 6) { for (let i = 0; i < n; i++) tone({ f: 2400 + Math.random() * 1200, to: 3300 + Math.random() * 600, dur: 0.16, vol: 0.06, at: i * 0.06 + Math.random() * 0.03 }); },
    reelStop() { tone({ f: 200, to: 90, dur: 0.13, vol: 0.24 }); hiss({ f: 900, q: 1, dur: 0.06, vol: 0.14 }); },
    lever() { tone({ f: 120, to: 300, type: "sawtooth", dur: 0.25, vol: 0.07 }); hiss({ f: 600, to: 2000, dur: 0.25, vol: 0.1 }); },
    error() { tone({ f: 200, type: "square", dur: 0.12, vol: 0.05 }); tone({ f: 160, type: "square", dur: 0.16, vol: 0.05, at: 0.1 }); },
    notify() { tone({ f: 880, dur: 0.12, vol: 0.07 }); tone({ f: 1318, dur: 0.22, vol: 0.06, at: 0.09 }); },
  };

  return {
    ...S,
    get muted() { return prefs.muted; },
    get volume() { return prefs.volume; },
    setMuted(m) { prefs.muted = !!m; save(); if (ctx) master.gain.setTargetAtTime(prefs.muted ? 0 : prefs.volume, ctx.currentTime, 0.02); if (!m) ensure(); },
    setVolume(v) { prefs.volume = Math.max(0, Math.min(1, v)); save(); if (ctx && !prefs.muted) master.gain.setTargetAtTime(prefs.volume, ctx.currentTime, 0.02); },
  };
})();
