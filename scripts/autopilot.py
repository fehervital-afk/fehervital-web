#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "assets" / "content"
AUTOPILOT = CONTENT / "autopilot.json"
QUEUE = CONTENT / "execution_queue.json"
MARKETING = CONTENT / "marketing.json"
AUDIT = CONTENT / "ai_audit.json"

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def now():
    return datetime.now(timezone.utc).isoformat()

def run_py(script, *args):
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=str(ROOT), capture_output=True, text=True, timeout=180
    )
    return p

def overall_score():
    m = load(MARKETING, {})
    return int((m.get("scores") or {}).get("overall") or 0)

def append_history(ap, event, message, details=None):
    ap.setdefault("history", []).append({
        "time": now(),
        "event": event,
        "message": message,
        "details": details or {}
    })
    ap["history"] = ap["history"][-300:]

def sync_executor():
    p = run_py("executor_engine.py", "--sync")
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "Executor sync hiba").strip())
    try:
        return json.loads((p.stdout or "{}").strip())
    except Exception:
        return {"ok":True,"added":0}

def run_marketing():
    p = run_py("marketing_manager.py", "--analyze", "--no-ai")
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "Marketing ellenőrzés hiba").strip())

def run_audit():
    p = run_py("ai_webmaster.py", "--audit")
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "Audit hiba").strip())

def apply_low_risk(ap):
    q = load(QUEUE, {"items":[]})
    applied = []
    for item in q.get("items", []):
        if item.get("status") not in {"ready","previewed"}:
            continue
        if item.get("risk") != "low":
            continue

        before_score = overall_score()

        p = run_py("executor_engine.py", "--approve", str(item.get("id")))
        if p.returncode != 0:
            raise RuntimeError((p.stderr or p.stdout or "Automatikus végrehajtási hiba").strip())

        run_audit()
        run_marketing()
        after_score = overall_score()

        rolled_back = False
        drop = before_score - after_score
        if ap.get("rollback_on_score_drop", True) and drop > int(ap.get("max_score_drop",3) or 3):
            rb = run_py("executor_engine.py", "--rollback", str(item.get("id")))
            if rb.returncode == 0:
                rolled_back = True
                ap.setdefault("stats",{}).setdefault("rolled_back",0)
                ap["stats"]["rolled_back"] += 1
                run_audit()
                run_marketing()

        applied.append({
            "item_id": item.get("id"),
            "before_score": before_score,
            "after_score": after_score,
            "score_drop": drop,
            "rolled_back": rolled_back
        })
        if not rolled_back:
            ap.setdefault("stats",{}).setdefault("auto_applied",0)
            ap["stats"]["auto_applied"] += 1

    return applied

def run_once(force=False):
    ap = load(AUTOPILOT, {})
    ap.setdefault("stats", {"runs":0,"synced":0,"auto_applied":0,"rolled_back":0,"errors":0})
    ap["last_run"] = now()
    ap["stats"]["runs"] = int(ap["stats"].get("runs",0)) + 1

    if not ap.get("enabled") and not force:
        result = {"status":"disabled","message":"Az Autopilot ki van kapcsolva."}
        ap["last_result"] = result
        append_history(ap, "skipped", result["message"])
        save(AUTOPILOT, ap)
        return result

    try:
        run_audit()
        run_marketing()
        sync = sync_executor()
        added = int(sync.get("added",0) or 0)
        ap["stats"]["synced"] = int(ap["stats"].get("synced",0)) + added

        applied = []
        if ap.get("mode") == "safe_auto" and ap.get("auto_apply_low_risk"):
            applied = apply_low_risk(ap)

        result = {
            "status":"ok",
            "synced": added,
            "auto_applied": len([x for x in applied if not x.get("rolled_back")]),
            "rolled_back": len([x for x in applied if x.get("rolled_back")]),
            "overall_score": overall_score()
        }
        ap["last_result"] = result
        append_history(ap, "run", "Autopilot ciklus sikeresen lefutott.", result)
        save(AUTOPILOT, ap)
        return result

    except Exception as e:
        ap["stats"]["errors"] = int(ap["stats"].get("errors",0)) + 1
        result = {"status":"error","error":str(e)}
        ap["last_result"] = result
        append_history(ap, "error", str(e))
        save(AUTOPILOT, ap)
        raise

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_once(force=args.force)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
