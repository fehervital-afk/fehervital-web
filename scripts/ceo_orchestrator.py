#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, urllib.request, uuid
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "assets" / "content"

PAGES = CONTENT / "pages.json"
MARKETING = CONTENT / "marketing.json"
TASKS = CONTENT / "ai_tasks.json"
AUDIT = CONTENT / "ai_audit.json"
EXECUTION = CONTENT / "execution_queue.json"
AUTOPILOT = CONTENT / "autopilot.json"
CONTENT_STATE = CONTENT / "content_generator.json"
AGENTS = CONTENT / "agents.json"
CEO = CONTENT / "ceo.json"
BOS = CONTENT / "business_os.json"
WEEKLY = CONTENT / "weekly_report.json"
MEMORY = CONTENT / "business_memory.json"

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def now():
    return datetime.now(timezone.utc).isoformat()

def clamp(n):
    try:
        n=float(n)
    except Exception:
        n=0
    return max(0, min(100, int(round(n))))

def response_text(data):
    if isinstance(data,dict) and isinstance(data.get("output_text"),str):
        return data["output_text"]
    parts=[]
    if isinstance(data,dict):
        for item in data.get("output",[]) or []:
            for c in item.get("content",[]) or []:
                if isinstance(c.get("text"),str):
                    parts.append(c["text"])
    return "\n".join(parts)

def call_openai(system,user):
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key:
        return None
    body=json.dumps({
        "model":os.getenv("OPENAI_MODEL","gpt-5"),
        "input":[
            {"role":"system","content":system},
            {"role":"user","content":user}
        ]
    }).encode("utf-8")
    req=urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req,timeout=90) as r:
        return response_text(json.loads(r.read().decode("utf-8")))

def clean_json(text):
    text=(text or "").strip()
    text=re.sub(r"^```(?:json)?\s*","",text)
    text=re.sub(r"\s*```$","",text)
    return text.strip()

def marketing_scores():
    m=load(MARKETING,{})
    s=m.get("scores") or {}
    seo=clamp(s.get("seo",0))
    content=clamp(s.get("content",0))
    conversion=clamp(s.get("conversion",0))
    technical=clamp(s.get("technical",0))
    overall=clamp(s.get("overall",0))
    if overall == 0:
        overall=clamp((seo+content+conversion+technical)/4)
    return {
        "seo":seo,
        "content":content,
        "conversion":conversion,
        "technical":technical,
        "marketing":overall
    }

def automation_score():
    a=load(AUTOPILOT,{})
    if a.get("enabled"):
        if a.get("mode")=="safe_auto" and a.get("auto_apply_low_risk"):
            return 95
        return 80
    return 45

def agents_score():
    a=load(AGENTS,{"agents":[]})
    agents=a.get("agents") or []
    if not agents:
        return 0
    return clamp(100*sum(1 for x in agents if x.get("enabled"))/len(agents))

def health_components():
    scores=marketing_scores()
    comps={
        "seo":scores["seo"],
        "content":scores["content"],
        "marketing":scores["marketing"],
        "conversion":scores["conversion"],
        "technical":scores["technical"],
        "automation":automation_score(),
        "agents":agents_score()
    }
    # baseline only for missing individual analyzer values
    pages=load(PAGES,{})
    page_count=len((pages.get("pages") or {}))
    if page_count:
        if comps["seo"] == 0: comps["seo"] = 35
        if comps["content"] == 0: comps["content"] = 45
        if comps["marketing"] == 0: comps["marketing"] = 40
        if comps["conversion"] == 0: comps["conversion"] = 40
        if comps["technical"] == 0: comps["technical"] = 60
    return comps

def audit_penalty():
    audit=load(AUDIT,{})
    items=audit.get("items") or []
    high=sum(1 for x in items if x.get("severity")=="high")
    medium=sum(1 for x in items if x.get("severity")=="medium")
    low=sum(1 for x in items if x.get("severity")=="low")
    # Important: audit cannot wipe the whole score to zero.
    return min(18, high*7 + medium*1.2 + low*0.3)

def system_health():
    c=health_components()
    weighted=(
        c["seo"]*0.18 +
        c["content"]*0.14 +
        c["marketing"]*0.14 +
        c["conversion"]*0.18 +
        c["technical"]*0.18 +
        c["automation"]*0.09 +
        c["agents"]*0.09
    )
    score=clamp(weighted - audit_penalty())
    # A running populated system should not report 0 merely because analyzer scores are low.
    if any(v>0 for v in c.values()) and score == 0:
        score = 1
    return score, c

