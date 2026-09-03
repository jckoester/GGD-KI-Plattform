/**
 * Wo ein Baustein bearbeitet wird — nicht jeder Typ im allgemeinen Editor.
 *
 * **Das Problem, das dieses Modul löst.** Die Knotenliste führte jeden Typ auf dieselbe
 * Detailseite und von dort in denselben Editor. Für einen Stundenentwurf ist das
 * irreführend: Sein Inhalt sind Phasen, Kompetenzverweise und Sozialformen, und der
 * allgemeine Editor zeigt davon ein rohes JSON-Feld. Man kommt also genau dort an, wo
 * man die beabsichtigte Änderung **nicht** machen kann.
 *
 * Drei Fälle:
 *
 * 1. **Eigener Editor, Ziel aus dem Knoten ableitbar** — Planungsobjekte tragen ihre
 *    Gruppe (`write_scope_group_id`) und ihr Fach; daraus ergibt sich die Planer-Route.
 *    Sammlungen kennen ihren Editor über den Typ.
 * 2. **Allgemeiner Editor** — alles, was keinen eigenen hat.
 * 3. **Kein Bearbeiten** — importierte Bausteine (Bildungsplan), und Fälle, in denen
 *    der eigene Editor Angaben braucht, die am Knoten nicht stehen. Dann sagt die
 *    Oberfläche, wo es hingehört, statt an die falsche Stelle zu führen.
 */
import { sammlung } from "$lib/collections.js"

/** Typen, deren Pflege ausschließlich im Planer stattfindet. */
const PLANUNG = {
  jahresplan: { tief: false, wort: "Jahresplan" },
  unterrichtseinheit: { tief: false, wort: "Unterrichtseinheit" },
  unterrichtsstunde: { tief: true, wort: "Stundenentwurf" },
}

/**
 * @param {object} node        Knoten mit `content_type`, `write_scope_group_id`, `subject_id`
 * @param {object|null} fach   Fach-Eintrag aus `subjectMap` (braucht `slug`)
 * @param {string|null} back   Rückweg, der weitergereicht wird
 * @returns {{art: 'planer'|'sammlung'|'allgemein'|'keiner', url: string|null,
 *            label: string, hinweis: string|null}}
 */
export function bearbeitenZiel(node, fach = null, back = null) {
  if (!node) return { art: "keiner", url: null, label: "Bearbeiten", hinweis: null }

  const query = back ? `?back=${encodeURIComponent(back)}` : ""

  const planung = PLANUNG[node.content_type]
  if (planung) {
    const gruppe = node.write_scope_group_id ?? node.read_scope_group_id
    // Ohne Gruppe oder Fach gibt es keine Planer-Adresse. Das kommt bei von Hand
    // angelegten Knoten vor — dann lieber sagen, wo es hingehört, als in einen Editor
    // zu führen, der die Phasen als JSON zeigt.
    if (!gruppe || !fach?.slug) {
      return {
        art: "keiner",
        url: null,
        label: "Bearbeiten",
        hinweis: `${planung.wort}e werden im Planer der Unterrichtsgruppe bearbeitet.`,
      }
    }
    const basis = `/subjects/${fach.slug}/groups/${gruppe}/planner`
    return {
      art: "planer",
      url: planung.tief ? `${basis}/lessons/${node.id}` : basis,
      label: "Im Planer öffnen",
      hinweis: null,
    }
  }

  if (sammlung(node.content_type)) {
    return {
      art: "sammlung",
      url: `/knowledge/collections/${node.content_type}/${node.id}/edit${query}`,
      label: "Bearbeiten",
      hinweis: null,
    }
  }

  return {
    art: "allgemein",
    url: `/knowledge/${node.id}/edit${query}`,
    label: "Bearbeiten",
    hinweis: null,
  }
}
