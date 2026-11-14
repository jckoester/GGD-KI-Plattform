<script>
    /**
     * Einrichtung beim ersten Login (0.43) — Rahmen: Seiten, Schrittanzeige, Weiter/Zurück/Später.
     *
     * Welche Seiten, in welcher Reihenfolge und wo ein Wiedereinstieg beginnt, steht in
     * `$lib/einrichtung.js`. Jede Wahl auf einer Seite wird sofort gespeichert; dieser Rahmen
     * speichert nur den **Stand**: „später“ samt Seite beim Schließen (auch Escape und Klick
     * daneben), „erledigt“, sobald die letzte Seite erreicht ist.
     *
     * Props: `daten` (Antwort von `GET /einrichtung`), `rolle`, `onClose(neueDaten?)`.
     */
    import { untrack } from 'svelte'
    import Dialog from '$lib/components/Dialog.svelte'
    import { putEinrichtung } from '$lib/api.js'
    import { fortschritt, SEITEN, seitenNummer, sichtbareSeiten, startIndex } from '$lib/einrichtung.js'

    const { daten, rolle, onClose } = $props()

    // Seitenliste und Einstieg einmal beim Öffnen — eine Antwort, die während des Durchgangs
    // nachkommt, soll die Seiten nicht unter der Hand verschieben.
    const seiten = untrack(() => sichtbareSeiten(rolle, daten))
    let index = $state(untrack(() => startIndex(rolle, seiten, daten)))
    let erledigt = $state(false)
    let neu = $state(null)

    const seite = $derived(seiten[index])
    const letzte = $derived(index === seiten.length - 1)

    $effect(() => {
        if (letzte && !erledigt) {
            erledigt = true
            putEinrichtung('erledigt', seitenNummer(rolle, seite))
                .then((d) => (neu = d))
                .catch(() => {})
        }
    })

    async function schliessen() {
        if (erledigt) return onClose(neu)
        try {
            onClose(await putEinrichtung('spaeter', seitenNummer(rolle, seite)))
        } catch {
            // Nicht gespeichert: Der Dialog kommt beim nächsten Laden wieder — besser als festhängen.
            onClose(null)
        }
    }

    const weiter = () => (index = Math.min(index + 1, seiten.length - 1))
    const zurueck = () => (index = Math.max(index - 1, 0))

    const knopf = 'px-3 py-1.5 text-sm rounded-md'
    const nebenKnopf = `${knopf} text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2`
    const hauptKnopf = `${knopf} bg-primary dark:bg-primary-dark text-white hover:opacity-90`
</script>

<Dialog open onClose={schliessen} titelId="einrichtung-titel" breite="max-w-2xl max-h-[90dvh] flex flex-col">
    <div class="flex items-start justify-between gap-4 mb-1">
        <div>
            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">Einrichtung · {fortschritt(index, seiten)}</p>
            <h2 id="einrichtung-titel" class="text-lg font-semibold text-light-tx dark:text-dark-tx">
                {SEITEN[seite].titel}
            </h2>
        </div>
        {#if !letzte}
            <button type="button" class={nebenKnopf} onclick={schliessen}>Später</button>
        {/if}
    </div>
    <div class="h-1 mb-4 rounded bg-light-ui-2 dark:bg-dark-ui-2" aria-hidden="true">
        <div class="h-1 rounded bg-primary dark:bg-primary-dark transition-all"
             style="width: {((index + 1) / seiten.length) * 100}%"></div>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto text-sm text-light-tx dark:text-dark-tx">
        <!-- Inhalte der Seiten: Schritt 4 (1–4, 6) und Schritt 5 (Gruppen). -->
        <p class="text-light-tx-2 dark:text-dark-tx-2">{SEITEN[seite].titel}</p>
    </div>

    <div class="flex justify-between gap-2 mt-4 pt-4 border-t border-light-ui-3 dark:border-dark-ui-3">
        <button type="button" class={nebenKnopf} onclick={zurueck} disabled={index === 0}
                class:invisible={index === 0}>Zurück</button>
        {#if letzte}
            <button type="button" class={hauptKnopf} onclick={schliessen} data-autofocus>Fertig</button>
        {:else}
            <button type="button" class={hauptKnopf} onclick={weiter} data-autofocus>Weiter</button>
        {/if}
    </div>
</Dialog>
