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
  const SRC_AR = { demo: "محاكاة", datagovsg: "كاميرا حقيقية · سنغافورة LTA", az511: "كاميرا حقيقية · أريزونا ADOT", fl511: "كاميرا حقيقية · فلوريدا FDOT", caltrans: "فيديو مباشر · كاليفورنيا Caltrans", madrid: "كاميرا حقيقية · بلدية مدريد" };
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
    mic: "<path d=\"M168,64v64a40,40,0,0,1-40,40h0a40,40,0,0,1-40-40V64a40,40,0,0,1,40-40h0A40,40,0,0,1,168,64Z\" class=\"d\"/><path d=\"M128,176a48.05,48.05,0,0,0,48-48V64a48,48,0,0,0-96,0v64A48.05,48.05,0,0,0,128,176ZM96,64a32,32,0,0,1,64,0v64a32,32,0,0,1-64,0Zm40,143.6V240a8,8,0,0,1-16,0V207.6A80.11,80.11,0,0,1,48,128a8,8,0,0,1,16,0,64,64,0,0,0,128,0,8,8,0,0,1,16,0A80.11,80.11,0,0,1,136,207.6Z\"/>",
    coins: "<path d=\"M240,132c0,19.88-35.82,36-80,36-19.6,0-37.56-3.17-51.47-8.44h0C146.76,156.85,176,142,176,124V96.72h0C212.52,100.06,240,114.58,240,132ZM176,84c0-19.88-35.82-36-80-36S16,64.12,16,84s35.82,36,80,36S176,103.88,176,84Z\" class=\"d\"/><path d=\"M184,89.57V84c0-25.08-37.83-44-88-44S8,58.92,8,84v40c0,20.89,26.25,37.49,64,42.46V172c0,25.08,37.83,44,88,44s88-18.92,88-44V132C248,111.3,222.58,94.68,184,89.57ZM232,132c0,13.22-30.79,28-72,28-3.73,0-7.43-.13-11.08-.37C170.49,151.77,184,139,184,124V105.74C213.87,110.19,232,122.27,232,132ZM72,150.25V126.46A183.74,183.74,0,0,0,96,128a183.74,183.74,0,0,0,24-1.54v23.79A163,163,0,0,1,96,152,163,163,0,0,1,72,150.25Zm96-40.32V124c0,8.39-12.41,17.4-32,22.87V123.5C148.91,120.37,159.84,115.71,168,109.93ZM96,56c41.21,0,72,14.78,72,28s-30.79,28-72,28S24,97.22,24,84,54.79,56,96,56ZM24,124V109.93c8.16,5.78,19.09,10.44,32,13.57v23.37C36.41,141.4,24,132.39,24,124Zm64,48v-4.17c2.63.1,5.29.17,8,.17,3.88,0,7.67-.13,11.39-.35A121.92,121.92,0,0,0,120,171.41v23.46C100.41,189.4,88,180.39,88,172Zm48,26.25V174.4a179.48,179.48,0,0,0,24,1.6,183.74,183.74,0,0,0,24-1.54v23.79a165.45,165.45,0,0,1-48,0Zm64-3.38V171.5c12.91-3.13,23.84-7.79,32-13.57V172C232,180.39,219.59,189.4,200,194.87Z\"/>",
    chat: "<path d=\"M224,56V184a8,8,0,0,1-8,8H150.93l-16,28a8,8,0,0,1-13.9,0l-16-28H40a8,8,0,0,1-8-8V56a8,8,0,0,1,8-8H216A8,8,0,0,1,224,56Z\" class=\"d\"/><path d=\"M88,104a8,8,0,0,1,8-8h64a8,8,0,0,1,0,16H96A8,8,0,0,1,88,104Zm8,40h64a8,8,0,0,0,0-16H96a8,8,0,0,0,0,16ZM232,56V184a16,16,0,0,1-16,16H155.57l-13.68,23.94a16,16,0,0,1-27.78,0L100.43,200H40a16,16,0,0,1-16-16V56A16,16,0,0,1,40,40H216A16,16,0,0,1,232,56Zm-16,0H40V184h65.07a8,8,0,0,1,7,4l16,28,16-28a8,8,0,0,1,7-4H216Z\"/>",
    report: "<path d=\"M240,120a40,40,0,0,1-40,40H160V80h40A40,40,0,0,1,240,120Z\" class=\"d\"/><path d=\"M248,120a48.05,48.05,0,0,0-48-48H160.2c-2.91-.17-53.62-3.74-101.91-44.24A16,16,0,0,0,32,40V200a16,16,0,0,0,26.29,12.25c37.77-31.68,77-40.76,93.71-43.3v31.72A16,16,0,0,0,159.12,214l11,7.33A16,16,0,0,0,194.5,212l11.77-44.36A48.07,48.07,0,0,0,248,120ZM48,199.93V40h0c42.81,35.91,86.63,45,104,47.24v65.48C134.65,155,90.84,164.07,48,199.93Zm131,8,0,.11-11-7.33V168h21.6ZM200,152H168V88h32a32,32,0,1,1,0,64Z\"/>",
    phone: "<path d=\"M192,56V200H64V56Z\" class=\"d\"/><path d=\"M176,16H80A24,24,0,0,0,56,40V216a24,24,0,0,0,24,24h96a24,24,0,0,0,24-24V40A24,24,0,0,0,176,16ZM72,64H184V192H72Zm8-32h96a8,8,0,0,1,8,8v8H72V40A8,8,0,0,1,80,32Zm96,192H80a8,8,0,0,1-8-8v-8H184v8A8,8,0,0,1,176,224Z\"/>",
    send: "<path d=\"M223.69,42.18l-58.22,192a8,8,0,0,1-14.92,1.25L108,148,20.58,105.45a8,8,0,0,1,1.25-14.92l192-58.22A8,8,0,0,1,223.69,42.18Z\" class=\"d\"/><path d=\"M227.32,28.68a16,16,0,0,0-15.66-4.08l-.15,0L19.57,82.84a16,16,0,0,0-2.49,29.8L102,154l41.3,84.87A15.86,15.86,0,0,0,157.74,248q.69,0,1.38-.06a15.88,15.88,0,0,0,14-11.51l58.2-191.94c0-.05,0-.1,0-.15A16,16,0,0,0,227.32,28.68ZM157.83,231.85l-.05.14,0-.07-40.06-82.3,48-48a8,8,0,0,0-11.31-11.31l-48,48L24.08,98.25l-.07,0,.14,0L216,40Z\"/>",
    pin: "<path d=\"M128,24a80,80,0,0,0-80,80c0,72,80,128,80,128s80-56,80-128A80,80,0,0,0,128,24Zm0,112a32,32,0,1,1,32-32A32,32,0,0,1,128,136Z\" class=\"d\"/><path d=\"M128,64a40,40,0,1,0,40,40A40,40,0,0,0,128,64Zm0,64a24,24,0,1,1,24-24A24,24,0,0,1,128,128Zm0-112a88.1,88.1,0,0,0-88,88c0,31.4,14.51,64.68,42,96.25a254.19,254.19,0,0,0,41.45,38.3,8,8,0,0,0,9.18,0A254.19,254.19,0,0,0,174,200.25c27.45-31.57,42-64.85,42-96.25A88.1,88.1,0,0,0,128,16Zm0,206c-16.53-13-72-60.75-72-118a72,72,0,0,1,144,0C200,161.23,144.53,209,128,222Z\"/>",
    sparkle: "<path d=\"M194.82,151.43l-55.09,20.3-20.3,55.09a7.92,7.92,0,0,1-14.86,0l-20.3-55.09-55.09-20.3a7.92,7.92,0,0,1,0-14.86l55.09-20.3,20.3-55.09a7.92,7.92,0,0,1,14.86,0l20.3,55.09,55.09,20.3A7.92,7.92,0,0,1,194.82,151.43Z\" class=\"d\"/><path d=\"M197.58,129.06,146,110l-19-51.62a15.92,15.92,0,0,0-29.88,0L78,110l-51.62,19a15.92,15.92,0,0,0,0,29.88L78,178l19,51.62a15.92,15.92,0,0,0,29.88,0L146,178l51.62-19a15.92,15.92,0,0,0,0-29.88ZM137,164.22a8,8,0,0,0-4.74,4.74L112,223.85,91.78,169A8,8,0,0,0,87,164.22L32.15,144,87,123.78A8,8,0,0,0,91.78,119L112,64.15,132.22,119a8,8,0,0,0,4.74,4.74L191.85,144ZM144,40a8,8,0,0,1,8-8h16V16a8,8,0,0,1,16,0V32h16a8,8,0,0,1,0,16H184V64a8,8,0,0,1-16,0V48H152A8,8,0,0,1,144,40ZM248,88a8,8,0,0,1-8,8h-8v8a8,8,0,0,1-16,0V96h-8a8,8,0,0,1,0-16h8V72a8,8,0,0,1,16,0v8h8A8,8,0,0,1,248,88Z\"/>",
    zoomin: "<path d=\"M192,112a80,80,0,1,1-80-80A80,80,0,0,1,192,112Z\" class=\"d\"/><path d=\"M229.66,218.34,179.6,168.28a88.21,88.21,0,1,0-11.32,11.31l50.06,50.07a8,8,0,0,0,11.32-11.32ZM40,112a72,72,0,1,1,72,72A72.08,72.08,0,0,1,40,112Zm112,0a8,8,0,0,1-8,8H120v24a8,8,0,0,1-16,0V120H80a8,8,0,0,1,0-16h24V80a8,8,0,0,1,16,0v24h24A8,8,0,0,1,152,112Z\"/>",
    zoomout: "<path d=\"M192,112a80,80,0,1,1-80-80A80,80,0,0,1,192,112Z\" class=\"d\"/><path d=\"M229.66,218.34,179.6,168.28a88.21,88.21,0,1,0-11.32,11.31l50.06,50.07a8,8,0,0,0,11.32-11.32ZM40,112a72,72,0,1,1,72,72A72.08,72.08,0,0,1,40,112Zm112,0a8,8,0,0,1-8,8H80a8,8,0,0,1,0-16h64A8,8,0,0,1,152,112Z\"/>",
    fit: "<path d=\"M208,64V192a16,16,0,0,1-16,16H64a16,16,0,0,1-16-16V64A16,16,0,0,1,64,48H192A16,16,0,0,1,208,64Z\" class=\"d\"/><path d=\"M152,96V48a8,8,0,0,1,16,0V88h40a8,8,0,0,1,0,16H160A8,8,0,0,1,152,96ZM96,152H48a8,8,0,0,0,0,16H88v40a8,8,0,0,0,16,0V160A8,8,0,0,0,96,152Zm112,0H160a8,8,0,0,0-8,8v48a8,8,0,0,0,16,0V168h40a8,8,0,0,0,0-16ZM96,40a8,8,0,0,0-8,8V88H48a8,8,0,0,0,0,16H96a8,8,0,0,0,8-8V48A8,8,0,0,0,96,40Z\"/>",
    prev: "<path d=\"M176,128,96,208V48Z\" class=\"d\"/><path d=\"M181.66,122.34l-80-80A8,8,0,0,0,88,48V208a8,8,0,0,0,13.66,5.66l80-80A8,8,0,0,0,181.66,122.34ZM104,188.69V67.31L164.69,128Z\"/>",
    next: "<path d=\"M160,48V208L80,128Z\" class=\"d\"/><path d=\"M163.06,40.61a8,8,0,0,0-8.72,1.73l-80,80a8,8,0,0,0,0,11.32l80,80A8,8,0,0,0,168,208V48A8,8,0,0,0,163.06,40.61ZM152,188.69,91.31,128,152,67.31Z\"/>",
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
    if (name === "assistant") { setChatMode(); setTimeout(() => $("#chatQ").focus(), 50); }
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
      ...(s.gulf?.max_pavement ? [
        kpi("أعلى حرارة رصف", `${fmtN(s.gulf.max_pavement, 0)}°م`, esc(s.gulf.max_pavement_camera), s.gulf.max_pavement >= 64, "sun", "warn"),
        kpi("خطر تخدد مرتفع", fmtN(s.gulf.rutting_high), `${fmtN(s.gulf.rutting_medium)} متوسط · ${fmtN(s.gulf.pg_deficit)} برابط أقل من المطلوب`, s.gulf.rutting_high > 0, "road", "warn"),
      ] : []),
    ].join("");
    const ev = s.gulf?.events || [];
    $("#eventsNote").hidden = !ev.length;
    $("#eventsNote").innerHTML = ev.map((e) => `<div>${svg("alert")}<span><b>${esc((state.regions.find((r) => r.key === e.region)?.name) || e.region)} · ${esc(e.date)}:</b> ${esc(e.text)}</span></div>`).join("");

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
    // طبقة الرصد الميداني: خلايا الخشونة ثم البلاغات
    state.fieldLayer?.remove();
    state.fieldLayer = L.layerGroup().addTo(state.map);
    for (const r of state.rough || []) {
      L.circleMarker([r.lat, r.lng], { radius: 5, stroke: false, fillOpacity: 0.8, fillColor: ROUGH[r.class]?.[1] || "#999" })
        .bindTooltip(`خشونة ${fmtN(r.iri, 1)} م/كم · ${ROUGH[r.class]?.[0] || ""} · ${fmtN(r.n)} قراءة`).addTo(state.fieldLayer);
    }
    for (const r of state.reports || []) {
      const icon = L.divIcon({ className: "", iconSize: [20, 18], iconAnchor: [10, 16], html: `<i class="tri ${r.status === "verified" ? "" : "review"}"></i>` });
      L.marker([r.lat, r.lng], { icon }).bindPopup(`<div class="pop">${r.thumb ? `<img src="${r.thumb}" alt="">` : ""}<b>${esc(r.kind_ar)}</b>
        <span class="muted">${fmtDT(r.ts)} · ${REP_STATUS[r.status] || r.status}</span>${r.note ? `<div>${esc(r.note)}</div>` : ""}</div>`, { maxWidth: 270 }).addTo(state.fieldLayer);
    }
    for (const c of state.cameras) {
      const lvl = c.risk?.level || "low";
      const col = c.risk ? color(lvl) : css("--muted");
      const icon = L.divIcon({ className: "", iconSize: [22, 22], iconAnchor: [11, 11],
        html: `<div class="marker ${c.open_alerts ? "pulse" : ""}" style="background:${col};color:${col}"></div>` });
      const s = c.last_snapshot;
      const m = L.marker([c.lat, c.lng], { icon }).addTo(state.map).bindPopup(`<div class="pop">
        ${s ? `<img src="/api/snapshots/${s.id}/image?annotated=1" alt="" data-zoom-cam="${esc(c.id)}" title="اضغط للتكبير">` : ""}
        <b>${esc(c.name)}</b><span class="muted">${esc(c.road)}</span>
        <div class="row">${c.risk ? `<span class="pill ${lvl}">${LEVEL_AR[lvl]} · ${fmtN(c.risk.score)}</span>` : ""}
        <span class="muted">${s ? `مؤشر الحالة <b style="display:inline">${fmtN(c.risk?.ci ?? s.condition_index)}</b>` : "بانتظار أول التقاط نهاري"}</span></div>
        <button class="btn" data-cam="${esc(c.id)}">التفاصيل والتنبؤ</button></div>`, { maxWidth: 270 });
      state.markers[c.id] = m;
    }
  }

  // ---------- معاينة الصور وتكبيرها ----------
  // عارض بملء الشاشة: تكبير حتى 8× بالعجلة أو القرص بإصبعين أو النقر المزدوج، سحب للتنقل، تبديل العيوب، وتصفح اللقطات
  const hiSrc = (id, ann) => `/api/snapshots/${id}/image?annotated=${ann}`;
  const lb = { items: [], i: 0, ann: 1, s: 1, x: 0, y: 0, fit: 1, cam: null, onClose: null, ptrs: new Map(), pinch: null, tap: 0, touchAt: 0 };
  document.body.insertAdjacentHTML("beforeend", `<div class="lb" id="lb" hidden role="dialog" aria-modal="true" aria-label="معاينة الصورة">
    <div class="lb-stage" id="lbStage"><img id="lbImg" alt="" draggable="false"><span class="lb-spin"></span></div>
    <div class="lb-top"><div class="lb-cap"><b id="lbTitle"></b><span id="lbMeta"></span></div>
      <button class="lb-btn" type="button" data-lb="close" aria-label="إغلاق" title="إغلاق (Esc)">${svg("close")}</button></div>
    <button class="lb-nav prev" type="button" data-lb="prev" aria-label="اللقطة الأقدم" title="الأقدم">${svg("prev")}</button>
    <button class="lb-nav next" type="button" data-lb="next" aria-label="اللقطة الأحدث" title="الأحدث">${svg("next")}</button>
    <div class="lb-bar">
      <button class="lb-btn" type="button" data-lb="out" aria-label="تصغير" title="تصغير (−)">${svg("zoomout")}</button>
      <span class="lb-zoom" id="lbZoom">100%</span>
      <button class="lb-btn" type="button" data-lb="in" aria-label="تكبير" title="تكبير (+)">${svg("zoomin")}</button>
      <button class="lb-btn" type="button" data-lb="fit" aria-label="ملاءمة الشاشة" title="ملاءمة الشاشة (0)">${svg("fit")}</button>
      <span class="lb-sep"></span>
      <label class="lb-switch"><input type="checkbox" id="lbAnn" checked> إظهار العيوب</label>
      <a class="lb-btn" id="lbDl" download aria-label="تنزيل الصورة" title="تنزيل">${svg("download")}</a>
      <span class="lb-count" id="lbCount"></span>
    </div></div>`);
  const lbEl = $("#lb"), lbImg = $("#lbImg"), lbStage = $("#lbStage");
  function lbApply() {
    lbImg.style.transform = `translate(${lb.x}px, ${lb.y}px) scale(${lb.s})`;
    $("#lbZoom").textContent = `${Math.round((lb.s / lb.fit) * 100)}%`;
    lbEl.classList.toggle("zoomed", lb.s > lb.fit * 1.01);
  }
  function lbFit() {
    const r = lbStage.getBoundingClientRect(), w = lbImg.naturalWidth || 1, h = lbImg.naturalHeight || 1;
    lb.fit = lb.s = Math.min(r.width / w, r.height / h);
    lb.x = (r.width - w * lb.s) / 2; lb.y = (r.height - h * lb.s) / 2;
    lbApply();
  }
  function lbClamp() {  // لا تخرج الصورة المكبّرة كلها من الشاشة
    const r = lbStage.getBoundingClientRect(), w = lbImg.naturalWidth * lb.s, h = lbImg.naturalHeight * lb.s;
    lb.x = w <= r.width ? (r.width - w) / 2 : Math.min(0, Math.max(r.width - w, lb.x));
    lb.y = h <= r.height ? (r.height - h) / 2 : Math.min(0, Math.max(r.height - h, lb.y));
  }
  function lbZoomAt(f, cx, cy) {
    const r = lbStage.getBoundingClientRect();
    const ns = Math.min(lb.fit * 8, Math.max(lb.fit, lb.s * f));
    const px = (cx ?? r.left + r.width / 2) - r.left, py = (cy ?? r.top + r.height / 2) - r.top;
    lb.x = px - ((px - lb.x) * ns) / lb.s; lb.y = py - ((py - lb.y) * ns) / lb.s; lb.s = ns;
    lbClamp(); lbApply();
  }
  function lbShow(keepView = false) {
    const it = lb.items[lb.i]; if (!it) return;
    const src = hiSrc(it.id, lb.ann);
    lbEl.classList.add("loading");
    lbImg.onload = () => { lbEl.classList.remove("loading"); if (!keepView) lbFit(); };
    lbImg.onerror = () => lbEl.classList.remove("loading");
    lbImg.src = src;
    const dl = $("#lbDl"); dl.href = src; dl.download = `darb-${lb.cam?.id || "camera"}-${(it.ts || "").slice(0, 10)}${lb.ann ? "-defects" : ""}.jpg`;
    $("#lbTitle").textContent = lb.cam?.name || "";
    $("#lbMeta").textContent = [it.ts && fmtDT(it.ts), KIND_AR[it.kind] || it.kind, it.condition_index != null && `الحالة ${fmtN(it.condition_index)}`,
      it.pothole_count ? `حفر ${fmtN(it.pothole_count)}` : ""].filter(Boolean).join(" · ");
    $("#lbCount").textContent = lb.items.length > 1 ? `${fmtN(lb.i + 1)} / ${fmtN(lb.items.length)}` : "";
    lbEl.querySelector(".prev").hidden = lb.i <= 0;
    lbEl.querySelector(".next").hidden = lb.i >= lb.items.length - 1;
  }
  function openLightbox(cam, items, i = items.length - 1, ann = true, onClose = null) {
    Object.assign(lb, { cam, items, i, ann: ann ? 1 : 0, onClose });
    $("#lbAnn").checked = !!ann;
    lbEl.hidden = false; document.body.classList.add("lb-open");
    lbShow();
  }
  function closeLightbox() {
    lbEl.hidden = true; document.body.classList.remove("lb-open");
    lb.onClose?.(lb.i, lb.ann); lb.onClose = null;
  }
  function lbStep(d) { const n = lb.i + d; if (n >= 0 && n < lb.items.length) { lb.i = n; lbShow(); } }
  lbEl.addEventListener("click", (e) => {
    const a = e.target.closest("[data-lb]")?.dataset.lb;
    if (a === "close") closeLightbox();
    else if (a === "prev") lbStep(-1);
    else if (a === "next") lbStep(1);
    else if (a === "in") lbZoomAt(1.5);
    else if (a === "out") lbZoomAt(1 / 1.5);
    else if (a === "fit") lbFit();
  });
  $("#lbAnn").addEventListener("change", (e) => { lb.ann = e.target.checked ? 1 : 0; lbShow(true); });
  lbStage.addEventListener("wheel", (e) => { e.preventDefault(); lbZoomAt(e.deltaY < 0 ? 1.18 : 1 / 1.18, e.clientX, e.clientY); }, { passive: false });
  lbStage.addEventListener("dblclick", (e) => {
    if (Date.now() - lb.touchAt < 800) return;  // اللمس يعالَج بالنقر المزدوج أدناه (المتصفح يطلق dblclick أيضًا)
    lb.s > lb.fit * 1.05 ? lbFit() : lbZoomAt(2.5, e.clientX, e.clientY);
  });
  lbStage.addEventListener("pointerdown", (e) => {
    lbStage.setPointerCapture(e.pointerId);
    if (e.pointerType === "touch") lb.touchAt = Date.now();
    lb.ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (lb.ptrs.size === 2) {
      const [a, b] = [...lb.ptrs.values()];
      lb.pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), s: lb.s };
    }
  });
  lbStage.addEventListener("pointermove", (e) => {
    const p = lb.ptrs.get(e.pointerId); if (!p) return;
    if (lb.ptrs.size === 2 && lb.pinch) {  // قرص بإصبعين
      p.x = e.clientX; p.y = e.clientY;
      const [a, b] = [...lb.ptrs.values()];
      const f = (lb.pinch.s * (Math.hypot(a.x - b.x, a.y - b.y) / lb.pinch.d)) / lb.s;
      lbZoomAt(f, (a.x + b.x) / 2, (a.y + b.y) / 2);
    } else if (lb.ptrs.size === 1) {  // سحب
      lb.x += e.clientX - p.x; lb.y += e.clientY - p.y; p.x = e.clientX; p.y = e.clientY;
      lbClamp(); lbApply();
    }
  });
  const lbUp = (e) => {
    if (!lb.ptrs.delete(e.pointerId)) return;
    if (lb.ptrs.size < 2) lb.pinch = null;
    if (e.pointerType === "touch" && e.type === "pointerup") {  // نقر مزدوج باللمس
      const now = Date.now();
      if (now - lb.tap < 300) { lb.s > lb.fit * 1.05 ? lbFit() : lbZoomAt(2.5, e.clientX, e.clientY); lb.tap = 0; } else lb.tap = now;
    }
  };
  lbStage.addEventListener("pointerup", lbUp); lbStage.addEventListener("pointercancel", lbUp);
  document.addEventListener("keydown", (e) => {
    if (lbEl.hidden) return;
    const k = e.key;
    if (k === "Escape") closeLightbox();
    else if (k === "+" || k === "=") lbZoomAt(1.5);
    else if (k === "-") lbZoomAt(1 / 1.5);
    else if (k === "0") lbFit();
    else if (k === "ArrowRight") lbStep(-1);  // واجهة من اليمين لليسار: اليمين = الأقدم
    else if (k === "ArrowLeft") lbStep(1);
    else return;
    e.preventDefault(); e.stopImmediatePropagation();  // لا يُغلق لوحة التفاصيل خلفه
  }, true);
  addEventListener("resize", () => { if (!lbEl.hidden) lbFit(); });
  // تكبير صورة كاميرا من البطاقة أو الخريطة مباشرة
  document.addEventListener("click", (e) => {
    const z = e.target.closest("[data-zoom-cam]"); if (!z) return;
    e.stopPropagation(); e.preventDefault();
    const c = state.cameras.find((x) => x.id === z.dataset.zoomCam);
    if (c?.last_snapshot) openLightbox(c, [c.last_snapshot], 0, z.dataset.ann !== "0");
  }, true);

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
        <div class="img">${s ? "" : `<span class="wait">${svg("camoff")}بانتظار أول التقاط نهاري</span>`}${s ? `<img loading="lazy" src="/api/snapshots/${s.id}/image?annotated=${ann}" alt="لقطة ${esc(c.name)}">
          <button class="zoom-btn" type="button" data-zoom-cam="${esc(c.id)}" data-ann="${ann}" aria-label="تكبير الصورة" title="تكبير ومعاينة">${svg("zoomin")}</button>` : ""}
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
  const regionName = (c) => (state.regions.find((r) => r.key === c.region)?.name || "المنطقة").replace(/\s*\(.*\)/, "");
  function liveFrameHTML(c) {
    live.cams[c.id] = c;
    // بث فيديو متصل (HLS): مشغّل فيديو حقيقي يعمل فقط حين يكون ظاهرًا على الشاشة لتوفير الإنترنت
    if (c.live.kind === "hls") return `<div class="frame video" data-video="${esc(c.id)}"><video muted playsinline autoplay aria-label="بث فيديو مباشر — ${esc(c.name)}"></video>
      <span class="loading">جارٍ تشغيل البث…</span><span class="clock"></span>
      <button class="fs" type="button" data-fs aria-label="ملء الشاشة" title="ملء الشاشة">${svg("expand")}</button></div>`;
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
    const stamp = () => { clock.textContent = `${f.ts ? "التُقطت" : "حُدّثت"} ${fmt.format(f.ts ? new Date(f.ts) : new Date())} بتوقيت ${regionName(c)}`; };
    if (el.dataset.src === f.src) { if (!f.ts) stamp(); return; }
    const pre = new Image();
    pre.onload = () => { img.src = f.src; el.dataset.src = f.src; el.classList.add("on"); el.classList.remove("off"); stamp(); };
    pre.onerror = () => { if (!el.dataset.src) { msg.textContent = "البث غير متاح الآن"; el.classList.add("off"); } };
    pre.src = f.src;
  }
  const players = new Map();
  function attachVideo(el) {
    if (players.has(el) || live.paused) return;
    const c = live.cams[el.dataset.video], v = el.querySelector("video"), msg = el.querySelector(".loading");
    const fail = () => { msg.textContent = "البث غير متاح الآن"; el.classList.add("off"); el.classList.remove("on"); };
    v.onplaying = () => { el.classList.add("on"); el.classList.remove("off"); };
    let hls = null;
    if (window.Hls?.isSupported()) {
      hls = new Hls({ liveSyncDurationCount: 2, maxBufferLength: 10, backBufferLength: 0 });
      hls.on(Hls.Events.ERROR, (_, d) => { if (d.fatal) { fail(); detachVideo(el); } });
      hls.loadSource(c.live.url); hls.attachMedia(v);
    } else if (v.canPlayType("application/vnd.apple.mpegurl")) {
      v.src = c.live.url; v.onerror = fail;   // سفاري يشغّل HLS مباشرة
    } else { fail(); return; }
    v.play().catch(() => {});
    players.set(el, hls);
  }
  function detachVideo(el) {
    if (!players.has(el)) return;
    const hls = players.get(el), v = el.querySelector("video");
    players.delete(el); hls?.destroy(); v.removeAttribute("src"); v.load(); el.classList.remove("on");
  }
  const io = "IntersectionObserver" in window ? new IntersectionObserver((ents) => ents.forEach((e) =>
    (e.isIntersecting ? attachVideo : detachVideo)(e.target)), { rootMargin: "120px" }) : null;
  const inView = (el) => { const r = el.getBoundingClientRect(); return el.offsetParent && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
  setInterval(() => $$("[data-video].on").forEach((el) => {
    const c = live.cams[el.dataset.video];
    el.querySelector(".clock").textContent = `فيديو متصل · ${new Intl.DateTimeFormat("ar-AE", { timeZone: regionTz(c), hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date())} بتوقيت ${regionName(c)}`;
  }), 1000);
  function liveTick() {
    clearTimeout(live.timer);
    players.forEach((_, el) => { if (!el.isConnected) detachVideo(el); });
    $$("[data-video]").forEach((el) => {
      if (!el.dataset.obs) { el.dataset.obs = "1"; io?.observe(el); }
      if (live.paused) detachVideo(el); else if (!io && inView(el)) attachVideo(el); else if (io && inView(el)) attachVideo(el);
    });
    if (!live.paused) $$("[data-live]").filter((el) => el.offsetParent).forEach(updateFrame);
    live.timer = setTimeout(liveTick, 15000);
  }
  function renderLive() {
    // المناطق التي يسود فيها النهار الآن أولًا
    const hour = (c) => +new Intl.DateTimeFormat("en-US", { timeZone: regionTz(c) || "UTC", hour: "numeric", hourCycle: "h23" }).format(new Date());
    const day = (c) => { const h = hour(c); return h >= 7 && h < 18; };
    const list = state.cameras.filter((c) => c.live).sort((a, b) => day(b) - day(a) || (b.live.kind === "hls") - (a.live.kind === "hls"));
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

  // واجهة مشتركة لمختبر نماذج الطرق (lab.js)
  window.DARB = { $, fmtN, esc, svg, money: (usd) => money(usd), color, safeGet, safeSet };

  // ملاحظة «يُحدَّث آليًا» تُختصر في سطرين على الجوال، وتنفتح بالنقر
  document.addEventListener("click", (e) => { const n = e.target.closest(".snapnote > div"); if (n) n.classList.toggle("open"); });

  // ---------- الرصد الميداني ----------
  const ROUGH = { excellent: ["ممتاز", "#16a34a"], good: ["جيد", "#84cc16"], fair: ["متوسط", "#facc15"], poor: ["سيئ", "#f97316"], very_poor: ["سيئ جدًا", "#dc2626"] };
  const REP_STATUS = { verified: "تأكد بالذكاء الاصطناعي", review: "قيد المراجعة", no_image: "بلا صورة", resolved: "عولج" };
  const REP_KINDS = { pothole: "حفرة", cracks: "تشققات", sand: "رمال", water: "تجمّع مياه", debris: "مخلّفات", other: "أخرى" };
  const isStatic = () => !!state.status?.static_snapshot;
  const repo = () => { const o = location.hostname.split(".")[0], r = location.pathname.split("/").filter(Boolean)[0]; return location.hostname.endsWith("github.io") && r ? `${o}/${r}` : "ahsasgaly11-ai/darb-ai"; };
  const rep_ = { kind: "pothole", img: null, loc: null };
  $("#repKinds").innerHTML = Object.entries(REP_KINDS).map(([k, v]) => `<button type="button" class="chip-btn ${k === rep_.kind ? "on" : ""}" data-kind="${k}">${v}</button>`).join("");
  $("#repKinds").addEventListener("click", (e) => { const b = e.target.closest("[data-kind]"); if (!b) return; rep_.kind = b.dataset.kind; $$("#repKinds .chip-btn").forEach((x) => x.classList.toggle("on", x === b)); });
  $("#repPhoto").addEventListener("change", (e) => {
    const f = e.target.files[0]; if (!f) return;
    const im = new Image();
    im.onload = () => {  // تصغير إلى 1280 قبل الإرسال (أسرع وأوفر للبيانات)
      const k = Math.min(1, 1280 / im.width), cv = document.createElement("canvas");
      cv.width = Math.round(im.width * k); cv.height = Math.round(im.height * k);
      cv.getContext("2d").drawImage(im, 0, 0, cv.width, cv.height);
      rep_.img = cv.toDataURL("image/jpeg", 0.85);
      $("#repPreview").src = rep_.img; $("#repPreview").hidden = false; $("#repPhotoTxt").hidden = true;
      URL.revokeObjectURL(im.src);
    };
    im.src = URL.createObjectURL(f);
  });
  $("#repLocBtn").addEventListener("click", () => {
    if (!navigator.geolocation) { $("#repMsg").textContent = "المتصفح لا يدعم تحديد الموقع — اكتب الإحداثيات."; return; }
    $("#repMsg").textContent = "جارٍ تحديد موقعك…";
    navigator.geolocation.getCurrentPosition((p) => {
      rep_.loc = [p.coords.latitude, p.coords.longitude];
      $("#repLoc").value = `${rep_.loc[0].toFixed(5)}, ${rep_.loc[1].toFixed(5)}`; $("#repMsg").textContent = `تم تحديد الموقع (دقة ~${fmtN(p.coords.accuracy)} م).`;
    }, () => { $("#repMsg").textContent = "تعذّر تحديد الموقع — اسمح للمتصفح بالوصول أو اكتب الإحداثيات."; }, { enableHighAccuracy: true, timeout: 15000 });
  });
  $("#repForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const m = $("#repLoc").value.match(/(-?\d+(?:\.\d+)?)\s*[,،]\s*(-?\d+(?:\.\d+)?)/);
    if (!m) { $("#repMsg").textContent = "حدد الموقع أولًا."; return; }
    const lat = +m[1], lng = +m[2], note = $("#repNote").value.trim();
    if (isStatic()) {
      // الموقع المجاني بلا خادم: البلاغ يُرسل عبر GitHub Issues، ويتحقق منه التشغيل اليومي بالذكاء الاصطناعي ويرد عليك
      const body = `النوع: ${REP_KINDS[rep_.kind] === "رمال" ? "رمال على الطريق" : REP_KINDS[rep_.kind]}\nالموقع: ${lat.toFixed(5)}, ${lng.toFixed(5)}\nالملاحظة: ${note || "—"}\n\n<!-- اسحب صورة المشكلة إلى هذا المربع قبل الضغط على Submit -->\n`;
      window.open(`https://github.com/${repo()}/issues/new?title=${encodeURIComponent(`[بلاغ] ${REP_KINDS[rep_.kind]} — ${lat.toFixed(4)}, ${lng.toFixed(4)}`)}&body=${encodeURIComponent(body)}`, "_blank", "noopener");
      $("#repMsg").innerHTML = `فُتحت صفحة البلاغ على GitHub: <b>اسحب الصورة إلى مربع النص</b> ثم اضغط Submit. يتحقق منه دَرْب بالذكاء الاصطناعي في التشغيل التالي ويرد عليك هناك.`;
      return;
    }
    $("#repSend").disabled = true; $("#repMsg").textContent = "جارٍ الإرسال والتحقق بالذكاء الاصطناعي…";
    try {
      const r = await api("/api/reports", { method: "POST", body: JSON.stringify({ lat, lng, kind: rep_.kind, note, image: rep_.img }) });
      $("#repMsg").innerHTML = `${r.status === "verified" ? "✅ <b>تأكد البلاغ آليًا</b>" : r.status === "review" ? "🔎 <b>سُجّل وسيراجعه مختص</b>" : "📍 <b>سُجّل بلا صورة</b>"}
        ${r.ai?.pothole_count != null ? ` · حفر: ${fmtN(r.ai.pothole_count)} · تشققات: ${fmtN(r.ai.crack_count)}` : ""}${r.camera_id ? ` · أقرب كاميرا على بعد ~${fmtN(r.distance_m)} م` : ""}. شكرًا لك!`;
      refresh().catch(() => {});
    } catch (err) { $("#repMsg").textContent = `تعذّر الإرسال: ${err.message}`; }
    $("#repSend").disabled = false;
  });
  function renderReports() {
    const list = state.reports || [];
    $("#repCount").textContent = list.length ? `${fmtN(list.length)} بلاغ · ${fmtN(list.filter((r) => r.status === "verified").length)} مؤكد` : "";
    $("#repList").innerHTML = list.slice(0, 30).map((r) => `<article class="rep">
      ${r.thumb ? `<img src="${r.thumb}" alt="" loading="lazy">` : `<div class="noimg">${svg("pin")}</div>`}
      <div><b>${esc(r.kind_ar)}</b> <span class="pill ${r.status === "verified" ? "high" : "low"}">${REP_STATUS[r.status] || r.status}</span>
        <div class="muted">${fmtDT(r.ts)} · ${esc(regionLabel(r.region))}${r.camera_id ? ` · قرب كاميرا (~${fmtN(r.distance_m)} م)` : ""}</div>
        ${r.note ? `<div>${esc(r.note)}</div>` : ""}</div></article>`).join("") || `<div class="empty">لا بلاغات بعد — كن أول من يبلّغ عن مشكلة في طريقه.</div>`;
  }
  // قياس الخشونة: الاهتزاز (مقدار التسارع ناقص الجاذبية) كل ثانية + الموقع والسرعة ← تقدير IRI
  const rough = { on: false, samples: [], pts: [], pos: null, last: null, dist: 0, watch: null, timer: null };
  const iriEst = (rms, v) => Math.max(0.5, 0.9 + 2.1 * rms * Math.sqrt(20 / Math.max(v, 5)));  // نفس صيغة الخادم (field.iri_estimate)
  const onMotion = (e) => {
    const a = e.accelerationIncludingGravity; if (!a || a.x == null) return;
    rough.samples.push(Math.hypot(a.x, a.y, a.z));
  };
  async function roughStart() {
    if (!navigator.geolocation || !("DeviceMotionEvent" in window)) { $("#roughMsg").textContent = "هذا الجهاز لا يدعم حساسات الحركة أو الموقع — جرّب من هاتف."; return; }
    if (typeof DeviceMotionEvent.requestPermission === "function") {  // آيفون: إذن صريح
      try { if (await DeviceMotionEvent.requestPermission() !== "granted") throw 0; } catch { $("#roughMsg").textContent = "يلزم السماح بالوصول لحساسات الحركة."; return; }
    }
    Object.assign(rough, { on: true, samples: [], pts: [], last: null, dist: 0 });
    addEventListener("devicemotion", onMotion);
    rough.watch = navigator.geolocation.watchPosition((p) => {
      const c = p.coords;
      if (rough.pos) rough.dist += haversine(rough.pos.lat, rough.pos.lng, c.latitude, c.longitude);
      const dt = rough.pos ? (p.timestamp - rough.pos.t) / 1000 : 0;
      const v = c.speed ?? (dt > 0 && rough.pos ? haversine(rough.pos.lat, rough.pos.lng, c.latitude, c.longitude) * 1000 / dt : 0);
      rough.pos = { lat: c.latitude, lng: c.longitude, speed: v, t: p.timestamp };
    }, () => {}, { enableHighAccuracy: true, maximumAge: 0 });
    rough.timer = setInterval(() => {
      const s = rough.samples.splice(0); if (s.length < 5 || !rough.pos) return;
      const mean = s.reduce((a, b) => a + b, 0) / s.length;
      const rms = Math.sqrt(s.reduce((a, b) => a + (b - mean) ** 2, 0) / s.length);
      const v = rough.pos.speed || 0;
      $("#rlSpeed").textContent = fmtN(v * 3.6);
      if (v < 4.2) { $("#rlClass").textContent = "سرعة منخفضة — القراءة متوقفة"; return; }
      const iri = iriEst(rms, v), cls = iri < 2 ? "excellent" : iri < 4 ? "good" : iri < 6 ? "fair" : iri < 8 ? "poor" : "very_poor";
      rough.pts.push({ lat: +rough.pos.lat.toFixed(6), lng: +rough.pos.lng.toFixed(6), rms: +rms.toFixed(3), speed: +v.toFixed(1), iri: +iri.toFixed(2), ts: new Date().toISOString() });
      $("#rlIri").textContent = fmtN(iri, 1); $("#rlClass").textContent = ROUGH[cls][0]; $("#roughLive").style.setProperty("--rc", ROUGH[cls][1]);
      $("#rlN").textContent = fmtN(rough.pts.length); $("#rlDist").textContent = fmtN(rough.dist, 1);
      $("#rlAvg").textContent = fmtN(rough.pts.reduce((a, p) => a + p.iri, 0) / rough.pts.length, 1);
    }, 1000);
    $("#roughBtn").innerHTML = `${svg("pause")}إيقاف القياس`; $("#roughSave").hidden = true;
    $("#roughMsg").textContent = "القياس يعمل — أبقِ الصفحة مفتوحة والهاتف مثبتًا.";
  }
  function roughStop() {
    rough.on = false; removeEventListener("devicemotion", onMotion); navigator.geolocation.clearWatch(rough.watch); clearInterval(rough.timer);
    $("#roughBtn").innerHTML = `${svg("play")}ابدأ القياس`;
    $("#roughSave").hidden = !rough.pts.length;
    $("#roughMsg").textContent = rough.pts.length ? `انتهى القياس: ${fmtN(rough.pts.length)} قراءة على ${fmtN(rough.dist, 1)} كم.` : "لم تُسجل قراءات (السرعة أقل من 15 كم/س أو لا إشارة GPS).";
  }
  const haversine = (a, b, c, d) => { const p = Math.PI / 180, x = 0.5 - Math.cos((c - a) * p) / 2 + Math.cos(a * p) * Math.cos(c * p) * (1 - Math.cos((d - b) * p)) / 2; return 12742 * Math.asin(Math.sqrt(x)); };
  $("#roughBtn").addEventListener("click", () => (rough.on ? roughStop() : roughStart()));
  $("#roughSave").addEventListener("click", async () => {
    if (!isStatic()) {
      try {
        const r = await api("/api/roughness", { method: "POST", body: JSON.stringify({ device: safeGet("darb-device") || (() => { const d = "p" + Math.random().toString(36).slice(2, 10); safeSet("darb-device", d); return d; })(), points: rough.pts }) });
        $("#roughMsg").textContent = `أُرسل القياس: ${fmtN(r.accepted)} قراءة أُضيفت لخريطة الخشونة. شكرًا لك!`; refresh().catch(() => {}); return;
      } catch (err) { $("#roughMsg").textContent = `تعذّر الإرسال (${err.message}) — نُزّل ملفًا بدلًا منه.`; }
    }
    // الموقع المجاني: ملف GeoJSON يمكن إرفاقه ببلاغ GitHub أو فتحه في أي برنامج خرائط
    const gj = { type: "FeatureCollection", features: rough.pts.map((p) => ({ type: "Feature", geometry: { type: "Point", coordinates: [p.lng, p.lat] }, properties: p })) };
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(gj)], { type: "application/geo+json" }));
    a.download = `darb-roughness-${new Date().toISOString().slice(0, 16).replace(":", "")}.geojson`; a.click();
    if (isStatic()) $("#roughMsg").innerHTML = `نُزّل ملف القياس. لإضافته للخريطة: <a href="https://github.com/${repo()}/issues/new?title=${encodeURIComponent("[خشونة] قياس من هاتف")}" target="_blank" rel="noopener">افتح بلاغًا على GitHub</a> وأرفق الملف.`;
  });

  // ---------- المساعد الهندسي ----------
  // محرك أسئلة عربي يعمل في المتصفح على بيانات الشبكة كلها (فيعمل في الموقع الثابت المجاني بلا أي مفتاح)،
  // ويستعين بـ Claude على الخادم إن كان مفعّلًا هناك (status.assistant_llm).
  const norm = (s) => String(s || "").replace(/[ً-ْـ]/g, "").replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي")
    .replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d)).replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d)).toLowerCase();
  const NUM_WORDS = { "واحد": 1, "اثنين": 2, "اثنان": 2, "ثلاث": 3, "ثلاثه": 3, "اربع": 4, "اربعه": 4, "خمس": 5, "خمسه": 5, "ست": 6, "سته": 6,
    "سبع": 7, "سبعه": 7, "ثمان": 8, "ثماني": 8, "ثمانيه": 8, "تسع": 9, "تسعه": 9, "عشر": 10, "عشره": 10, "عشرين": 20 };
  const REGION_ALIAS = { losangeles: ["لوس انجلس", "لوس انجليس", "la"], sandiego: ["سان دييجو", "سان دياغو"], singapore: ["سنغافورا"],
    phoenix: ["فينيكس", "فونكس"], tucson: ["توكسون", "تاكسون"], yuma: [], tampa: [], madrid: [] };
  const COUNTRY = { "اريزونا": ["phoenix", "tucson", "yuma"], "كاليفورنيا": ["losangeles", "sandiego"], "فلوريدا": ["tampa"], "اسبانيا": ["madrid"],
    "امريكا": ["phoenix", "tucson", "yuma", "tampa", "losangeles", "sandiego"], "الولايات المتحده": ["phoenix", "tucson", "yuma", "tampa", "losangeles", "sandiego"] };
  const GULF = ["الدوحه", "قطر", "دبي", "ابوظبي", "ابو ظبي", "الامارات", "الرياض", "جده", "السعوديه", "الدمام", "الكويت", "مسقط", "سلطنه عمان", "المنامه", "البحرين", "الشارقه", "الخليج"];
  const CUR_WORDS = [["درهم", "AED"], ["قطري", "QAR"], ["كويتي", "KWD"], ["بحريني", "BHD"], ["عماني", "OMR"], ["دولار", "USD"], ["يورو", "EUR"], ["ريال", "SAR"]];
  const STOP = new Set(["طريق", "شارع", "تقاطع", "عند", "جنوب", "شمال", "شرق", "غرب", "الطريق", "السريع", "قرب", "حاله", "وضع", "كيف", "ماذا", "عن", "في", "من", "الي", "على", "ما", "هي", "هو"]);
  const chat = { data: null, at: 0, busy: false };

  async function chatData() {
    if (chat.data && Date.now() - chat.at < 300000) return chat.data;
    const [cams, econ, summary] = await Promise.all([api("/api/cameras"), api("/api/economics").catch(() => null), api("/api/summary").catch(() => null)]);
    chat.data = { cams, econ: econ?.items || [], summary }; chat.at = Date.now();
    return chat.data;
  }
  function askCount(q) {
    const m = q.match(/(?:^|\s)(\d{1,2})(?!\s*(?:مليون|مليار|الف|ملي|مم|%|درجه|اسبوع|اسابيع|شهر|اشهر|شهور|يوم))(?=\s|$|[؟?،,])/);
    if (m) return Math.min(50, +m[1]);
    for (const w of q.split(/\s+/)) if (NUM_WORDS[w]) return NUM_WORDS[w];
    return null;
  }
  // المبالغ: «5 ملايين»، «2.5 مليون»، «خمسة ملايين»، «مليار»، «300 ألف»، «عشرة آلاف» (بعد التطبيع: الف/الاف)
  const MULT = [[/مليارات|مليار/, 1e9], [/ملايين|مليون/, 1e6], [/الاف|الف/, 1e3]];
  function askMoney(q) {
    if (!/ميزاني|مليون|ملايين|مليار|الف|الاف|ريال|درهم|دينار|دولار|يورو|اصرف|صرف/.test(q)) return null;
    let m = q.match(/(\d+(?:[.,]\d+)?)\s*(مليارات|مليار|ملايين|مليون|الاف|الف)?/);
    if (!m) {  // رقم بالكلمات قبل المضاعف، أو المضاعف وحده («بميزانية مليون»)
      const w = q.match(/(?:^|\s)([\u0600-\u06FF]+)?\s*(مليارات|مليار|ملايين|مليون|الاف|الف)/);
      if (!w) return null;
      m = [w[0], String(NUM_WORDS[w[1]] || 1), w[2]];
    }
    const mult = (MULT.find(([re]) => re.test(m[2] || "")) || [, 1])[1];
    const cur = (CUR_WORDS.find(([w]) => q.includes(w)) || [null, econ.cur])[1];
    return { amount: parseFloat(m[1].replace(",", ".")) * mult, cur };
  }
  function askRegions(q) {
    const hit = new Set();
    for (const r of state.regions) {
      const full = norm(r.name), city = full.replace(/\s*\(.*\)/, "");
      if (q.includes(city) || [...(REGION_ALIAS[r.key] || [])].some((a) => q.includes(norm(a)))) hit.add(r.key);
    }
    for (const [w, keys] of Object.entries(COUNTRY)) if (q.includes(w)) keys.forEach((k) => hit.add(k));
    return hit.size ? [...hit] : null;
  }
  const roadCodes = (s) => [...norm(s).matchAll(/\b([a-z]{1,3})\s?-?\s?(\d{1,3})\b/g)].map((m) => m[1] + m[2]);
  function askCamera(q, cams) {
    const words = q.split(/[\s،,؟?.]+/).filter((w) => w.length >= 3 && !STOP.has(w));
    const codes = roadCodes(q);
    let best = null, bestScore = 0, second = 0;
    const scored = [];
    for (const c of cams) {
      const hay = norm(`${c.name} ${c.road}`);
      // الكلمات اللاتينية (AYE، BKE، Congress…) أدق من العربية العامة فتُوزن أعلى
      let score = words.reduce((n, w) => n + (hay.includes(w) ? (/^[a-z]/.test(w) ? 1.5 : 1) : 0), 0);
      const cc = roadCodes(`${c.name} ${c.road}`);
      if (codes.some((k) => cc.includes(k))) score += 1.5;
      if (score > bestScore) { second = bestScore; best = c; bestScore = score; } else if (score > second) second = score;
      scored.push([c, score]);
    }
    // أكثر من مقطع على الطريق نفسه (مثل «BKE»): تُعاد كلها لتُعرض قائمةً
    if (bestScore >= 1.5 && bestScore === second) return scored.filter(([, sc]) => sc === bestScore).map(([c]) => c);
    // تطابق قوي، أو تطابق متوسط يخص مقطعًا واحدًا بوضوح (مثل «AYE»)
    return bestScore >= 2.5 || (bestScore >= 1.5 && bestScore > second) ? best : null;
  }
  const regionLabel = (k) => (state.regions.find((r) => r.key === k)?.name || k).replace(/\s*\(.*\)/, "");
  const camLink = (c) => `<a href="#" class="cam-link" data-cam="${esc(c.id)}">${esc(c.name)}</a> <span class="muted">(${esc(regionLabel(c.region))})</span>`;
  const ciOf = (c) => c.risk?.ci ?? c.last_snapshot?.condition_index;
  function camFacts(c) {
    const r = c.risk || {}, s = c.last_snapshot || {};
    return [ciOf(c) != null && `الحالة <b>${fmtN(ciOf(c))}</b>/100`, r.score != null && `الخطر ${fmtN(r.score)} (${LEVEL_AR[r.level]})`,
      r.weeks_to_threshold != null && `عتبة الصيانة ${weeksText(r.weeks_to_threshold)}`, s.pothole_count ? `حفر: <b>${fmtN(s.pothole_count)}</b>` : "",
      r.rutting >= 0.3 && `تخدد ${r.rutting >= 0.6 ? "مرتفع" : "متوسط"}`].filter(Boolean).join(" · ");
  }
  const list = (cams, fmt = camFacts) => `<ol class="chat-list">${cams.map((c) => `<li>${camLink(c)}<br><span class="muted">${fmt(c)}</span></li>`).join("")}</ol>`;

  function answer(raw, d) {
    const q = norm(raw);
    const regs = askRegions(q);
    const scope = (arr) => (regs ? arr.filter((c) => regs.includes(c.region)) : arr);
    const where = regs ? ` في ${regs.map(regionLabel).join(" و")}` : " في الشبكة";
    const cams = scope(d.cams), analysed = cams.filter((c) => c.risk);
    const n = askCount(q) || 5;
    if (/^(مرحبا|السلام|اهلا|هلا|صباح|مساء|شكرا)/.test(q.trim())) return /^شكرا/.test(q.trim()) ? "العفو! اسألني متى شئت عن أي طريق أو ميزانية." : "أهلًا بك! اسألني عن حالة أي طريق أو مدينة، أو خطر التخدد، أو أين تُصرف الميزانية. اختر سؤالًا من الأمثلة بالأسفل للبدء.";
    // كلمة كاملة (مع حروف الجر الملتصقة): «ريال قطري» ليس سؤالًا عن قطر
    const gulfCity = GULF.find((g) => new RegExp(`(^|[\\s،,؟?])(?:في|ب|ل|و|ال)?${norm(g)}(?=$|[\\s،,؟?.])`).test(q));
    if (gulfCity && !regs) return `لا تنشر <b>${esc(raw.match(new RegExp(gulfCity.replace(/ه$/, "."), "i"))?.[0] || "هذه المدينة")}</b> صور كاميرات مرورها للعامة بعد، فلا توجد لدينا بيانات عنها. النظام جاهز لإضافتها فور الحصول على صلاحية الوصول للكاميرات (يكفي ملف إعداد للمدينة) — والمدن الحالية الأقرب لمناخ الخليج: يوما وفينكس (صحراوي حار) وتامبا (ساحلي رطب).`;
    const money = askMoney(q);
    if (money && /ميزاني|اصرف|صرف|وزع|خطه/.test(q) || (money && money.amount >= 1000)) {
      const rate = state.econ?.currencies?.[money.cur]?.rate || 1, curName = state.econ?.currencies?.[money.cur]?.name || "";
      const items = scope(d.econ.map((e) => ({ ...e, region: e.region })));
      const p = econPlan(items, money.amount / rate);
      if (!items.length) return "لا توجد بيانات اقتصادية بعد لهذا النطاق.";
      return `بميزانية <b>${fmtN(money.amount)} ${esc(curName)}</b>${where}: تُموَّل <b>${fmtN(p.sel.length)}</b> من ${fmtN(p.sel.length + p.skip.length)} مقطعًا
        (${fmtN(p.sel.filter((x) => x.must_do).length)} إلزامية للسلامة)، والمصروف ${money_(p.spent, money.cur)}، والكلفة المتجنَّبة ${money_(p.benefit, money.cur)} (عائد ×${fmtN(p.roi, 1)}).
        ${p.sel.length ? `<br>أولويات الخطة:<ol class="chat-list">${p.sel.slice(0, 8).map((x) => `<li><a href="#" class="cam-link" data-cam="${esc(x.camera_id)}">${esc(x.name)}</a>: ${esc(x.treatment_now.name)} · ${money_(x.cost_now, money.cur)}${x.must_do ? " · <b>إلزامي</b>" : ""}</li>`).join("")}</ol>` : ""}
        ${p.skip.length ? `تأجيل الباقي سنة يرفع كلفته بنحو <b>${money_(p.penalty, money.cur)}</b>.` : "الميزانية تغطي الاحتياج كله."} <a href="#" data-goto="budget">افتح صفحة الميزانية</a>`;
    }
    const cam = askCamera(q, regs ? cams : d.cams);
    if (Array.isArray(cam) && !/اسوا|اخطر|افضل|اكثر|ترتيب|قائمه/.test(q))
      return `${fmtN(cam.length)} مقاطع تطابق سؤالك:${list(cam.slice(0, 10), (c) => camFacts(c) || "لم يُحلَّل بعد — بانتظار أول التقاط نهاري")}اضغط اسم المقطع لتفاصيله.`;
    if (cam && !Array.isArray(cam) && !/اسوا|اخطر|افضل|اكثر|ترتيب|قائمه/.test(q)) {
      const e = d.econ.find((x) => x.camera_id === cam.id);
      return `${camLink(cam)}<br>${camFacts(cam) || "لم يُحلَّل بعد — بانتظار أول التقاط نهاري."}
        ${cam.risk?.pavement_t ? `<br>حرارة الرصف (أعلى 7 أيام) ${fmtN(cam.risk.pavement_t)}°م${cam.risk.pg_deficit ? ` · الرابط أقل من المطلوب بـ${fmtN(cam.risk.pg_deficit)} درجة` : ""}.` : ""}
        ${cam.risk?.top_factor ? `<br>العامل الأبرز: ${esc(cam.risk.top_factor)}.` : ""}
        ${e ? `<br>المعالجة الآن: <b>${esc(e.treatment_now.name)}</b> (${money_(e.cost_now)})، وإن أُجّلت سنة: ${esc(e.treatment_later.name)} (${money_(e.cost_later)}).` : ""}`;
    }
    if (/سيل|سيول|مطر|امطار|عاصف|رياح|غبار/.test(q)) {
      const ev = (d.summary?.gulf?.events || []).filter((e) => !regs || regs.includes(e.region));
      return ev.length ? `أحداث الطقس المتطرفة في الأيام الثلاثة الأخيرة:<ol class="chat-list">${ev.map((e) => `<li><b>${esc(regionLabel(e.region))} · ${esc(e.date)}</b>: ${esc(e.text)}</li>`).join("")}</ol>`
        : `لا سيول ولا عواصف${where} في الأيام الثلاثة الأخيرة (حسب بيانات Open-Meteo). أعيد الفحص بعد أي أمطار تتجاوز 20 مم يوميًا في المناطق الجافة أو رياح فوق 60 كم/س.`;
    }
    if (/رمل|رمال/.test(q)) {
      const s = analysed.filter((c) => (c.risk.sand || 0) > 0.05).sort((a, b) => b.risk.sand - a.risk.sand).slice(0, n);
      return s.length ? `مقاطع رُصدت عليها رمال${where}:${list(s, (c) => `الغطاء الرملي ~${fmtN(c.risk.sand * 25, 0)}% من السطح`)}` : `لم تُرصد رمال على سطح الطرق${where} في آخر اللقطات.`;
    }
    if (/تخدد|حراره|حرار|ساخن|رابط|pg|بيتومين/.test(q)) {
      const s = analysed.filter((c) => c.risk.rutting != null).sort((a, b) => b.risk.rutting - a.risk.rutting).slice(0, n);
      if (!s.length) return "لم تُحسب فيزياء الرصف بعد لهذه المقاطع.";
      const calm = s[0].risk.rutting < 0.3 ? `لا يوجد خطر تخدد مرتفع${where} حاليًا (حرارة الرصف معتدلة هذا الموسم). الأعلى نسبيًا:` : "";
      return calm ? `${calm}${list(s.slice(0, 3), (c) => `خطر التخدد ${fmtN(c.risk.rutting * 100)}/100 · حرارة الرصف ${fmtN(c.risk.pavement_t)}°م`)}` : `أعلى المقاطع خطر تخدد${where} (حرارة الرصف × الشاحنات × درجة الرابط):${list(s, (c) => `خطر التخدد ${fmtN(c.risk.rutting * 100)}/100 · حرارة الرصف ${fmtN(c.risk.pavement_t)}°م${c.risk.pg_deficit ? ` · الرابط ناقص ${fmtN(c.risk.pg_deficit)} درجة` : ""}`)}`;
    }
    if (/حفر|حفره/.test(q)) {
      const s = cams.filter((c) => c.last_snapshot?.pothole_count > 0).sort((a, b) => b.last_snapshot.pothole_count - a.last_snapshot.pothole_count);
      return s.length ? `مقاطع فيها حفر${where} (${fmtN(s.length)}):${list(s.slice(0, n))}يوصى بردمها خلال 48 ساعة.` : `لا حفر مكتشفة${where} في آخر اللقطات.`;
    }
    if (/تنبيه|تنبيهات|انذار/.test(q)) {
      const s = cams.filter((c) => c.open_alerts > 0).sort((a, b) => b.open_alerts - a.open_alerts);
      return s.length ? `مقاطع عليها تنبيهات مفتوحة${where}:${list(s.slice(0, n), (c) => `${fmtN(c.open_alerts)} تنبيه · ${camFacts(c)}`)}<a href="#" data-goto="alerts">كل التنبيهات</a>` : `لا تنبيهات مفتوحة${where}.`;
    }
    if (/كلف|تكلف|سعر|يكلف|ميزاني/.test(q)) {
      const it = scope(d.econ).filter((x) => x.treatment_now.key !== "routine" || x.must_do);
      const now = it.reduce((a, x) => a + x.cost_now, 0), later = it.reduce((a, x) => a + x.cost_later, 0);
      return it.length ? `كلفة معالجة ${fmtN(it.length)} مقطعًا تحتاج تدخلًا${where}: <b>${money_(now)}</b> الآن، مقابل <b>${money_(later)}</b> إن أُجّلت سنة (زيادة ${money_(later - now)}). <a href="#" data-goto="budget">وزّع ميزانية</a>` : `لا مقاطع تحتاج معالجة مدفوعة${where} حاليًا.`;
    }
    const wk = q.match(/خلال\s+(\d+)\s*(اسبوع|اسابيع|شهر|اشهر|شهور)/);
    if (wk || /قبل الصيف|الصيف القادم/.test(q)) {
      let weeks;
      if (wk) weeks = +wk[1] * (/شهر|اشهر|شهور/.test(wk[2]) ? 4.35 : 1);
      else { const now = new Date(), june = new Date(now.getFullYear() + (now.getMonth() >= 5 ? 1 : 0), 5, 1); weeks = (june - now) / 6048e5; }
      const s = analysed.filter((c) => c.risk.weeks_to_threshold != null && c.risk.weeks_to_threshold <= weeks).sort((a, b) => a.risk.weeks_to_threshold - b.risk.weeks_to_threshold);
      return s.length ? `مقاطع يُتوقع أن تبلغ عتبة الصيانة خلال ~${fmtN(weeks)} أسبوع${where} (${fmtN(s.length)}):${list(s.slice(0, n))}`
        : `لا يُتوقع أن يبلغ أي مقطع عتبة الصيانة خلال ~${fmtN(weeks)} أسبوع${where} بالمعدلات الحالية.`;
    }
    if (/افضل|احسن|اجود|سليم/.test(q)) {
      const s = analysed.slice().sort((a, b) => (ciOf(b) ?? 0) - (ciOf(a) ?? 0)).slice(0, n);
      return s.length ? `أفضل ${fmtN(s.length)} مقاطع حالةً${where}:${list(s)}` : "لا مقاطع محلَّلة بعد.";
    }
    if (/اسوا|اخطر|خطر|اولوي|صيانه|تدخل|متدهور|سيئ/.test(q)) {
      const byCi = /اسوا|سيئ|متدهور/.test(q) && !/خطر/.test(q);
      const s = analysed.slice().sort((a, b) => byCi ? (ciOf(a) ?? 100) - (ciOf(b) ?? 100) : (b.risk.priority ?? 0) - (a.risk.priority ?? 0)).slice(0, n);
      return s.length ? `${byCi ? "أسوأ" : "أعلى"} ${fmtN(s.length)} مقاطع ${byCi ? "حالةً" : "أولويةً (الخطر × الأهمية المرورية)"}${where}:${list(s)}` : `لا مقاطع محلَّلة بعد${where} — بانتظار أول التقاط نهاري.`;
    }
    if (/كم|عدد|ملخص|احصا|نظره|حاله الشبكه|الوضع/.test(q)) {
      const lv = { low: 0, medium: 0, high: 0, critical: 0 }; analysed.forEach((c) => lv[c.risk.level]++);
      const cis = analysed.map(ciOf).filter((v) => v != null);
      return `${where.trim()}: <b>${fmtN(cams.length)}</b> كاميرا (${fmtN(analysed.length)} محلَّلة)، متوسط الحالة <b>${fmtN(cis.reduce((a, b) => a + b, 0) / (cis.length || 1), 1)}</b>/100.
        مستويات الخطر: ${fmtN(lv.critical)} حرج · ${fmtN(lv.high)} مرتفع · ${fmtN(lv.medium)} متوسط · ${fmtN(lv.low)} منخفض.
        ${regs ? "" : `<br>${state.regions.map((r) => `${esc(regionLabel(r.key))} ${fmtN(d.cams.filter((c) => c.region === r.key).length)}`).join(" · ")}`}`;
    }
    return null;
  }
  const money_ = (usd, cur) => money(usd, cur);
  const SUGGEST = ["ما أسوأ 5 طرق في الشبكة؟", "أين خطر التخدد مرتفع؟", "بميزانية 5 ملايين ريال أين أصرف؟", "ما الطرق التي تحتاج صيانة قبل الصيف؟",
    "هل توجد حفر في فينكس؟", "كم تكلفة معالجة طرق مدريد؟", "هل حدثت سيول أو عواصف؟", "ما حالة الشبكة في كاليفورنيا؟"];
  function chatPush(who, html) {
    const log = $("#chatLog");
    log.insertAdjacentHTML("beforeend", `<div class="msg ${who}"><div class="bubble">${html}</div></div>`);
    // بداية الإجابة الطويلة تبقى ظاهرة (لا نقفز إلى آخرها)
    const last = log.lastElementChild;
    log.scrollTop = who.startsWith("bot") && last.offsetHeight > log.clientHeight ? last.offsetTop - log.offsetTop - 8 : log.scrollHeight;
  }
  async function chatAsk(q) {
    q = q.trim(); if (!q || chat.busy) return;
    chat.busy = true; chatPush("me", esc(q)); $("#chatQ").value = "";
    chatPush("bot typing", "<span></span><span></span><span></span>");
    let html = null;
    try {
      const d = await chatData();
      if (state.status?.assistant_llm) {  // وضع الخادم: Claude يجيب من البيانات نفسها
        const r = await api("/api/ask", { method: "POST", body: JSON.stringify({ q }) }).catch(() => null);
        if (r?.ok) html = esc(r.answer).replace(/\n/g, "<br>") + `<div class="via">${svg("sparkle")}Claude</div>`;
      }
      html = html || answer(q, d) || `لم أفهم السؤال تمامًا. جرّب مثلًا: «ما أسوأ 5 طرق في فينكس؟» أو «أين خطر التخدد مرتفع؟» أو «بميزانية 10 ملايين درهم أين أصرف؟» أو اكتب اسم طريق مثل «I-405».`;
    } catch { html = "تعذّر تحميل البيانات الآن، حاول مجددًا."; }
    $("#chatLog .typing")?.remove();
    chatPush("bot", html); chat.busy = false;
    if (innerWidth < 720) $("#chatForm").scrollIntoView({ block: "end", behavior: "smooth" });  // الجوال: الإجابة فوق، وحقل السؤال ظاهر
  }
  $("#chatForm").addEventListener("submit", (e) => { e.preventDefault(); chatAsk($("#chatQ").value); });
  $("#chatSugg").innerHTML = SUGGEST.map((s) => `<button type="button" class="chip-btn">${esc(s)}</button>`).join("");
  $("#chatSugg").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) chatAsk(b.textContent); });
  $("#chatLog").addEventListener("click", (e) => { if (e.target.closest("a[href='#']")) e.preventDefault(); });
  chatPush("bot", `مرحبًا، أنا مساعد دَرْب. اسألني بالعربية عن حالة أي طريق أو مدينة، أو خطر التخدد وحرارة الرصف، أو أين تُصرف ميزانية الصيانة.`);
  // سؤال صوتي بالعربية (Web Speech API: كروم وسفاري وإيدج)
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SR) {
    const mic = $("#chatMic"); mic.hidden = false;
    let rec = null;
    mic.addEventListener("click", () => {
      if (rec) { rec.stop(); return; }
      rec = new SR(); rec.lang = "ar-SA"; rec.interimResults = true;
      mic.classList.add("on");
      rec.onresult = (e) => { const t = [...e.results].map((r) => r[0].transcript).join(""); $("#chatQ").value = t; if (e.results[e.results.length - 1].isFinal) chatAsk(t); };
      rec.onend = rec.onerror = () => { mic.classList.remove("on"); rec = null; };
      rec.start();
    });
  }
  // الجوال: تلميح أقصر يتسع للحقل (الطويل يُقص)
  const chatHint = () => { $("#chatQ").placeholder = innerWidth < 600 ? "اكتب سؤالك هنا…" : "مثال: ما أسوأ 5 طرق في لوس أنجلوس؟"; };
  chatHint(); addEventListener("resize", chatHint);
  const setChatMode = () => { $("#chatMode").textContent = state.status?.assistant_llm ? "مدعوم بـ Claude على الخادم، مع محرك عربي مدمج احتياطيًا." : "يعمل محليًا في متصفحك على بيانات الشبكة كلها، دون إرسال أسئلتك لأي جهة."; };

  // ---------- الميزانية والقرار الاقتصادي ----------
  // الخطة تُحسب في المتصفح (تعمل في الموقع الثابت): الإلزامي للسلامة أولًا ثم الأعلى عائدًا لكل وحدة نقدية
  const econ = { cur: safeGet("darb-cur") || "SAR", budget: null };
  const money = (usd, cur = econ.cur) => {
    const c = state.econ?.currencies?.[cur] || { rate: 1, name: "دولار" }, v = usd * c.rate;
    const t = Math.abs(v) >= 1e6 ? `${fmtN(v / 1e6, 1)} مليون` : Math.abs(v) >= 1e4 ? `${fmtN(v / 1e3, 0)} ألف` : fmtN(v);
    return `${t} ${c.name}`;
  };
  function econPlan(items, budget) {
    const order = items.filter((x) => x.treatment_now.key !== "routine" || x.must_do)
      .sort((a, b) => (b.must_do - a.must_do) || (b.ratio - a.ratio) || ((b.risk_score || 0) - (a.risk_score || 0)));
    const sel = [], skip = []; let left = budget;
    for (const x of order) (x.cost_now <= left ? (sel.push(x), left -= x.cost_now) : skip.push(x));
    const spent = budget - left, benefit = sel.reduce((n, x) => n + x.benefit, 0);
    return { sel, skip, spent, left, benefit, roi: spent ? benefit / spent : 0, penalty: skip.reduce((n, x) => n + x.cost_later - x.cost_now, 0) };
  }
  function renderBudget() {
    const e = state.econ; if (!e || !$("#budgetIn")) return;
    const sel = $("#curSel");
    if (!sel.options.length) sel.innerHTML = Object.entries(e.currencies).map(([k, v]) => `<option value="${k}">${esc(v.name)}</option>`).join("");
    sel.value = econ.cur;
    const rate = e.currencies[econ.cur]?.rate || 1;
    const need = e.items.filter((x) => x.treatment_now.key !== "routine" || x.must_do).reduce((n, x) => n + x.cost_now, 0);
    if (econ.budget == null) econ.budget = Math.round(need * 0.4);
    const r = $("#budgetRange"); r.max = Math.max(1, Math.round(need * 1.2 * rate)); r.value = Math.round(econ.budget * rate);
    if (document.activeElement !== $("#budgetIn")) $("#budgetIn").value = Math.round(econ.budget * rate);
    $("#budgetNeed").textContent = `الاحتياج الكامل للشبكة الآن: ${money(need)} · لو أُجّل كله سنة: ${money(e.items.filter((x) => x.treatment_now.key !== "routine" || x.must_do).reduce((n, x) => n + x.cost_later, 0))}`;
    $("#budgetPresets").innerHTML = [0.25, 0.5, 1].map((f) => `<button type="button" class="chip-btn" data-bud="${Math.round(need * f)}">${f === 1 ? "الاحتياج كاملًا" : `${f * 100}% من الاحتياج`}</button>`).join("");
    const p = econPlan(e.items, econ.budget);
    $("#budgetKpis").innerHTML = [
      kpi("مقاطع ممولة", `${fmtN(p.sel.length)} / ${fmtN(p.sel.length + p.skip.length)}`, `${fmtN(p.sel.filter((x) => x.must_do).length)} إلزامية للسلامة`, false, "check", "ok"),
      kpi("المصروف", money(p.spent), `المتبقي ${money(p.left)}`, false, "coins"),
      kpi("الكلفة المتجنَّبة", money(p.benefit), "وفر التأجيل + كلفة المستخدمين السنوية", false, "trend", "ok"),
      kpi("العائد لكل وحدة نقدية", `×${fmtN(p.roi, 1)}`, "كل وحدة نقدية تُصرف الآن توفّر هذا القدر", false, "gauge", "warn"),
      kpi("كلفة الانتظار", money(p.penalty), "زيادة كلفة المقاطع غير الممولة بعد سنة", p.penalty > 0, "clock"),
    ].join("");
    const row = (x, i) => `<tr data-cam="${esc(x.camera_id)}"><td><span class="rank">${fmtN(i + 1)}</span></td>
      <td class="name"><b>${esc(x.name)}</b><span>${x.must_do ? '<em class="must">إلزامي للسلامة</em> · ' : ""}الحالة ${fmtN(x.ci)} · ${fmtN(x.area_m2)} م²</span></td>
      <td><b>${esc(x.treatment_now.name)}</b><span class="muted sub">${esc(x.treatment_now.desc)}</span></td>
      <td class="num"><b>${money(x.cost_now)}</b></td>
      <td><span class="muted">${esc(x.treatment_later.name)}</span><br><span class="num">${money(x.cost_later)}</span></td>
      <td class="num good">${money(x.deferral_saving)}</td><td class="num"><b>×${fmtN(x.ratio, 1)}</b></td></tr>`;
    $("#planBody").innerHTML = p.sel.map(row).join("") || `<tr><td colspan="7" class="empty">الميزانية لا تكفي أي معالجة — ارفعها أو اختر إحدى النسب أعلاه</td></tr>`;
    $("#unfundedBody").innerHTML = p.skip.map((x) => `<tr data-cam="${esc(x.camera_id)}"><td class="name"><b>${esc(x.name)}</b><span>${esc(x.road)}</span></td>
      <td class="num">${fmtN(x.ci)} ← <b class="${x.ci_in_12m < x.ci - 5 ? "bad" : ""}">${fmtN(x.ci_in_12m)}</b></td>
      <td>${esc(x.treatment_now.name)} · ${money(x.cost_now)}</td><td>${esc(x.treatment_later.name)} · ${money(x.cost_later)}</td>
      <td class="num bad">+${money(x.cost_later - x.cost_now)}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">كل المقاطع ممولة</td></tr>`;
  }
  const setBudget = (localVal) => { econ.budget = Math.max(0, +localVal || 0) / (state.econ?.currencies?.[econ.cur]?.rate || 1); renderBudget(); };
  $("#budgetIn").addEventListener("input", (e) => setBudget(e.target.value));
  $("#budgetRange").addEventListener("input", (e) => { $("#budgetIn").value = e.target.value; setBudget(e.target.value); });
  $("#curSel").addEventListener("change", (e) => { econ.cur = e.target.value; safeSet("darb-cur", econ.cur); renderBudget(); });
  $("#budgetPresets").addEventListener("click", (e) => { const b = e.target.closest("[data-bud]"); if (b) { econ.budget = +b.dataset.bud; renderBudget(); } });
  function econCard(id) {
    const x = state.econ?.items.find((i) => i.camera_id === id); if (!x) return "";
    return `<div class="card mt">
      <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("coins")}</span>القرار الاقتصادي لهذا المقطع</h2><span class="muted">${fmtN(x.area_m2)} م² · ${fmtN(x.lanes)} مسارات</span></div>
      <div class="econ-cmp">
        <div class="ec now"><span class="muted">التدخل الآن</span><b>${esc(x.treatment_now.name)}</b><span>${esc(x.treatment_now.desc)}</span><strong>${money(x.cost_now)}</strong></div>
        <div class="ec-arrow">${svg("next")}</div>
        <div class="ec later"><span class="muted">إن أُجّل سنة (الحالة ${fmtN(x.ci)} ← ${fmtN(x.ci_in_12m)})</span><b>${esc(x.treatment_later.name)}</b><span>${esc(x.treatment_later.desc)}</span><strong>${money(x.cost_later)}</strong></div>
      </div>
      <p class="econ-verdict">${x.deferral_saving > 0 ? `التدخل الآن يوفّر <b>${money(x.deferral_saving)}</b>${x.user_cost_year ? ` + نحو <b>${money(x.user_cost_year)}</b> سنويًا على مستخدمي الطريق` : ""}.` : "لا وفر يُذكر من التدخل المبكر — الحالة مستقرة، والمراقبة تكفي حاليًا."}</p>
    </div>`;
  }

  // فيزياء الطريق الخليجية: حرارة الرصف ودرجة الرابط وخطر التخدد والرمال والأحداث المتطرفة
  const RUT_AR = { low: "منخفض", medium: "متوسط", high: "مرتفع" };
  function gulfCard(g, m) {
    if (!g) return "";
    const pos = (t) => Math.min(100, Math.max(0, ((t - 20) / 65) * 100));  // مقياس 20–85°م
    const rutLvl = { low: "low", medium: "medium", high: "critical" }[g.rutting_level] || "low";
    return `<div class="card mt gulf">
      <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("sun")}</span>فيزياء الطريق الخليجية</h2>
        <span class="muted">حرارة الرصف (نموذج SHRP + الإشعاع الشمسي) · ${g.source === "open-meteo" ? "طقس فعلي" : "متوسطات مناخية"}</span></div>
      <div class="thermo">
        <div class="thermo-bar"><i class="now" style="inset-inline-start:${pos(g.pavement_t7max)}%" title="أعلى 7 أيام"></i>
          <b class="pg" style="inset-inline-start:${pos(g.binder_pg)}%">PG ${g.binder_pg}<small>الرابط الحالي</small></b>
          <b class="pg need" style="inset-inline-start:${pos(g.pg_design)}%">PG ${g.pg_design}<small>المطلوب للمناخ</small></b></div>
        <div class="thermo-scale"><span>20°</span><span>40°</span><span>60°</span><span>80°م</span></div>
      </div>
      <div class="facts g4">
        <div class="fact"><div class="l">حرارة الرصف (متوسط أعلى 7 أيام)</div><div class="v">${fmtN(g.pavement_t7max, 1)}°م</div></div>
        <div class="fact"><div class="l">أقصى حرارة متوقعة (7 أيام)</div><div class="v">${fmtN(g.pavement_ahead_max, 1)}°م</div></div>
        <div class="fact"><div class="l">درجات-أيام التليّن (فوق 50°م، 30 يومًا)</div><div class="v">${fmtN(g.rut_degree_days)}</div></div>
        <div class="fact"><div class="l">الشاحنات يوميًا (تقدير)</div><div class="v">${fmtN(g.trucks_per_day)}</div></div>
      </div>
      <div class="gulf-row">
        <div class="gulf-risk"><span class="muted">خطر التخدد</span>
          <div class="meter"><div class="bar"><i style="width:${g.rutting_risk * 100}%;background:${color(rutLvl)}"></i></div>
          <span class="pill ${rutLvl}">${RUT_AR[g.rutting_level]} · ${fmtN(g.rutting_risk * 100)}</span></div></div>
        <div class="gulf-risk"><span class="muted">رمال على السطح</span><b>${fmtN((m.sand_cover || 0) * 100, 1)}%</b></div>
        <div class="gulf-risk"><span class="muted">نقص درجة الرابط</span><b>${g.pg_deficit_grades ? `${fmtN(g.pg_deficit_grades)} درجة` : "لا يوجد"}</b></div>
      </div>
      ${g.events?.length ? `<ul class="events">${g.events.map((e) => `<li class="${esc(e.kind)}">${esc(e.date)} · ${esc(e.text)}</li>`).join("")}</ul>` : ""}
    </div>`;
  }

  function renderDetail(d) {
    const rd = d.risk_detail, fc = rd?.forecast || {}, m = d.latest_metrics || {};
    const snaps = d.snapshots.filter((s) => s.quality === "ok").slice().reverse();
    const lvl = rd?.level || "low";
    $("#dBody").innerHTML = `
      ${d.live ? `<div class="card live-card">
        <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("live")}</span>البث المباشر من الكاميرا</h2></div>
        ${liveFrameHTML(d)}
        <p class="muted live-hint">${d.live.kind === "hls" ? `بث فيديو متصل لحظيًا من ${esc(srcLabel(d.source_type))}.` : `الصورة تأتي مباشرة من ${esc(srcLabel(d.source_type))} وتتحدّث تلقائيًا كل ${fmtN(d.live.refresh)} ثانية تقريبًا (المصدر لا ينشر فيديو متصلًا).`} قد تظهر ليلية حسب التوقيت المحلي للمنطقة.</p></div>` : ""}
      <div class="d-grid">
        <div class="card viewer">
          <div class="card-h"><h2 class="t"><span class="ico-sm">${svg("image")}</span>لقطات الكاميرا عبر الزمن</h2><label class="switch"><input type="checkbox" id="vAnn" checked> العيوب</label></div>
          <div class="zoomable" id="vZoom" role="button" tabindex="0" aria-label="تكبير اللقطة ومعاينتها"><img id="vImg" alt="لقطة الطريق">
            <span class="zoom-hint">${svg("zoomin")}اضغط للتكبير</span></div>
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
      ${gulfCard(fc.gulf, m)}
      ${econCard(d.id)}
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
    const zoom = () => openLightbox(d, snaps, +range.value, ann.checked, (i, a) => { range.value = i; ann.checked = !!a; show(); });
    $("#vZoom").addEventListener("click", zoom);
    $("#vZoom").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); zoom(); } });

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
      state.status = s;
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
        `الالتقاط: يوميًا بين 9 و12 صباحًا محليًا (5 إطارات)، والتأكيد بعد ساعة`,
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
    const [summary, cams, issues, econ] = await Promise.all([api(rq("/api/summary")), api(rq("/api/cameras")), api(rq("/api/issues")),
      api(rq("/api/economics")).catch(() => null)]);
    state.summary = summary; state.cameras = cams; state.issues = issues; state.econ = econ;
    [state.reports, state.rough] = await Promise.all([api(rq("/api/reports")).catch(() => []), api(rq("/api/roughness")).catch(() => [])]);
    renderReports();
    renderBudget();
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
    // بطاقة لكل مدينة: الاسم بخط واضح، وتحته البلد وعدد الكاميرات، ونقطة بلون المناخ
    const total = state.regions.reduce((n, r) => n + (r.cameras || 0), 0);
    const all = [{ key: "", name: "كل المناطق", climate: "", kind: "all", cameras: total }, ...state.regions];
    bar.innerHTML = all.map((r) => {
      const m = /^(.*?)\s*\((.*)\)\s*$/.exec(r.name), city = m ? m[1] : r.name, country = m ? m[2] : (r.key ? "" : "عرض الكل");
      return `<button data-region="${esc(r.key)}" class="${r.key === state.region ? "active" : ""}" title="${esc(r.climate || "")}">
        <i class="k ${esc(r.kind || "")}"></i><span><b>${esc(city)}</b><small>${[country, r.cameras ? `${fmtN(r.cameras)} كاميرا` : ""].filter(Boolean).map(esc).join(" · ")}</small></span></button>`;
    }).join("");
    bar.hidden = state.regions.length < 2;
    // على الجوال تمرّ البطاقات أفقيًا: أظهر المنطقة المختارة
    bar.querySelector(".active")?.scrollIntoView({ block: "nearest", inline: "center" });
    const active = state.regions.filter((r) => !state.region || r.key === state.region);
    // «كل المناطق» باختصار بدل سرد أسماء المدن الثماني (كانت تملأ أربعة أسطر على الجوال)
    $("#regionName").textContent = state.region ? active.map((r) => r.name).join(" · ") : `كل المناطق · ${fmtN(state.regions.length)} مدن في ${fmtN(new Set(state.regions.map((r) => (r.name.match(/\((.*)\)/) || [, r.name])[1])).size)} دول وولايات`;
    const foot = $("#attribution");
    const attr = [...new Set(active.map((r) => r.attribution).filter(Boolean))];  // مدن أريزونا الثلاث مصدرها واحد
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
