#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, sys, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "assets" / "content"
PAGES = CONTENT / "pages.json"
CONFIG = CONTENT / "automation.json"
TASKS = CONTENT / "ai_tasks.json"
AUDIT = CONTENT / "ai_audit.json"
LOG = CONTENT / "ai_log.json"

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def extract_response_text(data):
    if isinstance(data, dict):
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        parts = []
        for item in data.get("output", []) or []:
            for c in item.get("content", []) or []:
                txt = c.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
        return "\n".join(parts)
    return ""

def call_openai(prompt, model):
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY nincs beállítva.")
    body = json.dumps({
        "model": os.getenv("OPENAI_MODEL", model or "gpt-5"),
        "input": [
            {
                "role": "system",
                "content": (
                    "You are an AI webmaster for a Hungarian wellness website. "
                    "Return ONLY valid JSON. Never create medical diagnoses, treatment promises, "
                    "or claims of curing disease. Preserve legal/wellness framing."
                )
            },
            {"role": "user", "content": prompt}
        ]
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read().decode("utf-8"))
    return extract_response_text(data)

def clean_json_text(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def utcnow():
    return datetime.now(timezone.utc).isoformat()

def append_log(event, message, task_id=None, details=None):
    data = load(LOG, {"version": 1, "entries": []})
    entry = {
        "time": utcnow(),
        "event": event,
        "message": message
    }
    if task_id:
        entry["task_id"] = task_id
    if details is not None:
        entry["details"] = details
    data.setdefault("entries", []).append(entry)
    data["entries"] = data["entries"][-300:]
    save(LOG, data)

def validate_plan(plan, pages):
    errors = []
    if not isinstance(plan, dict):
        return ["A terv nem JSON objektum."]
    if plan.get("risk") not in {"low", "medium", "high"}:
        errors.append("Érvénytelen kockázati szint.")
    changes = plan.get("changes")
    if not isinstance(changes, list):
        errors.append("A changes mezőnek listának kell lennie.")
        return errors
    allowed_actions = {"set_field", "add_block", "set_seo"}
    allowed_blocks = {"text","image","video","iconbox","testimonial","price","buttons","divider","cta","faq"}
    page_names = set((pages.get("pages") or {}).keys())
    for i, ch in enumerate(changes):
        if not isinstance(ch, dict):
            errors.append(f"{i+1}. módosítás nem objektum.")
            continue
        if ch.get("action") not in allowed_actions:
            errors.append(f"{i+1}. módosítás ismeretlen művelet.")
        if ch.get("page") not in page_names:
            errors.append(f"{i+1}. módosítás ismeretlen oldalra mutat.")
        if ch.get("action") == "add_block":
            block = ch.get("block")
            if not isinstance(block, dict) or block.get("type") not in allowed_blocks:
                errors.append(f"{i+1}. módosítás blokktípusa nem engedélyezett.")
    return errors

def approval_required(plan, cfg):
    # Egészség/wellness oldalnál konzervatív alapértelmezés:
    # közepes/magas kockázat mindig jóváhagyásos.
    if plan.get("risk") in {"medium", "high"}:
        return True
    return bool(plan.get("requires_approval", True))


def audit_site():
    pages = load(PAGES, {})
    cfg = load(CONFIG, {})
    issues = []
    booking_url = cfg.get("booking_url","")

    for slug, p in (pages.get("pages") or {}).items():
        seo = p.get("seo") or {}
        title = str(seo.get("title") or "").strip()
        desc = str(seo.get("description") or "").strip()
        if not title:
            issues.append({"severity":"medium","page":slug,"type":"seo_title","message":"Hiányzó SEO cím."})
        elif len(title) > 65:
            issues.append({"severity":"low","page":slug,"type":"seo_title_length","message":"A SEO cím 65 karakternél hosszabb."})
        if not desc:
            issues.append({"severity":"medium","page":slug,"type":"seo_description","message":"Hiányzó meta leírás."})
        elif len(desc) > 165:
            issues.append({"severity":"low","page":slug,"type":"seo_description_length","message":"A meta leírás 165 karakternél hosszabb."})

        for f in p.get("fields") or []:
            v = str(f.get("value") or "")
            if "http://" in v:
                issues.append({"severity":"medium","page":slug,"type":"insecure_link","message":"Nem HTTPS hivatkozás található."})

        for b in p.get("blocks") or []:
            if b.get("type") == "image" and b.get("src") and not b.get("alt"):
                issues.append({"severity":"low","page":slug,"type":"alt_text","message":f"Hiányzó alt szöveg: {b.get('src')}"})
            if b.get("type") == "image" and str(b.get("src","")).startswith("assets/uploads/"):
                media = ROOT / str(b.get("src"))
                if not media.exists():
                    issues.append({"severity":"high","page":slug,"type":"missing_media","message":f"Hiányzó médiafájl: {b.get('src')}"})
            for key in ("url","link"):
                u = str(b.get(key) or "")
                if u.startswith("http://"):
                    issues.append({"severity":"medium","page":slug,"type":"insecure_link","message":f"Nem HTTPS hivatkozás: {u}"})

    if not booking_url:
        issues.append({"severity":"high","page":"site","type":"booking_url","message":"Nincs beállítva időpontfoglalási URL."})

    out = {
        "last_run": utcnow(),
        "status": "ok",
        "summary": {
            "high": sum(1 for x in issues if x["severity"] == "high"),
            "medium": sum(1 for x in issues if x["severity"] == "medium"),
            "low": sum(1 for x in issues if x["severity"] == "low")
        },
        "items": issues
    }
    save(AUDIT, out)
    append_log("audit", f"Automatikus audit lefutott: {len(issues)} észrevétel.", details=out["summary"])
    return out

def make_prompt(task, pages, cfg):
    return f"""
Feladat:
{task.get('prompt','')}

Oldal jelenlegi strukturált tartalma:
{json.dumps(pages, ensure_ascii=False)}

Márka- és jogi szabályok:
{json.dumps(cfg.get('brand_rules',[]), ensure_ascii=False)}

Foglalási URL:
{cfg.get('booking_url','')}

Készíts módosítási tervet ÉS végrehajtható strukturált módosításokat.
KIZÁRÓLAG ezt a JSON objektumot add vissza:
{{
  "summary": "rövid összefoglaló",
  "risk": "low|medium|high",
  "requires_approval": true,
  "changes": [
    {{
      "action": "set_field|add_block|set_seo",
      "page": "index|biorezonancia|harmonyscan|ai|kapcsolat",
      "key": "mező kulcsa set_field esetén",
      "value": "új érték set_field esetén",
      "block": {{}} ,
      "seo": {{}}
    }}
  ]
}}
A blocks JSON formátum a jelenlegi pages.json struktúráját kövesse.
"""

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

def process_tasks(force_auto=False):
    cfg = load(CONFIG, {})
    queue = load(TASKS, {"tasks":[]})
    pages = load(PAGES, {})
    pending = [t for t in queue.get("tasks", []) if t.get("status") == "pending"]
    results = []

    for task in pending:
        try:
            text = call_openai(make_prompt(task, pages, cfg), cfg.get("model","gpt-5"))
            plan = json.loads(clean_json_text(text))
            errors = validate_plan(plan, pages)
            if errors:
                raise RuntimeError("Érvénytelen AI terv: " + " | ".join(errors))
            task["plan"] = plan
            task["updated_at"] = utcnow()

            mode = cfg.get("mode","approval")
            risk = plan.get("risk","high")
            requires = approval_required(plan, cfg)

            auto = force_auto or (
                cfg.get("enabled") and (
                    (mode == "full_auto" and risk == "low" and not requires) or
                    (mode == "safe_auto" and risk == "low" and not requires)
                )
            )

            if auto:
                n = apply_changes(pages, plan)
                task["status"] = "applied"
                task["applied_changes"] = n
                task["applied_at"] = utcnow()
                append_log("applied", plan.get("summary","AI módosítás alkalmazva."), task.get("id"), {"changes":n,"risk":risk})
            else:
                task["status"] = "waiting_approval"
                append_log("plan_ready", plan.get("summary","AI terv elkészült."), task.get("id"), {"risk":risk})
            results.append({"id":task.get("id"),"status":task["status"]})
        except Exception as e:
            task["status"] = "error"
            task["error"] = str(e)
            task["updated_at"] = utcnow()
            append_log("error", str(e), task.get("id"))
            results.append({"id":task.get("id"),"status":"error","error":str(e)})

    save(PAGES, pages)
    save(TASKS, queue)
    return results

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--process", action="store_true")
    ap.add_argument("--force-auto", action="store_true")
    ap.add_argument("--approve-task")
    ap.add_argument("--reject-task")
    args = ap.parse_args()

    if args.audit:
        print(json.dumps(audit_site(), ensure_ascii=False, indent=2))
    if args.process:
        print(json.dumps(process_tasks(args.force_auto), ensure_ascii=False, indent=2))
    if args.approve_task:
        q = load(TASKS, {"tasks":[]})
        pages = load(PAGES, {})
        found = next((t for t in q.get("tasks",[]) if t.get("id") == args.approve_task), None)
        if not found or found.get("status") != "waiting_approval":
            raise SystemExit("A feladat nem található vagy nem vár jóváhagyásra.")
        n = apply_changes(pages, found.get("plan") or {})
        found["status"] = "applied"
        found["applied_changes"] = n
        found["applied_at"] = utcnow()
        save(PAGES, pages); save(TASKS, q)
        append_log("approved", found.get("plan",{}).get("summary","AI terv jóváhagyva."), found.get("id"), {"changes":n})
        print(json.dumps({"ok":True,"changes":n}, ensure_ascii=False))
        return

    if args.reject_task:
        q = load(TASKS, {"tasks":[]})
        found = next((t for t in q.get("tasks",[]) if t.get("id") == args.reject_task), None)
        if not found or found.get("status") != "waiting_approval":
            raise SystemExit("A feladat nem található vagy nem vár jóváhagyásra.")
        found["status"] = "rejected"
        found["updated_at"] = utcnow()
        save(TASKS, q)
        append_log("rejected", "AI terv elutasítva.", found.get("id"))
        print(json.dumps({"ok":True}, ensure_ascii=False))
        return

    if not args.audit and not args.process:
        audit_site()
        print(json.dumps(process_tasks(False), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
