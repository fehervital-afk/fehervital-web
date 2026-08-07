# Fehérvitál web

A Fehérvitál Egészségpont új, statikus weboldalának első verziója.

## Oldalak
- Főoldal
- Biorezonancia
- HarmonyScan
- Fehérvitál AI
- Időpontfoglalás
- Kapcsolat
- Adatkezelés

## Technológia
- HTML
- CSS
- JavaScript

A projekt Render Static Site-ként vagy más statikus tárhelyen is futtatható.

## Helyi ellenőrzés Windows alatt
Dupla kattintás az `INDITAS_FEHERVITAL_WEB.bat` fájlra. Ez elindít egy helyi webszervert a 8000-es porton, majd megnyitja a böngészőt a `http://localhost:8000` címen.


## Tartalomkezelő Admin V1
Windows alatt indítsd az `INDITAS_FEHERVITAL_WEB.bat` fájlt. Az admin a `http://127.0.0.1:8000/admin/` címen nyílik meg.

Az adminból az 5 fő oldalhoz szöveg-, kép- és videóblokkok adhatók. A feltöltött média az `assets/uploads/` mappába kerül. A Mentés csak a helyi projektet módosítja; a **Mentés + Közzététel** Git commit + push műveletet futtat, ezután a Render Auto Deploy frissíti az élő oldalt.

Biztonsági okból az admin API kizárólag a helyi `127.0.0.1` szerveren érhető el; az élő statikus oldalon nem működik szerkesztő API. Nagyobb videókhoz YouTube/Vimeo URL használata javasolt; közvetlen videófeltöltésnél 90 MB a limit.


## Fehérvitál Web Admin V2
A helyi admin a `http://127.0.0.1:8000/admin/` címen érhető el az `INDITAS_FEHERVITAL_WEB.bat` indítása után.

V2 funkciók:
- szövegblokkok címmel, igazítással, szélességgel és kiemelt dobozzal;
- kép feltöltés, képaláírás, alt szöveg, link, méret és igazítás;
- MP4/WEBM/OGG videó feltöltés;
- YouTube és Vimeo link beillesztés;
- blokkok mozgatása, másolása, törlése és elrejtése;
- oldalankénti tartalom ki-/bekapcsolás;
- helyi előnézet frissítése;
- Mentés és Mentés + Közzététel.


## Fehérvitál Web Admin V3
A jelenlegi, már meglévő oldalszövegek automatikusan betöltődnek az adminba, és közvetlenül szerkeszthetők.
A korábbi V2 médiablokkok továbbra is elérhetők: szöveg, kép, videó, YouTube/Vimeo, mozgatás, másolás, elrejtés.


## Fehérvitál Web Admin V4.0
- meglévő oldalszövegek szerkesztése;
- szöveg, kép, videó, CTA és GYIK blokkok;
- médiatár feltöltéssel és törléssel;
- automatikus helyi biztonsági mentés minden Mentés előtt (max. 25);
- korábbi mentés visszaállítása;
- egygombos Git commit/push és Render Auto Deploy.


## Fehérvitál Web Admin V5 – Médiakezelés
Újdonságok:
- központi médiatár képekhez és videókhoz;
- több fájl feltöltése egyszerre;
- média átnevezése és törlése;
- logó és favicon kiválasztása;
- főoldali hero kép vagy videó;
- YouTube/Vimeo hero videó URL;
- főoldali galéria sorrenddel, képaláírással és alt szöveggel;
- médiafájlok automatikus bevonása a GitHub közzétételbe.


## Fehérvitál Web Admin V6 – Professzionális CMS alap
Újdonságok:
- központi dizájnbeállítások: színek, betűtípus, lekerekítés, árnyék;
- oldalankénti SEO cím, meta leírás, kulcsszavak és Open Graph kép;
- központi kapcsolati adatok és közösségi linkek;
- új tartalomblokkok: ikondoboz, vélemény, ár, gombsor, elválasztó;
- a V5 médiatár, hero média, galéria, logó és favicon funkciói megmaradtak.


## Fehérvitál Web Admin V7 – Vizuális oldalépítő
Újdonságok:
- hárompaneles vizuális oldalépítő;
- bal oldali elempaletta;
- drag & drop blokk beszúrás és átrendezés;
- középső blokk-canvas;
- jobb oldali elem-inspektor;
- élő, mentés nélküli előnézet iframe-ben;
- blokk másolás, törlés, fel/le mozgatás;
- dupla kattintással is hozzáadható elem;
- a V6 dizájn, SEO, kapcsolat és a V5 médiatár funkciók változatlanul megmaradtak.


