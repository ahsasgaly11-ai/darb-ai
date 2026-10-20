"""تشغيل دَرْب AI دفعةً واحدة دون خادم دائم — للاستضافة المجانية (GitHub Actions أو أي مجدول).

    python -m backend.cli daily   --site site/   # الالتقاط اليومي (يُشغَّل كل بضع ساعات؛ يلتقط المناطق التي في نافذتها)
    python -m backend.cli confirm --site site/   # تأكيد الاشتباهات بعد ساعة

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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("darb.cli")
ROOT = Path(__file__).resolve().parent.parent
KEEP_IMAGES = int(os.getenv("DARB_KEEP_IMAGES", "10"))  # صور كل كاميرا المحفوظة على القرص (المقاييس تبقى كاملة)
FRAMES = int(os.getenv("DARB_DAILY_FRAMES", "5"))         # إطارات كل التقاط (للوسيط الزمني)
TARGET_HOUR = int(os.getenv("DARB_CAPTURE_HOUR", "10"))   # الساعة المحلية المستهدفة
WINDOW = (int(os.getenv("DARB_WINDOW_START", "9")), int(os.getenv("DARB_WINDOW_END", "12")))
CONFIRM_AFTER = timedelta(minutes=int(os.getenv("DARB_CONFIRM_AFTER_MIN", "50")))
PENDING_FILE = "pending_confirm.json"


def capture_time(cam, now_utc, pipeline, sources) -> datetime | None:
    """لحظة الالتقاط: العاشرة صباحًا محليًا للمصادر ذات الأرشيف، والآن للكاميرات الحية إن كانت في النافذة (9–12)."""
    tz = pipeline.tz(cam)
    local = now_utc.astimezone(tz)
    if sources.supports_history(cam) and cam["source"].get("type") != "demo":
        target = local.replace(hour=TARGET_HOUR, minute=0, second=0, microsecond=0)
        return (target if target <= local else target - timedelta(days=1)).astimezone(timezone.utc)
    return now_utc if WINDOW[0] <= local.hour < WINDOW[1] else None


def interval_for(cam) -> float:
    """الفاصل بين الإطارات: الفيديو كل 4 ثوانٍ، والصور المتجددة حسب المصدر، والأرشيف دقيقة."""
    t = cam["source"].get("type")
    if t in ("caltrans", "hls", "rtsp", "video", "mjpeg"):
        return 4.0
    if t == "datagovsg":
        return 60.0
    return float(cam["source"].get("burst_interval", 20.0))


def capture_all(plan, sources, workers: int = 12) -> list:
    """التقاط كل الكاميرات بالتوازي: أغلب الوقت انتظار تجدّد الصور، فلا داعي للتتابع."""
    def one(item):
        cam, at = item
        try:
            return sources.capture(cam, at, FRAMES, interval_for(cam))
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


def build_site(args) -> None:
    if args.site:
        site = Path(args.site)
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
    now = datetime.now(timezone.utc)
    plan, skipped = [], 0
    for cam in pipeline.cameras():
        at = capture_time(cam, now, pipeline, sources)
        if at is None:
            skipped += 1  # خارج نافذة 9–12 صباحًا في منطقتها
            continue
        local = at.astimezone(pipeline.tz(cam))
        day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
        day_end = (local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(timezone.utc).isoformat()
        if db.one("SELECT id FROM snapshots WHERE camera_id=? AND ts>=? AND ts<? AND kind IN ('weekly','sentinel','seed')",
                  (cam["id"], day_start, day_end)):
            skipped += 1  # التُقطت اليوم مسبقًا
            continue
        plan.append((cam, at))
    log.info("capturing %d cameras (%d frames each), skipped %d", len(plan), FRAMES, skipped)
    frames = capture_all(plan, sources)
    weekday_kind = lambda cam, at: "weekly" if at.astimezone(pipeline.tz(cam)).weekday() == 0 else "sentinel"
    done, failed, suspects = analyze_all(plan, frames, weekday_kind, pipeline)
    save_pending(config, load_pending(config) + suspects)
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
                        ("confirm", "إعادة التقاط الكاميرات المشتبه بها بعد ساعة")):
        d = sub.add_parser(name, help=help_)
        d.add_argument("--regions", help="المناطق (يتجاوز DARB_REGIONS)")
        d.add_argument("--site", help="مجلد إخراج الموقع الثابت")
        d.add_argument("--leaflet-css", default=str(ROOT / "tools" / "leaflet.css"))
    args = p.parse_args()
    if args.regions:
        os.environ["DARB_REGIONS"] = args.regions  # قبل استيراد config
    os.environ.setdefault("DARB_CONFIRM_RECAPTURE", "0")
    os.environ.setdefault("DARB_SCHEDULER", "0")
    return confirm(args) if args.cmd == "confirm" else daily(args)


if __name__ == "__main__":
    raise SystemExit(main())
