/**
 * Abbildungen eines Wissensknotens — SVG an der Stelle, an der es im Text steht.
 *
 * Der Platzhalter `{{abbildung:EN_H2O.svg}}` ist die Absprache zwischen drei Stellen
 * (Paket 9): Das Seed-Skript setzt ihn anstelle der Obsidian-Einbettung `![[…]]` (AP5),
 * `_fuer_modell` im Backend macht daraus die Bildbeschreibung fürs Modell (AP3), und
 * hier wird er zum Bild.
 *
 * **Warum ein eigenes Modul.** Zwei Regeln stecken darin, und keine ist an der
 * Oberfläche zu erkennen: welches SVG zu welchem Platzhalter gehört (verglichen wird
 * der **Dateiname**, nicht der Pfad), und welche Abbildungen übrig bleiben, weil sie im
 * Text nicht vorkommen. Das Projekt prüft solche Regeln im Modul, nicht in der
 * Komponente.
 *
 * ⚠️ **Eine Füllfunktion für alle Stellen.** `renderMarkdown` erzeugt leere Hüllen im
 * Fließtext, die Detailansicht erzeugt dieselben Hüllen für die Abbildungen ohne
 * Einbettung und für das Schaltzeichen eines Bauteils. Alle füllt dieselbe Funktion —
 * sonst driften Sanitisierung und Beschriftung an drei Orten auseinander.
 */
import { sanitizeSvg } from './serverRender.js';

/** Die Hülle, die `renderMarkdown` erzeugt und diese Datei füllt. */
export const HUELLE = 'abbildung-block';

/**
 * Wie stark eine Abbildung gegenüber ihrer Eigengröße vergrößert wird.
 *
 * ⚠️ **Die Eigengröße ist eine Druckgröße, keine Bildschirmgröße.** Die
 * Strukturformeln kommen aus LaTeX/chemfig und tragen ihre Maße in Punkt — so groß,
 * wie sie auf Papier stehen sollen. Gemessen am Pilotbestand (26.09.2026) sind das
 * 41 bis 189 px Breite, und die Beschriftungen darin landen bei **7 bis 9 px**: halb
 * so groß wie der Fließtext daneben. Auf Papier stimmt das, auf dem Schirm nicht.
 *
 * **2,5 bringt die Beschriftung auf 17–22 px** — etwas über der Fließtextgröße, wie
 * es sich für eine Bildunterschrift in einer Zeichnung gehört. Der Faktor ist eine
 * Setzung, aber eine gemessene: Er richtet sich nach der Schrift **in** den Bildern,
 * nicht nach der Bildbreite.
 *
 * ⚠️ **Ein fester Faktor, keine feste Zielbreite.** Alle Zeichnungen kommen aus
 * derselben LaTeX-Strecke und haben dieselbe Schriftgröße. Jede auf die Spaltenbreite
 * zu ziehen machte die Beschriftung im kleinen Bild (HF, zwei Atome) fünfmal so groß
 * wie im großen (Ionengitter) — dieselbe Zeichnung, zwei Schriftgrößen. Der Faktor
 * hält sie gleich.
 */
export const ANZEIGE_FAKTOR = 2.5;

// Längenangaben, wie sie in `width` vorkommen können. `pt` ist der Regelfall (LaTeX),
// eine blanke Zahl sind Nutzereinheiten = px.
const EINHEITEN = { '': 1, px: 1, pt: 96 / 72, pc: 16, mm: 96 / 25.4, cm: 96 / 2.54, in: 96 };

/**
 * Die Breite eines SVG in CSS-Pixeln — aus `width`, ersatzweise aus der `viewBox`.
 *
 * ``null``, wenn beides fehlt oder unbrauchbar ist (z. B. `width="100%"`): Dann bleibt
 * es bei der Eigengröße, statt auf eine geratene Zahl zu skalieren.
 */
export function intrinsischeBreite(svg) {
    const attribut = /^\s*([\d.]+)\s*([a-z]*)\s*$/.exec(svg?.getAttribute?.('width') ?? '');
    if (attribut && EINHEITEN[attribut[2]] !== undefined) {
        const px = Number(attribut[1]) * EINHEITEN[attribut[2]];
        if (px > 0) return px;
    }
    // Zwei der neun Piktogramme im Pilot tragen **gar keine** Maße — der Browser
    // setzt sie dann auf 300 × 150 und staucht die Zeichnung hinein. Die `viewBox`
    // hat jede Datei.
    const kasten = (svg?.getAttribute?.('viewBox') ?? '').trim().split(/[\s,]+/);
    const breite = Number(kasten[2]);
    return kasten.length === 4 && breite > 0 ? breite : null;
}

/** Pseudoname des Schaltzeichens: Es ist eine Abbildung wie jede andere, nur ohne
 *  Datei — der Name hängt es an denselben Renderer, statt einen zweiten zu bauen. */
export const SCHALTZEICHEN = 'schaltzeichen';

/**
 * Alle Abbildungen eines Knotens: `illustrationen`, bei einem Bauteil dazu das
 * Schaltzeichen. Eine Regel für die Detailansicht und die Kontextliste im Chat.
 * (Dieselbe steht als SQL in `app/context/bausteine.py`, `_HAT_ABBILDUNGEN`.)
 */
