/**
 * Die Sammlungs-Ansichten (`/knowledge/collections/<typ>`) — Regeln ohne Markup.
 *
 * **Warum ein eigenes Modul.** Liste und Editor lesen dieselbe Konfiguration, und die
 * Ableitungen daraus (Welche Spalten? Welcher Wert steht in einer Spalte? Ist das
 * Formular ausfüllbar?) sind das Einzige an den beiden Seiten, was sich ohne Browser
 * prüfen lässt — das Projekt hat keine Komponententests.
 *
 * Die Konfiguration selbst kommt aus der Taxonomie (`COLLECTIONS`, `FELD_SCHEMATA`) und
 * wird beim Build erzeugt. Sie ist **dieselbe**, aus der das Backend prüft
 * (`app/context/metadata.py`) — hier steht keine zweite Fassung der Regeln.
 */
import {
  COLLECTIONS,
  CONTENT_TYPES,
  CONTENT_TYPE_LABELS,
  FELD_SCHEMATA,
} from "$lib/taxonomy.js"

/**
 * Die Kategorie eines Typs — sie muss beim Anlegen mitgeschickt werden und ist das
 * einzige Feld mit Datenbank-Constraint.
 *
 * ⚠️ Nicht raten: Die fünf Sammlungen liegen in **drei** Kategorien (`begriff` ist
 * `concept`, `methodenblatt`/`operatorenblatt` sind `document`, `methode`/`sozialform`
 * sind `knowledge`). Der erste Entwurf des Editors schrieb `knowledge` fest und
 * scheiterte im Live-Test mit 422.
 */
export function kategorieVon(typ) {
  for (const [kategorie, typen] of Object.entries(CONTENT_TYPES)) {
    if (typen.includes(typ)) return kategorie
  }
  return null
}

/** Alle Sammlungen in Konfigurationsreihenfolge — so zeigt sie auch die Sidebar. */
export function alleSammlungen() {
  return Object.keys(COLLECTIONS).map((typ) => ({
    typ,
    label: CONTENT_TYPE_LABELS[typ] ?? typ,
    beschreibung: COLLECTIONS[typ].beschreibung ?? "",
  }))
}

/** Die Konfiguration eines Typs, oder `null` — für unbekannte Typen und 404-Fälle. */
export function sammlung(typ) {
  return COLLECTIONS[typ] ?? null
}

export function feldSchema(typ) {
  return FELD_SCHEMATA[typ] ?? {}
}

/**
 * Die Spalten einer Sammlung als Anzeigebeschreibung.
 *
 * Feste Spalten hängen am Knoten selbst, alle übrigen sind Metadatenfelder und holen
 * Label und Typ aus dem Schema — damit eine Zahl rechtsbündig stehen kann und eine
 * Liste als Aufzählung.
 */
const FESTE_LABELS = {
  titel: "Titel",
  fach: "Fach",
  status: "Status",
  geaendert: "Zuletzt geändert",
}

export function spalten(typ) {
  const config = sammlung(typ)
  if (!config) return []
  const schema = feldSchema(typ)
  return (config.spalten ?? []).map((name) => ({
    name,
    label: FESTE_LABELS[name] ?? schema[name]?.label ?? name,
    fest: name in FESTE_LABELS,
    typ: schema[name]?.typ ?? null,
  }))
}

/** Welche Filter die Sammlung anbietet (`fach`, `status`, `titel` oder ein Feldname). */
export function filter(typ) {
  return sammlung(typ)?.filter ?? []
}

/**
 * Der anzuzeigende Wert einer Spalte für einen Knoten.
 *
 * Gibt einen String zurück — die Liste zeigt Text, keine Objekte. Fehlt der Wert, steht
 * dort ein Gedankenstrich: Bei `methode` ist „kein Fach" der **Normalfall**
 * (fachübergreifende Einträge), keine Lücke.
 */
export function zellenwert(node, spalte, { fachname = null } = {}) {
  switch (spalte.name) {
    case "titel":
      return node.title ?? ""
    case "fach":
      return fachname ?? "—"
    case "status":
      return node.status === "archived" ? "archiviert" : "aktiv"
    case "geaendert":
      return node.updated_at
        ? new Date(node.updated_at).toLocaleDateString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
          })
        : "—"
    default: {
      const wert = (node.metadata ?? {})[spalte.name]
      if (wert === undefined || wert === null || wert === "") return "—"
      return Array.isArray(wert) ? wert.join(", ") : String(wert)
    }
  }
}

/** Label und Pflicht des Knotentexts — bei `begriff` heißt er „Definition". */
export function contentFeld(typ) {
  const c = sammlung(typ)?.content ?? {}
  return {
    label: c.label ?? "Inhalt",
    pflicht: Boolean(c.pflicht),
    hinweis: c.hinweis ?? null,
  }
}

/**
 * Ist das Formular abschickbar?
 *
 * Prüft **nur**, was ohne Server entscheidbar ist: Titel da, Pflichttext da, Zahlen im
 * erlaubten Bereich. Die verbindliche Prüfung bleibt im Backend — hier geht es darum,
 * dass niemand auf „Speichern" drückt und einen 422 bekommt, den er vorher hätte sehen
 * können.
 *
 * @returns {Record<string,string>} Feldname → Meldung; leer heißt abschickbar.
 */
export function pruefeEntwurf(typ, entwurf) {
  const fehler = {}
  const text = contentFeld(typ)

  if (!(entwurf.title ?? "").trim()) fehler.title = "Ein Titel ist nötig."
  if (text.pflicht && !(entwurf.content ?? "").trim()) {
    fehler.content = `„${text.label}“ ist ein Pflichtfeld.`
  }

  const schema = feldSchema(typ)
  for (const [name, feld] of Object.entries(schema)) {
    const wert = (entwurf.metadata ?? {})[name]
    if (wert === undefined || wert === null || wert === "") continue

    if (feld.typ === "int") {
      const zahl = Number(wert)
      if (!Number.isInteger(zahl)) {
        fehler[name] = `„${feld.label}“ muss eine ganze Zahl sein.`
      } else if (feld.min !== undefined && zahl < feld.min) {
        fehler[name] = `„${feld.label}“ muss mindestens ${feld.min} sein.`
      } else if (feld.max !== undefined && zahl > feld.max) {
        fehler[name] = `„${feld.label}“ darf höchstens ${feld.max} sein.`
      }
    } else if (feld.typ === "auswahl" && !(feld.werte ?? []).includes(wert)) {
      fehler[name] = `„${feld.label}“ hat einen unbekannten Wert.`
    }
  }
  return fehler
}

/**
 * Wandelt die Formularwerte in das `metadata`-Objekt für die API.
 *
 * Leere Felder werden **weggelassen**, nicht als `""` geschickt: Ein leeres Feld heißt
 * „nicht gesetzt", und ein leerer String stünde später in der Spalte.
 */
export function metadatenAusFormular(typ, werte, bestehend = {}) {
  const schema = feldSchema(typ)
  const md = { ...bestehend }
  for (const [name, feld] of Object.entries(schema)) {
    const roh = werte[name]
    if (roh === undefined || roh === null || roh === "" ||
        (Array.isArray(roh) && roh.length === 0)) {
      delete md[name]
      continue
    }
    md[name] = feld.typ === "int" ? Number(roh) : roh
  }
  return md
}
