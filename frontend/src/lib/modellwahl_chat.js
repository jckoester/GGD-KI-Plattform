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
