"""محرك القرار الاقتصادي: أين تُصرف ميزانية الصيانة؟

لكل مقطع: المعالجة المناسبة لحالته الآن وكلفتها، والمعالجة التي سيحتاجها بعد 12 شهرًا إن أُجّل
(حسب سرعة التدهور المتوقعة) وكلفتها، والفرق = ما يوفّره التدخل الآن. وتُضاف كلفة تقديرية على
مستخدمي الطريق (استهلاك المركبات يزيد مع خشونة السطح، بنهج HDM-4 المبسّط).

الأسعار تقديرية (دولار/م²) من متوسطات دولية لعقود الصيانة، وتُستبدل بأسعار الجهة المالكة
عبر meta.unit_costs أو متغيرات البيئة. قاعدة الصناعة: كل دولار في الصيانة الوقائية يوفّر 6–10 لاحقًا.
"""
from __future__ import annotations

from . import config

# (أدنى مؤشر حالة، المفتاح، الاسم، الوصف، دولار/م²)
TREATMENTS = [
    (85, "routine", "صيانة روتينية", "سد التشققات الموضعية ومراقبة", 0.8),
    (70, "preventive", "صيانة وقائية", "سد التشققات + طبقة رقيقة واقية (Micro-surfacing)", 4.5),
    (55, "thin_overlay", "كشط وإعادة رصف رقيق", "كشط 40 مم وطبقة سطحية جديدة", 14.0),
    (40, "structural", "إعادة رصف إنشائية", "كشط 100 مم وطبقتان مع إصلاح القاعدة موضعيًا", 32.0),
    (0, "reconstruction", "إعادة إنشاء كاملة", "إزالة الرصف وإعادة بناء القاعدة والطبقات", 78.0),
]
# أسعار صرف تقريبية مقابل الدولار (للعرض فقط)
CURRENCIES = {"USD": (1.0, "دولار"), "SAR": (3.75, "ريال سعودي"), "AED": (3.6725, "درهم إماراتي"), "QAR": (3.64, "ريال قطري"),
              "KWD": (0.307, "دينار كويتي"), "BHD": (0.376, "دينار بحريني"), "OMR": (0.385, "ريال عماني"), "EUR": (0.92, "يورو")}
LANE_WIDTH = 3.65
INFLATION = 0.04          # تضخم أسعار المقاولات السنوي
VOC_PER_CI_POINT = 0.001  # دولار/مركبة/كم لكل نقطة تحت 70: خشونة أعلى = وقود وإطارات وصيانة أكثر


def treatment_for(ci: float) -> dict:
    lim, key, name, desc, usd = next(t for t in TREATMENTS if ci >= t[0])
    return {"key": key, "name": name, "desc": desc, "usd_m2": usd}


def lanes(meta: dict) -> int:
    if meta.get("lanes"):
        return int(meta["lanes"])
    aadt = meta.get("aadt", 40000)
    return 5 if aadt > 150000 else 4 if aadt > 80000 else 3 if aadt > 40000 else 2


def analyze(camera: dict, risk: dict | None) -> dict | None:
    """اقتصاديات مقطع كاميرا واحدة (بالدولار؛ التحويل للعملة في الواجهة)."""
    if not risk:
        return None
    fc = risk.get("forecast") or {}
    ci = float(fc.get("ci") if fc.get("ci") is not None else risk.get("ci", 100))
    eff = float(fc.get("effective_slope") or 0.0)  # نقطة/أسبوع (سالب = تدهور)
    meta = camera.get("meta", {})
    length = float(meta.get("segment_length_m", 500))
    area = length * lanes(meta) * LANE_WIDTH
    unit = {**{t[1]: t[4] for t in TREATMENTS}, **(meta.get("unit_costs") or {})}

    now = treatment_for(ci)
    ci_later = max(0.0, ci + eff * 52)
    later = treatment_for(ci_later)
    cost_now = unit[now["key"]] * area
    cost_later = unit[later["key"]] * area * (1 + INFLATION)
    aadt = meta.get("aadt", 40000)
    user_cost = aadt * 365 * (length / 1000) * VOC_PER_CI_POINT * max(0.0, 70 - ci_later)  # سنويًا إن أُجّل
    must = ci <= config.MAINTENANCE_THRESHOLD or (camera.get("last_snapshot") or {}).get("pothole_count", 0) > 0
    saving = max(0.0, cost_later - cost_now)
    return {
        "camera_id": camera["id"], "name": camera["name"], "road": camera.get("road", ""), "region": camera.get("region", ""),
        "ci": round(ci, 1), "ci_in_12m": round(ci_later, 1), "area_m2": round(area), "lanes": lanes(meta), "length_m": length,
        "treatment_now": {**now, "usd_m2": unit[now["key"]]}, "treatment_later": {**later, "usd_m2": unit[later["key"]]},
        "cost_now": round(cost_now), "cost_later": round(cost_later), "deferral_saving": round(saving),
        "user_cost_year": round(user_cost), "benefit": round(saving + user_cost),
        "ratio": round((saving + user_cost) / cost_now, 2) if cost_now else 0.0,
        "must_do": bool(must), "risk_score": risk.get("score"), "level": risk.get("level"),
    }


def plan(items: list[dict], budget: float) -> dict:
    """توزيع ميزانية (بالدولار): الإلزامي للسلامة أولًا، ثم الأعلى عائدًا لكل دولار (حقيبة ظهر جشعة)."""
    order = sorted(items, key=lambda x: (not x["must_do"], -x["ratio"], -(x["risk_score"] or 0)))
    chosen, left = [], budget
    for x in order:
        if x["treatment_now"]["key"] == "routine" and not x["must_do"]:
            continue  # الروتيني يُموَّل من بند التشغيل لا من خطة الصيانة
        if x["cost_now"] <= left:
            chosen.append(x)
            left -= x["cost_now"]
    skipped = [x for x in order if x not in chosen and x["treatment_now"]["key"] != "routine"]
    spent = budget - left
    benefit = sum(x["benefit"] for x in chosen)
    return {"selected": chosen, "unfunded": skipped, "spent": round(spent), "remaining": round(left),
            "benefit": round(benefit), "roi": round(benefit / spent, 2) if spent else 0.0,
            "deferral_penalty": round(sum(x["cost_later"] - x["cost_now"] for x in skipped))}
