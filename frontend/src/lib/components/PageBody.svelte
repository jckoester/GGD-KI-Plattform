<script>
    /**
     * Der Seitenrahmen — zwei Muster, eine Stelle.
     *
     * **Warum es das gibt.** Die Seiten trugen ihren Rahmen jede für sich, und das
     * lief auseinander: fünf verschiedene Höchstbreiten (`max-w-2xl` bis `6xl`),
     * neun Seiten mit `max-w-*` **ohne** `mx-auto` (also linksbündig statt
     * zentriert, auf breiten Schirmen auffällig) und einzelne ganz ohne
     * Scroll-Rahmen.
     *
     * ⚠️ **Der Scroll-Rahmen ist Pflicht, nicht Zierde.** Das `(app)`-Layout gibt
     * `<main>` ein `flex-1 overflow-hidden`; eine Seite ohne `h-full
     * overflow-y-auto` wird unten abgeschnitten, statt zu scrollen. Der Fehler
     * sieht nicht kaputt aus — man merkt ihn erst, wenn der Inhalt lang wird.
     * Steckt er in dieser Komponente, kann er einer Seite nicht mehr passieren.
     *
     * **Zwei Muster:**
     *
     * - **`breit`** — Listen über die volle Breite (Vorbild `/knowledge`).
     *   Tabellen und Trefferlisten brauchen den Platz.
     * - **Vorgabe (schmal)** — alles, was gelesen oder ausgefüllt wird: Detail,
     *   Editoren, gruppierte Listen wie Leitperspektiven und Bildungsplan
     *   (Vorbild `/knowledge/mine`). Zentriert, weil eine Textspalte am linken
     *   Rand eines 27-Zoll-Schirms unlesbar ist.
     *
     * Seiten mit eigener Flex-Struktur (Chat, Graph, Curriculum-Editor, Planer)
     * benutzen sie **nicht** — sie verwalten ihren Scrollbereich selbst.
     */
    let { breit = false, children } = $props()
</script>

<div class="h-full overflow-y-auto">
    <div class={breit ? 'px-6 py-6' : 'max-w-4xl mx-auto px-4 py-6'}>
        {@render children()}
    </div>
</div>
