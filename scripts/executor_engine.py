#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil, subprocess, sys, uuid
from pathlib import Path
from datetime import datetime, timezone
from automation_policy import content_hash, evaluate_plan, write_audit_event

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "assets" / "content"
PAGES = CONTENT / "pages.json"
TASKS = CONTENT / "ai_tasks.json"
QUEUE = CONTENT / "execution_queue.json"
BACKUPS = ROOT / ".local_backups"

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def now():
    return datetime.now(timezone.utc).isoformat()

def snapshot():
    BACKUPS.mkdir(exist_ok=True)
    name = f"pages-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    target = BACKUPS / name
    shutil.copy2(PAGES, target)
    return str(target.relative_to(ROOT))

def apply_changes(pages, plan):
    changed = 0
    for ch in plan.get("changes", []) or []:
        slug = ch.get("page")
        if slug not in (pages.get("pages") or {}):
            continue
        p = pages["pages"][slug]
        action = ch.get("action")
        if action == "set_field":
            key = ch.get("key")
            for f in p.get("fields") or []:
                if f.get("key") == key:
                    f["value"] = str(ch.get("value",""))
                    changed += 1
                    break
        elif action == "add_block":
            block = ch.get("block")
            if isinstance(block, dict) and block.get("type"):
                p.setdefault("blocks", []).append(block)
                changed += 1
        elif action == "set_seo":
            seo = ch.get("seo")
            if isinstance(seo, dict):
                p.setdefault("seo", {}).update({k:v for k,v in seo.items() if k in {"title","description","keywords","og_image"}})
                changed += 1
    return changed

def build_preview(pages, plan):
    before = json.loads(json.dumps(pages))
    after = json.loads(json.dumps(pages))
    apply_changes(after, plan)
    return before, after

def run_validation():
    commands = (
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        [sys.executable, "scripts/build_public.py"],
    )
    results = []
    for command in commands:
        p = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, timeout=180)
        results.append({"command": " ".join(command[1:]), "returncode": p.returncode,
                        "output": (p.stdout or p.stderr or "")[-2000:]})
        if p.returncode != 0:
            return {"ok": False, "results": results}
    return {"ok": True, "results": results}

def queue_from_tasks():
    q = load(QUEUE, {"version":1,"settings":{},"items":[],"history":[]})
    tasks = load(TASKS, {"tasks":[]})
    existing = {str(x.get("task_id")) for x in q.get("items",[])}
    added = 0
    for t in tasks.get("tasks",[]):
        if t.get("status") != "waiting_approval" or not t.get("plan"):
            continue
        if str(t.get("id")) in existing:
            continue
        pages = load(PAGES,{})
        before, after = build_preview(pages, t["plan"])
        policy = evaluate_plan(t["plan"], approved=False, actor="executor_sync", autopilot=False)
        status = "blocked" if policy["risk"] == "BLOCKED" else "ready"
        q.setdefault("items", []).append({
            "id": str(uuid.uuid4()),
            "task_id": t.get("id"),
            "status": status,
            "risk": policy["risk"],
            "summary": t.get("plan",{}).get("summary",""),
            "created_at": now(),
            "before": before,
            "after": after,
            "plan": t["plan"],
            "policy": policy,
            "approval": {"required": policy["approval_required"], "status": "requested" if policy["approval_required"] else "not_required",
                         "approved_at": None, "approved_by": None, "policy_risk": policy["risk"],
                         "policy_reason": policy["reason"]}
        })
        write_audit_event("policy_checked", task_id=t.get("id", ""), actor="executor_sync", action="plan",
                          target="assets/content/pages.json", policy_risk=policy["risk"], result=status,
                          reason=policy["reason"])
        added += 1
    save(QUEUE, q)
    return added

def approve(item_id):
    # Backward-compatible entry point; all callers go through the hardened path.
    return secure_approve(item_id, actor="local_admin", autopilot=False)

