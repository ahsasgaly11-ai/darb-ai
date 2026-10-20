/* مختبر نماذج الطرق: تحليل لحظي بالكاميرا لنماذج مجسّمة (فلين/خشب) — سليم، متشقق، متضرر بالحفر.
 *
 * محرّكان يعملان في المتصفح دون خادم:
 * 1. كاشف بصري مصمَّم للنماذج المجسّمة (أساسي): يقارن عتمة كل بكسل بمحيطه (متوسط محلي بصورة تكاملية)،
 *    يستبعد علامات الطريق الفاتحة والملونة، ثم يصنّف المكوّنات المتصلة بالشكل:
 *    خط رفيع = تشقق (طولي/عرضي)، شبكة كثيفة = تشقق تمساحي، كتلة ممتلئة = حفرة.
 *    لماذا؟ نماذج YOLO العالمية دُرّبت على صور إسفلت حقيقي من كاميرات السيارات، وعلى النماذج المرسومة
 *    تفوتها أغلب العيوب (جُرّب ذلك على صور تحاكي النماذج) — فالكاشف البصري مع المعايرة أدق هنا.
 * 2. نموذج YOLO المدرّب على RDD2022 (تأكيد): يعمل كل ~1.5 ث عبر onnxruntime-web، وتظهر مربعاته متقطعة.
 *
 * المعايرة: وجّه الكاميرا للنموذج السليم واضغط «معايرة» فتُضبط العتبة على ملمس الفلين والإضاءة الحالية.
 */
