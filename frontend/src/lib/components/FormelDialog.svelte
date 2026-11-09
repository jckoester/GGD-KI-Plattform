<script>
    /**
     * Formel-Dialog der Chat-Eingabe (0.38): Formel mit MathLive eingeben, als `\(…\)` einsetzen.
     *
     * MathLive (≈ 230 KB gzip) wird erst beim ersten Öffnen geladen (`formel_editor.js`).
     * Die Vorschau rendert das bereinigte LaTeX mit KaTeX — so, wie es danach im Chat steht.
     * Enter setzt ein, Escape bricht ab (MathLives eigene Escape-Belegung ist entfernt).
     */
    import { X } from "lucide-svelte";
    import Dialog from "$lib/components/Dialog.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import { bereinigeLatex } from "$lib/formel.js";
    import { feldEinrichten, mathliveLaden } from "$lib/formel_editor.js";
    import { formelVorschau } from "$lib/markdown.js";

    /** `start`: die Formel unter dem Cursor (beim Ändern), sonst leer. */
    let { start = "", abgesetzt = false, onEinfuegen, onClose } = $props();

    let bereit = $state(false);
    let ladefehler = $state("");
    let feld = $state(null);
    let tex = $state("");

    const vorschau = $derived(tex ? formelVorschau(tex, abgesetzt) : null);
    const aendern = $derived(!!start);

    mathliveLaden()
        .then(() => (bereit = true))
        .catch((e) => {
            console.error("Formel-Editor nicht geladen:", e);
            ladefehler = "Der Formel-Editor ließ sich nicht laden. Lade die Seite neu und versuch es noch einmal.";
        });

    $effect(() => {
        if (!feld) return;
        feldEinrichten(feld);
        feld.value = start;
        lesen();
        feld.focus();
    });

    function lesen() {
        tex = bereinigeLatex(feld?.getValue("latex-expanded") ?? "");
    }

    function einfuegen() {
        if (vorschau?.fehler) return;
        onEinfuegen?.(tex);
    }

    function tasten(e) {
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
            e.preventDefault();
            einfuegen();
        }
    }
</script>

<Dialog open {onClose} titelId="formel-titel" breite="max-w-xl mx-4" onkeydown={tasten}>
    <div class="flex items-start justify-between gap-4">
        <h2 id="formel-titel" class="text-lg font-semibold text-light-tx dark:text-dark-tx">
            {aendern ? "Formel ändern" : "Formel einfügen"}
        </h2>
        <button
            onclick={onClose}
            aria-label="Schließen"
            class="p-1 rounded hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                   text-light-tx-2 dark:text-dark-tx-2"
        >
            <X class="w-4 h-4" />
        </button>
    </div>

    <div class="mt-4 space-y-3">
        {#if ladefehler}
            <ErrorBanner message={ladefehler} />
        {:else if !bereit}
            <LoadingBanner message="Formel-Editor wird geladen…" />
        {:else}
            <math-field
                bind:this={feld}
                oninput={lesen}
                math-virtual-keyboard-policy="auto"
                aria-label="Formel"
                class="formelfeld block w-full rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx px-3 py-2"
            ></math-field>

            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                <kbd>/</kbd> Bruch · <kbd>^</kbd> Hochzahl · <kbd>sqrt</kbd> Wurzel · <kbd>pi</kbd> π ·
                <kbd>&lt;=</kbd> ≤ · <kbd>→</kbd> oder Leertaste verlässt Bruch und Hochzahl.
                Weitere Zeichen über das Tastatursymbol im Feld.
            </p>

            <div class="min-h-[2.5rem] text-light-tx dark:text-dark-tx" aria-live="polite">
                {#if vorschau?.fehler}
                    <p class="text-sm text-light-re dark:text-dark-re">
                        Diese Formel kann der Chat nicht darstellen: {vorschau.fehler}
                    </p>
                {:else if vorschau}
                    <span class="sr-only">Vorschau:</span>
                    <!-- KaTeX-Ausgabe: dieselbe vertrauenswürdige Quelle wie in renderMarkdown -->
                    <!-- eslint-disable-next-line svelte/no-at-html-tags -->
                    {@html vorschau.html}
                {/if}
            </div>
        {/if}
    </div>

    <div class="mt-5 flex justify-end gap-2">
        <button
            onclick={onClose}
            class="px-3 py-1.5 text-sm rounded-lg text-light-tx dark:text-dark-tx
                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
        >
            Abbrechen
        </button>
        <button
            onclick={einfuegen}
            disabled={!bereit || !!vorschau?.fehler || (!tex && !aendern)}
            class="px-3 py-1.5 text-sm rounded-lg bg-primary dark:bg-primary-dark text-white
                   disabled:opacity-50 disabled:cursor-not-allowed"
        >
            {aendern && !tex ? "Formel entfernen" : aendern ? "Übernehmen" : "Einfügen"}
        </button>
    </div>
</Dialog>

<style>
    .formelfeld {
        font-size: 1.4rem;
        --caret-color: currentColor;
    }
    kbd {
        font-family: ui-monospace, monospace;
        padding: 0 0.2rem;
        border-radius: 0.2rem;
        border: 1px solid currentColor;
        opacity: 0.85;
    }
</style>
