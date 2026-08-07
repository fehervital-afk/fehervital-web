#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil, uuid
from pathlib import Path
from datetime import datetime, timezone

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
        q.setdefault("items", []).append({
            "id": str(uuid.uuid4()),
            "task_id": t.get("id"),
            "status": "ready",
            "risk": t.get("plan",{}).get("risk","high"),
            "summary": t.get("plan",{}).get("summary",""),
            "created_at": now(),
            "before": before,
            "after": after,
            "plan": t["plan"]
        })
        added += 1
    save(QUEUE, q)
    return added

def approve(item_id):
    q = load(QUEUE, {"version":1,"settings":{},"items":[],"history":[]})
    tasks = load(TASKS, {"tasks":[]})
    pages = load(PAGES,{})
    item = next((x for x in q.get("items",[]) if x.get("id")==item_id), None)
    if not item:
        raise SystemExit("Végrehajtási tétel nem található.")
    if item.get("status") not in {"ready","previewed"}:
        raise SystemExit("A tétel nem végrehajtható állapotban van.")

    backup = snapshot() if q.get("settings",{}).get("create_backup_before_apply",True) else None
    n = apply_changes(pages, item.get("plan") or {})
    save(PAGES, pages)
    item["status"] = "applied"
    item["applied_at"] = now()
    item["applied_changes"] = n
    item["backup"] = backup

    task = next((t for t in tasks.get("tasks",[]) if t.get("id")==item.get("task_id")), None)
    if task:
        task["status"] = "applied"
        task["applied_at"] = item["applied_at"]
        task["applied_changes"] = n
    save(TASKS, tasks)

    q.setdefault("history", []).append({
        "time": item["applied_at"],
        "event": "applied",
        "item_id": item["id"],
        "task_id": item.get("task_id"),
        "summary": item.get("summary",""),
        "backup": backup,
        "changes": n
    })
    q["history"] = q["history"][-200:]
    save(QUEUE, q)
    return {"ok":True,"changes":n,"backup":backup}

def reject(item_id):
    q = load(QUEUE, {"version":1,"settings":{},"items":[],"history":[]})
    tasks = load(TASKS, {"tasks":[]})
    item = next((x for x in q.get("items",[]) if x.get("id")==item_id), None)
    if not item:
        raise SystemExit("Végrehajtási tétel nem található.")
    item["status"] = "rejected"
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
    return {"ok":True,"backup":backup}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--approve")
    ap.add_argument("--reject")
    ap.add_argument("--rollback")
    args = ap.parse_args()

    if args.sync:
        print(json.dumps({"ok":True,"added":queue_from_tasks()},ensure_ascii=False))
    elif args.approve:
        print(json.dumps(approve(args.approve),ensure_ascii=False))
    elif args.reject:
        print(json.dumps(reject(args.reject),ensure_ascii=False))
    elif args.rollback:
        print(json.dumps(rollback(args.rollback),ensure_ascii=False))
    else:
        print(json.dumps({"ok":True,"added":queue_from_tasks()},ensure_ascii=False))

if __name__ == "__main__":
    main()
