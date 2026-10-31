"use strict";
/* ============================================================
   Efectos de partículas: confeti, monedas y destellos sobre toda la pantalla.
   ============================================================ */
const Fx = (() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let cv = null, g = null, parts = [], raf = 0, last = 0, dpr = 1;
  const rnd = (a, b) => a + Math.random() * (b - a);
  const COLORS = ["#e8c35a", "#f3d57a", "#8b5cf6", "#d946ef", "#ffffff", "#22c55e", "#38bdf8"];

  function resize() {
    dpr = Math.min(devicePixelRatio || 1, 2);
    cv.width = innerWidth * dpr; cv.height = innerHeight * dpr;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function ensure() {
    if (cv) return;
    cv = document.createElement("canvas"); cv.className = "fx-canvas";
    document.body.append(cv); g = cv.getContext("2d"); resize();
    addEventListener("resize", resize);
  }
  function star(x, y, r) {
    g.beginPath();
    for (let i = 0; i < 8; i++) { const rr = i % 2 ? r * 0.3 : r, a = i * Math.PI / 4; g.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr); }
    g.closePath(); g.fill();
  }
  function loop(t) {
    const dt = Math.min(0.033, (t - last) / 1000); last = t;
    g.clearRect(0, 0, innerWidth, innerHeight);
    parts = parts.filter(p => (p.life -= dt) > 0 && p.y < innerHeight + 80);
    for (const p of parts) {
      p.vy += p.gravity * dt; p.vx *= 1 - p.drag * dt; p.vy *= 1 - p.drag * dt;
      p.x += p.vx * dt; p.y += p.vy * dt; p.rot += p.vr * dt; p.spin += p.vs * dt;
      g.save(); g.globalAlpha = Math.max(0, Math.min(1, p.life * 2.2));
      g.translate(p.x, p.y); g.rotate(p.rot); g.fillStyle = p.color;
      if (p.shape === "rect") { g.scale(1, Math.cos(p.spin)); g.fillRect(-p.size / 2, -p.size / 3, p.size, p.size / 1.6); }
      else if (p.shape === "coin") {
        g.scale(Math.abs(Math.cos(p.spin)) * 0.9 + 0.1, 1);
        g.fillStyle = "#e8c35a"; g.beginPath(); g.arc(0, 0, p.size / 2, 0, 7); g.fill();
        g.strokeStyle = "#b8902b"; g.lineWidth = 1.5; g.beginPath(); g.arc(0, 0, p.size / 2 - 2.2, 0, 7); g.stroke();
      } else if (p.shape === "star") star(0, 0, p.size);
      else { g.beginPath(); g.arc(0, 0, p.size / 2, 0, 7); g.fill(); }
      g.restore();
    }
    if (parts.length) raf = requestAnimationFrame(loop); else { raf = 0; g.clearRect(0, 0, innerWidth, innerHeight); }
  }
  function spawn(list) {
    if (reduce) return;
    ensure(); parts.push(...list);
    if (!raf) { last = performance.now(); raf = requestAnimationFrame(loop); }
  }
  const mk = o => ({ x: 0, y: 0, vx: 0, vy: 0, gravity: 900, drag: 0.6, rot: rnd(0, 6.28), vr: rnd(-8, 8), spin: rnd(0, 6.28), vs: rnd(6, 14), size: rnd(7, 12), life: rnd(1.4, 2.4), color: "#fff", shape: "rect", ...o });

  return {
    confetti(x, y, n = 90, power = 1) {
      spawn(Array.from({ length: n }, () => {
        const a = rnd(-Math.PI * 0.95, -Math.PI * 0.05), v = rnd(260, 760) * power;
        return mk({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, color: COLORS[(Math.random() * COLORS.length) | 0], shape: Math.random() < 0.2 ? "circle" : "rect" });
      }));
    },
    coins(x, y, n = 22, power = 1) {
      spawn(Array.from({ length: n }, () => {
        const a = rnd(-Math.PI * 0.9, -Math.PI * 0.1), v = rnd(300, 720) * power;
        return mk({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, shape: "coin", size: rnd(14, 22), gravity: 1300, life: rnd(1.6, 2.6), vs: rnd(8, 18) });
      }));
    },
    rain(n = 70) {
      spawn(Array.from({ length: n }, () => mk({
        x: rnd(0, innerWidth), y: rnd(-innerHeight * 0.6, -20), vx: rnd(-40, 40), vy: rnd(80, 260), shape: "coin", size: rnd(14, 24), gravity: 500, drag: 0.1, life: rnd(2.5, 4),
      })));
    },
    sparkle(x, y, n = 14) {
      spawn(Array.from({ length: n }, () => {
        const a = rnd(0, 6.28), v = rnd(60, 220);
        return mk({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, shape: "star", size: rnd(4, 9), color: "#fff1b8", gravity: 0, drag: 2.2, life: rnd(0.5, 1) });
      }));
    },
    at(el, kind = "confetti", ...args) {                 // dispara el efecto desde el centro de un elemento
      if (!el) return;
      const r = el.getBoundingClientRect();
      this[kind](r.left + r.width / 2, r.top + r.height / 2, ...args);
    },
  };
})();
