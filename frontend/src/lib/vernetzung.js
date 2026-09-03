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
  reflects_on: { raus: "Reflektiert", rein: "Reflektiert durch" },
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

    const richtung =
      RELATION_LABEL[kante.relation]?.symmetrisch || raus ? "raus" : "rein"
    ;(nach[`${kante.relation}:${richtung}`] ??= []).push({ kante, gegen, raus })
  }

  return Object.entries(nach)
    .map(([schluessel, eintraege]) => {
      const [relation, richtung] = schluessel.split(":")
      const b = RELATION_LABEL[relation] ?? {}
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