def secure_approve(item_id, actor="local_admin", autopilot=False):
    q = load(QUEUE, {"version":1,"settings":{},"items":[],"history":[]})
    tasks = load(TASKS, {"tasks":[]})
    pages = load(PAGES,{})
    item = next((x for x in q.get("items",[]) if x.get("id")==item_id), None)
    if not item or item.get("status") not in {"ready", "previewed"}:
        raise SystemExit("Execution item is missing or not executable.")
    policy = evaluate_plan(item.get("plan") or {}, approved=not autopilot, actor=actor, autopilot=autopilot)
    write_audit_event("policy_checked", task_id=item.get("task_id", ""), actor=actor, action="plan",
                      target="assets/content/pages.json", policy_risk=policy["risk"],
                      result="allowed" if policy["allowed"] else "blocked", reason=policy["reason"])
    if not policy["allowed"]:
        item["status"] = "blocked"
        item["policy"] = policy
        save(QUEUE, q)
        write_audit_event("autopilot_blocked" if autopilot else "execution_blocked",
                          task_id=item.get("task_id", ""), actor=actor, action="plan",
                          target="assets/content/pages.json", policy_risk=policy["risk"],
                          result="blocked", reason=policy["reason"])
        raise SystemExit("Policy blocked: " + policy["reason"])

    backup = snapshot() if q.get("settings",{}).get("create_backup_before_apply",True) else None
    before_hash = content_hash(pages)
    approved_at = now()
    item["policy"] = policy
    item["approval"] = {"required": policy["approval_required"], "status": "approved",
                        "approved_at": approved_at, "approved_by": actor, "policy_risk": policy["risk"],
                        "policy_reason": policy["reason"]}
    write_audit_event("approved", task_id=item.get("task_id", ""), actor=actor, action="plan",
                      target="assets/content/pages.json", policy_risk=policy["risk"], result="approved",
                      reason=policy["reason"])
    write_audit_event("execution_started", task_id=item.get("task_id", ""), actor=actor, action="plan",
                      target="assets/content/pages.json", policy_risk=policy["risk"], result="started",
                      reason="Executor policy recheck passed.")
    n = apply_changes(pages, item.get("plan") or {})
    save(PAGES, pages)
    item.update({"status": "validating", "applied_at": now(), "applied_changes": n, "backup": backup})
    write_audit_event("change_applied", task_id=item.get("task_id", ""), actor=actor, action="plan",
                      target="assets/content/pages.json", policy_risk=policy["risk"], result="applied",
                      reason=f"Applied {n} changes.", details={"before_hash": before_hash, "after_hash": content_hash(pages)})
    write_audit_event("validation_started", task_id=item.get("task_id", ""), actor="validator", action="validate",
                      target="working_tree", policy_risk=policy["risk"], result="started",
                      reason="Running pytest and public build.")
    validation = run_validation()
    item["validation"] = validation
    if validation["ok"]:
        item["status"] = "applied"
        item["publish_ready"] = False
        write_audit_event("validation_passed", task_id=item.get("task_id", ""), actor="validator", action="validate",
                          target="working_tree", policy_risk=policy["risk"], result="passed",
                          reason="Tests and public build passed.")
    else:
        item["status"] = "validation_failed"
        item["publish_ready"] = False
        write_audit_event("validation_failed", task_id=item.get("task_id", ""), actor="validator", action="validate",
                          target="working_tree", policy_risk=policy["risk"], result="failed",
                          reason="Tests or public build failed.", details=validation)
        if backup:
            write_audit_event("rollback_started", task_id=item.get("task_id", ""), actor="executor", action="rollback",
                              target="assets/content/pages.json", policy_risk=policy["risk"], result="started",
                              reason="Validation failed.")
            shutil.copy2(ROOT / backup, PAGES)
            item["rolled_back_at"] = now()
            write_audit_event("rollback_completed", task_id=item.get("task_id", ""), actor="executor", action="rollback",
                              target="assets/content/pages.json", policy_risk=policy["risk"], result="completed",
                              reason="Restored pre-change snapshot.")

    task = next((t for t in tasks.get("tasks",[]) if t.get("id")==item.get("task_id")), None)
    if task:
        task["status"] = item["status"]
        task["approval"] = item["approval"]
        task["updated_at"] = now()
    save(TASKS, tasks)
    q.setdefault("history", []).append({"time": now(), "event": item["status"], "item_id": item["id"],
                                         "task_id": item.get("task_id"), "summary": item.get("summary", ""),
                                         "backup": backup, "changes": n})
    q["history"] = q["history"][-200:]
    save(QUEUE, q)
    return {"ok": validation["ok"], "changes": n, "backup": backup,
            "status": item["status"], "validation": validation}

