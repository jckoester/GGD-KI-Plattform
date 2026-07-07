# Server-Rendering-Sidecar (Phase 17)

Damit Assistenten **Schaltpläne** (CircuiTikZ) und **Funktionsgraphen** zeichnen und **Formeln**
im PDF-Export erscheinen, läuft ein kleiner interner Render-Dienst mit: `render-sidecar`
(CircuiTikZ via node-tikzjax, Mathe via MathJax). Reines Rendering — **keine KI, keine Kosten,
keine externen Aufrufe**; der Dienst ist **nur intern** erreichbar.

## Produktivbetrieb (Docker Compose)

Der Sidecar ist als Service `render-sidecar` in `docker-compose.yml` enthalten — er startet
automatisch mit `docker compose up`. Merkmale:

- **Kein `ports:`-Eintrag** → nur im Compose-Netz erreichbar, nie öffentlich.
- **Health-Check** auf `/health`; `restart: unless-stopped`.
- **Ressourcen-Limits** (Default: 1 CPU, 512 MB) — überschreibbar in `docker-compose.yml`.
- Das **Backend** erreicht ihn über `RENDER_SIDECAR_URL=http://render-sidecar:3200` (bereits
  gesetzt) und braucht `MPLCONFIGDIR` (schreibbarer matplotlib-Font-Cache — gesetzt).

Nach Änderungen am Sidecar-Code: `docker compose build render-sidecar && docker compose up -d`.

## Konfiguration (Env)

| Variable | Wo | Default | Bedeutung |
|---|---|---|---|
| `RENDER_SIDECAR_URL` | Backend | `http://render-sidecar:3200` | Adresse des Sidecars |
| `RENDER_POOL_SIZE` | Sidecar | `2` | Worker-Pool = gleichzeitige CircuiTikZ-Renders |
| `RENDER_TIMEOUT_MS` | Sidecar | `10000` | harter Render-Timeout (Runaway-Schutz) |
| `RENDER_TIMEOUT` | Backend | `15.0` s | Client-Timeout zum Sidecar |
| `RENDER_CACHE_MAX_AGE_DAYS` | Backend | `90` | Aufbewahrung des SVG-Caches (Cron) |
| `MPLCONFIGDIR` | Backend | `/tmp/matplotlib` | matplotlib-Font-Cache (muss schreibbar sein) |

## Was passiert, wenn der Sidecar aus ist?

Der Betrieb bricht **nicht** ab, es degradiert nur:

- **Im Chat:** Schaltpläne zeigen einen Fehler-Platzhalter statt des Bildes (Plots laufen
  in-process im Backend und funktionieren weiter).
- **Im PDF-Export:** Formeln/Schaltpläne erscheinen als Quelltext statt gerendert.

Prüfen, ob er läuft: `docker compose ps render-sidecar` bzw. Logs `docker compose logs render-sidecar`.

## Cache & Aufräumen

Gerenderte SVGs werden in der Tabelle `rendered_svg` zwischengespeichert (content-adressiert,
identische Eingabe = identisches SVG). Der Cron-Job `cleanup_rendered_svg.py` (täglich) löscht
Einträge älter als `RENDER_CACHE_MAX_AGE_DAYS`. Manuell:

```bash
docker compose exec backend python scripts/cleanup_rendered_svg.py
```

## Dev (ohne Docker)

Lokal ist der Sidecar ein **eigener Prozess** (wie LiteLLM), der separat gestartet werden muss:

```bash
cd render-sidecar
npm install          # einmalig (node-tikzjax + mathjax-full)
npm start            # http://127.0.0.1:3200
```

Läuft er nicht, greift dieselbe Degradierung wie oben. (Häufige Stolperfalle beim Testen.)
