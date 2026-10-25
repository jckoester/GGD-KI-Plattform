/**
 * Welche Assistenten eine **Anzeigeliste** zeigt (0.22, Päckchen C1, F3).
 *
 * `visibility: hidden` heißt: nicht in Übersicht, Auswahl und (später) Vorschlag — aber
 * benutzbar über Link (`/chat?assistant_id=`), Einstieg und Chat. Deshalb filtert hier die
 * **Darstellung**, nicht die Zugangsregel (`backend/app/assistants/sichtbarkeit.py`), und
 * die Einstiege (`assistentenwahl.js`) wählen weiter aus der vollen Liste.
 *
 * `private` als Sichtbarkeit gibt es seit 0.22 nicht mehr — das Modell speichert es als
 * `hidden` (Jan, 25.10.2026). Ein Altbestand mit `private` wird hier ebenso verborgen.
 *
 * @param {Array<{visibility?: string}>|null|undefined} liste
 */
export function zurAnzeige(liste) {
  return (liste ?? []).filter((a) => a?.visibility !== "hidden" && a?.visibility !== "private");
}
