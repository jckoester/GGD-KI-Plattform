/**
 * Die Unterrichtsgruppe eines Chats erkennbar machen (Paket 7, AP5).
 *
 * **Das Problem:** Eine Lehrkraft führt in derselben Woche Chats zu vier Gruppen. In der
 * Liste stehen sie untereinander und unterscheiden sich nur im Titel — „Sinusfunktionen
 * verstehen" sagt nicht, für welche Klasse.
 *
 * ⚠️ **Keine erfundenen Kürzel.** Naheliegend wäre, „Mathematik 9C" zu „M 9C" zu kürzen.
 * Das geht bei Mathematik gut und bei „Naturwissenschaft und Technik 10A/10B/10C"
 * schlecht — und eine Abkürzung, die die Lehrkraft nicht gewählt hat, steht dann in jeder
 * Zeile. Die Plattform hat für genau diesen Zweck bereits `groups.display_name`
 * (Alembic 0062): die **selbst vergebene** Kurzform. Das Backend liefert sie in `name`
 * bereits aufgelöst (`display_name or name`); wo keine gesetzt ist, steht hier der volle
 * Name und die Darstellung kürzt ihn mit CSS. Wer es kürzer will, vergibt einen
 * Anzeigenamen — an einer Stelle, statt in jeder Zeile zu raten.
 */

/**
 * Die Gruppe zu einer Konversation — oder `null`.
 *
 * `null` heißt „nichts anzeigen", und zwar in **drei** Fällen, die sich für die Anzeige
 * gleich verhalten: kein Gruppenbezug, Gruppe unbekannt (etwa nach dem Austritt), oder
 * die Liste ist noch nicht geladen. Eine Marke zu erfinden wäre in allen dreien falsch.
 */
export function gruppeZumChat(groupId, gruppen) {
    if (groupId == null) return null
    return (gruppen ?? []).find((g) => g.id === groupId) ?? null
}

/**
 * Die Marke für die Zeile: kurzer Text, oder `null`.
 *
 * Bewusst **kein** Rückfall auf die Fach-Bezeichnung: Das Fach steht in der Liste schon
 * als farbiges Symbol. Eine zweite Anzeige desselben Wissens kostet Platz und sagt nichts.
 *
 * ⚠️ **Nur für Lehrkräfte.** Aus Schülersicht *ist* die Unterrichtsgruppe das Fach
 * (CLAUDE.md, Fachbegriff-Tabelle): Sie sehen „Mathematik", nicht „M 10C". Und sie
 * brauchen die Unterscheidung nicht — sie haben je Fach in der Regel eine Gruppe, deren
 * Farbe schon in der Zeile steht. Für eine Lehrkraft ist es umgekehrt: Vier Chats
 * „Sinusfunktionen verstehen" untereinander unterscheiden sich nur durch die Gruppe.
 */
export function gruppenMarke(groupId, gruppen, { istLehrkraft = false } = {}) {
    if (!istLehrkraft) return null
    const gruppe = gruppeZumChat(groupId, gruppen)
    const text = (gruppe?.name ?? "").trim()
    return text ? text : null
}

/**
 * Der Tooltip einer Chat-Zeile: Titel, und dahinter die Gruppe, falls es eine gibt.
 *
 * ⚠️ **Der Titel bleibt vorn.** In der Sidebar ist er abgeschnitten; wer den Zeiger
 * daraufhält, will zuerst wissen, wie der Chat vollständig heißt. Die Gruppe ist der
 * Zusatz, nicht die Auskunft.
 */
export function chatTooltip(titel, marke) {
    const t = (titel ?? "").trim() || "Unbenannter Chat"
    return marke ? `${t} · ${marke}` : t
}

/**
 * Der Text der Marke unter der Chateingabe, wenn eine Gruppe gewählt ist (Patch 0.12.x).
 *
 * Dieselbe Regel wie bei `gruppenMarke`, aber ein anderer Rückgabewert: Die Marke ist
 * Text und hat kein farbiges Fachsymbol daneben, das die Auskunft schon gäbe — sie
 * schweigt deshalb nie, wo ein Fach bekannt ist.
 *
 * - **Lehrkraft:** die Gruppe. Vier Chats zu vier Gruppen desselben Fachs müssen
 *   unterscheidbar bleiben.
 * - **Schüler:in:** das Fach — und zwar **genau die Beschriftung der Fachauswahl**
 *   (`studentPickerItems`), also mit Gruppenzusatz, wenn sie zwei Gruppen desselben
 *   Fachs hat. Die Marke zeigt, was gewählt wurde, mit denselben Worten.
 *
 * ⚠️ Bis 0.12.0 stand hier für alle der Gruppenname — für Schüler:innen eine Kennung aus
 * Schulkonto oder Stundenplan, keine Auskunft.
 *
 * @param {number|null} groupId
 * @param {{istLehrkraft?: boolean, gruppen?: Array, schuelerAuswahl?: Array, fachName?: string|null}} kontext
 */
export function chatKontextText(groupId, { istLehrkraft = false, gruppen = [], schuelerAuswahl = [], fachName = null } = {}) {
    const fach = fachName ?? ""
    if (istLehrkraft) return gruppeZumChat(groupId, gruppen)?.name ?? fach
    return (schuelerAuswahl ?? []).find((i) => i.id === groupId)?.label ?? fach
}
