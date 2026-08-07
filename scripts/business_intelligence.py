#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math
from pathlib import Path
from datetime import datetime, timezone, timedelta

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
BI = CONTENT / "business_intelligence.json"
GOALS = CONTENT / "strategic_goals.json"

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
    try: n=float(n)
    except Exception: n=0
    return max(0, min(100, round(n,1)))

def get_scores():
    m=load(MARKETING,{})
    s=m.get("scores") or {}
    bos=load(BOS,{})
    c=bos.get("components") or {}
    def pick(name, fallback=0):
        v=s.get(name)
        if v is None or v == 0:
            v=c.get(name, fallback)
        return clamp(v)
    return {
        "seo": pick("seo",35),
        "content": pick("content",45),
        "conversion": pick("conversion",40),
        "technical": pick("technical",60),
        "marketing": clamp(s.get("overall") or c.get("marketing") or 40),
        "system_health": clamp(bos.get("system_health") or 0)
    }

def task_metrics():
    q=load(TASKS,{"tasks":[]})
    arr=q.get("tasks") or []
    active=[t for t in arr if t.get("status") in {"pending","waiting_approval","in_progress"}]
    done=[t for t in arr if t.get("status")=="applied"]
    errors=[t for t in arr if t.get("status")=="error"]
    return {
        "all":len(arr),
        "active":len(active),
        "done":len(done),
        "errors":len(errors),
        "completion_rate": clamp(100*len(done)/max(1,len(arr)))
    }

def agent_metrics():
    agents=load(AGENTS,{"agents":[]}).get("agents") or []
    tasks=load(TASKS,{"tasks":[]}).get("tasks") or []
    result=[]
    for a in agents:
        name=a.get("name") or a.get("id")
        owned=[t for t in tasks if str(t.get("owner","")).lower()==str(name).lower()]
        done=sum(1 for t in owned if t.get("status")=="applied")
        err=sum(1 for t in owned if t.get("status")=="error")
        score=clamp(55 + done*5 - err*12 + (10 if a.get("enabled") else -20))
        result.append({
            "id":a.get("id"),
            "name":name,
            "enabled":bool(a.get("enabled")),
            "tasks":len(owned),
            "done":done,
            "errors":err,
            "score":score
        })
    return result

def content_metrics():
    st=load(CONTENT_STATE,{"drafts":[]})
    drafts=st.get("drafts") or []
    return {
        "drafts":len(drafts),
        "qa_passed":sum(1 for d in drafts if d.get("status")=="qa_passed"),
        "queued":sum(1 for d in drafts if d.get("status")=="queued_to_webmaster")
    }

def audit_metrics():
    a=load(AUDIT,{})
    items=a.get("items") or []
    return {
        "high":sum(1 for x in items if x.get("severity")=="high"),
        "medium":sum(1 for x in items if x.get("severity")=="medium"),
        "low":sum(1 for x in items if x.get("severity")=="low"),
        "total":len(items)
    }

def execution_metrics():
    e=load(EXECUTION,{"items":[],"history":[]})
    items=e.get("items") or []
    hist=e.get("history") or []
    return {
        "ready":sum(1 for x in items if x.get("status") in {"ready","previewed"}),
        "applied":sum(1 for x in items if x.get("status")=="applied"),
        "rolled_back":sum(1 for x in items if x.get("status")=="rolled_back"),
        "history_events":len(hist)
    }

def synthetic_business_kpis(scores, tasks, content, audit):
    # These are operational proxy KPIs until analytics/booking connectors are attached.
    engagement=clamp(scores["content"]*.35 + scores["marketing"]*.35 + scores["technical"]*.15 + scores["seo"]*.15)
    lead_readiness=clamp(scores["conversion"]*.55 + scores["marketing"]*.25 + scores["technical"]*.20)
    booking_readiness=clamp(scores["conversion"]*.60 + scores["technical"]*.20 + max(0,100-audit["high"]*20-audit["medium"]*4)*.20)
    execution_velocity=clamp(tasks["completion_rate"]*.60 + max(0,100-tasks["active"]*4)*.20 + scores["system_health"]*.20)
    return {
        "engagement_index": engagement,
        "lead_readiness": lead_readiness,
        "booking_readiness": booking_readiness,
        "execution_velocity": execution_velocity
    }

def moving_projection(current, momentum, horizon=30):
    # conservative bounded projection; no fake external traffic counts
    return clamp(current + momentum * min(1, horizon/30))

def momentum_from_history(history, key):
    vals=[]
    for h in history[-7:]:
        try: vals.append(float((h.get("kpis") or {}).get(key,0)))
        except Exception: pass
    if len(vals)<2:
        return 0
    return max(-8,min(8,(vals[-1]-vals[0])/max(1,len(vals)-1)))

