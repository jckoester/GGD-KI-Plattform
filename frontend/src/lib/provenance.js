// Herkunftsangaben: Modellname aufbereiten (Modell-Transparenz)
//
// Gespeichert wird das volle Anbietermodell, wie es in der LiteLLM-Config steht —
// `openai/openai/gpt-oss-120b`, `mistral/mistral-small-latest`, `anthropic/claude-sonnet-5`.
// Das Präfix ist LiteLLM-Syntax und gehört nicht in eine Quellenangabe.
//
// ⚠️ Die Umkehrung ist **kein** Anbietername: Bei IONOS lautet der Eintrag
// `openai/openai/gpt-oss-120b`, weil die API OpenAI-kompatibel ist — „openai" wäre hier
// schlicht falsch. Deshalb wird der Anbieter bewusst nirgends aus dem Modellnamen
// abgeleitet; genannt wird das Modell, und als Werkzeug die Plattform selbst.

/**
 * Volles Anbietermodell → der Name, den man zitiert.
 * `openai/openai/gpt-oss-120b` → `gpt-oss-120b`
 * @param {string | null | undefined} providerModel
 * @returns {string | null}
 */
export function zitiername(providerModel) {
    if (!providerModel) return null;
    const teile = String(providerModel).replace(/\/+$/, '').split('/');
    return teile[teile.length - 1] || null;
}

/**
 * Hat dieser Inhalt eine belegbare Herkunft?
 * @param {{ provider_model?: string | null }} objekt
 */
export function hatHerkunft(objekt) {
    return !!zitiername(objekt?.provider_model);
}
