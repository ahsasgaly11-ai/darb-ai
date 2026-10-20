/* دَرْب AI — الواجهة */
(() => {
  "use strict";

  const LEVEL_AR = { low: "منخفض", medium: "متوسط", high: "مرتفع", critical: "حرج" };
  const KIND_AR = { seed: "أسبوعية", weekly: "أسبوعية", sentinel: "فحص يومي", manual: "يدوية" };
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const color = (lvl) => css(`--${lvl}`) || "#888";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // الأرقام السالبة تُعزل باتجاه LTR حتى لا تظهر الإشارة في الطرف الخطأ داخل النص العربي
  const fmtN = (n, d = 0) => {
    if (n == null) return "—";
    const s = Number(n).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
    return Number(n) < 0 ? `\u2066${s}\u2069` : s;
  };
  const dtf = new Intl.DateTimeFormat("ar-AE", { timeZone: "Asia/Dubai", dateStyle: "medium", timeStyle: "short" });
  const df = new Intl.DateTimeFormat("ar-AE", { timeZone: "Asia/Dubai", day: "numeric", month: "short" });
  const fmtDT = (s) => dtf.format(new Date(s));
  const ago = (s) => {
    const m = (Date.now() - new Date(s)) / 60000;
    if (m < 60) return `قبل ${fmtN(Math.max(1, m))} دقيقة`;
    if (m < 1440) return `قبل ${fmtN(m / 60)} ساعة`;
    return `قبل ${fmtN(m / 1440)} يوم`;
  };
  const SRC_AR = { demo: "محاكاة", datagovsg: "كاميرا حقيقية · سنغافورة LTA", az511: "كاميرا حقيقية · أريزونا ADOT" };
  const ISSUE_KIND_AR = { deterioration: "تدهور الرصف", pothole: "حفرة", sudden: "تغيّر مفاجئ", cracking: "تشققات" };
  const srcLabel = (t) => SRC_AR[t] || "كاميرا حية";
  const weeksText = (w) => (w == null ? "مستقر" : w === 0 ? "تجاوزها" : w > 52 ? "أكثر من سنة" : `~${fmtN(w)} أسبوع`);

  async function api(path, opts = {}) {
    const headers = { "Content-Type": "application/json" };
    const tok = safeGet("darb-admin");
    if (tok) headers["X-Admin-Token"] = tok;
    const r = await fetch(path, { ...opts, headers });
    if (r.status === 401) {
      const t = prompt("هذه العملية تتطلب رمز المشرف:");
      if (t) { safeSet("darb-admin", t); return api(path, opts); }
      throw new Error("unauthorized");
    }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  }
  function safeGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
  function safeSet(k, v) { try { localStorage.setItem(k, v); } catch { /* تخزين غير متاح */ } }


  // أيقونات خطية (24×24) — تُحقن في كل عنصر يحمل data-icon
  const ICONS = {
    grid: "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
    map: "M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14",
    cycle: "M21 12a9 9 0 0 1-15.5 6.2M3 12A9 9 0 0 1 18.5 5.8M18.5 2v4h-4M5.5 22v-4h4",
    camera: "M4 7h3l2-3h6l2 3h3a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
    camoff: "M2 2l20 20M7 7H4a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h15M9.5 4h5l2 3h3a1 1 0 0 1 1 1v9.5M14.1 14.2A3 3 0 0 1 9.8 9.9",
    bell: "M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10 21a2 2 0 0 0 4 0",
    book: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5zM20 17v4H6.5A2.5 2.5 0 0 1 4 19.5",
    gauge: "M12 14l4-4M3.3 18a10 10 0 1 1 17.4 0",
    alert: "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
    wrench: "M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z",
    clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2",
    check: "M22 11.1V12a10 10 0 1 1-5.9-9.1M22 4 12 14l-3-3",
    activity: "M22 12h-4l-3 9L9 3l-3 9H2",
    trend: "M3 17l6-6 4 4 8-8M15 7h6v6",
    bars: "M4 20V10M10 20V4M16 20v-7M22 20H2",
    list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
    search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
    moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
    sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
    road: "M4 21 9 3M20 21 15 3M12 4v2M12 10v3M12 17v3",
    shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
    target: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
    image: "M3 5h18v14H3zM3 15l5-5 4 4 3-3 6 6M15.5 9.5h.01",
    brain: "M9 3a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 3 3h0a3 3 0 0 0 3-3V6a3 3 0 0 0-3-3zM15 3a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-3 3 3 3 0 0 1-3-3",
  };
  const svg = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICONS[name] || ""}"/></svg>`;
  function hydrateIcons(root = document) {
    root.querySelectorAll("[data-icon]:not([data-iconed])").forEach((el) => {
      el.insertAdjacentHTML("afterbegin", svg(el.dataset.icon)); el.dataset.iconed = "1";
    });
  }
  hydrateIcons();
  // الوضع الافتراضي نهاري أبيض؛ الليلي اختيار صريح من الزر ويُحفظ للزائر
  function applyTheme(t) {
    document.documentElement.dataset.ui = t;
    const b = document.getElementById("themeBtn");
    if (b) {
      b.setAttribute("aria-pressed", t === "dark" ? "true" : "false");
      const ic = b.querySelector("[data-icon]");
      if (ic) { ic.dataset.icon = t === "dark" ? "sun" : "moon"; ic.removeAttribute("data-iconed"); ic.innerHTML = ""; hydrateIcons(b); }
    }
  }
  applyTheme(safeGet("darb-ui") === "dark" ? "dark" : "light");

  const state = { summary: null, cameras: [], alerts: [], issues: [], alertFilter: "all", charts: {}, map: null, markers: {},
    current: null, region: safeGet("darb-region") || "", regions: [] };
  const rq = (path) => path + (state.region ? (path.includes("?") ? "&" : "?") + "region=" + encodeURIComponent(state.region) : "");

  // ---------- التبويبات ----------
  function showTab(name) {
    $$(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
    $$(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${name}`));
    safeSet("darb-tab", name);
    if (name === "map") setTimeout(initMap, 30);
  }
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  document.addEventListener("click", (e) => {
    const g = e.target.closest("[data-goto]");
    if (g) showTab(g.dataset.goto);
    const c = e.target.closest("[data-cam]");
    if (c && !e.target.closest("button[data-ack]")) openCamera(c.dataset.cam);
  });

  // ---------- لوحة التحكم ----------
  function renderSummary(s) {
    $("#seedingNote").hidden = !s.seeding;
    const crit = s.levels.critical + s.levels.high;
    $("#kpis").innerHTML = [
      kpi("الكاميرات المراقَبة", fmtN(s.cameras), s.awaiting ? `${fmtN(s.snapshots)} لقطة · ${fmtN(s.awaiting)} بانتظار أول التقاط نهاري` : `${fmtN(s.snapshots)} لقطة محلّلة`, false, "camera"),
      kpi("متوسط حالة الشبكة", fmtN(s.avg_condition, 1), "مؤشر الحالة من 100", false, "gauge", "ok"),
      kpi("مقاطع عالية الخطورة", fmtN(crit), `${fmtN(s.levels.critical)} حرج · ${fmtN(s.levels.high)} مرتفع`, crit > 0, "alert", "warn"),
      kpi("دون عتبة الصيانة", fmtN(s.below_threshold), "تحتاج تدخلًا تصحيحيًا", s.below_threshold > 0, "wrench"),
      kpi("مشكلات متوقعة (قبل)", fmtN(s.lifecycle.stages.predicted), "فرص صيانة وقائية", false, "clock", "warn"),
      kpi("مشكلات نشطة (أثناء)", fmtN(s.lifecycle.stages.active), `${fmtN(s.lifecycle.stages.monitoring)} قيد المراقبة بعد المعالجة`, s.lifecycle.stages.active > 0, "activity"),
      kpi("تنبيهات مفتوحة", fmtN(s.open_alerts), `${fmtN(s.alerts_7d)} خلال 7 أيام`, s.open_alerts > 0, "bell"),
    ].join("");

    const max = Math.max(1, ...Object.values(s.levels));
    $("#levelBars").innerHTML = ["critical", "high", "medium", "low"].map((l) => `
      <div class="lvl"><span>${LEVEL_AR[l]}</span><div class="track"><div class="fill" style="width:${(100 * s.levels[l]) / max}%;background:${color(l)}"></div></div><b>${fmtN(s.levels[l])}</b></div>`).join("");

    $("#prioBody").innerHTML = s.priorities.map((c, i) => {
      const r = c.risk, ci = r.ci ?? c.last_snapshot?.condition_index;
      const sl = r.slope ?? 0;
      const tr = sl < -0.15 ? ["down", "▼"] : sl > 0.15 ? ["up", "▲"] : ["flat", "■"];
      return `<tr data-cam="${esc(c.id)}">
        <td><span class="rank">${fmtN(i + 1)}</span></td>
        <td class="name"><b>${esc(c.name)}</b><span>${esc(c.road)}</span></td>
        <td><span class="pill ${r.level}">${LEVEL_AR[r.level]} · ${fmtN(r.score)}</span></td>
        <td><div class="meter"><div class="bar"><i style="width:${r.prob_90d * 100}%;background:${color(r.level)}"></i></div><span class="num">${fmtN(r.prob_90d * 100)}%</span></div></td>
        <td class="num"><b>${fmtN(ci, 0)}</b></td>
        <td class="trend ${tr[0]} num">${tr[1]} ${fmtN(sl, 2)}</td>
        <td>${weeksText(r.weeks_to_threshold)}</td>
        <td class="muted">${esc(r.top_factor || "—")}</td>
      </tr>`;
    }).join("") || `<tr><td colspan="8" class="empty">لا توجد بيانات بعد</td></tr>`;

    drawNetworkChart(s.network_trend);
  }
  const kpi = (label, value, sub, alert, icon = "gauge", tone = "") => `<div class="kpi${alert ? " alert" : ""}">
    <div class="kpi-top"><span class="ico3d ${alert ? "crit" : tone}">${svg(icon)}</span><div class="label">${label}</div></div>
    <div class="value">${value}</div><div class="sub">${sub}</div></div>`;

  function chartDefaults() {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = css("--muted");
    Chart.defaults.borderColor = css("--line");
  }

  function drawNetworkChart(rows) {
    chartDefaults();
    const ctx = $("#networkChart");
    const data = { labels: rows.map((r) => df.format(new Date(r.d))), datasets: [{
      label: "متوسط مؤشر الحالة", data: rows.map((r) => +r.ci.toFixed(1)), borderColor: css("--brand"),
      backgroundColor: css("--brand") + "22", fill: true, tension: .35, pointRadius: 0, borderWidth: 2.5 }] };
    if (state.charts.net) { state.charts.net.data = data; state.charts.net.update("none"); return; }
    state.charts.net = new Chart(ctx, { type: "line", data, options: {
      maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } }, y: { suggestedMin: 50, suggestedMax: 100 } } } });
  }

  // ---------- التنبيهات ----------
  function alertItem(a, compact) {
    return `<li class="${a.ack ? "acked" : ""}" data-cam="${esc(a.camera_id)}" style="cursor:pointer">
      <span class="sev ${a.severity}"></span>
      <div><div class="t">${esc(a.title)}</div><div class="m">${esc(a.message)}</div>
        ${!compact && !a.ack ? `<div class="row-actions"><button class="btn ghost" data-ack="${a.id}">تمت المعالجة ✓</button></div>` : ""}</div>
      <div class="when" title="${esc(fmtDT(a.ts))}">${ago(a.ts)}</div></li>`;
  }
  function renderAlerts() {
    const f = state.alertFilter;
    const list = state.alerts.filter((a) => f === "all" || (f === "open" ? !a.ack : a.severity === f));
    $("#alertList").innerHTML = list.map((a) => alertItem(a)).join("") || `<li class="empty">لا توجد تنبيهات</li>`;
    $("#recentAlerts").innerHTML = state.alerts.filter((a) => a.type !== "scene_change").slice(0, 6).map((a) => alertItem(a, true)).join("") || `<li class="empty">لا توجد تنبيهات</li>`;
    const open = state.alerts.filter((a) => !a.ack).length;
    const b = $("#alertBadge"); b.hidden = !open; b.textContent = fmtN(open);
  }
  $("#alertFilter").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    state.alertFilter = b.dataset.f;
    $$("#alertFilter button").forEach((x) => x.classList.toggle("active", x === b));
    renderAlerts();
  });
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-ack]"); if (!b) return;
    e.stopPropagation();
    await api(`/api/alerts/${b.dataset.ack}/ack`, { method: "POST" });
    await loadAlerts();
  });

  // ---------- الخريطة ----------
  function initMap() {
    if (!state.map) {
      state.map = L.map("map", { zoomControl: true }).setView([25.16, 55.3], 11);
      state.fitPending = true;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(state.map);
    }
    state.map.invalidateSize();
    renderMarkers();
  }
  function renderMarkers() {
    if (!state.map) return;
    Object.values(state.markers).forEach((m) => m.remove());
    state.markers = {};
    if (state.fitPending && state.cameras.length) {
      state.map.fitBounds(L.latLngBounds(state.cameras.map((c) => [c.lat, c.lng])).pad(0.25), { maxZoom: 13 });
      state.fitPending = false;
    }
    for (const c of state.cameras) {
      const lvl = c.risk?.level || "low";
      const col = c.risk ? color(lvl) : css("--muted");
      const icon = L.divIcon({ className: "", iconSize: [22, 22], iconAnchor: [11, 11],
        html: `<div class="marker ${c.open_alerts ? "pulse" : ""}" style="background:${col};color:${col}"></div>` });
      const s = c.last_snapshot;
      const m = L.marker([c.lat, c.lng], { icon }).addTo(state.map).bindPopup(`<div class="pop">
        ${s ? `<img src="/api/snapshots/${s.id}/image?annotated=1" alt="">` : ""}
        <b>${esc(c.name)}</b><span class="muted">${esc(c.road)}</span>
        <div class="row">${c.risk ? `<span class="pill ${lvl}">${LEVEL_AR[lvl]} · ${fmtN(c.risk.score)}</span>` : ""}
        <span class="muted">${s ? `مؤشر الحالة <b style="display:inline">${fmtN(c.risk?.ci ?? s.condition_index)}</b>` : "بانتظار أول التقاط نهاري"}</span></div>
        <button class="btn" data-cam="${esc(c.id)}">التفاصيل والتنبؤ</button></div>`, { maxWidth: 270 });
      state.markers[c.id] = m;
    }
  }

  // ---------- الكاميرات ----------
  function renderCameras() {
    const q = $("#camSearch").value.trim();
    const ann = $("#annToggle").checked ? 1 : 0;
    // الكاميرات التي لها لقطات أولًا، ثم الأعلى خطرًا
    const list = state.cameras.filter((c) => !q || (c.name + c.road).includes(q))
      .sort((a, b) => (!!b.last_snapshot - !!a.last_snapshot) || ((b.risk?.score ?? 0) - (a.risk?.score ?? 0)));
    $("#camGrid").innerHTML = list.map((c) => {
      const s = c.last_snapshot, r = c.risk;
      return `<article class="cam" data-cam="${esc(c.id)}">
        <div class="img">${s ? "" : `<span class="wait">${svg("camoff")}بانتظار أول التقاط نهاري</span>`}${s ? `<img loading="lazy" src="/api/snapshots/${s.id}/image?annotated=${ann}" alt="لقطة ${esc(c.name)}">` : ""}
          ${r ? `<span class="pill ${r.level}">${LEVEL_AR[r.level]}</span>` : ""}
          <span class="live">${srcLabel(c.source_type)} · ${s ? ago(s.ts) : "—"}</span></div>
        <div class="body"><b>${esc(c.name)}</b><span class="muted">${esc(c.road)}</span>
          <div class="stats"><span>الحالة <strong>${fmtN(s?.condition_index)}</strong></span>
          <span>الحفر <strong>${fmtN(s?.pothole_count)}</strong></span>
          <span>الخطر <strong>${fmtN(r?.score)}</strong></span>
          ${c.open_alerts ? `<span style="color:var(--critical)">● ${fmtN(c.open_alerts)} تنبيه</span>` : ""}</div></div></article>`;
    }).join("") || `<div class="empty">لا نتائج</div>`;
  }
  $("#camSearch").addEventListener("input", renderCameras);
  $("#annToggle").addEventListener("change", renderCameras);

  // ---------- تفاصيل الكاميرا ----------
  const drawer = $("#drawer");
  function closeDrawer() { drawer.classList.remove("open"); drawer.setAttribute("aria-hidden", "true"); state.current = null; }
  drawer.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeDrawer(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

  async function openCamera(id) {
    state.current = id;
    drawer.classList.add("open"); drawer.setAttribute("aria-hidden", "false");
    $("#dBody").innerHTML = `<div class="empty">جارٍ التحميل…</div>`;
    const d = await api(`/api/cameras/${encodeURIComponent(id)}`);
    if (state.current !== id) return;
    $("#dTitle").textContent = d.name;
    $("#dRoad").textContent = `${d.road} · ${srcLabel(d.source_type)}${d.source.camera_id ? " #" + d.source.camera_id : ""} · ${fmtN(d.meta.aadt)} مركبة/يوم · شاحنات ${fmtN(d.meta.heavy_vehicle_pct)}%`;
    renderDetail(d);
  }

  function gaugeSVG(score, lvl) {
    const r = 50, c = 2 * Math.PI * r, f = Math.min(1, score / 100);
    return `<svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="${r}" fill="none" stroke="${css("--surface-2")}" stroke-width="12"/>
      <circle cx="60" cy="60" r="${r}" fill="none" stroke="${color(lvl)}" stroke-width="12" stroke-linecap="round"
        stroke-dasharray="${c * f} ${c}" transform="rotate(-90 60 60)"/>
      <text x="60" y="66" text-anchor="middle" font-size="26" font-weight="700" fill="${css("--ink")}">${Math.round(score)}</text></svg>`;
  }

  function renderDetail(d) {
    const rd = d.risk_detail, fc = rd?.forecast || {}, m = d.latest_metrics || {};
    const snaps = d.snapshots.filter((s) => s.quality === "ok").slice().reverse();
    const lvl = rd?.level || "low";
    $("#dBody").innerHTML = `
      <div class="d-grid">
        <div class="card viewer">
          <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("image")}</span>لقطات الكاميرا عبر الزمن</h2><label class="switch"><input type="checkbox" id="vAnn" checked> العيوب</label></div>
          <img id="vImg" alt="لقطة الطريق">
          <div class="ctrl"><input type="range" id="vRange" min="0" max="${Math.max(0, snaps.length - 1)}" value="${Math.max(0, snaps.length - 1)}" aria-label="الخط الزمني">
            <span class="ts" id="vTs"></span></div>
        </div>
        <div class="card">
          <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("gauge")}</span>تقدير المخاطر</h2><span class="pill ${lvl}">${LEVEL_AR[lvl]}</span></div>
          ${rd ? `<div class="gauge">${gaugeSVG(rd.score, lvl)}<div>
              <div class="muted">احتمال الوصول لحالة تستوجب الصيانة خلال 90 يومًا</div>
              <div class="big" style="color:${color(lvl)}">${fmtN(rd.prob_90d * 100)}%</div></div></div>
            <div class="facts">
              <div class="fact"><div class="l">مؤشر الحالة (وسيط آخر 3 لقطات)</div><div class="v">${fmtN(fc.ci ?? m.condition_index, 1)} / 100</div></div>
              <div class="fact"><div class="l">الاتجاه (نقطة/أسبوع)</div><div class="v">${fmtN(fc.ci_slope, 2)}</div></div>
              <div class="fact"><div class="l">بلوغ عتبة الصيانة</div><div class="v">${weeksText(rd.weeks_to_threshold)}</div></div>
              <div class="fact"><div class="l">الفحص الميداني التالي</div><div class="v">خلال ${fmtN(fc.next_inspection_days)} يوم</div></div>
              <div class="fact"><div class="l">متوسط العظمى (30 يومًا)</div><div class="v">${fmtN(fc.heat?.mean_tmax, 1)}°م</div></div>
              <div class="fact"><div class="l">العامل الموسمي القادم</div><div class="v">×${fmtN(fc.season_factor, 2)}</div></div>
            </div>` : `<div class="empty">لا يوجد تقييم بعد</div>`}
        </div>
      </div>
      <div class="card mt">
        <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("trend")}</span>مؤشر الحالة: السجل والتنبؤ</h2><span class="muted">الخط المتقطع = التنبؤ لـ12 أسبوعًا · الأحمر = عتبة الصيانة</span></div>
        <div class="chart-box"><canvas id="ciChart"></canvas></div>
      </div>
      <div class="d-grid mt">
        <div class="card">
          <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("bars")}</span>لماذا هذا التقييم؟</h2><span class="muted">مساهمة كل عامل</span></div>
          ${(rd?.factors || []).map((f) => `<div class="factor"><span>${esc(f.label)}</span><div class="track"><i style="width:${f.share}%"></i></div><b>${fmtN(f.share)}%</b></div>`).join("")}
        </div>
        <div class="card">
          <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("brain")}</span>العيوب المكتشفة الآن</h2><span class="muted">${String(m.engine || "").startsWith("ai") ? "ذكاء اصطناعي (RDD2022)" : "رؤية حاسوبية"}</span></div>
          <div class="chips">${Object.entries(m.by_type || {}).map(([k, v]) => `<span class="chip">${esc(d.labels[k] || k)}: <b>${fmtN(v)}</b></span>`).join("")}</div>
          <div class="facts">
            <div class="fact"><div class="l">كثافة التشققات</div><div class="v">${fmtN(m.crack_density, 2)}%</div></div>
            <div class="fact"><div class="l">مساحة الحفر</div><div class="v">${fmtN(m.pothole_area_pct, 2)}%</div></div>
          </div>
        </div>
      </div>
      <div class="card mt">
        <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("wrench")}</span>التوصيات</h2>
          <button class="btn" id="captureBtn">📷 التقاط وتحليل الآن</button></div>
        <ul class="recs">${(rd?.recommendations || []).map((r) => `<li><span class="p p-${esc(r.priority)}">${esc(r.priority)}</span><span>${esc(r.text)}</span></li>`).join("")}</ul>
      </div>
      <div class="d-grid mt">
        <div class="card">
          <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("cycle")}</span>دورة حياة المشكلات</h2><span class="muted">قبل ← أثناء ← بعد</span></div>
          ${d.issues.length ? d.issues.map(issueTimeline).join("") : `<div class="empty">لا مشكلات مسجّلة لهذا المقطع</div>`}
        </div>
        <div class="card">
          <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("target")}</span>العيوب المتتبَّعة</h2><span class="muted">مطابقة الموقع عبر اللقطات</span></div>
          ${d.tracks.length ? d.tracks.map((t) => `<div class="trk"><span>${esc(d.labels[t.type] || t.type)} <span class="muted">· منذ ${df.format(new Date(t.first_ts))} · ${fmtN(t.hits)} رصد</span></span>
            <span class="muted">${t.growth_pct_week == null ? "" : (t.growth_pct_week > 0 ? "▲ " : "▼ ") + fmtN(Math.abs(t.growth_pct_week), 1) + "%/أسبوع"}</span>
            <span class="pill ${t.status === "confirmed" ? "high" : "low"}">${{ confirmed: "قائم", gone: "زال", repaired: "رُقّع" }[t.status] || t.status}</span></div>`).join("")
            : `<div class="empty">لا عيوب مؤكَّدة</div>`}
        </div>
      </div>
      <div class="d-grid mt">
        <div class="card">
          <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("bell")}</span>تنبيهات هذه الكاميرا</h2></div>
          <ul class="alert-list">${d.alerts.map((a) => alertItem(a)).join("") || `<li class="empty">لا توجد تنبيهات</li>`}</ul>
        </div>
        <div class="card">
          <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("list")}</span>سجل الصيانة</h2></div>
          <ul class="alert-list compact">${d.maintenance.map((x) => `<li><span class="sev info"></span><div><div class="t">${esc(x.action)}</div></div><div class="when">${esc(x.date)}</div></li>`).join("") || `<li class="empty">لا يوجد</li>`}</ul>
          <form class="maint" id="maintForm">
            <input type="date" name="date" required value="${new Date().toISOString().slice(0, 10)}">
            <input name="action" required placeholder="نوع الأعمال (سد تشققات، ردم حفر، إعادة رصف…)" minlength="2">
            <button class="btn">تسجيل</button>
          </form>
          <p class="muted">تسجيل الصيانة يعيد ضبط عمر الطبقة في نموذج المخاطر، ويُستخدم لاحقًا لمعايرة الأوزان.</p>
        </div>
      </div>`;

    // عارض اللقطات
    const img = $("#vImg"), range = $("#vRange"), ts = $("#vTs"), ann = $("#vAnn");
    const show = () => {
      const s = snaps[+range.value]; if (!s) return;
      img.src = `/api/snapshots/${s.id}/image?annotated=${ann.checked ? 1 : 0}`;
      ts.textContent = `${fmtDT(s.ts)} · ${KIND_AR[s.kind] || s.kind} · الحالة ${fmtN(s.condition_index)}`;
    };
    range.addEventListener("input", show); ann.addEventListener("change", show); show();

    drawCIChart(d, rd);

    $("#captureBtn").addEventListener("click", async (e) => {
      const b = e.currentTarget; b.disabled = true;
      const lastId = d.snapshots[0]?.id;
      try {
        await api(`/api/cameras/${encodeURIComponent(d.id)}/capture`, { method: "POST" });
        b.textContent = "بدأ الالتقاط — تظهر النتيجة هنا خلال دقائق…";
        // متابعة حتى تصل لقطة جديدة (حتى 8 دقائق)
        for (let i = 0; i < 32 && state.current === d.id; i++) {
          await new Promise((r) => setTimeout(r, 15000));
          const nd = await api(`/api/cameras/${encodeURIComponent(d.id)}`);
          if (nd.snapshots[0]?.id !== lastId) { await refresh(); if (state.current === d.id) openCamera(d.id); return; }
        }
        b.disabled = false; b.textContent = "📷 التقاط وتحليل الآن";
      } catch (err) { b.disabled = false; b.textContent = "تعذّر الالتقاط: " + err.message; }
    });
    $("#maintForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.currentTarget);
      await api(`/api/cameras/${encodeURIComponent(d.id)}/maintenance`, { method: "POST", body: JSON.stringify({ date: fd.get("date"), action: fd.get("action") }) });
      openCamera(d.id);
    });
  }

  function drawCIChart(d, rd) {
    chartDefaults();
    if (state.charts.ci) state.charts.ci.destroy();
    const hist = d.history.map((h) => ({ x: new Date(h.ts).getTime(), y: h.condition_index, kind: h.kind }));
    const fc = rd?.forecast?.forecast || [];
    const last = hist[hist.length - 1];
    // يبدأ خط التنبؤ من المؤشر المُنعَّم لا من آخر قراءة منفردة
    const anchor = rd?.forecast?.ci ?? last?.y;
    const fcPts = last ? [{ x: last.x, y: anchor }, ...fc.map((p) => ({ x: new Date(p.ts).getTime(), y: p.condition_index }))] : [];
    const xs = [...hist, ...fcPts].map((p) => p.x);
    const thr = window.__thr ?? 55;
    state.charts.ci = new Chart($("#ciChart"), {
      type: "line",
      data: { datasets: [
        { label: "المرصود", data: hist, borderColor: css("--brand"), backgroundColor: css("--brand"), tension: .25, borderWidth: 2.5,
          pointRadius: (c) => (hist[c.dataIndex]?.kind === "sentinel" ? 2 : 3.5) },
        { label: "التنبؤ", data: fcPts, borderColor: color(rd?.level || "medium"), borderDash: [6, 5], pointRadius: 0, borderWidth: 2.5 },
        { label: "عتبة الصيانة", data: xs.length ? [{ x: Math.min(...xs), y: thr }, { x: Math.max(...xs), y: thr }] : [],
          borderColor: css("--critical"), borderWidth: 1.5, pointRadius: 0, borderDash: [2, 3] },
      ] },
      options: {
        maintainAspectRatio: false, parsing: false, interaction: { mode: "nearest", intersect: false },
        plugins: { legend: { position: "bottom", labels: { boxWidth: 14 } },
          tooltip: { callbacks: { title: (it) => fmtDT(it[0].parsed.x), label: (it) => `${it.dataset.label}: ${fmtN(it.parsed.y, 1)}` } } },
        scales: {
          x: { type: "linear", ticks: { callback: (v) => df.format(new Date(v)), maxTicksLimit: 8 }, grid: { display: false } },
          y: { min: 0, max: 100 },
        },
      },
    });
  }

  // ---------- الحالة والتحديث ----------
  async function loadStatus() {
    const pill = $("#statusPill");
    try {
      const s = await api("/api/status");
      window.__thr = s.maintenance_threshold;
      $("#asOf").textContent = s.static_snapshot ? `بيانات حتى ${s.static_snapshot}` : `آخر تحديث ${dtf.format(new Date())}`;
      if (!state.regions.length) {
        state.regions = s.regions;
        if (state.region && !s.regions.some((r) => r.key === state.region)) state.region = "";
        renderRegions();
      }
      const weekly = s.jobs.filter((j) => j.id.startsWith("weekly")).sort((a, b) => (a.next_run || "").localeCompare(b.next_run || ""))[0];
      pill.className = "status " + (s.seeding ? "busy" : "ok");
      $("span", pill).textContent = s.seeding ? "يُبنى السجل التاريخي…" :
        weekly?.next_run ? `الالتقاط الأسبوعي التالي: ${df.format(new Date(weekly.next_run))}` : "النظام يعمل";
      $("#sysInfo").innerHTML = [
        `محرك الكشف: ${s.ai_models.length ? "ذكاء اصطناعي — " + s.ai_models.map(esc).join(" + ") : "رؤية حاسوبية كلاسيكية"}`,
        `الجدول الأسبوعي: ${esc(s.schedule.weekly)}`,
        `الفحص السريع: يوميًا ظهرًا (نهارًا فقط)`,
        `بيانات الطقس: ${s.weather ? "Open-Meteo" : "متوسطات مناخية"}`,
        `عتبة الصيانة: ${fmtN(s.maintenance_threshold)}`,
      ].map((t) => `<span class="chip">${t}</span>`).join("");
      return s;
    } catch {
      pill.className = "status err"; $("span", pill).textContent = "تعذّر الاتصال بالخادم";
    }
  }
  async function loadAlerts() {
    const ids = new Set(state.cameras.map((c) => c.id));
    state.alerts = (await api("/api/alerts?limit=300")).filter((a) => !state.region || ids.has(a.camera_id));
    renderAlerts();
  }
  async function refresh() {
    const [summary, cams, issues] = await Promise.all([api(rq("/api/summary")), api(rq("/api/cameras")), api(rq("/api/issues"))]);
    state.summary = summary; state.cameras = cams; state.issues = issues;
    renderSummary(summary); renderCameras(); renderMarkers(); renderLifecycle(summary.lifecycle, issues);
    await loadAlerts();
    return summary;
  }

  $("#themeBtn").addEventListener("click", () => {
    const t = document.documentElement.dataset.ui === "dark" ? "light" : "dark";
    applyTheme(t); safeSet("darb-ui", t);
    // المخططات تقرأ ألوانها من الرموز: تُعاد رسمها
    if (state.charts.net) { state.charts.net.destroy(); state.charts.net = null; }
    if (state.summary) renderSummary(state.summary);
    if (state.current) openCamera(state.current);
  });

  // ---------- المناطق ----------
  function renderRegions() {
    const bar = $("#regionBar");
    const all = [{ key: "", name: "كل المناطق" }, ...state.regions];
    bar.innerHTML = all.map((r) => `<button data-region="${esc(r.key)}" class="${r.key === state.region ? "active" : ""}">${esc(r.name)}</button>`).join("");
    bar.hidden = state.regions.length < 2;
    const active = state.regions.filter((r) => !state.region || r.key === state.region);
    $("#regionName").textContent = active.map((r) => r.name).join(" · ");
    const foot = $("#attribution");
    const attr = active.map((r) => r.attribution).filter(Boolean);
    foot.hidden = !attr.length; foot.textContent = attr.join(" — ");
  }
  $("#regionBar").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-region]"); if (!b) return;
    state.region = b.dataset.region; safeSet("darb-region", state.region);
    state.fitPending = true; renderRegions(); refresh().catch(() => {});
  });

  // ---------- دورة حياة المشكلات ----------
  function issueCard(i) {
    const last = i.events[i.events.length - 1] || {};
    const dates = [
      i.predicted_ts && `تُوقّعت ${df.format(new Date(i.predicted_ts))}`,
      i.expected_ts && i.stage === "predicted" && `متوقعة ~${df.format(new Date(i.expected_ts))}`,
      i.detected_ts && `رُصدت ${df.format(new Date(i.detected_ts))}`,
      i.resolved_ts && `${esc(i.resolution_ar || "عولجت")} ${df.format(new Date(i.resolved_ts))}`,
    ].filter(Boolean);
    const sev = i.stage === "predicted" ? "medium" : i.stage === "active" ? (i.severity === "critical" ? "critical" : "high") : "low";
    return `<article class="issue" data-cam="${esc(i.camera_id)}">
      <div class="top"><div><b>${esc(ISSUE_KIND_AR[i.kind] || i.kind)}</b><span class="cam">${esc(i.camera_name || "")}</span></div>
        <span class="pill ${sev}">${esc(i.stage_ar)}</span></div>
      <div class="dates">${dates.map((x) => `<span>${x}</span>`).join("")}</div>
      ${last.note ? `<div class="last">${esc(last.note)}</div>` : ""}</article>`;
  }
  function issueTimeline(i) {
    return `<div class="mt"><b>${esc(ISSUE_KIND_AR[i.kind] || i.kind)}</b> <span class="pill ${i.stage === "active" ? "critical" : i.stage === "predicted" ? "medium" : "low"}">${esc(i.stage_ar)}</span>
      <ul class="timeline mt">${i.events.map((e) => `<li class="${esc(e.stage)}"><div class="when">${fmtDT(e.ts)}</div>${esc(e.note || "")}</li>`).join("")}</ul></div>`;
  }
  function renderLifecycle(k, issues) {
    $("#lifeKpis").innerHTML = [
      kpi("سبق التنبؤ للحدث", k.avg_lead_weeks == null ? "—" : `${fmtN(k.avg_lead_weeks, 1)} أسبوع`, "متوسط المدة بين التوقع ووقوع المشكلة", false, "clock", "warn"),
      kpi("دقة التنبؤ", k.prediction_precision == null ? "—" : `${fmtN(k.prediction_precision * 100)}%`, `${fmtN(k.predicted_total)} توقعًا · ${fmtN(k.prevented)} عولج وقائيًا`, false, "target"),
      kpi("زمن المعالجة", k.avg_days_to_resolve == null ? "—" : `${fmtN(k.avg_days_to_resolve)} يوم`, "من الرصد حتى زوال المشكلة", false, "wrench", "ok"),
      kpi("العودة بعد الإصلاح", k.recurrence_rate == null ? "—" : `${fmtN(k.recurrence_rate * 100)}%`, "خلال فترة المراقبة", false, "shield"),
    ].join("");
    const col = (stages) => issues.filter((i) => stages.includes(i.stage)).map(issueCard).join("") || `<div class="empty">لا شيء</div>`;
    $("#colBefore").innerHTML = col(["predicted"]);
    $("#colDuring").innerHTML = col(["active"]);
    $("#colAfter").innerHTML = col(["monitoring", "closed"]);
    const b = $("#issueBadge"); b.hidden = !k.stages.active; b.textContent = fmtN(k.stages.active);
  }

  async function boot() {
    const s = await loadStatus();
    const tab = safeGet("darb-tab");
    if (tab && $(`#tab-${tab}`)) showTab(tab);
    await refresh().catch(() => {});
    let seeding = s?.seeding;
    setInterval(async () => {
      const st = await loadStatus();
      if (seeding || st?.seeding) await refresh().catch(() => {});
      seeding = st?.seeding;
    }, 8000);
    setInterval(() => refresh().catch(() => {}), 120000);
  }
  boot();
})();