(() => {
  const D = window.DARB; if (!D) return;
  const { $, fmtN, esc, svg, money } = D;
  const PW = +(new URLSearchParams(location.search).get("pw") || 640);  // عرض المعالجة: 640 يلتقط خطوط التشقق الرفيعة (قلم 2–4 مم على نموذج بعرض متر)
  const ZONE = { x: 0.06, y: 0.1, w: 0.88, h: 0.8 };  // منطقة التحليل: ضع النموذج داخل الإطار
  const KIND = { healthy: ["سليم", "low"], cracked: ["تشققات", "medium"], damaged: ["متضرر وحفر", "critical"] };
  const TYPES = { long: "تشقق طولي", trans: "تشقق عرضي", alli: "تشقق تمساحي", pot: "حفرة" };
  const lab = { stream: null, raf: 0, busy: false, last: 0, frames: [], T: +(D.safeGet("darb-lab-T") || 26), ai: null, aiDets: [], aiBusy: false,
    aiAt: 0, aiOn: true, fps: 0, slots: [null, null, null], cur: null, img: null };
  const cv = document.createElement("canvas"), cx = cv.getContext("2d", { willReadFrequently: true });

  // ---------- الكاشف البصري ----------
  function analyze(src, sw, sh) {
    const W = PW, H = Math.round(PW * sh / sw);
    cv.width = W; cv.height = H; cx.drawImage(src, 0, 0, W, H);
    const px = cx.getImageData(0, 0, W, H).data, N = W * H;
    const G = new Uint8Array(N), S = new Uint8Array(N);
    for (let i = 0, j = 0; i < N; i++, j += 4) {
      const r = px[j], g = px[j + 1], b = px[j + 2], mx = Math.max(r, g, b), mn = Math.min(r, g, b);
      G[i] = (r * 77 + g * 150 + b * 29) >> 8; S[i] = mx ? ((mx - mn) * 255 / mx) | 0 : 0;
    }
    const zx0 = Math.round(W * ZONE.x), zy0 = Math.round(H * ZONE.y), zx1 = Math.round(W * (ZONE.x + ZONE.w)), zy1 = Math.round(H * (ZONE.y + ZONE.h));
    const zw = zx1 - zx0, zh = zy1 - zy0, zA = zw * zh;
    // سطح الطريق = ما حول وسيط سطوع المنطقة؛ الأفتح بوضوح (الطاولة، العلامات البيضاء والصفراء) لا يدخل المتوسط ولا التحليل
    const hist = new Uint32Array(256); for (let y = zy0; y < zy1; y += 2) for (let x = zx0; x < zx1; x += 2) hist[G[y * W + x]]++;
    let acc = 0, med = 0; const half = (zw * zh) / 8; for (; med < 255 && acc + hist[med] < half; med++) acc += hist[med];
    const M = new Uint8Array(N);
    for (let i = 0; i < N; i++) M[i] = G[i] <= med + 32 && !(S[i] > 110 && G[i] > 80) ? 1 : 0;
    // متوسط محلي مقنَّع (صندوق نصف قطره 5% من العرض) بصورتين تكامليتين: مجموع السطوع وعدد بكسلات السطح
    const W1 = W + 1, I = new Float64Array(W1 * (H + 1)), C = new Float64Array(W1 * (H + 1));
    for (let y = 0; y < H; y++) { let row = 0, cnt = 0; for (let x = 0; x < W; x++) { const i = y * W + x; row += M[i] * G[i]; cnt += M[i]; I[(y + 1) * W1 + x + 1] = I[y * W1 + x + 1] + row; C[(y + 1) * W1 + x + 1] = C[y * W1 + x + 1] + cnt; } }
    const R = Math.max(8, Math.round(W * 0.05)), box = (T, a, b, c, d) => T[d * W1 + c] - T[b * W1 + c] - T[d * W1 + a] + T[b * W1 + a];
    const dark = new Uint8Array(N), diffs = [];
    for (let y = zy0; y < zy1; y++) for (let x = zx0; x < zx1; x++) {
      const i = y * W + x; if (!M[i]) continue;               // ليس سطح طريق
      const a = Math.max(0, x - R), b = Math.max(0, y - R), c = Math.min(W, x + R + 1), d = Math.min(H, y + R + 1);
      const n = box(C, a, b, c, d); if (n < 20) continue;
      const B = box(I, a, b, c, d) / n, g = G[i];
      const df = B - g;
      if ((x & 3) === 0 && (y & 3) === 0) diffs.push(df);
      if (df > lab.T && g < B * 0.84) dark[i] = 1;
    }
    // مكوّنات متصلة (8 جيران)
    const lbl = new Int32Array(N), comps = [], stack = new Int32Array(N);
    const minA = Math.max(10, zA * 0.00008);
    for (let s = 0; s < N; s++) {
      if (!dark[s] || lbl[s]) continue;
      let top = 0, area = 0, inner = 0, x0 = W, x1 = 0, y0 = H, y1 = 0;
      stack[top++] = s; lbl[s] = comps.length + 1;
      while (top) {
        const p = stack[--top], x = p % W, y = (p / W) | 0; area++;
        if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
        let n = 0;
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
          if (!dx && !dy) continue;
          const xx = x + dx, yy = y + dy; if (xx < 0 || yy < 0 || xx >= W || yy >= H) continue;
          const q = yy * W + xx; if (!dark[q]) continue; n++;
          if (!lbl[q]) { lbl[q] = lbl[s]; stack[top++] = q; }
        }
        if (n === 8) inner++;
      }
      if (area < minA) { comps.push(null); continue; }
      const w = x1 - x0 + 1, h = y1 - y0 + 1, interior = inner / area;
      // ما يلامس حافة الإطار ويمتد على أكثر من ثلثه غالبًا خلفية أو ظل (حافة النموذج، الطاولة) لا عيب
      const touches = x0 <= zx0 + 1 || y0 <= zy0 + 1 || x1 >= zx1 - 2 || y1 >= zy1 - 2;
      if (touches && (w > zw * 0.33 || h > zh * 0.33 || interior > 0.45)) { comps.push(null); continue; }
      let type = null;
      if (interior > 0.45 && area > zA * 0.0012 && Math.min(w, h) > 6) type = "pot";
      else if (Math.max(w, h) >= zw * 0.035) {
        type = area / (w + h) >= 5 && w >= zw * 0.05 && h >= zh * 0.05 ? "alli" : w >= 2 * h ? "long" : h >= 2 * w ? "trans" : "long";
      }
      comps.push(type ? { type, area, x0, y0, w, h, interior } : null);
    }
    const found = comps.filter(Boolean);
    return { W, H, zone: [zx0, zy0, zw, zh], comps: found, ...metrics(found, zw, zh), diffs };
  }

  function metrics(comps, zw, zh) {
    const zA = zw * zh;
    let len = 0, alli = 0, pot = 0, potN = 0;
    const n = { long: 0, trans: 0, alli: 0, pot: 0 };
    for (const c of comps) {
      n[c.type]++;
      if (c.type === "pot") { pot += c.area; potN++; }
      else if (c.type === "alli") alli += c.w * c.h;
      else len += Math.max(c.w, c.h) * 1.08;
    }
    const lenRatio = len / zw, alliPct = 100 * alli / zA, potPct = 100 * pot / zA;
    // خصومات مشبعة على نهج ASTM D6433: تشققات متفرقة ⇐ «مقبول» (~60–70)، تمساحي ⇐ «متوسط»، حفر ⇐ «سيئ» (~20–35)
    const ci = Math.max(0, Math.min(100, 100 - (25 * (1 - Math.exp(-lenRatio)) + 35 * (1 - Math.exp(-alliPct / 4))
      + 60 * (1 - Math.exp(-(potPct + 1.2 * potN) / 4)))));
    const kind = potN > 0 ? "damaged" : lenRatio >= 0.25 || alliPct >= 0.5 ? "cracked" : "healthy";
    return { n, lenRatio, alliPct, potPct, potN, ci, kind };
  }

  // ---------- الذكاء الاصطناعي (YOLO عبر onnxruntime-web) ----------
  const AI_MAP = { d00: "long", longitudinal_crack: "long", d10: "trans", transverse_crack: "trans", d20: "alli", alligator_crack: "alli", d40: "pot", pothole: "pot" };
  async function loadAI() {
    if (lab.ai || lab.aiLoading) return lab.ai;
    lab.aiLoading = true; setAI("جارٍ تحميل نموذج الذكاء الاصطناعي (~23 م.ب لأول مرة)…");
    try {
      if (!window.ort) await new Promise((ok, no) => { const s = document.createElement("script"); s.src = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/ort.min.js"; s.onload = ok; s.onerror = no; document.head.append(s); });
      ort.env.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/";
      ort.env.wasm.numThreads = self.crossOriginIsolated ? Math.min(4, navigator.hardwareConcurrency || 2) : 1;
      const man = await (await fetch("models/browser-models.json")).json();
      const m = man.find((x) => /yolov8s/.test(x.file)) || man[0];   // الأدق على صور النماذج في اختباراتنا
      const session = await ort.InferenceSession.create(`models/${m.file}`, { executionProviders: ["wasm"], graphOptimizationLevel: "all" });
      lab.ai = { session, names: m.names.map((n) => AI_MAP[String(n).toLowerCase()] || null), size: m.imgsz || 640, file: m.file };
      setAI(`الذكاء الاصطناعي جاهز (${m.file.replace(".q8.onnx", "")}) — يؤكد كل ~1.5 ث`);
    } catch (e) { setAI("تعذّر تحميل نموذج الذكاء الاصطناعي — يعمل الكاشف البصري وحده"); lab.aiOn = false; }
    lab.aiLoading = false; return lab.ai;
  }
  const setAI = (t) => { const el = $("#labAI"); if (el) el.textContent = t; };
  async function runAI(src, sw, sh) {
    const ai = lab.ai; if (!ai || lab.aiBusy) return;
    lab.aiBusy = true;
    try {
      const S = ai.size, r = Math.min(S / sw, S / sh), nw = Math.round(sw * r), nh = Math.round(sh * r), dx = (S - nw) >> 1, dy = (S - nh) >> 1;
      const c = document.createElement("canvas"); c.width = S; c.height = S; const g = c.getContext("2d", { willReadFrequently: true });
      g.fillStyle = "rgb(114,114,114)"; g.fillRect(0, 0, S, S); g.drawImage(src, dx, dy, nw, nh);
      const p = g.getImageData(0, 0, S, S).data, t = new Float32Array(3 * S * S);
      for (let i = 0, j = 0; i < S * S; i++, j += 4) { t[i] = p[j] / 255; t[i + S * S] = p[j + 1] / 255; t[i + 2 * S * S] = p[j + 2] / 255; }
      const out = await ai.session.run({ [ai.session.inputNames[0]]: new ort.Tensor("float32", t, [1, 3, S, S]) });
      const o = out[ai.session.outputNames[0]], [, F, A] = o.dims, d = o.data, nc = F - 4, dets = [];
      for (let k = 0; k < A; k++) {
        let best = 0, cls = -1;
        for (let c2 = 0; c2 < nc; c2++) { const v = d[(4 + c2) * A + k]; if (v > best) { best = v; cls = c2; } }
        if (best < 0.3 || !ai.names[cls]) continue;
        const bx = d[k], by = d[A + k], bw = d[2 * A + k], bh = d[3 * A + k];
        dets.push({ type: ai.names[cls], conf: best, x: (bx - bw / 2 - dx) / r / sw, y: (by - bh / 2 - dy) / r / sh, w: bw / r / sw, h: bh / r / sh });
      }
      dets.sort((a, b) => b.conf - a.conf);
      const keep = [];
      for (const a of dets) if (!keep.some((b) => b.type === a.type && iou(a, b) > 0.45)) keep.push(a);
      lab.aiDets = keep.filter((b) => b.x + b.w / 2 > ZONE.x && b.x + b.w / 2 < ZONE.x + ZONE.w && b.y + b.h / 2 > ZONE.y && b.y + b.h / 2 < ZONE.y + ZONE.h);
    } catch (e) { setAI("خطأ في تشغيل الذكاء الاصطناعي — يعمل الكاشف البصري وحده"); lab.aiOn = false; }
    lab.aiBusy = false;
  }
  const iou = (a, b) => { const x = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)), y = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)); const i = x * y; return i / (a.w * a.h + b.w * b.h - i || 1); };

  // دمج: حفرة يؤكدها الذكاء الاصطناعي بثقة عالية ولم يلتقطها الكاشف البصري تُضاف
  function fuse(r) {
    // صرامة: النماذج العالمية قد تعدّ تشققًا مرسومًا «حفرة» — فلا تُضاف حفرة فوق تشقق يراه الكاشف البصري،
    // ولا حفرة منفردة بلا ثقة عالية جدًا (حتى لا يقلب الذكاء الاصطناعي وحده تصنيف نموذج سليم أو متشقق)
    const box = (c) => ({ x: c.x0 / r.W, y: c.y0 / r.H, w: c.w / r.W, h: c.h / r.H });
    const need = r.potN ? 0.55 : 0.7;
    const extra = lab.aiDets.filter((a) => a.type === "pot" && a.conf >= need &&
      !r.comps.some((c) => c.type === "pot" && iou(a, box(c)) > 0.1) && !r.comps.some((c) => c.type !== "pot" && iou(a, box(c)) > 0.25));
    if (!extra.length) return r;
    const comps = r.comps.concat(extra.map((a) => ({ type: "pot", area: a.w * r.W * a.h * r.H * 0.6, x0: a.x * r.W, y0: a.y * r.H, w: a.w * r.W, h: a.h * r.H, ai: true })));
    return { ...r, comps, ...metrics(comps, r.zone[2], r.zone[3]) };
  }

  // ثبات القراءة: وسيط آخر 7 إطارات، والتصنيف بالأغلبية
  function stable(r) {
    lab.frames.push(r); if (lab.frames.length > 7) lab.frames.shift();
    const cis = lab.frames.map((f) => f.ci).sort((a, b) => a - b), votes = {};
    lab.frames.forEach((f) => (votes[f.kind] = (votes[f.kind] || 0) + 1));
    const kind = Object.entries(votes).sort((a, b) => b[1] - a[1])[0][0];
    return { ...r, ci: cis[cis.length >> 1], kind, agree: votes[kind] / lab.frames.length };
  }

  // ---------- العرض ----------
  const COLORS = { long: "#f59e0b", trans: "#fb923c", alli: "#a855f7", pot: "#ef4444" };
  // geo: موضع الصورة داخل اللوحة (العرض «contain» قد يترك هوامش، خاصة مع كاميرا الجوال الطولية)
  function draw(r, ov, geo) {
    const g = ov.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, ov.width, ov.height);
    g.setTransform(1, 0, 0, 1, geo.ox, geo.oy);
    const k = geo.w / r.W, ow = geo.w, oh = geo.h;
    const [zx, zy, zw, zh] = r.zone;
    g.setLineDash([8, 6]); g.strokeStyle = "rgba(255,255,255,.85)"; g.lineWidth = 2; g.strokeRect(zx * k, zy * k, zw * k, zh * k); g.setLineDash([]);
    g.font = `600 ${Math.round(Math.max(12, ow / 48))}px "Readex Pro", sans-serif`; g.textBaseline = "bottom"; g.direction = "rtl"; g.textAlign = "right";
    for (const c of r.comps) {
      const x = c.x0 * k, y = c.y0 * k, w = c.w * k, h = c.h * k;
      g.strokeStyle = COLORS[c.type]; g.lineWidth = c.type === "pot" ? 3 : 2;
      if (c.type === "pot") { g.fillStyle = "rgba(239,68,68,.22)"; g.fillRect(x, y, w, h); }
      if (c.ai) g.setLineDash([5, 4]);
      g.strokeRect(x, y, w, h); g.setLineDash([]);
      const t = TYPES[c.type] + (c.ai ? " (AI)" : ""), fs = parseFloat(g.font.split(" ")[1]) || 14, tw = g.measureText(t).width + 10, th = fs + 8;
      const lx = Math.min(Math.max(0, x), geo.w - tw), ly = y - th < 0 ? y + h : y - th;  // داخل الصورة دائمًا
      g.fillStyle = COLORS[c.type]; g.fillRect(lx, ly, tw, th); g.fillStyle = "#fff"; g.fillText(t, lx + tw - 5, ly + th - 4);
    }
    g.setLineDash([4, 4]); g.strokeStyle = "#22d3ee"; g.lineWidth = 2;
    for (const a of lab.aiDets) g.strokeRect(a.x * ow, a.y * oh, a.w * ow, a.h * oh);
    g.setLineDash([]); g.setTransform(1, 0, 0, 1, 0, 0);
  }
  function panel(r) {
    const [name, lvl] = KIND[r.kind];
    $("#labKind").textContent = name; $("#labKind").className = `pill big ${lvl}`;
    $("#labCI").textContent = fmtN(r.ci); $("#labCIbar").style.width = `${r.ci}%`; $("#labCIbar").style.background = D.color(r.ci >= 70 ? "low" : r.ci >= 55 ? "medium" : r.ci >= 40 ? "high" : "critical");
    $("#labCounts").innerHTML = Object.entries(TYPES).map(([k, v]) => `<span><i style="background:${COLORS[k]}"></i>${v}: <b>${fmtN(r.n[k])}</b></span>`).join("");
    $("#labStats").textContent = `طول التشققات ${fmtN(r.lenRatio * 100)}% من عرض النموذج · مساحة الحفر ${fmtN(r.potPct, 1)}%${r.agree != null ? ` · ثبات القراءة ${fmtN(r.agree * 100)}%` : ""}${lab.fps ? ` · ${fmtN(lab.fps, 0)} إطار/ث` : ""}`;
  }

  // ---------- الكاميرا ----------
  async function start() {
    if (!navigator.mediaDevices?.getUserMedia) { msg("المتصفح لا يتيح الكاميرا هنا — جرّب كروم أو سفاري، أو استخدم «تحليل صورة»."); return; }
    try {
      lab.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
    } catch { msg("لم يُسمح بالكاميرا — اسمح للمتصفح باستخدامها من إعدادات الموقع، أو استخدم «تحليل صورة»."); return; }
    const v = $("#labVideo"); v.srcObject = lab.stream; await v.play().catch(() => {});
    $("#labStage").classList.add("on"); $("#labImg").hidden = true; v.hidden = false;
    $("#labStart").innerHTML = `${svg("pause")}إيقاف الكاميرا`; msg("ضع نموذج الطريق داخل الإطار المتقطع، وبإضاءة متساوية دون انعكاسات.");
    if (innerWidth < 720) setTimeout(() => $("#labStage").scrollIntoView({ block: "start", behavior: "smooth" }), 300);  // الجوال: الكاميرا والنتيجة في الشاشة
    if (lab.aiOn) loadAI();
    loop();
  }
  function stop() {
    cancelAnimationFrame(lab.raf); lab.stream?.getTracks().forEach((t) => t.stop()); lab.stream = null;
    $("#labStart").innerHTML = `${svg("camera")}تشغيل الكاميرا`;
  }
  function loop(ts = 0) {
    lab.raf = requestAnimationFrame(loop);
    const v = $("#labVideo"); if (!v.videoWidth || ts - lab.last < 110) return;  // ~8 إطارات/ث تكفي وتوفر البطارية
    const dt = Math.max(1, ts - lab.last); lab.fps = lab.fps ? lab.fps * 0.8 + 200 / dt : 1000 / dt; lab.last = ts;
    process(v, v.videoWidth, v.videoHeight, true);
    if (lab.ai && lab.aiOn && ts - lab.aiAt > 1500) { lab.aiAt = ts; runAI(v, v.videoWidth, v.videoHeight); }
  }
  function process(src, sw, sh, live) {
    const stage = $("#labStage"), ov = $("#labOverlay");
    if (stage.dataset.ar !== `${sw}/${sh}`) { stage.style.aspectRatio = `${sw} / ${sh}`; stage.dataset.ar = `${sw}/${sh}`; }
    const box = stage.getBoundingClientRect(), dpr = devicePixelRatio || 1;
    ov.width = Math.round(box.width * dpr); ov.height = Math.round(box.height * dpr);
    const s = Math.min(ov.width / sw, ov.height / sh), geo = { w: sw * s, h: sh * s, ox: (ov.width - sw * s) / 2, oy: (ov.height - sh * s) / 2 };
    let r = fuse(analyze(src, sw, sh));
    lab.raw = r;
    if (live) r = stable(r);
    lab.cur = r; lab.src = src; lab.sw = sw; lab.sh = sh;
    draw(r, ov, geo); panel(r);
  }
  const msg = (t) => { $("#labMsg").textContent = t; };

  function calibrate() {
    const r = lab.raw; if (!r) { msg("شغّل الكاميرا أو حلّل صورة للنموذج السليم أولًا."); return; }
    const d = r.diffs.slice().sort((a, b) => a - b), p = d[Math.floor(d.length * 0.998)] || 20;
    lab.T = Math.round(Math.min(60, Math.max(18, p + 8))); D.safeSet("darb-lab-T", lab.T); lab.frames = [];
    msg(`تمت المعايرة على النموذج السليم: حساسية العتمة ${fmtN(lab.T)} (تُحفظ في هذا المتصفح). الآن وجّه الكاميرا لنموذجَي التشققات والحفر.`);
    if (!lab.stream && lab.img) process(lab.img, lab.img.naturalWidth, lab.img.naturalHeight, false);
  }

  // ---------- مقارنة النماذج الثلاثة: التحليل + التنبؤ + القرار ----------
  function predict(r) {
    // تنبؤ توضيحي بمعدلات هندسية سنوية: رصف سليم يفقد ~4 نقاط/سنة، ×1.5 في حرارة الخليج،
    // وتسرّعه التشققات (تسرب الماء والرمل للطبقات) ثم التمساحي ثم الحفر (حتى ~30 نقطة/سنة)
    const perYear = 4 * 1.5 + 8 * Math.min(1, r.lenRatio) + 10 * Math.min(1, r.alliPct / 4) + 15 * Math.min(1, r.potN / 3);
    const rate = perYear / 52;   // نقطة/أسبوع
    const thr = 55, weeks = r.ci > thr ? (r.ci - thr) / rate : 0;
    return { rate, weeks, ci6: Math.max(0, r.ci - rate * 26), ci12: Math.max(0, r.ci - rate * 52) };
  }
  const TREAT = [[85, "صيانة روتينية", 0.8], [70, "صيانة وقائية (سد تشققات + طبقة واقية)", 4.5], [55, "كشط وإعادة رصف رقيق", 14], [40, "إعادة رصف إنشائية", 32], [0, "إعادة إنشاء كاملة", 78]];
  const treat = (ci) => { const t = TREAT.find(([m]) => ci >= m); return { name: t[1], usd: t[2] * 7300 }; };  // 1 كم من طريق بمسارين (7.3 م)
  function save(slot) {
    const r = lab.cur; if (!r) { msg("لا توجد قراءة بعد."); return; }
    const c = document.createElement("canvas"), W = 640, H = Math.round(640 * lab.sh / lab.sw);
    const o = document.createElement("canvas"); o.width = W; o.height = H; draw(r, o, { w: W, h: H, ox: 0, oy: 0 });
    c.width = W; c.height = H; const g = c.getContext("2d"); g.drawImage(lab.src, 0, 0, W, H); g.drawImage(o, 0, 0);  // الصورة ثم العيوب فوقها
    lab.slots[slot] = { r: { ...r, comps: undefined, diffs: undefined }, img: c.toDataURL("image/jpeg", 0.8), at: new Date() };
    renderSlots(); msg(`حُفظت القراءة في «النموذج ${slot + 1}».`);
  }
  function renderSlots() {
    $("#labSlots").innerHTML = lab.slots.map((s, i) => {
      if (!s) return `<div class="lab-slot empty"><b>النموذج ${fmtN(i + 1)}</b><span>${["الشارع السليم", "الشارع المتشقق", "الشارع المتضرر بالحفر"][i]}</span><span class="muted">وجّه الكاميرا إليه ثم اضغط «احفظ في النموذج ${fmtN(i + 1)}»</span></div>`;
      const r = s.r, [name, lvl] = KIND[r.kind], p = predict(r), now = treat(r.ci), later = treat(p.ci12);
      return `<div class="lab-slot"><img src="${s.img}" alt="">
        <div class="ls-h"><b>النموذج ${fmtN(i + 1)}</b><span class="pill ${lvl}">${name}</span></div>
        <div class="ls-ci"><span>مؤشر الحالة</span><b>${fmtN(r.ci)}</b><span>/100</span></div>
        <div class="ls-n">${Object.entries(TYPES).filter(([k]) => r.n[k]).map(([k, v]) => `${v}: ${fmtN(r.n[k])}`).join(" · ") || "لا عيوب مكتشفة"}</div>
        <div class="ls-p"><b>التنبؤ</b> (صيف خليجي): ${r.ci <= 55 ? "<em class=bad>دون عتبة الصيانة الآن — تدخل فوري</em>" : `بلوغ عتبة الصيانة خلال ~<b>${p.weeks > 104 ? `${fmtN(p.weeks / 52, 1)} سنة` : `${fmtN(p.weeks)} أسبوع`}</b>`}
          · بعد 6 أشهر ${fmtN(p.ci6)} · بعد سنة ${fmtN(p.ci12)}</div>
        <div class="ls-t"><b>القرار:</b> ${esc(now.name)} الآن بـ<b>${money(now.usd)}</b>/كم، وإن أُجّل سنة: ${esc(later.name)} بـ${money(later.usd * 1.04)}/كم</div></div>`;
    }).join("");
  }

  // ---------- تحليل صورة (بديل الكاميرا) ----------
  function fromFile(f) {
    const im = new Image();
    im.onload = async () => {
      stop(); lab.img = im; lab.frames = [];
      $("#labImg").src = im.src; $("#labImg").hidden = false; $("#labVideo").hidden = true; $("#labStage").classList.add("on");
      await new Promise((ok) => requestAnimationFrame(ok));
      if (lab.aiOn) { await loadAI(); await runAI(im, im.naturalWidth, im.naturalHeight); }
      process(im, im.naturalWidth, im.naturalHeight, false);
      msg("حُللت الصورة. يمكنك حفظ النتيجة في أحد النماذج الثلاثة.");
      if (innerWidth < 720) $("#labStage").scrollIntoView({ block: "start", behavior: "smooth" });
    };
    im.src = URL.createObjectURL(f);
  }

  $("#labStart").addEventListener("click", () => (lab.stream ? stop() : start()));
  $("#labCal").addEventListener("click", calibrate);
  $("#labFile").addEventListener("change", (e) => e.target.files[0] && fromFile(e.target.files[0]));
  $("#labAIon").addEventListener("change", (e) => { lab.aiOn = e.target.checked; lab.aiDets = []; if (lab.aiOn) loadAI(); else setAI("الذكاء الاصطناعي متوقف — الكاشف البصري وحده"); });
  $("#labSave").addEventListener("click", (e) => { const b = e.target.closest("[data-slot]"); if (b) save(+b.dataset.slot); });
  document.addEventListener("visibilitychange", () => { if (document.hidden && lab.stream) stop(); });
  renderSlots();
  window.DARB_LAB = { analyze, metrics, lab };  // للاختبار
})();
