"""يبني صفحة العرض الثابتة من الواجهة الأصلية: يدمج CSS و JS، ويضيف طبقة تحاكي الواجهة البرمجية من ملفات JSON."""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend"
OUT = Path(sys.argv[1])
LEAFLET_CSS = Path(sys.argv[2]).read_text()

html = (SRC / "index.html").read_text()
css = (SRC / "styles.css").read_text()
js = (SRC / "app.js").read_text()

# الصور من البيانات المضمّنة بدل الخادم
js = js.replace('src="/api/snapshots/${s.id}/image?annotated=1"', 'src="${imgSrc(s.id, 1)}"')
js = js.replace('src="/api/snapshots/${s.id}/image?annotated=${ann}"', 'src="${imgSrc(s.id, ann)}"')
js = js.replace('img.src = `/api/snapshots/${s.id}/image?annotated=${ann.checked ? 1 : 0}`;', 'img.src = imgSrc(s.id, ann.checked ? 1 : 0);')
# بلاطات الخريطة من البيانات المضمّنة
js = re.sub(r'L\.tileLayer\("https://\{s\}\.tile\.openstreetmap\.org/\{z\}/\{x\}/\{y\}\.png", \{\s*maxZoom: 19, attribution: (\'[^\']*\') \}\)\.addTo\(state\.map\);',
            r'state.tiles = new (L.GridLayer.extend({ createTile(c) { const t = (window.__TILES || {})[`${c.z}/${c.x}/${c.y}`]; if (!t) return document.createElement("div"); const i = document.createElement("img"); i.alt = ""; i.src = t; return i; } }))({ maxZoom: 12, attribution: \1 }).addTo(state.map); window.__redrawTiles = () => state.tiles.redraw();', js)
js = js.replace('L.map("map", { zoomControl: true })', 'L.map("map", { zoomControl: true, maxZoom: 12, minZoom: 1 })')
js = js.replace("{ maxZoom: 13 }", "{ maxZoom: 12 }")
assert "imgSrc(s.id" in js and "GridLayer" in js, "patch failed"

shim = r'''
window.__IMG = {}; window.__TILES = {};
window.imgSrc = (id, ann) => window.__IMG[id + ":" + (+ann ? 1 : 0)] || window.__IMG[id + ":1"] || "";
(() => {
  const real = window.fetch.bind(window);
  const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json" } });
  const ready = real("data/thumbs.json").then((r) => r.json()).then((t) => Object.assign(window.__IMG, t)).catch(() => {});
  // بلاطات الخريطة كبيرة: تُحمَّل في الخلفية وتُرسم عند وصولها
  real("data/tiles.json").then((r) => r.json()).then((t) => { Object.assign(window.__TILES, t); window.__redrawTiles?.(); }).catch(() => {});
  window.fetch = async (url, opts = {}) => {
    const u = new URL(url, location.href);
    const at = u.pathname.indexOf("/api/");
    if (at < 0) return real(url, opts);
    if (opts.method && opts.method !== "GET") return json({ detail: "هذه نسخة عرض للقراءة فقط" }, 403);
    await ready;
    const p = u.pathname.slice(at + 5);
    const region = u.searchParams.get("region") || "all";
    const file = p.startsWith("cameras/") ? `data/cam_${p.slice(8)}.json`
      : p === "alerts" ? "data/alerts.json" : p === "status" ? "data/status.json" : `data/${p}_${region}.json`;
    const r = await real(file);
    if (!r.ok) return json({ detail: "غير متاح في نسخة العرض" }, 404);
    const j = await r.json();
    if (j._images) { Object.assign(window.__IMG, j._images); delete j._images; }
    return json(j);
  };
})();
'''

static_css = '''
/* نسخة العرض: إخفاء العمليات التي تحتاج الخادم */
#captureBtn, #maintForm, #maintForm + p, button[data-ack], a[href$="priorities.csv"] { display: none !important; }
.snapnote { max-width: 1400px; margin: 12px auto 0; padding-inline: 24px; }
.snapnote div { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 10px 14px; font-size: .85rem; color: var(--muted); }
.snapnote b { color: var(--ink); }
@media (max-width: 720px) { .snapnote { padding-inline: 16px; } }
'''

head_links = '\n'.join(re.findall(r'<link rel="(?:preconnect|stylesheet)" href="https://fonts\.[^"]+"[^>]*>', html))
body = html[html.index("<body>") + 6: html.index("</body>")]
body = re.sub(r'\s*<script src="app\.js"></script>', "", body)
body = body.replace('<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>',
                    '<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>')
import os
if os.getenv("DARB_SITE_MODE") == "auto":
    note = ('<div class="snapnote"><div><b>يُحدَّث آليًا كل يوم</b>: صورة واحدة من كل كاميرا حقيقية '
            'في خمس مدن (سنغافورة — هيئة النقل البري LTA؛ فينكس وتوسان ويوما، أريزونا — وزارة النقل ADOT؛ تامبا، فلوريدا — وزارة النقل FDOT) يحلّلها الذكاء الاصطناعي '
            'ظهر كل يوم بالتوقيت المحلي.</div></div>')
else:
    note = ('<div class="snapnote"><div><b>نسخة عرض للقراءة فقط</b> من بيانات كاميرات حقيقية: '
            'سنغافورة (6 أشهر من أرشيف هيئة النقل البري LTA) وفينكس، أريزونا (وزارة النقل ADOT). '
            'الالتقاط الحي والعمليات تعمل عند تشغيل الخادم (انظر README).</div></div>')
body = body.replace('</header>', '</header>\n  ' + note, 1)

page = f'''<title>دَرْب AI</title>
<script>document.documentElement.lang = "ar"; document.documentElement.dir = "rtl";</script>
{head_links}
<style>
{LEAFLET_CSS}
{css}
{static_css}
</style>
{body}
<script>{shim}</script>
<script>{js}</script>
'''
if os.getenv("DARB_SITE_MODE") == "auto":
    # استضافة عادية (GitHub Pages وغيرها): مستند HTML كامل
    page = ('<!doctype html>\n<html lang="ar" dir="rtl">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<meta name="description" content="دَرْب AI — التنبؤ بمخاطر الطرق من كاميرات المرور بالذكاء الاصطناعي">\n'
            '</head>\n<body>\n' + page + '\n</body>\n</html>\n')
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "index.html").write_text(page, encoding="utf-8")
print("page KB", round(len(page.encode()) / 1024))
