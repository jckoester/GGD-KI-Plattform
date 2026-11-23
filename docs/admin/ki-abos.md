# Schnittstelle für KI-Abos (MCP)

Seit 0.54 kann die Plattform Curricula, Bildungspläne und Leitlinien an ein KI-Programm
liefern, das die Schule abonniert hat, etwa Claude. Lehrkräfte fragen dann dort: „Wo kommt
BNE in unseren Curricula vor?“, „Vergleiche die Curricula Klasse 7 in Mathematik und
Physik.“ Technisch ist das ein **MCP-Server** (Model Context Protocol) im Backend.

Ab Werk ist die Schnittstelle **aus**. Sie einzuschalten ist eine Entscheidung der Schule:
Was das Programm liest, geht an dessen Anbieter.

## Was die Schnittstelle kann

- **Nur lesen.** Sieben Werkzeuge: Leitlinien, Leitperspektiven, die Übersicht einer Leitlinie
  oder Leitperspektive, Curricula finden, ein Curriculum lesen, seine Abdeckung, die
  Kompetenzen des Bildungsplans. Schreiben ist nicht möglich; ein Test im Code hält das so.
- **Mit den Rechten der Lehrkraft.** Gelesen wird, was die Person auch im Browser sieht —
  veröffentlichte Curricula und Entwürfe, eigene private, keine fremden privaten.
- **Ohne Personen.** Die Antworten enthalten keine Pseudonyme und keine Namen. Chats,
  Unterrichtsplanung, Budgets und Verwaltung sind nicht erreichbar.
- **Nur für Lehrkräfte und Admins**, angemeldet mit einem persönlichen Zugangstoken mit der
  Berechtigung `curriculum:read`. Diese Berechtigung öffnet sonst keinen Weg in die Plattform.

## Einschalten

In der `.env`:

```bash
MCP_AKTIV=true
MCP_OEFFENTLICHE_URL=https://ki.ihre-schule.de/api/mcp
```

`MCP_OEFFENTLICHE_URL` ist die Adresse, wie die Programme sie aufrufen, also **mit** `/api`.
Aus ihr übernimmt der Server die erlaubten Host- und Origin-Werte. Anfragen mit einem anderen
Host-Kopf weist er ab (Schutz vor DNS-Rebinding). Fehlt die Adresse, bleibt die Schnittstelle
trotz `MCP_AKTIV=true` aus, und das Log des Backends meldet einen Fehler.

Danach das Backend neu starten:

```bash
docker compose up -d backend
```

Im Profil erscheint die Berechtigung „Curricula, Bildungspläne und Leitlinien lesen — für
KI-Programme“ mit der Adresse erst, wenn die Schnittstelle eingeschaltet ist.

## Reverse Proxy

Der mitgelieferte nginx (`infra/nginx.conf.template`) braucht keine Änderung: `location /api/`
reicht `/api/mcp` als `/mcp` an das Backend weiter, setzt den `Host`-Kopf und puffert nicht.
Wer einen eigenen Proxy betreibt, muss dasselbe sicherstellen:

- `/api/mcp` → Backend `/mcp`, mindestens die Methode `POST`;
- `Host` unverändert weitergeben (sonst greift die Host-Prüfung);
- `Authorization` nicht entfernen.

**Erreichbarkeit:** Claude ruft den Server von Anthropics Servern aus auf, nicht vom Gerät der
Lehrkraft. Wer den Zugang auf Adressbereiche beschränkt, gibt den Bereich frei, den Anthropic
dafür veröffentlicht (Stand 11/2026: `160.79.104.0/21`). Claude Code ruft dagegen vom Gerät
der Lehrkraft aus auf.

## Prüfen

Ohne Token muss der Server mit `401` antworten:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://ki.ihre-schule.de/api/mcp \
  -H "content-type: application/json" -d '{}'
```

`404` heißt: Die Schnittstelle ist aus oder der Proxy leitet `/api/mcp` nicht weiter.

## Drossel

Je Token höchstens 60 Nachrichten in der Minute, danach `429` mit `Retry-After`. Ein Auftrag
im KI-Programm löst mehrere Werkzeugaufrufe aus; 60 genügen dafür und bremsen eine Schleife.
Einstellbar in `config/rate_limits.yaml` (Eimer `mcp`).

## Datenschutz

Die Schnittstelle liefert Curricula, Bildungspläne und Leitlinien, keine personenbezogenen
Daten aus der Plattform. In den Freitexten eines Curriculums kann trotzdem etwas stehen, das
nicht hinausgehen soll. Ob und mit welchem Anbieter die Schule das nutzt, entscheidet sie;
dazu gehört ein Vertrag zur Auftragsverarbeitung mit dem Anbieter des Abos und ein Eintrag im
Verarbeitungsverzeichnis.

## Abschalten

`MCP_AKTIV=false` und das Backend neu starten. Die Route verschwindet (`404`); vorhandene
Token mit der Berechtigung bleiben bestehen, führen aber nirgends hin. Einzelne Verbindungen
beendet die Lehrkraft, indem sie ihr Token im Profil beendet.
