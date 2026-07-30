// Werkzeug-Assistenten — Definition & Filter
//
// Ein „Werkzeug-Assistent" ist ein Assistent, der eine artefakterzeugende
// Werkzeug-Gruppe führt (aktuell Bildgenerierung; künftig z. B. Video, Sprache/TTS,
// Mindmaps). Bewusst NICHT enthalten: pädagogische/Wissens-Werkzeuge wie `planning`,
// `student_planning`, `context_search` — die sind keine „Werkzeuge" im Sinne der
// Werkzeug-Übersicht. Diese Menge kann später erweitert werden (oder per Wunsch auch
// Planungs-Assistenten aufnehmen).
export const MEDIA_TOOL_GROUPS = ["image_generation"];

/**
 * Prüft, ob ein Assistent (AssistantSummary aus GET /assistants) eine
 * artefakterzeugende Werkzeug-Gruppe führt.
 * @param {{ tool_groups?: string[] }} assistant
 * @returns {boolean}
 */
export function isToolAssistant(assistant) {
    const groups = assistant?.tool_groups ?? [];
    return groups.some((g) => MEDIA_TOOL_GROUPS.includes(g));
}
