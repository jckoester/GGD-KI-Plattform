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

/** Datum + Uhrzeit in der Form, die in eine Quellenangabe gehört. */
export function zeitpunkt(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString('de-DE', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });
}

/** Kürzt einen Prompt fürs Zitat — der volle Text sprengt jede Quellenangabe. */
function gekuerzt(text, max = 300) {
    const t = String(text ?? '').replace(/\s+/g, ' ').trim();
    if (!t) return null;
    return t.length > max ? `${t.slice(0, max - 1)}…` : t;
}

/**
 * Baut den Textbaustein für eine Quellenangabe.
 *
 * Bewusst Fließtext und keine Norm-Zitierweise: Die Vorgaben für GFS, Seminarkurs und
 * Facharbeit unterscheiden sich von Schule zu Schule und von Fach zu Fach. Der Baustein
 * liefert die **Angaben**, die Formatierung macht die Schülerin nach ihrer Vorgabe.
 *
 * @param {{
 *   werkzeug: string,
 *   modell?: string | null,
 *   zeitpunkt?: string | null,
 *   eingabe?: string | null,
 *   bilder?: Array<{ modell?: string | null, prompt?: string | null }>,
 * }} angaben
 * @returns {string}
 */
export function zitatText({ werkzeug, modell, zeitpunkt: wann, eingabe, bilder = [] }) {
    const zeilen = [];

    const kopf = [werkzeug];
    if (modell) kopf.push(`Modell ${modell}`);
    zeilen.push(wann ? `${kopf.join(', ')}, abgerufen am ${wann}` : kopf.join(', '));

    const eigene = gekuerzt(eingabe);
    if (eigene) zeilen.push(`Eigene Eingabe: „${eigene}“`);

    for (const bild of bilder) {
        const teile = [];
        if (bild.modell) teile.push(`Bild erzeugt mit ${bild.modell}`);
        const bp = gekuerzt(bild.prompt);
        // Der Bild-Prompt stammt vom Sprachmodell, nicht von der Nutzerin. Ihn als eigene
        // Eingabe zu zitieren wäre eine Falschangabe — deshalb steht die Urheberschaft
        // ausdrücklich dabei.
        if (bp) teile.push(`Bild-Prompt (vom Sprachmodell formuliert): „${bp}“`);
        if (teile.length) zeilen.push(teile.join('. '));
    }

    return zeilen.join('\n');
}
