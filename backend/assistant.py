"""المساعد العربي (وضع الخادم): يجيب عن أسئلة المهندسين بالعربية من بيانات دَرْب فقط، عبر Claude.

يعمل فقط إن وُجد مفتاح ANTHROPIC_API_KEY (أو ملف تعريف ant) ومكتبة anthropic. الموقع الثابت المجاني
يستخدم بدلًا منه محرك الأسئلة العربي المدمج في الواجهة (frontend/app.js)، فلا يحتاج مفتاحًا.
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("darb.assistant")
MODEL = os.getenv("DARB_ASSISTANT_MODEL", "claude-opus-5-5")

SYSTEM = """أنت «مساعد دَرْب»، مساعد هندسي لمراقبة حالة الطرق بالذكاء الاصطناعي من كاميرات المرور.
تجيب مهندسي البلديات وهيئات الطرق بالعربية الفصحى المختصرة.

القواعد:
- اعتمد فقط على بيانات JSON المرفقة مع السؤال. لا تخترع أرقامًا أو طرقًا أو مدنًا غير موجودة فيها.
- إن لم تكفِ البيانات للإجابة فقل ذلك صراحة واقترح ما يلزم (مثل إضافة كاميرات أو انتظار مزيد من اللقطات).
- اذكر أسماء المقاطع كما وردت، والأرقام مع وحداتها: مؤشر الحالة من 100، الحرارة بالدرجة المئوية، والكلفة بالعملة التي يطلبها السائل (الكلفة في البيانات بالدولار؛ أسعار الصرف في الحقل currencies).
- رتّب القوائم بالأهم أولًا، واجعل الإجابة قصيرة: فقرة أو قائمة نقطية لا تتجاوز 10 بنود.
- لا كاميرات مفتوحة في مدن الخليج بعد؛ إن سُئلت عنها فوضّح أن النظام جاهز لإضافتها عند توفر صلاحية الوصول."""


def available() -> bool:
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def ask(question: str, context: dict) -> dict:
    """إجابة Claude عن سؤال عربي، مع بيانات الشبكة المضغوطة سياقًا."""
    import anthropic

    client = anthropic.Anthropic()
    data = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "low"},  # أسئلة استعلام عن بيانات جاهزة: لا تحتاج تفكيرًا عميقًا
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # إن رُفض الطلب لأسباب أمان يُعاد تلقائيًا على نموذج بديل
            system=SYSTEM,
            messages=[{"role": "user", "content": f"<data>\n{data}\n</data>\n\nالسؤال: {question}"}],
        )
    except anthropic.RateLimitError:
        return {"ok": False, "error": "تجاوزنا حد الطلبات مؤقتًا — حاول بعد دقيقة."}
    except anthropic.APIStatusError as e:
        log.warning("assistant API error %s: %s", e.status_code, e.message)
        return {"ok": False, "error": "تعذّر الوصول إلى خدمة المساعد الآن."}
    except anthropic.APIConnectionError:
        return {"ok": False, "error": "لا اتصال بخدمة المساعد."}
    if response.stop_reason == "refusal":
        return {"ok": False, "error": "لا أستطيع الإجابة عن هذا السؤال."}
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return {"ok": True, "answer": text, "model": response.model}


def context_for(cams: list[dict], econ_items: list[dict], gulf_overview: dict, currencies: dict, regions: list[dict]) -> dict:
    """بيانات مضغوطة للسياق: ما يحتاجه السؤال الهندسي، دون صور أو سجلات طويلة."""
    econ = {e["camera_id"]: e for e in econ_items}
    rows = []
    for c in cams:
        r, s, e = c.get("risk") or {}, c.get("last_snapshot") or {}, econ.get(c["id"], {})
        rows.append({
            "name": c["name"], "road": c.get("road"), "region": c.get("region"),
            "ci": r.get("ci", s.get("condition_index")), "slope_per_week": r.get("slope"), "risk": r.get("score"),
            "level": r.get("level"), "weeks_to_maintenance": r.get("weeks_to_threshold"), "potholes": s.get("pothole_count"),
            "rutting_risk": r.get("rutting"), "pavement_temp_c": r.get("pavement_t"), "binder_deficit_grades": r.get("pg_deficit"),
            "sand": r.get("sand"), "open_alerts": c.get("open_alerts"), "top_factor": r.get("top_factor"),
            "treatment_now": (e.get("treatment_now") or {}).get("name"), "cost_now_usd": e.get("cost_now"),
            "treatment_in_12m": (e.get("treatment_later") or {}).get("name"), "cost_in_12m_usd": e.get("cost_later"),
            "must_do_for_safety": e.get("must_do"),
        })
    return {"regions": [{"key": r["key"], "name": r["name"]} for r in regions], "cameras": rows,
            "gulf_overview": gulf_overview, "currencies": {k: v["rate"] for k, v in currencies.items()},
            "maintenance_threshold": 55}