## Fehérvitál Web Admin V8 – AI Webmester alap

A V8 célja a számítógéptől független, távoli AI-automatizálás alapjának létrehozása.

### Új elemek
- Admin → AI Webmester természetes nyelvű feladatmező.
- AI feladatsor (`assets/content/ai_tasks.json`).
- AI automatizálási szabályok (`assets/content/automation.json`).
- Automatikus SEO/alt-text audit (`assets/content/ai_audit.json`).
- `scripts/ai_webmaster.py` OpenAI Responses API alapú feldolgozó.
- GitHub Actions óránkénti háttérfuttatás.
- Jóváhagyásos / biztonságos automata / teljes automata módok.

### Távoli működés bekapcsolása GitHubban
1. Repository → Settings → Secrets and variables → Actions.
2. Secret létrehozása: `OPENAI_API_KEY`.
3. Variable létrehozása: `AI_WEBMASTER_ENABLED` = `true`.
4. Opcionális Variable: `OPENAI_MODEL` = `gpt-5`.
5. A `.github/workflows/ai_webmaster.yml` óránként lefut.
6. Ha a munkafolyamat fájlmódosítást végez, automatikusan commitolja/pusholja, a Render pedig az új commitot deployolja.

Biztonsági okból a V8 alapértelmezett módja `approval`.


## Fehérvitál Web Admin V9 – AI Webmester végrehajtási réteg

Újdonságok:
- AI terv részletes megjelenítése az adminban.
- Kockázati szint: low / medium / high.
- Jóváhagyás és alkalmazás gomb.
- Elutasítás gomb.
- AI műveleti napló (`assets/content/ai_log.json`).
- AI terv validálása alkalmazás előtt.
- Közepes és magas kockázatú módosítás mindig jóváhagyást igényel.
- Kibővített automatikus audit: SEO-hossz, HTTPS, hiányzó média, alt szöveg, foglalási URL.
- `safe_auto` mód: csak alacsony kockázatú és AI által jóváhagyást nem igénylő feladatot alkalmaz automatikusan.
- `full_auto` mód is megtartja a kockázati védelmet.

Javasolt indulás: `approval` mód. A teljes automatizálást csak a GitHub/Render teszt után kapcsoljuk be.


## Fehérvitál Web Admin V10 – AI Marketing Manager

Új modul:
- AI Marketing dashboard.
- Összesített, SEO, tartalom, konverzió és technikai pontszám.
- Automatikus növekedési javaslatok.
- Heti marketingterv.
- Pontszám-trend.
- Egy kattintással marketing javaslat átadása az AI Webmester feladatsorába.
- OpenAI API kulcs nélkül is működő determinisztikus alap-elemzés.
- OpenAI API kulccsal AI-val kibővített marketing ajánlások.
- Napi GitHub Actions háttérelemzés (`AI_MARKETING_ENABLED=true`).

### GitHub háttérműködés
Repository → Settings → Secrets and variables → Actions:
- Secret: `OPENAI_API_KEY`
- Variable: `AI_MARKETING_ENABLED` = `true`
- Opcionális Variable: `OPENAI_MODEL`

A Marketing Manager önmagában javaslatokat és feladatokat készít; a weboldal módosítását továbbra is az AI Webmester jóváhagyási/kockázati rétege végzi.


## Fehérvitál Web Admin V11 – AI Feladatkezelő

Új modul:
- Közös AI feladatközpont.
- AI Marketing, AI Webmester és kézi feladatok egy listában.
- Prioritás: high / medium / low.
- Állapotok: pending / waiting_approval / in_progress / applied / rejected / error.
- Forrás megjelölése.
- Kézi AI feladat létrehozása.
- Feladat státuszváltás.
- Prioritásváltás.
- Feladat törlés.
- AI Webmester jóváhagyási feladatra közvetlen átugrás.
- Szűrés állapot és prioritás alapján.

A Task Center nem kerüli meg a V9-ben beépített AI Webmester jóváhagyási/kockázati réteget.


## Fehérvitál Web Admin V12 – AI Végrehajtó Motor

Új modul:
- AI végrehajtási sor.
- AI Webmester `waiting_approval` terveinek szinkronizálása.
- Jelenlegi és AI által módosított strukturált oldalállapot összehasonlítása.
- Jóváhagyás és helyi alkalmazás.
- Elutasítás.
- Automatikus biztonsági mentés alkalmazás előtt.
- Visszaállítás korábbi mentésből.
- Végrehajtási eseménynapló.
- Automata mód kapcsolók előkészítése.

A V12 helyben már ténylegesen módosítja a `pages.json` tartalmat. A GitHub push + Render deploy teljes automatikus láncot a következő stabil lépcsőben kapcsoljuk a motorhoz.


