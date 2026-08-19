# Fehérvitál Web V19.3 P0 – automatizálási biztonsági alapréteg

## Mit véd a P0?

A P0 központi, fail-closed policy ellenőrzést vezet be minden AI által előkészített CMS-módosítás elé. Védi többek között a Git- és workflow-fájlokat, deploy/build konfigurációt, hostvédelmet, jogi tartalmat, hivatalos kapcsolati adatokat, foglalási URL-eket és secret jellegű adatokat.

## Action- és kockázati modell

A kódban rögzített registry az egyetlen engedélyezési forrás. A `set_field`, `add_block` és `set_seo` CMS-módosítások legalább MEDIUM kockázatúak és emberi jóváhagyást igényelnek. A publikus művelet HIGH. Ismeretlen vagy tiltott action BLOCKED. Az AI által megadott risk csak tájékoztató adat, nem írhatja felül a policy-t.

## Jóváhagyás és végrehajtás

Az Executor közvetlenül alkalmazás előtt újraellenőrzi a policy-t, eltárolja a jóváhagyás actorát és idejét, mentést készít, majd pytestet és publikus buildet futtat. Sikertelen validáció esetén `validation_failed` állapot és biztonságos rollback következik.

## Kikapcsolva maradt funkciók

Az Autopilot továbbra is `enabled: false`, `observe` módban marad. A hard kill switchet a `--force` kapcsoló sem kerülheti meg. A GitHub Actions workflow-k read-only repository jogosultságúak, és nem commitolnak vagy pusholnak automatikusan.

## Amit még nem szabad production Autopilotként használni

CMS-módosítás, kapcsolati vagy foglalási adat változtatása, jogi/hostvédelmi/build/deploy/Git művelet, publish vagy production deploy nem futtatható felügyelet nélküli Autopilotként. A későbbi P3 feladat a PR/staging publikálási folyamat kialakítása.

## Biztonsági napló és helyi admin

Az `automation_audit.json` strukturált, nem publikus auditnaplót tárol secret-redakcióval. A helyi admin state-changing endpointjai localhost Host/Origin ellenőrzést és folyamatonként generált CSRF tokent követelnek.

## Tesztek

A P0 célzott tesztjei lefedik a fail-closed policy-t, risk downgrade tiltását, védett erőforrásokat, approval gate-et, Autopilot hard stopot, force bypass tiltását, Executor újraellenőrzést, validációs rollbacket, auditredakciót, helyi admin védelmet, hostvédelmet és publikus build kizárásokat.
