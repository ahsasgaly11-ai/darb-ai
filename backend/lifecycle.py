"""دورة حياة مشكلات الطريق: قبل ← أثناء ← بعد.

تتبّع العيوب (tracks): كل عيب مكتشَف يُطابَق مع عيوب اللقطات السابقة بموقعه (تداخل المربعات)،
فيصبح له تاريخ: أول ظهور، آخر ظهور، عدد مرات الرصد، ونمو مساحته. العيب «مؤكَّد» بعد رصده
في لقطتين، ويُعدّ «زائلًا» إذا غاب لقطتين متتاليتين.

المشكلات (issues) ومراحلها:
  predicted  قبل:  نموذج المخاطر يتوقع بلوغ عتبة الصيانة خلال PREDICT_HORIZON_WEEKS.
  active     أثناء: تحقّقت (المؤشر دون العتبة) أو وقع حدث مفاجئ مؤكَّد أو ظهرت حفرة مؤكَّدة.
  monitoring بعد:  رُصد زوالها (إصلاح أو إزالة) ويُراقَب المقطع POST_REPAIR_WEEKS لرصد عودة العيب.
  closed     انتهت المراقبة دون عودة، أو لم يتحقق التوقع.
وتُحسب مؤشرات الأداء: مدة سبق التنبؤ للحدث، وزمن الاستجابة حتى الإصلاح، ونسبة العودة بعد الإصلاح.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from . import config, db

log = logging.getLogger("darb.lifecycle")

STAGE_AR = {"predicted": "متوقعة", "active": "نشطة", "monitoring": "مراقبة بعد المعالجة", "closed": "مغلقة"}
KIND_AR = {"deterioration": "تدهور الرصف", "pothole": "حفرة", "sudden": "تغيّر مفاجئ", "cracking": "تشققات"}
RESOLUTION_AR = {"repaired": "أُصلحت", "cleared": "أُزيلت", "not_occurred": "لم يتحقق التوقع", "recurred": "عادت بعد الإصلاح",
                 "merged": "دُمجت في مشكلة التدهور", "prevented": "عولجت وقائيًا قبل وقوعها"}
FAMILY = {"crack_long": "crack", "crack_trans": "crack", "alligator": "crack", "pothole": "pothole"}


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    return inter / max(1, aw * ah + bw * bh - inter)


def _near(a, b) -> bool:
    """تطابق متسامح: تداخل كافٍ، أو احتواء مربع لآخر (العيب ينمو أو يُكتشف جزء منه)."""
    if _iou(a, b) > 0.2:
        return True
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    cx, cy = ax + aw / 2, ay + ah / 2
    return bx <= cx <= bx + bw and by <= cy <= by + bh


def _weeks(a: str, b: str) -> float:
    return round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 604800, 1)


# ---------- تتبّع العيوب ----------

def update_tracks(cam_id: str, ts: str, detections: list[dict], repairs: list[dict]) -> dict:
    open_tracks = [db.loads(t, "bbox", "areas") for t in
                   db.query("SELECT * FROM tracks WHERE camera_id=? AND status IN ('tentative','confirmed')", (cam_id,))]
    matched, newly_confirmed, gone = set(), [], []
    with db.tx() as c:
        for d in sorted(detections, key=lambda d: -d["area"]):
            fam = FAMILY.get(d["type"], "crack")
            t = next((t for t in open_tracks if t["id"] not in matched and FAMILY.get(t["type"], "crack") == fam
                      and _near(t["bbox"], d["bbox"])), None)
            if t is None:
                tid = c.execute("""INSERT INTO tracks(camera_id,type,bbox,first_ts,last_ts,status,areas,confidence)
                                   VALUES (?,?,?,?,?,'tentative',?,?)""",
                                (cam_id, d["type"], json.dumps(d["bbox"]), ts, ts, json.dumps([[ts, d["area"]]]),
                                 d.get("confidence", 0))).lastrowid
                matched.add(tid)
                continue
            matched.add(t["id"])
            status = "confirmed" if t["hits"] + 1 >= 2 else "tentative"
            if status == "confirmed" and t["status"] == "tentative":
                newly_confirmed.append({**t, "type": d["type"], "bbox": d["bbox"]})
            kind = "alligator" if "alligator" in (t["type"], d["type"]) else d["type"]  # التمساحي أخطر — لا يتراجع الوصف
            c.execute("""UPDATE tracks SET type=?, bbox=?, last_ts=?, hits=hits+1, misses=0, status=?, areas=?,
                         confidence=MAX(confidence, ?) WHERE id=?""",
                      (kind, json.dumps(d["bbox"]), ts, status, json.dumps((t["areas"] + [[ts, d["area"]]])[-60:]),
                       d.get("confidence", 0), t["id"]))
        for t in open_tracks:
            if t["id"] in matched:
                continue
            if t["misses"] + 1 >= 2:
                if t["status"] == "tentative":
                    c.execute("DELETE FROM tracks WHERE id=?", (t["id"],))  # ظهر مرة واحدة: ضجيج
                    continue
                fixed = any(_near(t["bbox"], r["bbox"]) for r in repairs)
                status = "repaired" if fixed else "gone"
                c.execute("UPDATE tracks SET misses=misses+1, status=? WHERE id=?", (status, t["id"]))
                gone.append({**t, "status": status})
            else:
                c.execute("UPDATE tracks SET misses=misses+1 WHERE id=?", (t["id"],))
    return {"newly_confirmed": newly_confirmed, "gone": gone}


def growth(track: dict) -> float | None:
    """نسبة نمو مساحة العيب أسبوعيًا (انحدار بسيط على آخر الرصدات)."""
    pts = track["areas"] if isinstance(track["areas"], list) else json.loads(track["areas"])
    if len(pts) < 3:
        return None
    t0 = datetime.fromisoformat(pts[0][0])
    xs = [(datetime.fromisoformat(p[0]) - t0).total_seconds() / 604800 for p in pts]
    ys = [p[1] for p in pts]
    if max(xs) - min(xs) < 1:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / max(1e-9, sum((x - mx) ** 2 for x in xs))
    return round(100 * slope / max(my, 1), 1)


# ---------- المشكلات ----------

def _open_issues(cam_id: str) -> list[dict]:
    return [db.loads(i, "track_ids", "events") for i in
            db.query("SELECT * FROM issues WHERE camera_id=? AND stage IN ('predicted','active','monitoring')", (cam_id,))]


def _save(issue: dict) -> None:
    cols = [k for k in issue if k != "id"]
    vals = [json.dumps(issue[k], ensure_ascii=False) if isinstance(issue[k], (list, dict)) else issue[k] for k in cols]
    with db.tx() as c:
        c.execute(f"UPDATE issues SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?", vals + [issue["id"]])


def _new(cam_id: str, kind: str, stage: str, severity: str, title: str, ts: str, **kw) -> dict:
    row = {"camera_id": cam_id, "kind": kind, "stage": stage, "severity": severity, "title": title,
           "events": [{"ts": ts, "stage": stage, "note": kw.pop("note", "")}], "track_ids": kw.pop("track_ids", []), **kw}
    row["id"] = db.insert("issues", row)
    return row


def _event(issue: dict, ts: str, stage: str, note: str) -> None:
    issue["events"] = issue["events"] + [{"ts": ts, "stage": stage, "note": note}]


def update(cam: dict, ts: str, result: dict, assessment: dict | None, alerts: list[dict], add_alert) -> list[dict]:
    """يُستدعى بعد كل لقطة صالحة. يعيد قائمة بالتغيّرات (للسجل والاختبارات)."""
    cam_id = cam["id"]
    changes = []
    tr = update_tracks(cam_id, ts, result["detections"], result.get("repairs", []))
    thr = config.MAINTENANCE_THRESHOLD
    ci = assessment["ci"] if assessment else result["condition_index"]
    weeks_to = assessment.get("weeks_to_threshold") if assessment else None
    issues = _open_issues(cam_id)
    by_kind = lambda k, stages: [i for i in issues if i["kind"] == k and i["stage"] in stages]  # noqa: E731

    for i in issues:
        if i["stage"] == "active":
            i["worst_ci"] = min(i["worst_ci"] if i["worst_ci"] is not None else ci, ci)
        i["last_ci"] = ci

    # ---------- بعد: انتهاء المراقبة أو عودة المشكلة ----------
    for i in [i for i in issues if i["stage"] == "monitoring"]:
        recurred = (i["kind"] == "deterioration" and ci <= thr) or (
            i["kind"] in ("sudden", "pothole") and any(a["type"] in ("sudden_change", "new_pothole") and a["severity"] == "critical"
                                                       for a in alerts))
        if recurred:
            i.update(stage="closed", closed_ts=ts, resolution="recurred")
            _event(i, ts, "closed", "عادت المشكلة خلال فترة المراقبة بعد الإصلاح")
            _save(i)
            add_alert(cam, ts, "recurrence", "warning",
                      f"عادت مشكلة «{KIND_AR[i['kind']]}» بعد {_weeks(i['resolved_ts'], ts):.0f} أسبوع من رصد معالجتها — "
                      "يوصى بمراجعة جودة الإصلاح.")
            changes.append(("recurred", i["id"]))
        elif _weeks(i["resolved_ts"], ts) >= config.POST_REPAIR_WEEKS:
            i.update(stage="closed", closed_ts=ts)
            _event(i, ts, "closed", f"انتهت مراقبة ما بعد المعالجة ({config.POST_REPAIR_WEEKS} أسابيع) دون عودة")
            _save(i)
            changes.append(("closed", i["id"]))
    issues = [i for i in issues if i["stage"] != "closed"]

    # ---------- قبل: تنبؤ بتدهور قادم ----------
    det = by_kind("deterioration", ("predicted", "active"))
    if weeks_to is not None and 0 < weeks_to <= config.PREDICT_HORIZON_WEEKS and ci > thr and not det:
        expected = (datetime.fromisoformat(ts) + timedelta(weeks=weeks_to)).isoformat(timespec="seconds")
        i = _new(cam_id, "deterioration", "predicted", "warning" if weeks_to > 4 else "critical",
                 f"تدهور متوقع: بلوغ عتبة الصيانة خلال ~{weeks_to:.0f} أسبوع", ts,
                 predicted_ts=ts, expected_ts=expected, baseline_ci=ci, last_ci=ci,
                 note=f"المؤشر المُنعَّم {ci:.0f}، والاتجاه {assessment['ci_slope']:+.2f} نقطة/أسبوع")
        add_alert(cam, ts, "predicted", "info",
                  f"يتوقع النموذج بلوغ عتبة الصيانة ({thr:.0f}) قرابة {expected[:10]} — فرصة لصيانة وقائية أقل كلفة.")
        changes.append(("predicted", i["id"]))
    for i in by_kind("deterioration", ("predicted",)):
        if i["baseline_ci"] is not None and ci - i["baseline_ci"] >= 15:
            # تحسّن كبير قبل وقوع المتوقع = صيانة وقائية (النتيجة المثلى لمرحلة «قبل»)
            i.update(stage="closed", closed_ts=ts, resolved_ts=ts, resolution="prevented")
            _event(i, ts, "closed", f"عولج وقائيًا قبل وقوعه — ارتفع المؤشر من {i['baseline_ci']:.0f} إلى {ci:.0f}")
            changes.append(("prevented", i["id"]))
        elif weeks_to is None or weeks_to > 2 * config.PREDICT_HORIZON_WEEKS:
            # الاتجاه استقر أو تباطأ كثيرًا: لم يعد التدهور متوقعًا ضمن الأفق
            i.update(stage="closed", closed_ts=ts, resolution="not_occurred")
            _event(i, ts, "closed", "تباطأ التدهور ولم يعد بلوغ العتبة متوقعًا ضمن الأفق")
            changes.append(("not_occurred", i["id"]))
        elif weeks_to > 0:
            new_exp = (datetime.fromisoformat(ts) + timedelta(weeks=weeks_to)).isoformat(timespec="seconds")
            if abs(_weeks(i["expected_ts"], new_exp)) >= 4:
                _event(i, ts, "predicted", f"تحديث الموعد المتوقع إلى {new_exp[:10]}")
            i["expected_ts"] = new_exp

    # ---------- أثناء: حدث مفاجئ مؤكَّد / حفرة مؤكَّدة ----------
    sudden = [a for a in alerts if a["type"] in ("sudden_change", "new_pothole") and a["severity"] in ("critical", "warning")]
    pothole_tracks = [t for t in tr["newly_confirmed"] if t["type"] == "pothole"]
    if (sudden or pothole_tracks) and not by_kind("sudden", ("active",)) and not by_kind("pothole", ("active",)):
        kind = "pothole" if pothole_tracks or any(a["type"] == "new_pothole" for a in sudden) else "sudden"
        prev = db.one("""SELECT condition_index FROM snapshots WHERE camera_id=? AND condition_index IS NOT NULL
                         AND ts<? ORDER BY ts DESC LIMIT 1 OFFSET 1""", (cam_id, ts))
        msg = sudden[0]["message"] if sudden else "حفرة رُصدت في لقطتين متتاليتين"
        i = _new(cam_id, kind, "active", "critical" if kind == "pothole" or (sudden and sudden[0]["severity"] == "critical") else "warning",
                 f"{KIND_AR[kind]} — رُصد أثناء المراقبة", ts, detected_ts=ts,
                 baseline_ci=prev["condition_index"] if prev else None, worst_ci=result["condition_index"],
                 last_ci=result["condition_index"], track_ids=[t["id"] for t in pothole_tracks], note=msg[:200])
        issues.append(i)
        changes.append(("sudden-active", i["id"]))

    # ---------- أثناء: تحقق التدهور ----------
    # هبوط سببه حدث مفاجئ (حفرة/مخلّفات) يُتابَع ضمن مشكلته ولا يُفتح له «تدهور» منفصل
    sudden_now = [i for i in issues if i["stage"] == "active" and i["kind"] in ("sudden", "pothole")
                  and i.get("detected_ts") and _weeks(i["detected_ts"], ts) <= 2]
    if ci <= thr and not sudden_now:
        pred = by_kind("deterioration", ("predicted",))
        if pred:
            i = pred[0]
            lead = _weeks(i["predicted_ts"], ts)
            i.update(stage="active", detected_ts=ts, worst_ci=ci, severity="critical")
            i["title"] = "تدهور الرصف: دون عتبة الصيانة (تحقق التنبؤ)"
            _event(i, ts, "active", f"تحقق التنبؤ — سبقه النظام بـ {lead:.0f} أسبوع")
            changes.append(("predicted->active", i["id"]))
        elif not by_kind("deterioration", ("active",)):
            i = _new(cam_id, "deterioration", "active", "critical", "تدهور الرصف: دون عتبة الصيانة", ts,
                     detected_ts=ts, baseline_ci=ci, worst_ci=ci, last_ci=ci, note="رُصد دون تنبؤ سابق")
            issues.append(i)
            changes.append(("active", i["id"]))

    # التغيّر «المستمر» التدريجي يُدمج في مشكلة التدهور النشطة بدل أن يبقى مشكلة مستقلة مفتوحة
    active_det = by_kind("deterioration", ("active",))
    if active_det:
        for i in [i for i in issues if i["stage"] == "active" and i["kind"] == "sudden" and not i["track_ids"]
                  and i.get("detected_ts") != ts]:
            i.update(stage="closed", closed_ts=ts, resolution="merged")
            _event(i, ts, "closed", f"دُمجت في مشكلة التدهور #{active_det[0]['id']}")
            changes.append(("merged", i["id"]))

    # ---------- بعد: رصد المعالجة تلقائيًا ----------
    gone_ids = {t["id"] for t in tr["gone"]}
    repaired_ids = {t["id"] for t in tr["gone"] if t["status"] == "repaired"}
    for i in [i for i in issues if i["stage"] == "active"]:
        resolved, resolution = False, None
        if i["kind"] == "deterioration":
            # إعادة رصف: قفزة كبيرة في المؤشر فوق العتبة بوضوح
            if ci >= thr + 15 and ci - (i["worst_ci"] or ci) >= 15:
                resolved, resolution = True, "repaired"
        else:
            raw_ci = result["condition_index"]
            back = i["baseline_ci"] is not None and raw_ci >= i["baseline_ci"] - 3
            tracks_gone = bool(i["track_ids"]) and set(i["track_ids"]) <= (gone_ids | {
                t["id"] for t in db.query("SELECT id FROM tracks WHERE camera_id=? AND status IN ('gone','repaired')", (cam_id,))})
            prev_back = i.get("_back_once") or any(e["note"] == "عاد المؤشر لمستواه" for e in i["events"])
            if tracks_gone or (back and prev_back):
                resolved = True
                resolution = "repaired" if (i["kind"] == "pothole" or set(i["track_ids"]) & repaired_ids) else "cleared"
            elif back:
                _event(i, ts, "active", "عاد المؤشر لمستواه")
        if resolved:
            dur = _weeks(i["detected_ts"], ts)
            i.update(stage="monitoring", resolved_ts=ts, resolution=resolution)
            _event(i, ts, "monitoring", f"{RESOLUTION_AR[resolution]} — بعد {dur * 7:.0f} يوم من رصدها؛ تبدأ مراقبة "
                                         f"{config.POST_REPAIR_WEEKS} أسابيع لرصد أي عودة")
            add_alert(cam, ts, "resolved", "info",
                      f"رُصد زوال «{KIND_AR[i['kind']]}» ({RESOLUTION_AR[resolution]}) بعد {dur * 7:.0f} يوم. "
                      f"يستمر النظام بمراقبة المقطع {config.POST_REPAIR_WEEKS} أسابيع.")
            changes.append(("resolved", i["id"]))

    for i in issues:
        i.pop("_back_once", None)
        if i.get("id"):
            _save(i)
    return changes


def maintenance_logged(cam: dict, date: str, action: str) -> int:
    """تسجيل صيانة يدويًا يغلق المشكلات النشطة كـ«أُصلحت» ويبدأ مراقبة ما بعد الإصلاح."""
    n = 0
    ts = f"{date}T12:00:00+00:00"
    for i in _open_issues(cam["id"]):
        if i["stage"] in ("active", "predicted"):
            i.update(stage="monitoring", resolved_ts=ts, resolution="repaired")
            if not i.get("detected_ts"):
                i["detected_ts"] = ts  # صيانة وقائية قبل وقوع المتوقع
            _event(i, ts, "monitoring", f"صيانة مسجّلة: {action}")
            _save(i)
            n += 1
    return n


def kpis(region_cams: list[str] | None = None) -> dict:
    rows = db.query("SELECT * FROM issues")
    if region_cams is not None:
        rows = [r for r in rows if r["camera_id"] in region_cams]
    stages = {k: sum(1 for r in rows if r["stage"] == k) for k in STAGE_AR}
    leads = [_weeks(r["predicted_ts"], r["detected_ts"]) for r in rows if r["predicted_ts"] and r["detected_ts"]]
    fix = [_weeks(r["detected_ts"], r["resolved_ts"]) * 7 for r in rows if r["detected_ts"] and r["resolved_ts"]]
    predicted = [r for r in rows if r["predicted_ts"]]
    # تحقق التنبؤ أو عولج وقائيًا = تنبؤ مفيد؛ تباطأ دون تدخل = لم يتحقق
    hit = [r for r in predicted if r["detected_ts"] or r["resolution"] == "prevented"]
    miss = [r for r in predicted if r["resolution"] == "not_occurred"]
    resolved = [r for r in rows if r["resolved_ts"]]
    return {
        "stages": stages,
        "avg_lead_weeks": round(sum(leads) / len(leads), 1) if leads else None,
        "avg_days_to_resolve": round(sum(fix) / len(fix), 1) if fix else None,
        "prediction_precision": round(len(hit) / (len(hit) + len(miss)), 2) if (hit or miss) else None,
        "recurrence_rate": round(sum(1 for r in resolved if r["resolution"] == "recurred") / len(resolved), 2) if resolved else None,
        "prevented": sum(1 for r in rows if r["resolution"] == "prevented"),
        "predicted_total": len(predicted), "unpredicted_active": sum(1 for r in rows if r["detected_ts"] and not r["predicted_ts"]),
    }