def deterministic_priorities():
    marketing=load(MARKETING,{})
    audit=load(AUDIT,{})
    content=load(CONTENT_STATE,{})
    tasks=load(TASKS,{"tasks":[]})
    out=[]

    for r in (marketing.get("recommendations") or [])[:6]:
        out.append({
            "id":str(uuid.uuid4()),
            "title":r.get("title","Marketing javaslat"),
            "priority":r.get("priority","medium"),
            "owner":"AI Marketing",
            "reason":r.get("reason",""),
            "task_prompt":r.get("task_prompt","")
        })

    highs=[x for x in (audit.get("items") or []) if x.get("severity")=="high"]
    mediums=[x for x in (audit.get("items") or []) if x.get("severity")=="medium"]
    if highs:
        out.insert(0,{
            "id":str(uuid.uuid4()),
            "title":"Magas súlyú audit problémák rendezése",
            "priority":"high",
            "owner":"AI Webmaster",
            "reason":f"{len(highs)} magas súlyú audit eltérés található.",
            "task_prompt":"Vizsgáld át a magas súlyú audit problémákat és készíts biztonságos javítási tervet."
        })
    elif mediums:
        out.append({
            "id":str(uuid.uuid4()),
            "title":"Közepes audit hibák ütemezett rendezése",
            "priority":"medium",
            "owner":"AI Webmaster",
            "reason":f"{len(mediums)} közepes súlyú audit eltérés található.",
            "task_prompt":"Rangsorold a közepes audit hibákat és készíts biztonságos javítási tervet."
        })

    drafts=[d for d in (content.get("drafts") or []) if d.get("status") in {"draft","qa_passed"}]
    if drafts:
        out.append({
            "id":str(uuid.uuid4()),
            "title":"Tartalom draftok feldolgozása",
            "priority":"medium",
            "owner":"AI Szövegíró",
            "reason":f"{len(drafts)} draft vár feldolgozásra.",
            "task_prompt":"Ellenőrizd és készítsd elő publikálásra a függő tartalom draftokat."
        })

    active=[t for t in (tasks.get("tasks") or []) if t.get("status") in {"pending","waiting_approval","in_progress"}]
    if len(active)>8:
        out.append({
            "id":str(uuid.uuid4()),
            "title":"AI feladatsor tehermentesítése",
            "priority":"high",
            "owner":"AI Cégvezető",
            "reason":f"{len(active)} aktív feladat vár feldolgozásra.",
            "task_prompt":"Rangsorold az aktív AI feladatokat üzleti hatás és kockázat szerint."
        })

    return out[:10] or [{
        "id":str(uuid.uuid4()),
        "title":"Következő növekedési lehetőség kiválasztása",
        "priority":"low",
        "owner":"AI Marketing",
        "reason":"Nincs kritikus aktív probléma.",
        "task_prompt":"Javasolj egy biztonságos következő SEO vagy konverziós fejlesztést."
    }]

def ai_decisions(ceo,bos):
    system=(
        "Te egy magyar AI Cégvezető vagy egy wellness weboldal digitális AI csapatának élén. "
        "Ne adj orvosi diagnózist és ne tegyél gyógyulási ígéretet. KIZÁRÓLAG érvényes JSON-t adj."
    )
    user=f"""
Elsődleges üzleti cél:
{ceo.get('primary_goal','')}

Business OS állapot:
{json.dumps(bos,ensure_ascii=False)}

Aktuális prioritások:
{json.dumps(ceo.get('priorities',[]),ensure_ascii=False)}

Adj vissza:
{{
  "executive_summary":"3-5 mondatos vezetői összefoglaló",
  "next_action":"egy konkrét következő lépés",
  "decisions":[
    {{
      "title":"rövid döntés",
      "priority":"high|medium|low",
      "owner":"AI ügynök neve",
      "reason":"miért fontos",
      "task_prompt":"konkrét feladat"
    }}
  ]
}}
"""
    raw=call_openai(system,user)
    if not raw:
        return None
    try:
        return json.loads(clean_json(raw))
    except Exception:
        return None

def create_tasks(decisions):
    q=load(TASKS,{"version":2,"tasks":[]})
    active_prompts={str(t.get("prompt","")).strip() for t in q.get("tasks",[]) if t.get("status") in {"pending","waiting_approval","in_progress"}}
    added=[]
    for d in decisions:
        prompt=str(d.get("task_prompt") or "").strip()
        if not prompt or prompt in active_prompts:
            continue
        task={
            "id":str(uuid.uuid4()),
            "prompt":prompt,
            "status":"pending",
            "priority":d.get("priority","medium"),
            "category":"ceo",
            "impact":"AI Cégvezető által kijelölt üzleti prioritás",
            "reason":d.get("reason",""),
            "owner":d.get("owner","AI Webmester"),
            "source":"ai_ceo",
            "created_at":now()
        }
        q.setdefault("tasks",[]).append(task)
        added.append(task["id"])
    save(TASKS,q)
    return added