## Fehérvitál Web Admin V13 – AI Autopilot

Új modul:
- Automatikus audit és marketing alap-ellenőrzés.
- AI Webmester → Végrehajtó automatikus szinkronizálás.
- `observe` mód: csak figyel, elemez és szinkronizál.
- `safe_auto` mód: csak `low` kockázatú, végrehajtásra kész AI módosításokat alkalmazhat.
- Alkalmazás után új audit + marketing pontszám ellenőrzés.
- Automatikus rollback, ha a pontszám a beállított küszöbnél jobban romlik.
- Autopilot futásnapló és statisztikák.
- GitHub Actions óránkénti távoli futtatás előkészítve.

Biztonsági alapértelmezés: az Autopilot kikapcsolva és `observe` módban érkezik.
A `safe_auto` módot csak helyi teszt és GitHub/Render stabil mentés után érdemes engedélyezni.


## Fehérvitál Web Admin V14 – AI Tartalomgenerátor + AI Ügynökök

Új modulok:
- AI Tartalomgenerátor: weboldal/cikk, SEO csomag, GYIK, social csomag, képgeneráló prompt.
- AI Márkamemória: márkanév, hangnem, célközönség, kötelező és kerülendő elemek.
- AI Minőségellenőrzés: tiltott gyógyítási/diagnosztikai állítások alapellenőrzése.
- Draft → AI Webmester átadási lánc.
- AI Ügynökök: Webmaster, Szövegíró, SEO, Marketing, Grafikus, Minőségellenőr, Publikáló.
- Ügynökök külön ki-/bekapcsolhatók.
- Orchestration mód: jóváhagyásos vagy biztonságos automata.

API kulcs nélkül is működik egy determinisztikus tartalom-fallback; `OPENAI_API_KEY` esetén az AI tartalomgenerálás használható.


## Fehérvitál Web Admin V15 – AI Cégvezető

Ez a külön V15 stabil lépcső kizárólag az AI Cégvezető réteget adja hozzá a V14 rendszerhez.

Új modul:
- AI Cégvezető dashboard.
- Elsődleges üzleti cél.
- Rendszer-egészségi pontszám.
- Vezetői összefoglaló.
- Prioritások és döntések.
- AI ügynök feladatkiosztás.
- Vezetői napló.
- Jóváhagyásos / biztonságos automata mód.
- AI Cégvezető által generált feladatok bekerülnek az AI Feladatkezelőbe.
- OpenAI API nélkül is működő determinisztikus vezetői elemzés.
- OpenAI API-val AI-val kibővített vezetői döntések.

A V16 AI Business OS erre a külön V15 stabil rétegre épül.


## Fehérvitál Web Admin V16 – AI Business OS

A V16 a külön V15 AI Cégvezetőre épül.

Fő fejlesztések:
- Valós, komponens-alapú egészségi pontszám.
- SEO, tartalom, marketing, konverzió, technikai, automatizálási és AI ügynök pontszámok összesítése.
- A CEO többé nem ragad 0/100-on pusztán alacsony vagy hiányzó részpontszámok miatt.
- Audit hibák kontrollált büntető tényezőként kerülnek bele.
- AI Business OS dashboard.
- Riasztások és következő lépés.
- AI üzleti memória.
- Heti vezetői jelentés.
- A V15 AI Cégvezető külön menüpontként megmarad.


## Fehérvitál Web Admin V17 – AI Business Intelligence

A V17 közvetlenül a felhasználó által visszaküldött V16 projektből készült.

Új funkciók:
- AI Business Intelligence dashboard.
- Valós belső KPI-k: SEO, tartalom, marketing, konverzió, technikai állapot, rendszer-egészség.
- Operatív proxy KPI-k: engagement index, lead readiness, booking readiness, execution velocity.
- 14 napos napi trend és hosszabb heti/havi adatsor előkészítés.
- Konzervatív 30 napos előrejelzés a saját rendszertrendekből.
- Bizalmi index az adatforrások teljességére.
- Kockázatok és lehetőségek automatikus felismerése.
- AI ügynök teljesítménymérés.
- Stratégiai célok és cél-előrehaladás.
- A V15 AI Cégvezető és V16 Business OS változatlanul megmaradnak.

Fontos: a V17 jelenlegi üzleti KPI-jai belső rendszeradatokra és proxy mutatókra épülnek. Valós látogatói, Search Console, Analytics és Recepciós AI foglalási adatok bekötése külön integrációs lépcső lesz; a rendszer nem állít elő kitalált forgalmi vagy bevételi számokat.