def reject(item_id):
    q = load(QUEUE, {"version":1,"settings":{},"items":[],"history":[]})
    tasks = load(TASKS, {"tasks":[]})
    item = next((x for x in q.get("items",[]) if x.get("id")==item_id), None)
    if not item:
        raise SystemExit("Végrehajtási tétel nem található.")
    item["status"] = "rejected"
    write_audit_event("rejected", task_id=item.get("task_id", ""), actor="local_admin", action="plan",
                      target="assets/content/pages.json", policy_risk=(item.get("policy") or {}).get("risk", item.get("risk", "")),
                      result="rejected", reason="Human rejected the execution item.")
    item["updated_at"] = now()
    task = next((t for t in tasks.get("tasks",[]) if t.get("id")==item.get("task_id")), None)
    if task:
        task["status"] = "rejected"
        task["updated_at"] = now()
    save(TASKS, tasks)
    q.setdefault("history", []).append({
        "time": now(),
        "event": "rejected",
        "item_id": item["id"],
        "task_id": item.get("task_id"),
        "summary": item.get("summary","")
    })
    save(QUEUE, q)
    return {"ok":True}

def rollback(item_id):
    q = load(QUEUE, {"version":1,"settings":{},"items":[],"history":[]})
    item = next((x for x in q.get("items",[]) if x.get("id")==item_id), None)
    if not item:
        raise SystemExit("Tétel nem található.")
    backup = item.get("backup")
    if not backup:
        raise SystemExit("Ehhez a tételhez nincs biztonsági mentés.")
    source = ROOT / backup
    if not source.exists():
        raise SystemExit("A biztonsági mentés fájlja nem található.")
    write_audit_event("rollback_started", task_id=item.get("task_id", ""), actor="local_admin", action="rollback",
                      target="assets/content/pages.json", policy_risk=(item.get("policy") or {}).get("risk", item.get("risk", "")),
                      result="started", reason="Human requested rollback.")
    shutil.copy2(source, PAGES)
    item["status"] = "rolled_back"
    item["rolled_back_at"] = now()
    q.setdefault("history", []).append({
        "time": now(),
        "event": "rolled_back",
        "item_id": item["id"],
        "task_id": item.get("task_id"),
        "backup": backup
    })
    save(QUEUE, q)
    write_audit_event("rollback_completed", task_id=item.get("task_id", ""), actor="local_admin", action="rollback",
                      target="assets/content/pages.json", policy_risk=(item.get("policy") or {}).get("risk", item.get("risk", "")),
                      result="completed", reason="Snapshot restored.")
    return {"ok":True,"backup":backup}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--approve")
    ap.add_argument("--reject")
    ap.add_argument("--rollback")
    ap.add_argument("--actor", default="local_admin")
    ap.add_argument("--autopilot", action="store_true")
    args = ap.parse_args()

    if args.sync:
        print(json.dumps({"ok":True,"added":queue_from_tasks()},ensure_ascii=False))
    elif args.approve:
        print(json.dumps(secure_approve(args.approve, actor=args.actor, autopilot=args.autopilot),ensure_ascii=False))
    elif args.reject:
        print(json.dumps(reject(args.reject),ensure_ascii=False))
    elif args.rollback:
        print(json.dumps(rollback(args.rollback),ensure_ascii=False))
    else:
        print(json.dumps({"ok":True,"added":queue_from_tasks()},ensure_ascii=False))

if __name__ == "__main__":
    main()
