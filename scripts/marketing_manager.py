#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "assets" / "content"
PAGES = CONTENT / "pages.json"
AUDIT = CONTENT / "ai_audit.json"
MARKETING = CONTENT / "marketing.json"
TASKS = CONTENT / "ai_tasks.json"
AUTOMATION = CONTENT / "automation.json"

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
    return max(0, min(100, int(round(n))))

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

def call_openai(prompt, model="gpt-5"):
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return None
    body = json.dumps({
        "model": os.getenv("OPENAI_MODEL", model),
        "input": [
            {
                "role": "system",
                "content": (
                    "You are the AI Marketing Manager of a Hungarian wellness information website. "
                    "Return ONLY valid JSON. Do not make medical diagnoses, treatment claims, or cure promises. "
                    "Keep recommendations concrete, ethical, conversion-aware, SEO-aware and brand-safe."
                )
            },
            {"role": "user", "content": prompt}
        ]
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return extract_response_text(json.loads(r.read().decode("utf-8")))

def clean_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()

def fields_text(page):
    vals = []
    for f in page.get("fields") or []:
        vals.append(str(f.get("value") or ""))
    for b in page.get("blocks") or []:
        for k in ("heading","text","caption","price","author"):
            if b.get(k):
                vals.append(str(b[k]))
    return " ".join(vals)

def base_analysis(pages, audit, marketing, automation):
    ps = pages.get("pages") or {}
    page_count = max(1, len(ps))
    seo_ok = 0
    content_words = 0
    cta_count = 0
    faq_count = 0
    image_count = 0
    alt_ok = 0

    for slug, p in ps.items():
        seo = p.get("seo") or {}
        if seo.get("title") and seo.get("description"):
            seo_ok += 1
        content_words += len(fields_text(p).split())
        for b in p.get("blocks") or []:
            typ = b.get("type")
            if typ in {"cta","buttons"}:
                cta_count += 1
            if typ == "faq":
                faq_count += 1
            if typ == "image":
                image_count += 1
                if b.get("alt"):
                    alt_ok += 1

    issues = audit.get("items") or []
    high = sum(1 for x in issues if x.get("severity") == "high")
    medium = sum(1 for x in issues if x.get("severity") == "medium")
    low = sum(1 for x in issues if x.get("severity") == "low")

    seo_score = clamp((seo_ok / page_count) * 75 + (alt_ok / max(1, image_count)) * 15 + max(0, 10 - medium*2 - high*5))
    content_score = clamp(min(80, content_words / 25) + min(20, faq_count*4))
    conversion_score = clamp(min(70, cta_count * 14) + (30 if automation.get("booking_url") else 0))
    technical_score = clamp(100 - high*18 - medium*7 - low*2)
    overall = clamp(seo_score*.30 + content_score*.25 + conversion_score*.25 + technical_score*.20)

    recs = []
    def add(priority, category, title, reason, task_prompt):
        recs.append({
            "id": f"rec-{len(recs)+1}",
            "priority": priority,
            "category": category,
            "title": title,
            "reason": reason,
            "task_prompt": task_prompt,
            "status": "new"
        })

    if seo_ok < page_count:
        add("high","SEO","Hiányzó SEO mezők kitöltése",
            f"{page_count-seo_ok} oldal SEO címe vagy meta leírása hiányos.",
            "Ellenőrizd az összes oldalt, és készíts jogilag óvatos, magyar SEO címet és meta leírást a hiányos oldalakhoz. Ne módosíts semmit jóváhagyás nélkül.")
    if cta_count < 3:
        add("high","Konverzió","Erősebb időpontfoglalási útvonal",
            "Kevés strukturált CTA blokk található.",
            "Javasolj a főoldalra és a legfontosabb szolgáltatási oldalakra rövid időpontfoglalási CTA blokkokat a Recepciós AI foglalási linkjére. Ne módosíts semmit jóváhagyás nélkül.")
    if content_words < 1200:
        add("medium","Tartalom","Tartalmi mélység növelése",
            "A teljes weboldal szövegmennyisége még kevés a szélesebb organikus lefedettséghez.",
            "Készíts tartalombővítési tervet a Fehérvitál számára: biorezonanciás állapotfelmérés, HarmonyScan, wellness technológiák és gyakori kérdések témában. Kerüld az orvosi ígéreteket.")
    if faq_count < 4:
        add("medium","Tartalom","GYIK bővítése",
            "Kevés strukturált GYIK elem található.",
            "Javasolj legalább 6 közérthető GYIK kérdés-választ a látogatók tipikus kérdéseire, wellness és tájékoztató megfogalmazással.")
    if medium or high:
        add("high","Technikai","Audit hibák rendezése",
            f"Az audit {high} magas és {medium} közepes súlyú problémát talált.",
            "Vizsgáld át az aktuális AI audit hibáit, és készíts biztonságos javítási tervet. Ne törölj tartalmat, és ne módosíts kapcsolati adatot jóváhagyás nélkül.")
    if not recs:
        add("low","Növekedés","Új edukációs tartalom",
            "Az alapok rendben vannak; következő lépés a keresési lefedettség növelése.",
            "Javasolj három új, edukációs és SEO-barát weboldal témát a Fehérvitál célközönségének, diagnózis és gyógyulási ígéret nélkül.")

    weekly = [
        {"day":"Hétfő","task":"SEO és technikai audit áttekintése","type":"audit"},
        {"day":"Kedd","task":"Egy edukációs tartalom vagy GYIK frissítése","type":"content"},
        {"day":"Szerda","task":"Főoldali CTA és foglalási útvonal ellenőrzése","type":"conversion"},
        {"day":"Csütörtök","task":"Belső linkelés és kapcsolódó oldalak áttekintése","type":"seo"},
        {"day":"Péntek","task":"Következő heti tartalomötletek előkészítése","type":"planning"}
    ]

    return {
        "scores": {
            "seo": seo_score,
            "content": content_score,
            "conversion": conversion_score,
            "technical": technical_score,
            "overall": overall
        },
        "recommendations": recs[:12],
        "weekly_plan": weekly,
        "stats": {
            "pages": page_count,
            "words": content_words,
            "cta_blocks": cta_count,
            "faq_blocks": faq_count,
            "audit_high": high,
            "audit_medium": medium,
            "audit_low": low
        }
    }

def ai_enrich(base, pages, marketing, automation):
    prompt = f"""
A Fehérvitál AI Marketing Manager moduljához készíts marketing elemzést.

Cél:
{marketing.get('goal','')}

Célközönség:
{marketing.get('target_audience','')}

Aktuális pontszámok és statisztikák:
{json.dumps(base, ensure_ascii=False)}

Weboldal szerkezete:
{json.dumps({k: {'name':v.get('name'), 'seo':v.get('seo'), 'field_count':len(v.get('fields') or []), 'block_count':len(v.get('blocks') or [])} for k,v in (pages.get('pages') or {}).items()}, ensure_ascii=False)}

Foglalási URL:
{automation.get('booking_url','')}

Adj vissza KIZÁRÓLAG ilyen JSON objektumot:
{{
  "summary": "3-5 mondatos vezetői összefoglaló",
  "recommendations": [
    {{
      "priority":"high|medium|low",
      "category":"SEO|Tartalom|Konverzió|Technikai|Növekedés",
      "title":"rövid cím",
      "reason":"miért fontos",
      "task_prompt":"konkrét utasítás az AI Webmesternek; egészségügyi állítások nélkül"
    }}
  ],
  "weekly_plan":[
    {{"day":"Hétfő","task":"...","type":"audit|content|conversion|seo|planning"}}
  ]
}}
"""
    raw = call_openai(prompt)
    if not raw:
        return None
    try:
        return json.loads(clean_json(raw))
    except Exception:
        return None

def run_analysis(use_ai=True):
    pages = load(PAGES, {})
    audit = load(AUDIT, {})
    marketing = load(MARKETING, {})
    automation = load(AUTOMATION, {})
    base = base_analysis(pages, audit, marketing, automation)

    summary = (
        f"Marketing állapot: {base['scores']['overall']}/100. "
        f"SEO: {base['scores']['seo']}, tartalom: {base['scores']['content']}, "
        f"konverzió: {base['scores']['conversion']}, technikai állapot: {base['scores']['technical']}."
    )
    recommendations = base["recommendations"]
    weekly_plan = base["weekly_plan"]

    if use_ai:
        enriched = ai_enrich(base, pages, marketing, automation)
        if enriched:
            summary = str(enriched.get("summary") or summary)
            extra = enriched.get("recommendations")
            if isinstance(extra, list) and extra:
                recommendations = []
                for i, r in enumerate(extra[:12], 1):
                    if not isinstance(r, dict):
                        continue
                    recommendations.append({
                        "id": f"ai-rec-{i}",
                        "priority": r.get("priority","medium"),
                        "category": r.get("category","Növekedés"),
                        "title": r.get("title","AI javaslat"),
                        "reason": r.get("reason",""),
                        "task_prompt": r.get("task_prompt",""),
                        "status": "new"
                    })
            wp = enriched.get("weekly_plan")
            if isinstance(wp, list) and wp:
                weekly_plan = wp[:7]

    marketing["last_run"] = now()
    marketing["scores"] = base["scores"]
    marketing["summary"] = summary
    marketing["recommendations"] = recommendations
    marketing["weekly_plan"] = weekly_plan
    marketing["stats"] = base["stats"]
    marketing.setdefault("history", []).append({
        "time": marketing["last_run"],
        "overall": base["scores"]["overall"],
        "seo": base["scores"]["seo"],
        "content": base["scores"]["content"],
        "conversion": base["scores"]["conversion"],
        "technical": base["scores"]["technical"]
    })
    marketing["history"] = marketing["history"][-90:]
    save(MARKETING, marketing)
    return marketing

def queue_recommendations(ids=None):
    marketing = load(MARKETING, {})
    queue = load(TASKS, {"version":1,"tasks":[]})
    ids = set(ids or [])
    added = []
    for rec in marketing.get("recommendations") or []:
        if ids and rec.get("id") not in ids:
            continue
        if rec.get("status") == "queued":
            continue
        prompt = str(rec.get("task_prompt") or "").strip()
        if not prompt:
            continue
        task = {
            "id": f"marketing-{int(datetime.now().timestamp())}-{len(added)+1}",
            "prompt": prompt,
            "status": "pending",
            "created_at": now(),
            "source": "ai_marketing_manager",
            "marketing_recommendation_id": rec.get("id")
        }
        queue.setdefault("tasks", []).append(task)
        rec["status"] = "queued"
        added.append(task["id"])
    save(TASKS, queue)
    save(MARKETING, marketing)
    return added

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--queue-all", action="store_true")
    args = ap.parse_args()

    if args.analyze or not args.queue_all:
        out = run_analysis(use_ai=not args.no_ai)
        print(json.dumps({"ok":True,"scores":out.get("scores"),"recommendations":len(out.get("recommendations") or [])}, ensure_ascii=False))
    if args.queue_all:
        added = queue_recommendations()
        print(json.dumps({"ok":True,"queued":added}, ensure_ascii=False))

if __name__ == "__main__":
    main()
