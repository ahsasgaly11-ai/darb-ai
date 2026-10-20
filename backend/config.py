"""إعدادات دَرْب AI — تُقرأ من متغيرات البيئة مع قيم افتراضية مناسبة للتجربة."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# المناطق: إعدادات جاهزة لكل مدينة (الكاميرات، التوقيت، موقع الطقس، المناخ الاحتياطي).
# تعمل عدة مناطق معًا في لوحة واحدة، ولكل كاميرا منطقتها (توقيتها وطقسها ومناخها).
# لإضافة مدينة خليجية (الدوحة، دبي، الرياض…) أضف مدخلًا هنا وملف كاميرات في config/ عند توفر كاميرات مرخّصة.
REGIONS = {
    "singapore": {
        # حار رطب طوال العام — يشبه الساحل الخليجي في الرطوبة. كاميرات LTA بدقة 1920×1080 مع أرشيف
        "name_ar": "سنغافورة", "cameras": "cameras.singapore.json", "tz": "Asia/Singapore", "lat": 1.35, "lng": 103.82,
        "climate": {m: (31.5, 25.0) for m in range(1, 13)},
        "attribution": "Contains information from Traffic Images accessed from data.gov.sg, made available under the "
                       "terms of the Singapore Open Data Licence version 1.0",
    },
    "phoenix": {
        # صحراء سونورا: صيف 45–48°م ومدى حراري يومي كبير — الأقرب لمناخ الخليج الجاف. كاميرات ADOT بدقة 1920×1080
        "name_ar": "فينكس (أريزونا)", "cameras": "cameras.phoenix.json", "tz": "America/Phoenix", "lat": 33.45, "lng": -112.07,
        "climate": {1: (19.5, 7.5), 2: (21.5, 9.0), 3: (25.5, 12.0), 4: (30.0, 16.0), 5: (35.5, 21.0),
                    6: (40.5, 26.0), 7: (41.5, 29.5), 8: (40.5, 29.0), 9: (37.5, 25.5), 10: (31.0, 18.5),
                    11: (24.0, 11.5), 12: (19.0, 7.0)},
        "attribution": "Camera images: Arizona Department of Transportation (ADOT) via AZ511",
    },
    "tucson": {
        # صحراء سونورا على ارتفاع أعلى قليلًا من فينكس: صيف 38–40°م ومدى حراري يومي كبير جدًا (يصل إلى 17°م)
        "name_ar": "توسان (أريزونا)", "cameras": "cameras.tucson.json", "tz": "America/Phoenix", "lat": 32.22, "lng": -110.97,
        "climate": {1: (19.6, 4.3), 2: (21.3, 5.6), 3: (24.8, 8.3), 4: (28.9, 11.7), 5: (34.2, 16.6),
                    6: (38.9, 21.9), 7: (38.3, 24.7), 8: (37.3, 24.1), 9: (35.6, 21.3), 10: (30.3, 14.8),
                    11: (23.9, 8.3), 12: (18.9, 4.4)},
        "attribution": "Camera images: Arizona Department of Transportation (ADOT) via AZ511",
    },
    "yuma": {
        # من أشد المدن حرارة وجفافًا وشمسًا في أمريكا الشمالية: صيف 42°م — الأقرب لحرارة الرياض والكويت
        "name_ar": "يوما (أريزونا)", "cameras": "cameras.yuma.json", "tz": "America/Phoenix", "lat": 32.69, "lng": -114.62,
        "climate": {1: (21.4, 7.6), 2: (23.6, 9.3), 3: (27.0, 12.1), 4: (30.9, 15.4), 5: (35.4, 19.6),
                    6: (40.1, 23.9), 7: (41.9, 28.4), 8: (41.6, 28.3), 9: (39.1, 24.6), 10: (33.1, 17.8),
                    11: (26.1, 11.2), 12: (20.8, 7.0)},
        "attribution": "Camera images: Arizona Department of Transportation (ADOT) via AZ511",
    },
    "tampa": {
        # ساحل خليج المكسيك: حار رطب وأمطار صيفية غزيرة — يشبه رطوبة الساحل الخليجي (الدمام، الدوحة، دبي)
        "name_ar": "تامبا (فلوريدا)", "cameras": "cameras.tampa.json", "tz": "America/New_York", "lat": 27.95, "lng": -82.46,
        "climate": {1: (21.6, 11.7), 2: (23.0, 13.1), 3: (25.2, 15.2), 4: (27.8, 17.9), 5: (30.9, 21.5),
                    6: (32.2, 24.2), 7: (32.6, 24.8), 8: (32.7, 24.8), 9: (31.9, 24.1), 10: (29.4, 20.6),
                    11: (25.9, 16.0), 12: (22.8, 13.4)},
        "attribution": "Camera images: Florida Department of Transportation (FDOT) via FL511",
    },
}
# المناطق المفعّلة (DARB_REGION القديم ما زال مدعومًا لمنطقة واحدة)
REGION_KEYS = [r.strip() for r in os.getenv("DARB_REGIONS", os.getenv("DARB_REGION", "singapore,phoenix,tucson,yuma,tampa")).split(",") if r.strip()]
for _r in REGION_KEYS:
    if _r not in REGIONS:
        raise ValueError(f"منطقة غير معروفة: {_r} — المتاح: {', '.join(REGIONS)}")

# لكل مجموعة مناطق قاعدة بيانات وصور مستقلة
DATA_DIR = Path(os.getenv("DARB_DATA_DIR", ROOT / "data" / "-".join(REGION_KEYS)))
SNAPSHOT_DIR = DATA_DIR / "snapshots"
DB_PATH = Path(os.getenv("DARB_DB_PATH", DATA_DIR / "darb.sqlite3"))
CAMERAS_FILE = os.getenv("DARB_CAMERAS_FILE", "")  # اختياري: ملف كاميرات واحد بدل ملفات المناطق
FRONTEND_DIR = ROOT / "frontend"
MODELS_DIR = Path(os.getenv("DARB_MODELS_DIR", ROOT / "models"))

# التوقيت الافتراضي (للمجدول العام)؛ لكل كاميرا توقيت منطقتها
TIMEZONE = REGIONS[REGION_KEYS[0]]["tz"]


def tz_of(region: str) -> str:
    return REGIONS.get(region, REGIONS[REGION_KEYS[0]])["tz"]


# جدول الالتقاط: تحليل كامل أسبوعي لبناء الاتجاه الزمني + فحص سريع يومي لرصد المشاكل المفاجئة
WEEKLY_DAY = os.getenv("DARB_WEEKLY_DAY", "mon")      # يوم الالتقاط الأسبوعي
WEEKLY_HOUR = int(os.getenv("DARB_WEEKLY_HOUR", "10"))  # 10 صباحًا: إضاءة جيدة وظلال أقصر
SENTINEL_HOURS = float(os.getenv("DARB_SENTINEL_HOURS", "24"))  # 0 لإيقاف الفحص السريع
ENABLE_SCHEDULER = os.getenv("DARB_SCHEDULER", "1") == "1"
# الالتقاط الحي لا يُجرى ليلًا (الإضاءة لا تكفي لرؤية التشققات): ساعات النهار المحلية [من، إلى)
DAYLIGHT_HOURS = tuple(int(x) for x in os.getenv("DARB_DAYLIGHT_HOURS", "7,18").split(","))

# عدد الإطارات في كل التقاط والفاصل بينها (ثوانٍ) — الوسيط الزمني يزيل المركبات من الصورة
BURST_FRAMES = int(os.getenv("DARB_BURST_FRAMES", "7"))
BURST_INTERVAL = float(os.getenv("DARB_BURST_INTERVAL", "4"))
SENTINEL_BURST_FRAMES = int(os.getenv("DARB_SENTINEL_BURST_FRAMES", "3"))

# كشف التغيّر المفاجئ
SUDDEN_CHANGE_PCT = float(os.getenv("DARB_SUDDEN_CHANGE_PCT", "1.2"))
SUDDEN_CI_DROP = float(os.getenv("DARB_SUDDEN_CI_DROP", "8"))
# عند الاشتباه بتغيّر مفاجئ تُلتقط دفعة تأكيد بعد هذه المدة (ثوانٍ) لاستبعاد مركبة متوقفة أو ظل عابر
CONFIRM_DELAY = float(os.getenv("DARB_CONFIRM_DELAY", "120"))
# وضع «الصورة الواحدة» (التشغيل المجاني المجدول): لا لقطة تأكيد فورية — التأكيد يتم في لقطة اليوم التالي
CONFIRM_RECAPTURE = os.getenv("DARB_CONFIRM_RECAPTURE", "1") == "1"
SEED_FRAMES = int(os.getenv("DARB_SEED_FRAMES", "5"))

# عند الاشتباه بتغيّر مفاجئ في لقطة حية: فحص متابعة بعد هذه المدة (دقائق) لتأكيده أو استبعاده
FOLLOWUP_MINUTES = float(os.getenv("DARB_FOLLOWUP_MINUTES", "60"))

# فوق هذه النسبة من حجب المركبات تُعدّ اللقطة «مزدحمة» ولا تدخل التحليل (انظر sources.occlusion)
CONGESTION_OCCLUSION = float(os.getenv("DARB_CONGESTION_OCCLUSION", "0.10"))

# عتبة مؤشر الحالة التي تستوجب الصيانة (على غرار PCI)
MAINTENANCE_THRESHOLD = float(os.getenv("DARB_MAINTENANCE_THRESHOLD", "55"))

# نماذج YOLO مدرّبة على عيوب الطرق (RDD2022). قائمة مسارات مفصولة بفواصل؛ إن تُركت فارغة تُستخدم
# الملفات الموجودة في models/ (نزّلها بـ python -m backend.models). أكثر من نموذج = تجميع (Ensemble).
YOLO_MODELS = [p for p in os.getenv("DARB_YOLO_MODELS", os.getenv("DARB_YOLO_MODEL", "")).split(",") if p.strip()]
YOLO_CONF = float(os.getenv("DARB_YOLO_CONF", "0.25"))
YOLO_TILE = int(os.getenv("DARB_YOLO_TILE", "640"))  # تقطيع الصورة الكبيرة لاكتشاف التشققات الصغيرة

# بيانات دبي المفتوحة (Dubai Pulse) — حوادث المرور اللحظية، اختيارية
DUBAI_PULSE_KEY = os.getenv("DUBAI_PULSE_API_KEY", "")
DUBAI_PULSE_SECRET = os.getenv("DUBAI_PULSE_API_SECRET", "")

# الطقس: Open-Meteo مجاني ولا يحتاج مفتاحًا (موقع كل منطقة من REGIONS)
WEATHER_ENABLED = os.getenv("DARB_WEATHER", "1") == "1"

# data.gov.sg: يعمل دون مفتاح؛ المفتاح المجاني يرفع حدود الطلبات
DATAGOVSG_API_KEY = os.getenv("DATAGOVSG_API_KEY", "")

# Webhook اختياري لإرسال التنبيهات (Slack/Teams/نظام بلاغات)
ALERT_WEBHOOK = os.getenv("DARB_ALERT_WEBHOOK", "")

# دورة حياة المشكلة: المدة التي يُراقب فيها المقطع بعد الإصلاح لرصد عودة العيب
POST_REPAIR_WEEKS = int(os.getenv("DARB_POST_REPAIR_WEEKS", "8"))
# التنبؤ: فتح «مشكلة متوقعة» إذا كان بلوغ عتبة الصيانة متوقعًا خلال هذه المدة (أسابيع)
PREDICT_HORIZON_WEEKS = float(os.getenv("DARB_PREDICT_HORIZON_WEEKS", "12"))

# عند أول تشغيل: توليد سجلّ تاريخي للكاميرات التجريبية (بالأسابيع) لعرض الاتجاهات فورًا
SEED_WEEKS = int(os.getenv("DARB_SEED_WEEKS", "26"))

USER_AGENT = "DARB-AI/1.0 (road-risk research prototype)"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
