/**
 * Ansichtslogik der Artefakt-Übernahme (AP8).
 *
 * **Warum ein eigenes Modul.** Die Übernahme hat zwei Einstiege — die Bibliothek und
 * den Chat — und beide sollen dieselben Sätze sagen und dieselbe Nutzlast schicken.
 * Als Funktionen neben der Komponente ist das prüfbar, ohne eine Seite zu rendern; als
 * Zweitfassung in der zweiten Komponente wäre es die übliche Drift.
 *
 * Was hier **nicht** steht: die Rechteentscheidung. Welche Bausteinart eine Rolle wählen
 * darf und ob die Sichtbarkeit festliegt, sagt der Server (`GET /artifacts/{id}/baustein`).
 * Diese Datei stellt nur dar, was er geantwortet hat.
 */
import { auswaehlbareTypOptionen } from "$lib/knotentypen.js"
import { SCOPE_DEFAULTS, SCHULJAHRESENDE_CONTENT_TYPES } from "$lib/taxonomy.js"

/** Die angebotenen Bausteinarten als beschriftete, alphabetisch sortierte Optionen. */
export function typOptionen(vorschlag) {
  return auswaehlbareTypOptionen(vorschlag?.typen ?? [])
}

/**
 * Vorbelegung der Sichtbarkeit für eine Bausteinart.
 *
 * Erzwingt der Server die Sichtbarkeit (Schüler:innen), gilt seine Angabe — sonst die
 * Vorgabe der Taxonomie, dieselbe wie im Anlege-Formular.
 *
 * @returns {{read: string, write: string, fest: boolean}}
 */
export function scopeVorgabe(vorschlag, contentType) {
  const erzwungen = vorschlag?.scopes_erzwungen
  if (erzwungen) return { read: erzwungen[0], write: erzwungen[1], fest: true }
  const [read, write] = SCOPE_DEFAULTS[contentType] ?? ["school", "private"]
  return { read, write, fest: false }
}

/** Braucht dieser Scope eine Trägergruppe? */
export function brauchtGruppe(scope) {
  return scope === "group" || scope === "subject"
}

/**
 * Die Nutzlast für `POST /artifacts/{id}/baustein`.
 *
 * ⚠️ Gruppen-IDs werden **genullt**, wenn der Scope sie nicht trägt. Bliebe eine ID
 * einer vorher gewählten Gruppe stehen, hinge der Baustein an einer Klasse, die in
 * seiner Sichtbarkeit gar nicht vorkommt — stumm, weil die Datenbank nur das Fehlen
 * prüft, nicht das Zuviel.
 */
export function nutzlast({
  contentType,
  titel,
  readScope = null,
  writeScope = null,
  readGroupId = null,
  writeGroupId = null,
  validUntil = "",
  schuljahr = "",
}) {
  return {
    content_type: contentType,
    title: (titel ?? "").trim() || null,
    read_scope: readScope,
    write_scope: writeScope,
    read_scope_group_id: brauchtGruppe(readScope) ? readGroupId : null,
    write_scope_group_id: brauchtGruppe(writeScope) ? writeGroupId : null,
    valid_until: validUntil || null,
    schuljahr: schuljahr || null,
  }
}

/** Beschriftung des Bestätigungsknopfes — beim zweiten Mal heißt er anders. */
export function knopfBeschriftung(vorschlag) {
  return vorschlag?.vorhandener_baustein_id
    ? "Baustein aktualisieren"
    : "Als Baustein speichern"
}

/**
 * Was nach dem Speichern dasteht.
 *
 * Drei Ausgänge, die sich für die Nutzer:in wirklich unterscheiden: neu, neue Fassung
 * (mit archivierter Vorgängerin), oder nichts zu tun.
 */
export function erfolgsMeldung(antwort) {
  if (!antwort?.created) {
    return "Dieser Baustein ist bereits gespeichert — es hat sich nichts geändert."
  }
  if (antwort.ersetzt_node_id) {
    return "Neue Fassung gespeichert. Die vorherige liegt im Archiv und bleibt über den Baustein erreichbar."
  }
  return "Als Baustein gespeichert."
}

/**
 * Hinweis zum leeren Ablaufdatum.
 *
 * Bei diesen Arten heißt „kein Datum" nicht „läuft nie ab": Der Server trägt das
 * Schuljahresende ein. Ohne den Satz bekäme man ein Ablaufdatum, das man nicht
 * gewählt hat — derselbe Hinweis wie im Anlege-Formular.
 */
export function ablaufHinweis(contentType, validUntil) {
  if (validUntil) return null
  if (!SCHULJAHRESENDE_CONTENT_TYPES.has(contentType)) return null
  return "Ohne Angabe gilt dieser Baustein bis zum Ende des Schuljahres und wandert danach ins Archiv."
}
