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
  const SRC_AR = { demo: "محاكاة", datagovsg: "كاميرا حقيقية · سنغافورة LTA", az511: "كاميرا حقيقية · أريزونا ADOT", fl511: "كاميرا حقيقية · فلوريدا FDOT" };
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


  // أيقونات Phosphor (ثنائية اللون، MIT) — تُحقن في كل عنصر يحمل data-icon؛ الطبقة الخلفية .d شفافة جزئيًا
  const ICONS = {
    grid: "<path d=\"M112,56v48a8,8,0,0,1-8,8H56a8,8,0,0,1-8-8V56a8,8,0,0,1,8-8h48A8,8,0,0,1,112,56Zm88-8H152a8,8,0,0,0-8,8v48a8,8,0,0,0,8,8h48a8,8,0,0,0,8-8V56A8,8,0,0,0,200,48Zm-96,96H56a8,8,0,0,0-8,8v48a8,8,0,0,0,8,8h48a8,8,0,0,0,8-8V152A8,8,0,0,0,104,144Zm96,0H152a8,8,0,0,0-8,8v48a8,8,0,0,0,8,8h48a8,8,0,0,0,8-8V152A8,8,0,0,0,200,144Z\" class=\"d\"/><path d=\"M200,136H152a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V152A16,16,0,0,0,200,136Zm0,64H152V152h48v48ZM104,40H56A16,16,0,0,0,40,56v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V56A16,16,0,0,0,104,40Zm0,64H56V56h48v48Zm96-64H152a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V56A16,16,0,0,0,200,40Zm0,64H152V56h48v48Zm-96,32H56a16,16,0,0,0-16,16v48a16,16,0,0,0,16,16h48a16,16,0,0,0,16-16V152A16,16,0,0,0,104,136Zm0,64H56V152h48v48Z\"/>",
    map: "<path d=\"M160,72V216L96,184V40Z\" class=\"d\"/><path d=\"M228.92,49.69a8,8,0,0,0-6.86-1.45L160.93,63.52,99.58,32.84a8,8,0,0,0-5.52-.6l-64,16A8,8,0,0,0,24,56V200a8,8,0,0,0,9.94,7.76l61.13-15.28,61.35,30.68A8.15,8.15,0,0,0,160,224a8,8,0,0,0,1.94-.24l64-16A8,8,0,0,0,232,200V56A8,8,0,0,0,228.92,49.69ZM104,52.94l48,24V203.06l-48-24ZM40,62.25l48-12v127.5l-48,12Zm176,131.5-48,12V78.25l48-12Z\"/>",
    cycle: "<path d=\"M216,128a88,88,0,1,1-88-88A88,88,0,0,1,216,128Z\" class=\"d\"/><path d=\"M224,48V96a8,8,0,0,1-8,8H168a8,8,0,0,1,0-16h28.69L182.06,73.37a79.56,79.56,0,0,0-56.13-23.43h-.45A79.52,79.52,0,0,0,69.59,72.71,8,8,0,0,1,58.41,61.27a96,96,0,0,1,135,.79L208,76.69V48a8,8,0,0,1,16,0ZM186.41,183.29a80,80,0,0,1-112.47-.66L59.31,168H88a8,8,0,0,0,0-16H40a8,8,0,0,0-8,8v48a8,8,0,0,0,16,0V179.31l14.63,14.63A95.43,95.43,0,0,0,130,222.06h.53a95.36,95.36,0,0,0,67.07-27.33,8,8,0,0,0-11.18-11.44Z\"/>",
    camera: "<path d=\"M200,72V184a8,8,0,0,1-8,8H32a8,8,0,0,1-8-8V72a8,8,0,0,1,8-8H192A8,8,0,0,1,200,72Z\" class=\"d\"/><path d=\"M251.77,73a8,8,0,0,0-8.21.39L208,97.05V72a16,16,0,0,0-16-16H32A16,16,0,0,0,16,72V184a16,16,0,0,0,16,16H192a16,16,0,0,0,16-16V159l35.56,23.71A8,8,0,0,0,248,184a8,8,0,0,0,8-8V80A8,8,0,0,0,251.77,73ZM192,184H32V72H192V184Zm48-22.95-32-21.33V116.28L240,95Z\"/>",
    camoff: "<path d=\"M208,64H176L160,40H96L80,64H48A16,16,0,0,0,32,80V192a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V80A16,16,0,0,0,208,64ZM128,168a36,36,0,1,1,36-36A36,36,0,0,1,128,168Z\" class=\"d\"/><path d=\"M53.92,34.62A8,8,0,1,0,42.08,45.38L51.73,56H48A24,24,0,0,0,24,80V192a24,24,0,0,0,24,24H197.19l4.89,5.38a8,8,0,1,0,11.84-10.76Zm51.66,80.61,37,40.69A27.71,27.71,0,0,1,128,160a28,28,0,0,1-22.42-44.77ZM48,200a8,8,0,0,1-8-8V80a8,8,0,0,1,8-8H66.28l28.41,31.26A44,44,0,0,0,128,176a44.21,44.21,0,0,0,25.44-8.12L182.64,200ZM232,80V186a8,8,0,0,1-16,0V80a8,8,0,0,0-8-8H176a8,8,0,0,1-6.65-3.56L155.71,48H100.24a8,8,0,0,1-12.91-9.42l2-3A8,8,0,0,1,96,32h64a8,8,0,0,1,6.66,3.56L180.28,56H208A24,24,0,0,1,232,80Z\"/>",
    bell: "<path d=\"M208,192H48a8,8,0,0,1-6.88-12C47.71,168.6,56,147.81,56,112a72,72,0,0,1,144,0c0,35.82,8.3,56.6,14.9,68A8,8,0,0,1,208,192Z\" class=\"d\"/><path d=\"M224,71.1a8,8,0,0,1-10.78-3.42,94.13,94.13,0,0,0-33.46-36.91,8,8,0,1,1,8.54-13.54,111.46,111.46,0,0,1,39.12,43.09A8,8,0,0,1,224,71.1ZM35.71,72a8,8,0,0,0,7.1-4.32A94.13,94.13,0,0,1,76.27,30.77a8,8,0,1,0-8.54-13.54A111.46,111.46,0,0,0,28.61,60.32,8,8,0,0,0,35.71,72Zm186.1,103.94A16,16,0,0,1,208,200H167.2a40,40,0,0,1-78.4,0H48a16,16,0,0,1-13.79-24.06C43.22,160.39,48,138.28,48,112a80,80,0,0,1,160,0C208,138.27,212.78,160.38,221.81,175.94ZM150.62,200H105.38a24,24,0,0,0,45.24,0ZM208,184c-10.64-18.27-16-42.49-16-72a64,64,0,0,0-128,0c0,29.52-5.38,53.74-16,72Z\"/>",
    book: "<path d=\"M232,56V200H160a32,32,0,0,0-32,32V88a32,32,0,0,1,32-32Z\" class=\"d\"/><path d=\"M232,48H160a40,40,0,0,0-32,16A40,40,0,0,0,96,48H24a8,8,0,0,0-8,8V200a8,8,0,0,0,8,8H96a24,24,0,0,1,24,24,8,8,0,0,0,16,0,24,24,0,0,1,24-24h72a8,8,0,0,0,8-8V56A8,8,0,0,0,232,48ZM96,192H32V64H96a24,24,0,0,1,24,24V200A39.81,39.81,0,0,0,96,192Zm128,0H160a39.81,39.81,0,0,0-24,8V88a24,24,0,0,1,24-24h64ZM160,88h40a8,8,0,0,1,0,16H160a8,8,0,0,1,0-16Zm48,40a8,8,0,0,1-8,8H160a8,8,0,0,1,0-16h40A8,8,0,0,1,208,128Zm0,32a8,8,0,0,1-8,8H160a8,8,0,0,1,0-16h40A8,8,0,0,1,208,160Z\"/>",
    gauge: "<path d=\"M232,152v24a8,8,0,0,1-8,8H32a8,8,0,0,1-8-8V153.13C24,95.65,70.15,48.2,127.63,48A104,104,0,0,1,232,152Z\" class=\"d\"/><path d=\"M207.06,72.67A111.24,111.24,0,0,0,128,40h-.4C66.07,40.21,16,91,16,153.13V176a16,16,0,0,0,16,16H224a16,16,0,0,0,16-16V152A111.25,111.25,0,0,0,207.06,72.67ZM224,176H119.71l54.76-75.3a8,8,0,0,0-12.94-9.42L99.92,176H32V153.13c0-3.08.15-6.12.43-9.13H56a8,8,0,0,0,0-16H35.27c10.32-38.86,44-68.24,84.73-71.66V80a8,8,0,0,0,16,0V56.33A96.14,96.14,0,0,1,221,128H200a8,8,0,0,0,0,16h23.67c.21,2.65.33,5.31.33,8Z\"/>",
    alert: "<path d=\"M215.46,216H40.54C27.92,216,20,202.79,26.13,192.09L113.59,40.22c6.3-11,22.52-11,28.82,0l87.46,151.87C236,202.79,228.08,216,215.46,216Z\" class=\"d\"/><path d=\"M236.8,188.09,149.35,36.22h0a24.76,24.76,0,0,0-42.7,0L19.2,188.09a23.51,23.51,0,0,0,0,23.72A24.35,24.35,0,0,0,40.55,224h174.9a24.35,24.35,0,0,0,21.33-12.19A23.51,23.51,0,0,0,236.8,188.09ZM222.93,203.8a8.5,8.5,0,0,1-7.48,4.2H40.55a8.5,8.5,0,0,1-7.48-4.2,7.59,7.59,0,0,1,0-7.72L120.52,44.21a8.75,8.75,0,0,1,15,0l87.45,151.87A7.59,7.59,0,0,1,222.93,203.8ZM120,144V104a8,8,0,0,1,16,0v40a8,8,0,0,1-16,0Zm20,36a12,12,0,1,1-12-12A12,12,0,0,1,140,180Z\"/>",
    wrench: "<path d=\"M224,96a64,64,0,0,1-94.94,56L73,217A24,24,0,0,1,39,183L104,126.94a64,64,0,0,1,80-90.29L144,80l5.66,26.34L176,112l43.35-40A63.8,63.8,0,0,1,224,96Z\" class=\"d\"/><path d=\"M226.76,69a8,8,0,0,0-12.84-2.88l-40.3,37.19-17.23-3.7-3.7-17.23,37.19-40.3A8,8,0,0,0,187,29.24,72,72,0,0,0,88,96,72.34,72.34,0,0,0,94,124.94L33.79,177c-.15.12-.29.26-.43.39a32,32,0,0,0,45.26,45.26c.13-.13.27-.28.39-.42L131.06,162A72,72,0,0,0,232,96,71.56,71.56,0,0,0,226.76,69ZM160,152a56.14,56.14,0,0,1-27.07-7,8,8,0,0,0-9.92,1.77L67.11,211.51a16,16,0,0,1-22.62-22.62L109.18,133a8,8,0,0,0,1.77-9.93,56,56,0,0,1,58.36-82.31l-31.2,33.81a8,8,0,0,0-1.94,7.1L141.83,108a8,8,0,0,0,6.14,6.14l26.35,5.66a8,8,0,0,0,7.1-1.94l33.81-31.2A56.06,56.06,0,0,1,160,152Z\"/>",
    clock: "<path d=\"M224,128a96,96,0,1,1-96-96A96,96,0,0,1,224,128Z\" class=\"d\"/><path d=\"M232,136.66A104.12,104.12,0,1,1,119.34,24,8,8,0,0,1,120.66,40,88.12,88.12,0,1,0,216,135.34,8,8,0,0,1,232,136.66ZM120,72v56a8,8,0,0,0,8,8h56a8,8,0,0,0,0-16H136V72a8,8,0,0,0-16,0Zm40-24a12,12,0,1,0-12-12A12,12,0,0,0,160,48Zm36,24a12,12,0,1,0-12-12A12,12,0,0,0,196,72Zm24,36a12,12,0,1,0-12-12A12,12,0,0,0,220,108Z\"/>",
    check: "<path d=\"M224,128a96,96,0,1,1-96-96A96,96,0,0,1,224,128Z\" class=\"d\"/><path d=\"M173.66,98.34a8,8,0,0,1,0,11.32l-56,56a8,8,0,0,1-11.32,0l-24-24a8,8,0,0,1,11.32-11.32L112,148.69l50.34-50.35A8,8,0,0,1,173.66,98.34ZM232,128A104,104,0,1,1,128,24,104.11,104.11,0,0,1,232,128Zm-16,0a88,88,0,1,0-88,88A88.1,88.1,0,0,0,216,128Z\"/>",
    activity: "<path d=\"M96,40l33.52,88H56Zm104,88H129.52L160,208Z\" class=\"d\"/><path d=\"M240,128a8,8,0,0,1-8,8H204.94l-37.78,75.58A8,8,0,0,1,160,216h-.4a8,8,0,0,1-7.08-5.14L95.35,60.76,63.28,131.31A8,8,0,0,1,56,136H24a8,8,0,0,1,0-16H50.85L88.72,36.69a8,8,0,0,1,14.76.46l57.51,151,31.85-63.71A8,8,0,0,1,200,120h32A8,8,0,0,1,240,128Z\"/>",
    trend: "<path d=\"M224,64V208H32V48H208A16,16,0,0,1,224,64Z\" class=\"d\"/><path d=\"M232,208a8,8,0,0,1-8,8H32a8,8,0,0,1-8-8V48a8,8,0,0,1,16,0V156.69l50.34-50.35a8,8,0,0,1,11.32,0L128,132.69,180.69,80H160a8,8,0,0,1,0-16h40a8,8,0,0,1,8,8v40a8,8,0,0,1-16,0V91.31l-58.34,58.35a8,8,0,0,1-11.32,0L96,123.31l-56,56V200H224A8,8,0,0,1,232,208Z\"/>",
    bars: "<path d=\"M208,40V208H152V40Z\" class=\"d\"/><path d=\"M224,200h-8V40a8,8,0,0,0-8-8H152a8,8,0,0,0-8,8V80H96a8,8,0,0,0-8,8v40H48a8,8,0,0,0-8,8v64H32a8,8,0,0,0,0,16H224a8,8,0,0,0,0-16ZM160,48h40V200H160ZM104,96h40V200H104ZM56,144H88v56H56Z\"/>",
    list: "<path d=\"M216,64V192H104V64Z\" class=\"d\"/><path d=\"M224,128a8,8,0,0,1-8,8H104a8,8,0,0,1,0-16H216A8,8,0,0,1,224,128ZM104,72H216a8,8,0,0,0,0-16H104a8,8,0,0,0,0,16ZM216,184H104a8,8,0,0,0,0,16H216a8,8,0,0,0,0-16ZM43.58,55.16,48,52.94V104a8,8,0,0,0,16,0V40a8,8,0,0,0-11.58-7.16l-16,8a8,8,0,0,0,7.16,14.32ZM79.77,156.72a23.73,23.73,0,0,0-9.6-15.95,24.86,24.86,0,0,0-34.11,4.7,23.63,23.63,0,0,0-3.57,6.46,8,8,0,1,0,15,5.47,7.84,7.84,0,0,1,1.18-2.13,8.76,8.76,0,0,1,12-1.59A7.91,7.91,0,0,1,63.93,159a7.64,7.64,0,0,1-1.57,5.78,1,1,0,0,0-.08.11L33.59,203.21A8,8,0,0,0,40,216H72a8,8,0,0,0,0-16H56l19.08-25.53A23.47,23.47,0,0,0,79.77,156.72Z\"/>",
    search: "<path d=\"M192,112a80,80,0,1,1-80-80A80,80,0,0,1,192,112Z\" class=\"d\"/><path d=\"M229.66,218.34,179.6,168.28a88.21,88.21,0,1,0-11.32,11.31l50.06,50.07a8,8,0,0,0,11.32-11.32ZM40,112a72,72,0,1,1,72,72A72.08,72.08,0,0,1,40,112Z\"/>",
    moon: "<path d=\"M227.89,147.89A96,96,0,1,1,108.11,28.11,96.09,96.09,0,0,0,227.89,147.89Z\" class=\"d\"/><path d=\"M233.54,142.23a8,8,0,0,0-8-2,88.08,88.08,0,0,1-109.8-109.8,8,8,0,0,0-10-10,104.84,104.84,0,0,0-52.91,37A104,104,0,0,0,136,224a103.09,103.09,0,0,0,62.52-20.88,104.84,104.84,0,0,0,37-52.91A8,8,0,0,0,233.54,142.23ZM188.9,190.34A88,88,0,0,1,65.66,67.11a89,89,0,0,1,31.4-26A106,106,0,0,0,96,56,104.11,104.11,0,0,0,200,160a106,106,0,0,0,14.92-1.06A89,89,0,0,1,188.9,190.34Z\"/>",
    sun: "<path d=\"M184,128a56,56,0,1,1-56-56A56,56,0,0,1,184,128Z\" class=\"d\"/><path d=\"M120,40V16a8,8,0,0,1,16,0V40a8,8,0,0,1-16,0Zm72,88a64,64,0,1,1-64-64A64.07,64.07,0,0,1,192,128Zm-16,0a48,48,0,1,0-48,48A48.05,48.05,0,0,0,176,128ZM58.34,69.66A8,8,0,0,0,69.66,58.34l-16-16A8,8,0,0,0,42.34,53.66Zm0,116.68-16,16a8,8,0,0,0,11.32,11.32l16-16a8,8,0,0,0-11.32-11.32ZM192,72a8,8,0,0,0,5.66-2.34l16-16a8,8,0,0,0-11.32-11.32l-16,16A8,8,0,0,0,192,72Zm5.66,114.34a8,8,0,0,0-11.32,11.32l16,16a8,8,0,0,0,11.32-11.32ZM48,128a8,8,0,0,0-8-8H16a8,8,0,0,0,0,16H40A8,8,0,0,0,48,128Zm80,80a8,8,0,0,0-8,8v24a8,8,0,0,0,16,0V216A8,8,0,0,0,128,208Zm112-88H216a8,8,0,0,0,0,16h24a8,8,0,0,0,0-16Z\"/>",
    road: "<path d=\"M232,192H24L96,64h64Z\" class=\"d\"/><path d=\"M235.92,199A8,8,0,0,1,225,195.92L155.32,72H136v8a8,8,0,0,1-16,0V72H100.68L31,195.92A8,8,0,0,1,17,188.08L82.32,72H24a8,8,0,0,1,0-16H232a8,8,0,0,1,0,16H173.68L239,188.08A8,8,0,0,1,235.92,199ZM128,112a8,8,0,0,0-8,8v16a8,8,0,0,0,16,0V120A8,8,0,0,0,128,112Zm0,56a8,8,0,0,0-8,8v16a8,8,0,0,0,16,0V176A8,8,0,0,0,128,168Z\"/>",
    shield: "<path d=\"M216,56v56c0,96-88,120-88,120S40,208,40,112V56a8,8,0,0,1,8-8H208A8,8,0,0,1,216,56Z\" class=\"d\"/><path d=\"M208,40H48A16,16,0,0,0,32,56v56c0,52.72,25.52,84.67,46.93,102.19,23.06,18.86,46,25.26,47,25.53a8,8,0,0,0,4.2,0c1-.27,23.91-6.67,47-25.53C198.48,196.67,224,164.72,224,112V56A16,16,0,0,0,208,40Zm0,72c0,37.07-13.66,67.16-40.6,89.42A129.3,129.3,0,0,1,128,223.62a128.25,128.25,0,0,1-38.92-21.81C61.82,179.51,48,149.3,48,112l0-56,160,0ZM82.34,141.66a8,8,0,0,1,11.32-11.32L112,148.69l50.34-50.35a8,8,0,0,1,11.32,11.32l-56,56a8,8,0,0,1-11.32,0Z\"/>",
    target: "<path d=\"M160,128a32,32,0,1,1-32-32A32,32,0,0,1,160,128Z\" class=\"d\"/><path d=\"M232,120h-8.34A96.14,96.14,0,0,0,136,32.34V24a8,8,0,0,0-16,0v8.34A96.14,96.14,0,0,0,32.34,120H24a8,8,0,0,0,0,16h8.34A96.14,96.14,0,0,0,120,223.66V232a8,8,0,0,0,16,0v-8.34A96.14,96.14,0,0,0,223.66,136H232a8,8,0,0,0,0-16Zm-96,87.6V200a8,8,0,0,0-16,0v7.6A80.15,80.15,0,0,1,48.4,136H56a8,8,0,0,0,0-16H48.4A80.15,80.15,0,0,1,120,48.4V56a8,8,0,0,0,16,0V48.4A80.15,80.15,0,0,1,207.6,120H200a8,8,0,0,0,0,16h7.6A80.15,80.15,0,0,1,136,207.6ZM128,88a40,40,0,1,0,40,40A40,40,0,0,0,128,88Zm0,64a24,24,0,1,1,24-24A24,24,0,0,1,128,152Z\"/>",
    image: "<path d=\"M224,56V178.06l-39.72-39.72a8,8,0,0,0-11.31,0L147.31,164,97.66,114.34a8,8,0,0,0-11.32,0L32,168.69V56a8,8,0,0,1,8-8H216A8,8,0,0,1,224,56Z\" class=\"d\"/><path d=\"M216,40H40A16,16,0,0,0,24,56V200a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A16,16,0,0,0,216,40Zm0,16V158.75l-26.07-26.06a16,16,0,0,0-22.63,0l-20,20-44-44a16,16,0,0,0-22.62,0L40,149.37V56ZM40,172l52-52,80,80H40Zm176,28H194.63l-36-36,20-20L216,181.38V200ZM144,100a12,12,0,1,1,12,12A12,12,0,0,1,144,100Z\"/>",
    brain: "<path d=\"M240,124a48,48,0,0,1-32,45.27h0V176a40,40,0,0,1-80,0,40,40,0,0,1-80,0v-6.73h0a48,48,0,0,1,0-90.54V72a40,40,0,0,1,80,0,40,40,0,0,1,80,0v6.73A48,48,0,0,1,240,124Z\" class=\"d\"/><path d=\"M248,124a56.11,56.11,0,0,0-32-50.61V72a48,48,0,0,0-88-26.49A48,48,0,0,0,40,72v1.39a56,56,0,0,0,0,101.2V176a48,48,0,0,0,88,26.49A48,48,0,0,0,216,176v-1.41A56.09,56.09,0,0,0,248,124ZM88,208a32,32,0,0,1-31.81-28.56A55.87,55.87,0,0,0,64,180h8a8,8,0,0,0,0-16H64A40,40,0,0,1,50.67,86.27,8,8,0,0,0,56,78.73V72a32,32,0,0,1,64,0v68.26A47.8,47.8,0,0,0,88,128a8,8,0,0,0,0,16,32,32,0,0,1,0,64Zm104-44h-8a8,8,0,0,0,0,16h8a55.87,55.87,0,0,0,7.81-.56A32,32,0,1,1,168,144a8,8,0,0,0,0-16,47.8,47.8,0,0,0-32,12.26V72a32,32,0,0,1,64,0v6.73a8,8,0,0,0,5.33,7.54A40,40,0,0,1,192,164Zm16-52a8,8,0,0,1-8,8h-4a36,36,0,0,1-36-36V80a8,8,0,0,1,16,0v4a20,20,0,0,0,20,20h4A8,8,0,0,1,208,112ZM60,120H56a8,8,0,0,1,0-16h4A20,20,0,0,0,80,84V80a8,8,0,0,1,16,0v4A36,36,0,0,1,60,120Z\"/>",
    download: "<path d=\"M216,48V208H40V48A16,16,0,0,1,56,32H200A16,16,0,0,1,216,48Z\" class=\"d\"/><path d=\"M224,144v64a8,8,0,0,1-8,8H40a8,8,0,0,1-8-8V144a8,8,0,0,1,16,0v56H208V144a8,8,0,0,1,16,0Zm-101.66,5.66a8,8,0,0,0,11.32,0l40-40a8,8,0,0,0-11.32-11.32L136,124.69V32a8,8,0,0,0-16,0v92.69L93.66,98.34a8,8,0,0,0-11.32,11.32Z\"/>",
    close: "<path d=\"M216,56V200a16,16,0,0,1-16,16H56a16,16,0,0,1-16-16V56A16,16,0,0,1,56,40H200A16,16,0,0,1,216,56Z\" class=\"d\"/><path d=\"M205.66,194.34a8,8,0,0,1-11.32,11.32L128,139.31,61.66,205.66a8,8,0,0,1-11.32-11.32L116.69,128,50.34,61.66A8,8,0,0,1,61.66,50.34L128,116.69l66.34-66.35a8,8,0,0,1,11.32,11.32L139.31,128Z\"/>",
    live: "<path d=\"M160,128a32,32,0,1,1-32-32A32,32,0,0,1,160,128Z\" class=\"d\"/><path d=\"M128,88a40,40,0,1,0,40,40A40,40,0,0,0,128,88Zm0,64a24,24,0,1,1,24-24A24,24,0,0,1,128,152Zm73.71,7.14a80,80,0,0,1-14.08,22.2,8,8,0,0,1-11.92-10.67,63.95,63.95,0,0,0,0-85.33,8,8,0,1,1,11.92-10.67,80.08,80.08,0,0,1,14.08,84.47ZM69,103.09a64,64,0,0,0,11.26,67.58,8,8,0,0,1-11.92,10.67,79.93,79.93,0,0,1,0-106.67A8,8,0,1,1,80.29,85.34,63.77,63.77,0,0,0,69,103.09ZM248,128a119.58,119.58,0,0,1-34.29,84,8,8,0,1,1-11.42-11.2,103.9,103.9,0,0,0,0-145.56A8,8,0,1,1,213.71,44,119.58,119.58,0,0,1,248,128ZM53.71,200.78A8,8,0,1,1,42.29,212a119.87,119.87,0,0,1,0-168,8,8,0,1,1,11.42,11.2,103.9,103.9,0,0,0,0,145.56Z\"/>",
    pause: "<path d=\"M208,48V208a8,8,0,0,1-8,8H160a8,8,0,0,1-8-8V48a8,8,0,0,1,8-8h40A8,8,0,0,1,208,48ZM96,40H56a8,8,0,0,0-8,8V208a8,8,0,0,0,8,8H96a8,8,0,0,0,8-8V48A8,8,0,0,0,96,40Z\" class=\"d\"/><path d=\"M200,32H160a16,16,0,0,0-16,16V208a16,16,0,0,0,16,16h40a16,16,0,0,0,16-16V48A16,16,0,0,0,200,32Zm0,176H160V48h40ZM96,32H56A16,16,0,0,0,40,48V208a16,16,0,0,0,16,16H96a16,16,0,0,0,16-16V48A16,16,0,0,0,96,32Zm0,176H56V48H96Z\"/>",
    play: "<path d=\"M228.23,134.69,84.15,222.81A8,8,0,0,1,72,216.12V39.88a8,8,0,0,1,12.15-6.69l144.08,88.12A7.82,7.82,0,0,1,228.23,134.69Z\" class=\"d\"/><path d=\"M232.4,114.49,88.32,26.35a16,16,0,0,0-16.2-.3A15.86,15.86,0,0,0,64,39.87V216.13A15.94,15.94,0,0,0,80,232a16.07,16.07,0,0,0,8.36-2.35L232.4,141.51a15.81,15.81,0,0,0,0-27ZM80,215.94V40l143.83,88Z\"/>",
    expand: "<path d=\"M208,48V208H48V48Z\" class=\"d\"/><path d=\"M216,48V96a8,8,0,0,1-16,0V67.31l-42.34,42.35a8,8,0,0,1-11.32-11.32L188.69,56H160a8,8,0,0,1,0-16h48A8,8,0,0,1,216,48ZM98.34,146.34,56,188.69V160a8,8,0,0,0-16,0v48a8,8,0,0,0,8,8H96a8,8,0,0,0,0-16H67.31l42.35-42.34a8,8,0,0,0-11.32-11.32ZM208,152a8,8,0,0,0-8,8v28.69l-42.34-42.35a8,8,0,0,0-11.32,11.32L188.69,200H160a8,8,0,0,0,0,16h48a8,8,0,0,0,8-8V160A8,8,0,0,0,208,152ZM67.31,56H96a8,8,0,0,0,0-16H48a8,8,0,0,0-8,8V96a8,8,0,0,0,16,0V67.31l42.34,42.35a8,8,0,0,0,11.32-11.32Z\"/>",
  };
  const svg = (name) => `<svg viewBox="0 0 256 256" fill="currentColor" aria-hidden="true">${ICONS[name] || ""}</svg>`;
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
    if (name === "live") renderLive();
    liveTick();
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

  // ---------- البث المباشر ----------
  // المصادر المفتوحة تنشر إطارًا ثابتًا يتجدّد (لا فيديو متصل): المتصفح يجلبه من الجهة المالكة مباشرة ويبدّله عند تغيّره
  const live = { sg: null, sgAt: 0, paused: false, timer: null, cams: {} };
  async function sgIndex() {
    if (live.sg && Date.now() - live.sgAt < 45000) return live.sg;
    try {
      const j = await (await fetch("https://api.data.gov.sg/v1/transport/traffic-images")).json();
      live.sg = Object.fromEntries((j.items?.[0]?.cameras || []).map((c) => [c.camera_id, c])); live.sgAt = Date.now();
    } catch { live.sg = live.sg || {}; }
    return live.sg;
  }
  async function liveFrame(c) {
    const L = c.live;
    if (L.kind === "datagovsg") { const x = (await sgIndex())[L.camera_id]; return x ? { src: x.image, ts: x.timestamp } : null; }
    if (L.kind === "mjpeg") return { src: L.url };
    return { src: L.url + (L.url.includes("?") ? "&" : "?") + "t=" + Math.floor(Date.now() / 15000) };
  }
  const regionTz = (c) => state.regions.find((r) => r.key === c.region)?.tz;
  function liveFrameHTML(c) {
    live.cams[c.id] = c;
    return `<div class="frame" data-live="${esc(c.id)}"><img alt="بث مباشر — ${esc(c.name)}"><span class="loading">جارٍ الاتصال بالكاميرا…</span>
      <span class="clock"></span><button class="fs" type="button" data-fs aria-label="ملء الشاشة" title="ملء الشاشة">${svg("expand")}</button></div>`;
  }
  async function updateFrame(el) {
    const c = live.cams[el.dataset.live]; if (!c) return;
    const f = await liveFrame(c).catch(() => null);
    const img = el.querySelector("img"), msg = el.querySelector(".loading"), clock = el.querySelector(".clock");
    if (!f) { msg.textContent = "البث غير متاح الآن"; el.classList.add("off"); return; }
    const tz = regionTz(c);
    const fmt = new Intl.DateTimeFormat("ar-AE", { timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const stamp = () => { clock.textContent = `${f.ts ? "التُقطت" : "حُدّثت"} ${fmt.format(f.ts ? new Date(f.ts) : new Date())} بتوقيت ${(state.regions.find((r) => r.key === c.region)?.name || "المنطقة").replace(/\s*\(.*\)/, "")}`; };
    if (el.dataset.src === f.src) { if (!f.ts) stamp(); return; }
    const pre = new Image();
    pre.onload = () => { img.src = f.src; el.dataset.src = f.src; el.classList.add("on"); el.classList.remove("off"); stamp(); };
    pre.onerror = () => { if (!el.dataset.src) { msg.textContent = "البث غير متاح الآن"; el.classList.add("off"); } };
    pre.src = f.src;
  }
  function liveTick() {
    clearTimeout(live.timer);
    if (!live.paused) $$("[data-live]").filter((el) => el.offsetParent).forEach(updateFrame);
    live.timer = setTimeout(liveTick, 15000);
  }
  function renderLive() {
    // المناطق التي يسود فيها النهار الآن أولًا
    const hour = (c) => +new Intl.DateTimeFormat("en-US", { timeZone: regionTz(c) || "UTC", hour: "numeric", hourCycle: "h23" }).format(new Date());
    const day = (c) => { const h = hour(c); return h >= 7 && h < 18; };
    const list = state.cameras.filter((c) => c.live).sort((a, b) => day(b) - day(a));
    $("#liveCount").textContent = fmtN(list.length);
    $("#liveGrid").innerHTML = list.map((c) => `<article class="live-tile">${liveFrameHTML(c)}
      <div class="body"><div><b>${esc(c.name)}</b><span class="muted">${esc(c.road)}</span></div>
        <button class="btn ghost sm" type="button" data-cam="${esc(c.id)}">التحليل والتفاصيل</button></div></article>`).join("")
      || `<div class="empty">لا توجد كاميرات ببث مباشر في هذه المنطقة</div>`;
    liveTick();
  }
  $("#livePause").addEventListener("click", (e) => {
    live.paused = !live.paused;
    const b = e.currentTarget; b.innerHTML = live.paused ? `${svg("play")}استئناف البث` : `${svg("pause")}إيقاف مؤقت`;
    $("#liveState").textContent = live.paused ? "متوقف مؤقتًا" : "مباشر";
    $("#liveState").classList.toggle("paused", live.paused);
    if (!live.paused) liveTick();
  });
  document.addEventListener("click", (e) => {
    const fs = e.target.closest("[data-fs]"); if (!fs) return;
    e.stopPropagation();
    const f = fs.closest(".frame");
    document.fullscreenElement ? document.exitFullscreen() : f.requestFullscreen?.();
  }, true);

  function renderDetail(d) {
    const rd = d.risk_detail, fc = rd?.forecast || {}, m = d.latest_metrics || {};
    const snaps = d.snapshots.filter((s) => s.quality === "ok").slice().reverse();
    const lvl = rd?.level || "low";
    $("#dBody").innerHTML = `
      ${d.live ? `<div class="card live-card">
        <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("live")}</span>البث المباشر من الكاميرا</h2></div>
        ${liveFrameHTML(d)}
        <p class="muted live-hint">الصورة تأتي مباشرة من ${esc(srcLabel(d.source_type))} وتتحدّث تلقائيًا كل ${fmtN(d.live.refresh)} ثانية تقريبًا. قد تظهر ليلية حسب التوقيت المحلي للمنطقة.</p></div>` : ""}
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
    liveTick();
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
    if ($("#tab-live").classList.contains("active")) renderLive();
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