def refresh_bos(ceo=None):
    ceo=ceo or load(CEO,{})
    health,components=system_health()
    tasks=load(TASKS,{"tasks":[]})
    execution=load(EXECUTION,{"items":[]})
    content=load(CONTENT_STATE,{"drafts":[]})
    agents=load(AGENTS,{"agents":[]})
    audit=load(AUDIT,{})

    active=[t for t in (tasks.get("tasks") or []) if t.get("status") in {"pending","waiting_approval","in_progress"}]
    ready=[x for x in (execution.get("items") or []) if x.get("status") in {"ready","previewed"}]
    drafts=[d for d in (content.get("drafts") or []) if d.get("status") not in {"queued_to_webmaster"}]
    highs=[x for x in (audit.get("items") or []) if x.get("severity")=="high"]
    mediums=[x for x in (audit.get("items") or []) if x.get("severity")=="medium"]

    alerts=[]
    if highs: alerts.append(f"{len(highs)} magas súlyú audit probléma.")
    if len(mediums)>=5: alerts.append(f"{len(mediums)} közepes audit probléma.")
    if len(active)>10: alerts.append(f"{len(active)} aktív AI feladat.")
    if ready: alerts.append(f"{len(ready)} végrehajtásra kész AI módosítás.")

    bos={
        "version":1,
        "last_refresh":now(),
        "system_health":health,
        "components":components,
        "alerts":alerts,
        "next_action":(ceo.get("decisions") or [{}])[0].get("title","") if ceo.get("decisions") else "",
        "metrics":{
            "active_tasks":len(active),
            "ready_execution":len(ready),
            "drafts":len(drafts),
            "agents_enabled":sum(1 for a in agents.get("agents",[]) if a.get("enabled")),
            "agents_total":len(agents.get("agents",[]))
        },
        "timeline":(ceo.get("history") or [])[-20:]
    }
    save(BOS,bos)
    return bos

def run_ceo(use_ai=True,create_task_items=True):
    ceo=load(CEO,{})
    ceo["last_run"]=now()
    ceo["health_score"],comps=system_health()
    ceo["priorities"]=deterministic_priorities()

    bos=refresh_bos(ceo)
    enriched=ai_decisions(ceo,bos) if use_ai else None

    if enriched:
        ceo["executive_summary"]=str(enriched.get("executive_summary") or "")
        ceo["decisions"]=enriched.get("decisions") or []
        bos["next_action"]=str(enriched.get("next_action") or bos.get("next_action",""))
    else:
        ceo["executive_summary"]=(
            f"A digitális rendszer aktuális egészségi pontszáma {ceo['health_score']}/100. "
            f"SEO: {comps['seo']}/100, tartalom: {comps['content']}/100, marketing: {comps['marketing']}/100, "
            f"konverzió: {comps['conversion']}/100, technikai állapot: {comps['technical']}/100. "
            f"{len(ceo['priorities'])} vezetői prioritás azonosítható."
        )
        ceo["decisions"]=[{
            "title":p.get("title"),
            "priority":p.get("priority"),
            "owner":p.get("owner"),
            "reason":p.get("reason"),
            "task_prompt":p.get("task_prompt")
        } for p in ceo["priorities"][:5]]

    ceo["agent_assignments"]=[
        {"agent":d.get("owner","AI Webmester"),"task":d.get("title",""),"priority":d.get("priority","medium")}
        for d in ceo.get("decisions",[])
    ]
    ceo.setdefault("history",[]).append({
        "time":now(),
        "event":"ceo_run",
        "health_score":ceo["health_score"],
        "components":comps,
        "decisions":len(ceo.get("decisions",[]))
    })
    ceo["history"]=ceo["history"][-300:]
    save(CEO,ceo)

    bos["system_health"]=ceo["health_score"]
    bos["components"]=comps
    save(BOS,bos)

    added=create_tasks(ceo.get("decisions",[])) if create_task_items else []
    return {"ok":True,"health_score":ceo["health_score"],"components":comps,"decisions":len(ceo.get("decisions",[])),"tasks_created":len(added)}

def weekly_report():
    ceo=load(CEO,{})
    bos=load(BOS,{})
    tasks=load(TASKS,{"tasks":[]})
    completed=[t for t in (tasks.get("tasks") or []) if t.get("status")=="applied"]
    open_items=[t for t in (tasks.get("tasks") or []) if t.get("status") in {"pending","waiting_approval","in_progress"}]
    report={
        "version":1,
        "generated_at":now(),
        "summary":ceo.get("executive_summary",""),
        "metrics":{
            "system_health":bos.get("system_health",0),
            **(bos.get("components") or {}),
            "completed_tasks":len(completed),
            "open_tasks":len(open_items)
        },
        "completed":[{"prompt":t.get("prompt",""),"owner":t.get("owner","")} for t in completed[-10:]],
        "open_items":[{"prompt":t.get("prompt",""),"priority":t.get("priority","medium")} for t in open_items[:10]],
        "next_week":[d.get("title","") for d in (ceo.get("decisions") or [])[:5]]
    }
    save(WEEKLY,report)
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--run",action="store_true")
    ap.add_argument("--no-ai",action="store_true")
    ap.add_argument("--no-tasks",action="store_true")
    ap.add_argument("--refresh-bos",action="store_true")
    ap.add_argument("--weekly",action="store_true")
    args=ap.parse_args()
    if args.weekly:
        result=weekly_report()
    elif args.refresh_bos:
        result=refresh_bos()
    else:
        result=run_ceo(use_ai=not args.no_ai,create_task_items=not args.no_tasks)
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()
