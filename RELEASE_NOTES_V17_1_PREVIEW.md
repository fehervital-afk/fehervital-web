# Fehérvitál Web – V17.1 Preview Access Patch

## Cél
A fejlesztés alatt álló valódi weboldal tulajdonosi előnézetének biztosítása úgy, hogy a normál látogatók továbbra is kizárólag a „Fejlesztés alatt” oldalt lássák.

## Újdonságok
- Új, nem navigált `preview.html` előnézeti belépőoldal.
- A preview oldal `noindex, nofollow, noarchive` keresőrobot-beállítást kapott.
- A `preview.html` megnyitása az aktuális böngészőfül munkamenetére engedélyezi a publikus aloldalak megtekintését.
- Preview módban a Főoldal/Fehérvitál linkek automatikusan a `preview.html` oldalra mutatnak.
- Normál publikus látogatásnál a korábbi maintenance-védelem változatlanul aktív.

## Használat
1. Nyisd meg közvetlenül: `https://www.fehervital.hu/preview.html`
2. Innen a weboldal menüpontjai szabadon bejárhatók ugyanabban a böngészőfülben.
3. Új privát/inkognitó ablakban vagy új munkamenetben a publikus aloldalak ismét a maintenance oldalra irányítanak, amíg a `preview.html` nincs megnyitva.

## Biztonsági megjegyzés
Ez nem jelszavas hozzáférés. A preview oldal nincs kilinkelve és keresőrobotok számára tiltott, de aki ismeri a pontos URL-t, meg tudja nyitni. A cél a fejlesztés alatti publikus láthatóság egyszerű korlátozása, nem hitelesített hozzáférés-védelem.

## Módosított / új fájlok
- `assets/js/app.js`
- `preview.html` (új)
- `RELEASE_NOTES_V17_1_PREVIEW.md` (új)
