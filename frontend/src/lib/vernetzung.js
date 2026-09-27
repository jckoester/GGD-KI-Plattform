/**
 * Die Nachbarschaft eines Knotens als Liste (UI-Notiz A3) — Regeln ohne Markup.
 *
 * **Warum ein eigenes Modul.** Drei Regeln stecken hier, und keine davon ist an der
 * Oberfläche zu erkennen: welche Kanten überhaupt zu diesem Knoten gehören, wie Richtung
 * und Symmetrie gruppiert werden, und ab wann eine Liste in eine Zahl umschlägt. Das
 * Projekt hat keine Komponententests — was geprüft werden soll, muss hier stehen.
 */

/**
 * Die Kantenarten in der Sprache der Sache — **je Richtung ein eigener Satz**.
 *
 * „Gehört zu" und „Enthält" sind dieselbe Kante von zwei Seiten gelesen, und beide Sätze
 * sagen etwas anderes. Ein kleiner Richtungspfeil neben dem Titel trug das gerade nicht:
 * Man musste ihn erst deuten.
 *
 * `symmetrisch` markiert Relationen, bei denen die Richtung **keine** Bedeutung trägt —
 * „A steht in Beziehung zu B" heißt dasselbe wie umgekehrt. Sie in zwei Gruppen zu
 * trennen wäre eine Unterscheidung ohne Unterschied.
 */
export const RELATION_LABEL = {
  related_to: { raus: "Steht in Beziehung zu", symmetrisch: true },
  used_with: { raus: "Wird verwendet mit", symmetrisch: true },
  part_of: { raus: "Gehört zu", rein: "Enthält" },
  references: { raus: "Verweist auf", rein: "Wird verwiesen von" },
  develops: { raus: "Entwickelt", rein: "Wird entwickelt von" },
  requires: { raus: "Setzt voraus", rein: "Vorausgesetzt für" },
  supersedes: { raus: "Löst ab", rein: "Abgelöst durch" },
  follows: { raus: "Folgt auf", rein: "Gefolgt von" },
  derived_from: { raus: "Abgeleitet aus", rein: "Grundlage für" },
  // ⚠️ **Nicht symmetrisch und nicht `part_of`.** „Natriumchlorid ist ein Salz"
  // liest sich rückwärts als „Salz — Unterart: Natriumchlorid", nicht als
  // „Salz ist ein Natriumchlorid".
  is_a: { raus: "Ist ein(e)", rein: "Unterarten" },
}

/**
 * Feinere Sätze für `related_to`-Kanten, die eine `art` tragen (Paket 9).
 *
 * ⚠️ **Warum nicht je eine eigene Relation.** Der Knotentyp `stoffsteckbrief` führt
 * `is_a`, `related_to` und `references` (AP2b); jede Spielart zu einer Relation zu
 * machen hieße, den CHECK-Constraint und drei Listen für eine Beschriftungsfrage
 * anzufassen. `art` steht in den **Kanten**-Metadaten — genau dafür sind sie da.
 *
 * Ohne Eintrag hier bleibt es bei „Steht in Beziehung zu": Eine unbekannte Art ist
 * kein Fehler, nur eine Kante ohne eigenen Satz.
 */
export const ART_LABEL = {
  abgrenzung: { raus: "Grenzt sich ab von", symmetrisch: true },
  // Richtung ist hier die Aussage: Die frühere Fassung wird in der späteren vertieft.
  vertiefung: { raus: "Wird vertieft in", rein: "Vertieft" },
  teilchen: { raus: "Besteht aus den Teilchen", rein: "Kommt vor in" },
  ghs: { raus: "Gefahrenpiktogramme", rein: "Gilt für" },
}

/** Ab hier wird gekappt und „+ n weitere" gezeigt (ADR-013-Leitplanke). */
export const KAPPUNG = 20

/**
 * Und ab hier bleibt nur die Zahl.
 *
 * Gemessen am 03.09.2026 am Bestand: Ein Leitperspektive-Aspekt trägt im Mittel 162
 * Kanten, in der Spitze **941** — davon 940 eingehende Verweise. Zwanzig Titel aus 940
 * wären dort keine Auskunft, sondern eine willkürliche Stichprobe, die nach Auswahl
 * aussieht.
 */
export const NUR_ZAHL_AB = 100

/**
 * Die Kanten der Nachbarschaft nach Relation **und Richtung** gruppieren.
 *
 * ⚠️ `GET /neighborhood` liefert **alle** Kanten zwischen den sichtbaren Knoten — auch
 * solche, die zwei Nachbarn untereinander verbinden und diesen Knoten gar nicht
 * berühren. Ohne die Prüfung unten stünden sie in der Liste, als gingen sie von hier
 * aus. Eine Liste kann sie nicht sinnvoll zeigen; ein Graph könnte es.
 *
 * Der Sichtbarkeitsfilter greift von selbst: Die Nachbarschaft enthält nur lesbare
 * Knoten, eine Kante ohne sichtbares Gegenstück fällt heraus — nicht anonymisiert
 * angedeutet.
 *
 * @returns {Array<{schluessel, label, gesamt, sichtbar, weitere, nurZahl}>}
 *          absteigend nach Anzahl.
 */
export function gruppiereKanten(node, nachbarschaft) {
  if (!node || !nachbarschaft) return []

  const knoten = Object.fromEntries((nachbarschaft.nodes ?? []).map((n) => [n.id, n]))
  const nach = {}

  for (const kante of nachbarschaft.edges ?? []) {
    const raus = kante.from_node_id === node.id
    const rein = kante.to_node_id === node.id
    if (!raus && !rein) continue

    const gegen = knoten[raus ? kante.to_node_id : kante.from_node_id]
    if (!gegen || gegen.id === node.id) continue

    // Die Art verfeinert nur `related_to` — bei `is_a` oder `requires` wäre sie eine
    // zweite Aussage über dieselbe Kante.
    const art =
      kante.relation === "related_to" && ART_LABEL[kante.metadata?.art]
        ? kante.metadata.art
        : ""
    const beschriftung = art ? ART_LABEL[art] : RELATION_LABEL[kante.relation]
    const richtung = beschriftung?.symmetrisch || raus ? "raus" : "rein"
    ;(nach[`${kante.relation}:${richtung}:${art}`] ??= []).push({ kante, gegen, raus })
  }

  return Object.entries(nach)
    .map(([schluessel, eintraege]) => {
      const [relation, richtung, art] = schluessel.split(":")
      const b = (art ? ART_LABEL[art] : RELATION_LABEL[relation]) ?? {}
      const nurZahl = eintraege.length > NUR_ZAHL_AB
      return {
        schluessel,
        label: (richtung === "rein" ? b.rein : b.raus) ?? `${relation} (${richtung})`,
        gesamt: eintraege.length,
        sichtbar: nurZahl ? [] : eintraege.slice(0, KAPPUNG),
        weitere: nurZahl ? eintraege.length : Math.max(0, eintraege.length - KAPPUNG),
        nurZahl,
      }
    })
    .sort((a, b) => b.gesamt - a.gesamt)
}
