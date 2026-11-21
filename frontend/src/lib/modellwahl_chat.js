/**
 * Modellwahl im Chat (0.51, Päckchen AV Schritt 5) — Regeln ohne Markup.
 *
 * Das Backend setzt sie durch (`app/chat/modellwahl.py`); hier steht nur, was die Oberfläche
 * anbietet und mitschickt:
 * - **Freier Chat:** wie bisher das gewählte Modell, für alle Rollen.
 * - **Mit Assistent:** Lehrkräfte wählen, Schüler:innen (und die Vorschau) nicht. Leer heißt
 *   „wie der Assistent“ — dann entscheidet der Server (Modell des Assistenten oder die Vorliebe
 *   der Lehrkraft für Planungs-Assistenten).
 * - **Assistent mit Fähigkeiten:** nur Modelle, die Funktionen aufrufen können (⚙). Unbekannt
 *   (`supports_function_calling` fehlt) bleibt wählbar, wie im Backend.
 */

/** Die Modelle, die eine Lehrkraft für diesen Assistenten wählen kann — `null`: kein Wähler. */
export function modelleFuerAssistent({ istLehrkraft, assistent, modelle }) {
  if (!istLehrkraft || !assistent) return null
  const braucht = (assistent.tool_groups ?? []).length > 0
  return braucht ? modelle.filter((m) => m.supports_function_calling !== false) : modelle
}

/** Welches Modell mit der Nachricht geht (`null`: keins, der Server entscheidet). */
export function zuSendendesModell({ mitAssistent, istLehrkraft, frei, imAssistenten }) {
  if (!mitAssistent) return frei || null
  return istLehrkraft ? imAssistenten || null : null
}


/**
 * Kosten **mit diesem Assistenten** für ein Modell (0.51, AV Schritt 6).
 *
 * Wie `app/assistants/kosten.py`: mittlere Nachricht des Modells + feste Token des Assistenten
 * (Prompt, Bausteine, Dokumente) × Eingabepreis. So stehen im Wähler und neben dem Assistenten
 * dieselben Zahlen. Fehlt eine Angabe, bleibt sie fehlend — eine Null hieße „kostenlos“.
 *
 * @returns {{usd_je_nachricht: number|null, usd_dokumente: number|null}}
 */
export function kostenMitAssistent(modell, assistent) {
  const preis = modell?.usd_je_eingabetoken
  if (modell?.usd_je_nachricht == null || preis == null || assistent?.token_zusatz == null) {
    return { usd_je_nachricht: null, usd_dokumente: null }
  }
  return {
    usd_je_nachricht: modell.usd_je_nachricht + assistent.token_zusatz * preis,
    usd_dokumente: assistent.token_dokumente ? assistent.token_dokumente * preis : null,
  }
}

/** Die Einträge des Wählers mit den Kosten mit diesem Assistenten. */
export function modelleMitAssistentenKosten(modelle, assistent) {
  return (modelle ?? []).map((m) => ({ ...m, usd_je_nachricht: kostenMitAssistent(m, assistent).usd_je_nachricht }))
}

/**
 * Der Assistent, wie ihn der Info-Knopf zeigt: mit den Kosten des **gewählten** Modells.
 * Ohne Wahl („wie der Assistent“) oder ohne passende Angaben bleibt seine eigene Schätzung.
 */
export function assistentMitModell(assistent, modell) {
  if (!assistent || !modell) return assistent
  const k = kostenMitAssistent(modell, assistent)
  return k.usd_je_nachricht == null ? assistent : { ...assistent, ...k }
}
