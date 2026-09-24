/**
 * Serverseitige Hooks des Frontends.
 *
 * ⚠️ **Nur CSS vorladen — sonst wird der Antwortkopf zu groß für den Proxy.**
 *
 * SvelteKit legt für jede Seite einen `Link`-Kopf mit Vorlade-Hinweisen an. Mit der
 * Vorgabe (`js` und `css`) standen dort **98 `modulepreload`-Einträge**, und der Kopf
 * wuchs mit der Routentiefe:
 *
 * | Route | Kopf mit Vorgabe | nur CSS |
 * |---|---|---|
 * | `/` | 2 460 B | 273 B |
 * | `/chat` | 7 041 B | 366 B |
 * | `/knowledge/curriculum/…` | 6 601 B | 468 B |
 *
 * nginx liest den Antwortkopf in **einen** Puffer, dessen Vorgabe eine Speicherseite ist
 * (4 KB). Alles darüber endet mit `upstream sent too big header` und **502** — beim
 * *Neuladen* einer tiefen URL, nicht beim Klicken, denn clientseitige Navigation holt
 * die Bausteine direkt. Genau so gemeldet aus dem Betatest (23.09.2026): „Nur `/` lädt
 * sauber."
 *
 * **Warum nicht bloß den Puffer hochsetzen?** Das ist zusätzlich geschehen
 * (`infra/nginx.conf`) — aber es genügt nicht: Vor dem Docker-Stack steht der
 * Reverse-Proxy der Schule, und der bekäme den großen Kopf dann als Erster. Eine
 * Plattform, die Schulen selbst betreiben, darf keine Köpfe senden, die ein
 * Standard-Proxy ablehnt.
 *
 * **Was der Verzicht kostet:** Die Modul-Hinweise sparen dem Browser das Entdecken der
 * Bausteine über die Skript-Tags der Seite — Millisekunden beim ersten Laden. CSS bleibt
 * vorgeladen, weil es das Rendern blockiert.
 */
export async function handle({ event, resolve }) {
    return resolve(event, { preload: ({ type }) => type === 'css' })
}