export function alleAbbildungen(node) {
    const illustrationen = Array.isArray(node?.metadata?.illustrationen)
        ? node.metadata.illustrationen
        : [];
    const schaltzeichen = node?.content_type === 'bauteil' && node?.metadata?.schaltzeichen?.svg
        ? { ...node.metadata.schaltzeichen, datei: SCHALTZEICHEN }
        : null;
    return schaltzeichen ? [...illustrationen, schaltzeichen] : illustrationen;
}

/** Nur der Dateiname, nie der Pfad: Im Vault steht im Text die bare Form
 *  (`EN_H2O.svg`), im Frontmatter eine Pfadangabe (`_Abb/EN_H2O.svg`). */
export function dateiname(pfad) {
    return String(pfad ?? '').split('/').pop().trim();
}

/** Welche Dateinamen im Text eingebettet sind. */
export function eingebettet(content) {
    const namen = new Set();
    for (const treffer of String(content ?? '').matchAll(/\{\{abbildung:([^{}]+)\}\}/g)) {
        namen.add(dateiname(treffer[1]));
    }
    return namen;
}

/**
 * Die Abbildungen, die **nicht** im Text stehen.
 *
 * Sie sind kein Fehler: `_Format.md` erlaubt Abbildungen ohne Einbettung, und die
 * Detailansicht zeigt sie am Ende. Der umgekehrte Fall — eine Einbettung ohne Eintrag —
 * ist einer, und den meldet das Seed-Skript beim Import (AP5).
 */
export function ohneEinbettung(content, illustrationen) {
    const imText = eingebettet(content);
    return (illustrationen ?? []).filter(
        (abb) => abb?.datei && !imText.has(dateiname(abb.datei)),
    );
}

/**
 * Eine Abbildung in ihre Hülle setzen.
 *
 * ⚠️ **Sanitisiert, obwohl die Quelle die eigene ist.** Das SVG kommt aus dem Vault
 * einer Lehrkraft über das Seed-Skript — vertrauenswürdig, aber ungeprüft: Eine aus dem
 * Netz übernommene Strukturformel kann ein `<script>` oder ein `onload` tragen, und
 * niemand sieht es der Datei an. Dasselbe Profil wie bei den server-gerenderten
 * Blöcken (`sanitizeSvg`).
 *
 * **Die Beschreibung steht genau einmal.** Sie ist die Bildbeschreibung (`aria-label`
 * am Bild) *und* der sichtbare Text darunter — deshalb ist der sichtbare Text
 * `aria-hidden`: Sonst läse ein Screenreader beides vor.
 */
function fuelle(huelle, abb) {
    huelle.replaceChildren();
    const beschreibung = (abb?.beschreibung ?? '').trim();

    const bild = document.createElement('span');
    bild.className = 'abbildung-bild';
    bild.innerHTML = sanitizeSvg(abb?.svg ?? '');

    // Die Breite als Stil setzen, nicht als Attribut: Das Stylesheet deckelt sie
    // anschließend (`max-width`/`max-height`), damit ein quadratisches
    // Gefahrenpiktogramm — im Pilot 772 px groß — die Seite nicht füllt.
    const svg = bild.querySelector('svg');
    const breite = svg && intrinsischeBreite(svg);
    if (breite) {
        svg.style.width = `${Math.round(breite * ANZEIGE_FAKTOR)}px`;
    }
    if (beschreibung) {
        bild.setAttribute('role', 'img');
        bild.setAttribute('aria-label', beschreibung);
    }
    huelle.appendChild(bild);

    if (beschreibung) {
        const text = document.createElement('span');
        text.className = 'abbildung-text';
        text.setAttribute('aria-hidden', 'true');
        text.textContent = beschreibung;
        huelle.appendChild(text);
    }
}

/**
 * Jede leere Hülle unterhalb von `wurzel` mit ihrer Abbildung füllen.
 *
 * Zu einer Hülle ohne passenden Eintrag gehört eine **sichtbare** Meldung: Eine leere
 * Stelle im Text sieht aus wie ein Ladefehler und wird nicht gemeldet — dieselbe Regel
 * wie bei den Hilfeseiten.
 *
 * @param {HTMLElement} wurzel
 * @param {Array<{datei?: string, svg?: string, beschreibung?: string}>} illustrationen
 */
export function fuelleAbbildungen(wurzel, illustrationen) {
    if (!wurzel) return;
    const nachName = new Map(
        (illustrationen ?? [])
            .filter((abb) => abb?.datei)
            .map((abb) => [dateiname(abb.datei), abb]),
    );
    for (const huelle of wurzel.querySelectorAll(`.${HUELLE}[data-datei]`)) {
        const abb = nachName.get(dateiname(huelle.dataset.datei));
        if (abb?.svg) {
            fuelle(huelle, abb);
            continue;
        }
        huelle.replaceChildren();
        const hinweis = document.createElement('span');
        hinweis.className = 'abbildung-fehlt';
        hinweis.textContent = abb
            ? `Abbildung ${huelle.dataset.datei}: Datei fehlt.`
            : `Abbildung ${huelle.dataset.datei} ist nicht hinterlegt.`;
        huelle.appendChild(hinweis);
    }
}