def build_risks(scores,tasks,audit,execution):
    risks=[]
    if audit["high"]:
        risks.append({"severity":"high","title":"Magas súlyú technikai/audit probléma","reason":f"{audit['high']} magas súlyú eltérés aktív."})
    if scores["seo"]<50:
        risks.append({"severity":"high","title":"Gyenge SEO alap","reason":f"SEO pontszám: {scores['seo']}/100."})
    if scores["conversion"]<50:
        risks.append({"severity":"medium","title":"Konverziós útvonal fejlesztendő","reason":f"Konverziós pontszám: {scores['conversion']}/100."})
    if tasks["active"]>10:
        risks.append({"severity":"medium","title":"AI feladatsor torlódás","reason":f"{tasks['active']} aktív feladat vár feldolgozásra."})
    if execution["ready"]>5:
        risks.append({"severity":"medium","title":"Végrehajtási sor felgyűlt","reason":f"{execution['ready']} módosítás vár végrehajtásra."})
    return risks[:10]

def build_opportunities(scores,content,tasks):
    out=[]
    if scores["content"]<70:
        out.append({"impact":"high","title":"Tartalmi lefedettség növelése","reason":"Új edukációs oldalak és GYIK-ek emelhetik az organikus lefedettséget."})
    if scores["seo"]<70:
        out.append({"impact":"high","title":"SEO mezők és belső linkelés","reason":"A keresési láthatóság javítható."})
    if scores["conversion"]<70:
        out.append({"impact":"high","title":"Foglalási CTA-k optimalizálása","reason":"A fontos oldalakon erősebb foglalási útvonal szükséges."})
    if content["drafts"]:
        out.append({"impact":"medium","title":"Meglévő draftok gyorsítása","reason":f"{content['drafts']} draft áll rendelkezésre."})
    if tasks["completion_rate"]<60:
        out.append({"impact":"medium","title":"AI végrehajtási sebesség javítása","reason":"A feladatok nagyobb részét érdemes lezárni vagy priorizálni."})
    return out[:10]

def update_goals(kpis):
    g=load(GOALS,{"goals":[]})
    for goal in g.get("goals",[]):
        gid=goal.get("id")
        if gid=="booking-growth":
            goal["progress"]=clamp(kpis["booking_readiness"])
        elif gid=="organic-growth":
            goal["progress"]=clamp(kpis["seo"])
        elif gid=="content-coverage":
            goal["progress"]=clamp(kpis["content"])
    g["updated_at"]=now()
    save(GOALS,g)
    return g

def refresh():
    old=load(BI,{"history":[]})
    history=old.get("history") or []
    scores=get_scores()
    tasks=task_metrics()
    content=content_metrics()
    audit=audit_metrics()
    execution=execution_metrics()
    agents=agent_metrics()
    proxy=synthetic_business_kpis(scores,tasks,content,audit)

    kpis={
        **scores,
        **proxy,
        "active_tasks":tasks["active"],
        "completion_rate":tasks["completion_rate"],
        "drafts":content["drafts"],
        "audit_issues":audit["total"],
        "ready_execution":execution["ready"]
    }

    mom={
        "seo":momentum_from_history(history,"seo"),
        "content":momentum_from_history(history,"content"),
        "conversion":momentum_from_history(history,"conversion"),
        "marketing":momentum_from_history(history,"marketing"),
        "booking_readiness":momentum_from_history(history,"booking_readiness")
    }

    forecast={
        "seo_30d":moving_projection(scores["seo"],mom["seo"]),
        "content_30d":moving_projection(scores["content"],mom["content"]),
        "conversion_30d":moving_projection(scores["conversion"],mom["conversion"]),
        "marketing_30d":moving_projection(scores["marketing"],mom["marketing"]),
        "booking_readiness_30d":moving_projection(proxy["booking_readiness"],mom["booking_readiness"])
    }

    # Confidence is about data completeness, not prediction certainty.
    populated=sum(1 for v in [scores["seo"],scores["content"],scores["conversion"],scores["technical"],scores["marketing"]] if v>0)
    confidence=clamp(35 + populated*8 + min(20,len(history)*2))

    stamp=now()
    history.append({"time":stamp,"kpis":kpis})
    history=history[-180:]

    risks=build_risks(scores,tasks,audit,execution)
    opportunities=build_opportunities(scores,content,tasks)
    recommendations=[]
    for x in risks[:3]:
        recommendations.append({"priority":x["severity"],"title":x["title"],"action":"Készíts javítási tervet és add át az AI Feladatkezelőnek."})
    for x in opportunities[:3]:
        recommendations.append({"priority":"medium","title":x["title"],"action":"Készíts konkrét növekedési feladatot az AI Cégvezető számára."})

    state={
        "version":1,
        "last_refresh":stamp,
        "kpis":kpis,
        "trends":{
            "daily":history[-14:],
            "weekly":history[-56::7] if history else [],
            "monthly":history[-180::30] if history else []
        },
        "forecast":forecast,
        "confidence":confidence,
        "risks":risks,
        "opportunities":opportunities,
        "recommendations":recommendations,
        "agent_performance":agents,
        "history":history
    }
    save(BI,state)
    goals=update_goals(kpis)
    return {"ok":True,"kpis":kpis,"forecast":forecast,"confidence":confidence,"goals":len(goals.get("goals",[]))}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--refresh",action="store_true")
    args=ap.parse_args()
    print(json.dumps(refresh(),ensure_ascii=False))

if __name__=="__main__":
    main()
