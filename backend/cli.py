"""تشغيل دَرْب AI دفعةً واحدة دون خادم دائم — للاستضافة المجانية (GitHub Actions أو أي مجدول).

    python -m backend.cli daily   --site site/   # الالتقاط اليومي (يُشغَّل كل نصف ساعة؛ يلتقط المستحق في نافذته)
    python -m backend.cli confirm --site site/   # تأكيد الاشتباهات بعد ساعة
    python -m backend.cli due                    # ما المطلوب الآن؟ daily | confirm | none (بلا مكتبات ثقيلة)

لكل كاميرا مرة يوميًا بين 9 و12 صباحًا بالتوقيت المحلي (ضوء جيد قبل تموّج الهواء من حرارة الأسفلت):
دفعة من 5 إطارات ← وسيط زمني يزيل المركبات ← تحليل بالذكاء الاصطناعي ← المخاطر ودورة حياة المشكلات.
الاتجاه يُبنى من وسيط أيام كل أسبوع. أي اشتباه بحدث مفاجئ يُعاد التقاطه بعد ساعة قبل إطلاق التنبيه.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("darb.cli")
ROOT = Path(__file__).resolve().parent.parent
KEEP_IMAGES = int(os.getenv("DARB_KEEP_IMAGES", "10"))  # صور كل كاميرا المحفوظة على القرص (المقاييس تبقى كاملة)
FRAMES = int(os.getenv("DARB_DAILY_FRAMES", "5"))         # إطارات كل التقاط (للوسيط الزمني) للصور المتجددة كل دقيقة أو أكثر
# البث المرئي إطاراته مجانية: 25 إطارًا على ~30 ث من البث. بخمسة إطارات على 16 ث كانت السيارات في الطرق المزدحمة
# تغطي النقطة نفسها في 3 منها فتبقى أجزاء منها في الصورة؛ الوسيط يحتاج أن يظهر الطريق في أكثر من نصف الإطارات فقط.
VIDEO_FRAMES = int(os.getenv("DARB_VIDEO_FRAMES", "25"))
VIDEO_TYPES = ("caltrans", "hls", "rtsp", "video", "mjpeg")
TARGET_HOUR = int(os.getenv("DARB_CAPTURE_HOUR", "10"))   # الساعة المحلية المستهدفة
WINDOW = (int(os.getenv("DARB_WINDOW_START", "9")), int(os.getenv("DARB_WINDOW_END", "12")))
CONFIRM_AFTER = timedelta(minutes=int(os.getenv("DARB_CONFIRM_AFTER_MIN", "50")))
PENDING_FILE = "pending_confirm.json"
MAX_TRIES = int(os.getenv("DARB_MAX_TRIES", "3"))  # محاولات الكاميرا المتعطلة في اليوم قبل تركها لليوم التالي
ATTEMPTS_FILE = "attempts.json"


def capture_time(cam, now_utc, pipeline, sources, window=None) -> datetime | None:
    """لحظة الالتقاط: العاشرة صباحًا محليًا للمصادر ذات الأرشيف، والآن للكاميرات الحية إن كانت في النافذة (9–12)."""
    tz = pipeline.tz(cam)
    local = now_utc.astimezone(tz)
    if sources.supports_history(cam) and cam["source"].get("type") != "demo":
        target = local.replace(hour=TARGET_HOUR, minute=0, second=0, microsecond=0)
        return (target if target <= local else target - timedelta(days=1)).astimezone(timezone.utc)
    start, end = window or WINDOW
    return now_utc if start <= local.hour < end else None


def interval_for(cam) -> float:
    """الفاصل بين الإطارات: الفيديو كل 1.2 ث (من زمن البث)، والصور المتجددة حسب المصدر، والأرشيف دقيقة."""
    t = cam["source"].get("type")
    if t in VIDEO_TYPES:
        return 1.2
    if t == "datagovsg":
        return 60.0
    return float(cam["source"].get("burst_interval", 20.0))


def frames_for(cam) -> int:
    return VIDEO_FRAMES if cam["source"].get("type") in VIDEO_TYPES else FRAMES


def capture_all(plan, sources, workers: int = 12) -> list:
    """التقاط كل الكاميرات بالتوازي: أغلب الوقت انتظار تجدّد الصور، فلا داعي للتتابع."""
    def one(item):
        cam, at = item
        try:
            return sources.capture(cam, at, frames_for(cam), interval_for(cam))
        except Exception as e:  # يُمرَّر للتحليل فيُسجَّل كتعطّل للكاميرا
            return e
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, plan))


def analyze_all(plan, frames, kind_of, pipeline) -> tuple[int, int, list[str]]:
    done = failed = 0
    suspects = []
    for (cam, at), fr in zip(plan, frames):
        r = pipeline.run_capture(cam["id"], kind_of(cam, at), at, frames=fr)
        if r.get("ok"):
            done += 1
            log.info("%s -> CI %s", cam["id"], r.get("condition_index"))
            if r.get("suspect"):
                suspects.append(cam["id"])
        else:
            failed += 1
            log.warning("%s failed: %s", cam["id"], r.get("error") or r.get("quality"))
    return done, failed, suspects


def save_pending(config, ids: list[str]) -> None:
    (config.DATA_DIR / PENDING_FILE).write_text(json.dumps(sorted(set(ids))))


def load_pending(config) -> list[str]:
    try:
        return json.loads((config.DATA_DIR / PENDING_FILE).read_text())
    except (OSError, ValueError):
        return []


def day_key(cam, at, pipeline) -> str:
    return f"{at.astimezone(pipeline.tz(cam)).date().isoformat()}|{cam['id']}"


def load_attempts(config, now) -> dict:
    try:
        data = json.loads((config.DATA_DIR / ATTEMPTS_FILE).read_text())
    except (OSError, ValueError):
        return {}
    oldest = (now - timedelta(days=3)).date().isoformat()
    return {k: v for k, v in data.items() if k.split("|")[0] >= oldest}


def save_attempts(config, attempts: dict) -> None:
    (config.DATA_DIR / ATTEMPTS_FILE).write_text(json.dumps(attempts, sort_keys=True))


def plan_captures(cams, now, pipeline, sources, db, attempts, force=False) -> tuple[list, int]:
    """الكاميرات المستحقة الآن: في نافذة منطقتها، ولم تُحلَّل بنجاح اليوم، ولم تستنفد محاولاتها.
    كل تشغيل في النافذة فرصة جديدة: تشغيل مجدول قد يسقط، وكاميرا قد تكون متوقفة لحظتها.
    force (تحديث يدوي بعد تعديل الإعدادات): كل كاميرا حية في ضوء النهار الآن، ولو التُقطت اليوم."""
    from . import config
    plan, skipped = [], 0
    for cam in cams:
        live_force = force and not sources.supports_history(cam)  # الأرشيف لحظته ثابتة (10:00) فلا يُكرر
        at = capture_time(cam, now, pipeline, sources, config.DAYLIGHT_HOURS if live_force else None)
        if at is None:
            skipped += 1  # خارج نافذة 9–12 صباحًا في منطقتها (أو خارج النهار في التحديث اليدوي)
            continue
        if live_force:
            plan.append((cam, at))
            continue
        day = at.astimezone(pipeline.tz(cam)).replace(hour=0, minute=0, second=0, microsecond=0)
        if db.one("""SELECT id FROM snapshots WHERE camera_id=? AND ts>=? AND ts<? AND kind IN ('weekly','sentinel','seed')
                     AND condition_index IS NOT NULL""",
                  (cam["id"], day.astimezone(timezone.utc).isoformat(), (day + timedelta(days=1)).astimezone(timezone.utc).isoformat())):
            skipped += 1  # حُلّلت اليوم (لقطة مظلمة أو مزدحمة لا تُحسب: تُعاد في التشغيل التالي)
            continue
        if attempts.get(day_key(cam, at, pipeline), 0) >= MAX_TRIES:
            skipped += 1  # متعطلة طوال النافذة: يحاولها اليوم التالي
            continue
        plan.append((cam, at))
    return plan, skipped


def due(args) -> int:
    """يطبع ما يلزم تشغيله الآن: daily | confirm | none. يعتمد على المكتبة القياسية فقط،
    فيعمل قبل تثبيت PyTorch وينتهي التشغيل المجدول خلال ثوانٍ إن لم يكن هناك عمل."""
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo
    from . import config, db
    now = datetime.now(timezone.utc)
    cams = []
    for region, path in config.camera_files():
        for cam in json.loads(path.read_text(encoding="utf-8")).get("cameras", []):
            if cam.get("enabled", True):
                cams.append({**cam, "region": cam.get("region") or region})
    pl = SimpleNamespace(tz=lambda cam: ZoneInfo(config.tz_of(cam.get("region", ""))))
    src = SimpleNamespace(supports_history=lambda cam: cam["source"].get("type") in config.HISTORY_SOURCES)
    plan, _ = plan_captures(cams, now, pipeline=pl, sources=src, db=db, attempts=load_attempts(config, now))
    if plan:
        log.info("due: %d cameras (%s)", len(plan), ", ".join(sorted({c["region"] for c, _ in plan})))
        print("daily")
        return 0
    for cid in load_pending(config):
        last = db.one("SELECT ts, metrics FROM snapshots WHERE camera_id=? AND condition_index IS NOT NULL ORDER BY ts DESC LIMIT 1", (cid,))
        if last and json.loads(last["metrics"]).get("suspect"):
            age = now - datetime.fromisoformat(last["ts"])
            if max(CONFIRM_AFTER, timedelta(hours=1)) <= age <= timedelta(hours=6):
                print("confirm")
                return 0
    print("none")
    return 0


def build_site(args) -> None:
    if args.site:
        site = Path(args.site)
        from . import config
        (site / "models").mkdir(parents=True, exist_ok=True)
        for f in [*config.MODELS_DIR.glob("*.q8.onnx"), config.MODELS_DIR / "browser-models.json"]:
            if f.exists():  # نماذج المتصفح تُنشر مع الموقع (التحليل اللحظي لنماذج الطرق بالكاميرا)
                shutil.copy(f, site / "models" / f.name)
        env = {**os.environ}
        subprocess.run([sys.executable, str(ROOT / "tools" / "export_static.py"), str(site)], check=True, env=env)
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_static.py"), str(site), args.leaflet_css], check=True, env=env)


def prune_images(config, db) -> int:
    """يحذف الصور الأقدم من آخر KEEP_IMAGES لكل كاميرا لإبقاء التخزين صغيرًا (المقاييس في قاعدة البيانات تبقى)."""
    removed = 0
    for cam in db.query("SELECT DISTINCT camera_id FROM snapshots"):
        rows = db.query("SELECT image_path, annotated_path FROM snapshots WHERE camera_id=? ORDER BY ts DESC", (cam["camera_id"],))
        for r in rows[KEEP_IMAGES:]:
            for rel in (r["image_path"], r["annotated_path"]):
                if rel and (config.DATA_DIR / rel).exists():
                    (config.DATA_DIR / rel).unlink()
                    removed += 1
    return removed


def daily(args) -> int:
    from . import config, db, pipeline, sources
    config.ensure_dirs()
    pipeline.sync_cameras()
    seeded = pipeline.seed_history()  # أول تشغيل: سجل من الأرشيف للمصادر التي تدعمه
    if seeded:
        log.info("seeded %d archive captures", seeded)
    if os.getenv("GITHUB_REPOSITORY") and os.getenv("GITHUB_TOKEN"):  # بلاغات المواطنين عبر GitHub Issues (الموقع المجاني)
        from . import field
        try:
            log.info("field reports from GitHub: %d", field.ingest_github(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]))
        except Exception:
            log.exception("GitHub reports ingest failed")
    now = datetime.now(timezone.utc)
    attempts = load_attempts(config, now)
    plan, skipped = plan_captures(pipeline.cameras(), now, pipeline, sources, db, attempts, force=getattr(args, "now", False))
    log.info("capturing %d cameras (%d frames each, %d for video), skipped %d", len(plan), FRAMES, VIDEO_FRAMES, skipped)
    for cam, at in plan:
        key = day_key(cam, at, pipeline)
        attempts[key] = attempts.get(key, 0) + 1
    save_attempts(config, attempts)
    frames = capture_all(plan, sources)
    weekday_kind = lambda cam, at: "weekly" if at.astimezone(pipeline.tz(cam)).weekday() == 0 else "sentinel"
    done, failed, suspects = analyze_all(plan, frames, weekday_kind, pipeline)
    save_pending(config, load_pending(config) + suspects)
    log.info("risk refreshed for %d cameras (weather/pavement physics)", pipeline.refresh_risk())
    log.info("alerts backfilled for %d active issues", pipeline.backfill_issue_alerts())
    log.info("alerts no longer valid under current rules: %d", pipeline.revalidate_alerts())
    log.info("captured=%d skipped=%d failed=%d suspects=%d pruned_images=%d", done, skipped, failed, len(suspects), prune_images(config, db))
    build_site(args)
    return 0


def confirm(args) -> int:
    """إعادة التقاط الكاميرات المشتبه بها بعد ساعة: الحدث الذي يبقى في الالتقاطين يُطلق التنبيه،
    والعابر (مركبة متوقفة، ظل، أرض مبتلة) يسقط."""
    from . import config, db, pipeline, sources
    config.ensure_dirs()
    pipeline.sync_cameras()
    now = datetime.now(timezone.utc)
    cams = {c["id"]: c for c in pipeline.cameras()}
    plan, keep = [], []
    for cid in load_pending(config):
        cam = cams.get(cid)
        last = cam and db.one("SELECT ts, metrics FROM snapshots WHERE camera_id=? AND condition_index IS NOT NULL ORDER BY ts DESC LIMIT 1", (cid,))
        if not last or not json.loads(last["metrics"]).get("suspect"):
            continue  # أُكّد أو سقط في التقاط لاحق
        ts = datetime.fromisoformat(last["ts"])
        if now - ts > timedelta(hours=6):
            continue  # فات وقته: يحسمه الالتقاط اليومي التالي
        at = ts + timedelta(hours=1) if sources.supports_history(cam) else now
        if at > now or now - ts < CONFIRM_AFTER:
            keep.append(cid)  # لم تمضِ الساعة بعد
            continue
        plan.append((cam, at))
    log.info("confirming %d suspects (%d waiting)", len(plan), len(keep))
    frames = capture_all(plan, sources)
    done, failed, again = analyze_all(plan, frames, lambda cam, at: "sentinel", pipeline)
    save_pending(config, keep)  # اشتباه جديد في التأكيد لا يُعاد بلا نهاية: يحسمه اليوم التالي
    log.info("confirmed_runs=%d failed=%d new_suspects=%d", done, failed, len(again))
    build_site(args)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="python -m backend.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, help_ in (("daily", "التقاط يومي (5 إطارات) للمناطق التي في نافذة 9–12 صباحًا + تحليل + بناء الموقع"),
                        ("confirm", "إعادة التقاط الكاميرات المشتبه بها بعد ساعة"),
                        ("due", "ما المطلوب الآن: daily | confirm | none")):
        d = sub.add_parser(name, help=help_)
        d.add_argument("--regions", help="المناطق (يتجاوز DARB_REGIONS)")
        d.add_argument("--site", help="مجلد إخراج الموقع الثابت")
        d.add_argument("--leaflet-css", default=str(ROOT / "tools" / "leaflet.css"))
        if name == "daily":
            d.add_argument("--now", action="store_true", help="تحديث يدوي: كل كاميرا حية في ضوء النهار الآن، ولو التُقطت اليوم")
    args = p.parse_args()
    if args.regions:
        os.environ["DARB_REGIONS"] = args.regions  # قبل استيراد config
    os.environ.setdefault("DARB_CONFIRM_RECAPTURE", "0")
    os.environ.setdefault("DARB_SCHEDULER", "0")
    return {"confirm": confirm, "due": due}.get(args.cmd, daily)(args)


if __name__ == "__main__":
    raise SystemExit(main())
