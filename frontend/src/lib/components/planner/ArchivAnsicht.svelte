<script>
    /**
     * Umschalter Liste/Kacheln im Archiv der Planung (0.42, F3). Gemerkt in den
     * Einstellungen (`planung_archiv_ansicht`), für alle drei Ebenen dieselbe Wahl.
     */
    import { LayoutGrid, List } from 'lucide-svelte'
    import { getPreferences, patchPreferences } from '$lib/api.js'
    import { ANSICHT_SCHLUESSEL, ansichtAusEinstellungen } from '$lib/planung_archiv.js'

    let { ansicht = $bindable('kacheln') } = $props()

    $effect(() => {
        getPreferences().then((p) => (ansicht = ansichtAusEinstellungen(p))).catch(() => {})
    })

    async function setze(wert) {
        ansicht = wert
        try {
            await patchPreferences({ [ANSICHT_SCHLUESSEL]: wert })
        } catch {
            // Nicht gemerkt, aber angewandt.
        }
    }

    const knopf = 'h-8 w-8 inline-flex items-center justify-center rounded-md border transition-colors'
    const an = 'border-light-ui-3 dark:border-dark-ui-3 bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx'
    const aus = 'border-transparent text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'
</script>

<div class="flex items-center gap-1" role="group" aria-label="Ansicht">
    <button type="button" class="{knopf} {ansicht === 'liste' ? an : aus}" aria-pressed={ansicht === 'liste'}
            title="Liste" aria-label="Liste" onclick={() => setze('liste')}>
        <List class="w-4 h-4" />
    </button>
    <button type="button" class="{knopf} {ansicht === 'kacheln' ? an : aus}" aria-pressed={ansicht === 'kacheln'}
            title="Kacheln" aria-label="Kacheln" onclick={() => setze('kacheln')}>
        <LayoutGrid class="w-4 h-4" />
    </button>
</div>
