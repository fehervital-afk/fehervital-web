#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, urllib.request, uuid
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "assets" / "content"
PAGES = CONTENT / "pages.json"
STATE = CONTENT / "content_generator.json"
AGENTS = CONTENT / "agents.json"
TASKS = CONTENT / "ai_tasks.json"

def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def now():
    return datetime.now(timezone.utc).isoformat()

def clean_json(text):
    text=(text or "").strip()
    text=re.sub(r"^```(?:json)?\s*","",text)
    text=re.sub(r"\s*```$","",text)
    return text.strip()

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

def call_openai(system, user, model="gpt-5"):
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key:
        return None
    body=json.dumps({
        "model":os.getenv("OPENAI_MODEL",model),
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

def fallback_generate(kind, topic, memory):
    brand=memory.get("brand_name","Fehérvitál")
    if kind=="faq":
        return {
            "title":f"{topic} – gyakori kérdések",
            "body":[
                {"q":f"Mi az a {topic}?","a":f"A {topic} a {brand} oldalán tájékoztató, wellness szemléletű megközelítésben jelenik meg."},
                {"q":"Mennyi időt érdemes rászánni?","a":"Az időtartam az adott szolgáltatástól és bemutatótól függ; a pontos részleteket az időpontfoglalásnál érdemes ellenőrizni."},
                {"q":"Helyettesít orvosi vizsgálatot?","a":"Nem. A tájékoztató wellness tartalom nem minősül orvosi diagnózisnak és nem helyettesít orvosi vizsgálatot."}
            ]
        }
    if kind=="seo":
        return {
            "title":f"{topic} | {brand}",
            "description":f"Ismerje meg a {topic} lehetőségeit a {brand} wellness szemléletű, tájékoztató bemutatójában.",
            "keywords":[topic,"wellness","Székesfehérvár",brand]
        }
    if kind=="social":
        return {
            "facebook":f"Ismerje meg közelebbről: {topic}. Közérthető, tájékoztató szemlélettel várjuk az érdeklődőket.",
            "instagram":f"{topic} – wellness szemlélet, közérthetően. #Fehérvitál #wellness",
            "google_business":f"Új tájékoztató tartalom: {topic}. További részletek a weboldalon."
        }
    if kind=="image_prompt":
        return {
            "prompt":f"Modern, nyugodt wellness enteriőr, zöld-fehér színvilág, prémium egészségpont hangulat, magyar közönségnek, témája: {topic}, fotórealisztikus, természetes fény, letisztult kompozíció"
        }
    # article/default
    return {
        "title":topic,
        "lead":f"A {topic} témáját közérthető, wellness szemléletű megközelítésben mutatjuk be.",
        "sections":[
            {"heading":"Mit érdemes tudni?","text":f"A {topic} kapcsán az elsődleges cél a tájékozódás és az érthető információátadás."},
            {"heading":"Mire számíthat?","text":"A bemutatás során közérthető információkat kap, és lehetősége van kérdéseket feltenni."},
            {"heading":"Fontos megjegyzés","text":"A tartalom tájékoztató jellegű, nem minősül orvosi diagnózisnak és nem helyettesít orvosi vizsgálatot."}
        ],
        "cta":"Foglaljon időpontot, ha szeretné személyesen is megismerni a lehetőségeket."
    }

def generate(kind, topic, page_slug=None):
    state=load(STATE,{"brand_memory":{},"drafts":[],"history":[]})
    memory=state.get("brand_memory") or {}
    pages=load(PAGES,{})
    page=(pages.get("pages") or {}).get(page_slug) if page_slug else None

    system=(
        "Te egy magyar AI tartalomkészítő vagy egy wellness témájú weboldal számára. "
        "Ne adj orvosi diagnózist, ne ígérj gyógyulást, ne állíts betegségek kezelését. "
        "A válasz KIZÁRÓLAG érvényes JSON legyen."
    )
    user=f"""
Márkamemória:
{json.dumps(memory,ensure_ascii=False)}

Tartalomtípus: {kind}
Téma: {topic}
Kapcsolódó oldal: {json.dumps(page,ensure_ascii=False) if page else "nincs"}

Készíts publikálás előtti DRAFT tartalmat. Legyen közérthető, professzionális és konverzióbarát.
"""

    raw=call_openai(system,user)
    content=None
    if raw:
        try:
            content=json.loads(clean_json(raw))
        except Exception:
            content=None
    if content is None:
        content=fallback_generate(kind,topic,memory)

    draft={
        "id":str(uuid.uuid4()),
        "created_at":now(),
        "kind":kind,
        "topic":topic,
        "page_slug":page_slug,
        "content":content,
        "status":"draft",
        "agent_flow":["copywriter","seo","qa"]
    }
    state.setdefault("drafts",[]).append(draft)
    state.setdefault("history",[]).append({"time":now(),"event":"generated","draft_id":draft["id"],"kind":kind,"topic":topic})
    state["history"]=state["history"][-300:]
    save(STATE,state)
    return draft

def quality_check(draft_id):
    state=load(STATE,{})
    draft=next((d for d in state.get("drafts",[]) if d.get("id")==draft_id),None)
    if not draft:
        raise SystemExit("Draft nem található.")
    txt=json.dumps(draft.get("content"),ensure_ascii=False).lower()
    forbidden=["meggyógyít","gyógyítja","biztosan gyógyul","orvosi diagnózis helyett"]
    issues=[x for x in forbidden if x in txt]
    result={
        "passed":not issues,
        "issues":issues,
        "checked_at":now()
    }
    draft["quality_check"]=result
    if result["passed"]:
        draft["status"]="qa_passed"
    else:
        draft["status"]="needs_revision"
    save(STATE,state)
    return result

def send_to_webmaster(draft_id):
    state=load(STATE,{})
    draft=next((d for d in state.get("drafts",[]) if d.get("id")==draft_id),None)
    if not draft:
        raise SystemExit("Draft nem található.")
    q=load(TASKS,{"version":2,"tasks":[]})
    task={
        "id":str(uuid.uuid4()),
        "prompt":(
            "A következő AI Tartalomgenerátor draftot dolgozd fel a weboldalhoz. "
            "Készíts strukturált módosítási tervet, de ne alkalmazd jóváhagyás nélkül.\n\n"
            + json.dumps(draft,ensure_ascii=False)
        ),
        "status":"pending",
        "priority":"medium",
        "category":"content",
        "impact":"Tartalmi és SEO minőség javítása",
        "reason":"AI Tartalomgenerátor draft publikálás előkészítése",
        "owner":"AI Webmester",
        "source":"ai_content_generator",
        "created_at":now(),
        "draft_id":draft_id
    }
    q.setdefault("tasks",[]).append(task)
    save(TASKS,q)
    draft["status"]="queued_to_webmaster"
    draft["task_id"]=task["id"]
    save(STATE,state)
    return task

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--generate")
    ap.add_argument("--topic")
    ap.add_argument("--page")
    ap.add_argument("--qa")
    ap.add_argument("--send")
    args=ap.parse_args()
    if args.generate:
        print(json.dumps(generate(args.generate,args.topic or "Új tartalom",args.page),ensure_ascii=False))
    elif args.qa:
        print(json.dumps(quality_check(args.qa),ensure_ascii=False))
    elif args.send:
        print(json.dumps(send_to_webmaster(args.send),ensure_ascii=False))
    else:
        print(json.dumps({"ok":True},ensure_ascii=False))

if __name__=="__main__":
    main()
