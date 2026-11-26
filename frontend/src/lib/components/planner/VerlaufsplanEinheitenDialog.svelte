<script>
    /**
     * „Einheiten aus dem Jahresverlaufsplan anlegen“ (BD Teil B, Schritt 5).
     *
     * Zeigt die Vorschau des Servers je Abschnitt (neu mit Kapitel und Stunden, oder übersprungen
     * und warum) und legt auf Wunsch an. Angelegt wird, was der Server in dem Moment vorschlägt —
     * er rechnet neu. Rückgängig bietet danach die Planerseite an (`onAngelegt(lauf)`).
     *
     * Gab es beim Anlegen inzwischen nichts mehr zu tun (anderer Tab), bleibt der Dialog offen und
     * zeigt die neue Vorschau mit einem Hinweis.
     *
     * Props: `open`, `groupId`, `onClose`, `onAngelegt(lauf, groupId)` — `groupId` der Anfrage, damit
     * die Seite eine Antwort nach einem Gruppenwechsel verwerfen kann.
     */
    import Dialog from '$lib/components/Dialog.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import InfoBanner from '$lib/components/InfoBanner.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import { getVerlaufsplanVorschau, legeVerlaufsplanEinheitenAn } from '$lib/api.js'
    import { ueColorIndex } from '$lib/planner.js'
    import { anlegenKnopf, vorschauSumme, vorschlagHinweise, vorschlagStand } from '$lib/verlaufsplan.js'

    const { open = false, groupId, onClose, onAngelegt = () => {} } = $props()

    let vorschau = $state(null)
    let fehler = $state(null)
    let laeuft = $state(false)
    let nichtsMehr = $state(false)

    $effect(() => {
        if (!open) return
        vorschau = null
        fehler = null
        nichtsMehr = false
        const id = groupId
        getVerlaufsplanVorschau(id)
            .then((v) => { if (open && id === groupId) vorschau = v })
            .catch((e) => { fehler = e.message })
    })

    async function anlegen() {
        if (laeuft || !vorschau?.neu) return
        laeuft = true
        fehler = null
        const id = groupId
        try {
            const lauf = await legeVerlaufsplanEinheitenAn(id)
            onAngelegt(lauf, id)
            if (lauf?.lauf_id) {
                onClose()
            } else {
                nichtsMehr = true
                vorschau = await getVerlaufsplanVorschau(id)
            }
        } catch (e) {
            fehler = e.message
        } finally {
            laeuft = false
        }
    }
</script>

{#if open}
    <Dialog open {onClose} titelId="verlaufsplan-einheiten-titel" breite="max-w-2xl">
        <h2 id="verlaufsplan-einheiten-titel" class="text-base font-semibold text-light-tx dark:text-dark-tx mb-1">
            Einheiten aus dem Jahresverlaufsplan anlegen
        </h2>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-3">
            Je Abschnitt des Plans entsteht eine Einheit mit seinem Kapitel. Sie bekommt die freien
            Unterrichtsstunden seiner Wochen. Vorhandene Einheiten und belegte Stunden bleiben, wie sie sind.
        </p>

        {#if fehler}
            <div class="mb-3"><ErrorBanner message={fehler} /></div>
        {/if}

        {#if !vorschau && !fehler}
            <LoadingBanner message="Vorschau wird geladen …" />
        {:else if vorschau}
            {#if vorschau.status === 'draft'}
                <div class="mb-3"><InfoBanner message="Der Plan ist ein Entwurf der Fachschaft und kann sich noch ändern." /></div>
            {/if}
            {#if nichtsMehr}
                <div class="mb-3"><InfoBanner message="Inzwischen gab es nichts mehr anzulegen — hier der aktuelle Stand." /></div>
            {/if}
            <ol class="max-h-[50vh] overflow-y-auto divide-y divide-light-ui-2 dark:divide-dark-ui-2 border-y border-light-ui-2 dark:border-dark-ui-2 text-sm">
                {#each vorschau.vorschlaege as v (v.index)}
                    {@const hinweise = vorschlagHinweise(v)}
                    <li class="py-2 flex items-start gap-3 {v.anlegen ? '' : 'text-light-tx-2 dark:text-dark-tx-2'}">
                        <span class="w-2.5 h-2.5 mt-1.5 rounded-full flex-shrink-0 {v.grund === 'puffer' ? 'verlaufsplan-puffer' : v.farbe == null ? 'bg-light-ui-3 dark:bg-dark-ui-3' : ''}"
                            style={v.farbe != null && v.grund !== 'puffer' ? `background-color: ${ueColorIndex(v.farbe)}` : undefined}
                            aria-hidden="true"></span>
                        <div class="flex-1 min-w-0">
                            <div class="flex items-baseline gap-2 flex-wrap">
                                <span class="font-medium {v.anlegen ? 'text-light-tx dark:text-dark-tx' : ''}">{v.nr}. {v.titel}</span>
                                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">{v.wochen}</span>
                            </div>
                            {#if v.anlegen && v.kapitel_titel && v.kapitel_titel !== v.titel}
                                <div class="text-xs text-light-tx-2 dark:text-dark-tx-2">Kapitel: {v.kapitel_titel}</div>
                            {/if}
                            {#each hinweise as h (h)}
                                <div class="text-xs text-light-tx-2 dark:text-dark-tx-2">{h}</div>
                            {/each}
                        </div>
                        <span class="flex-shrink-0 text-xs text-right max-w-[14rem] {v.anlegen ? 'text-light-tx dark:text-dark-tx font-medium' : ''}">{vorschlagStand(v)}</span>
                    </li>
                {/each}
            </ol>
            <p class="mt-3 text-sm text-light-tx dark:text-dark-tx">{vorschauSumme(vorschau)}</p>
        {/if}

        <div class="flex justify-end gap-2 mt-4">
            <button type="button" onclick={onClose} data-autofocus
                class="px-3 py-1.5 text-sm rounded-md text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2">
                {vorschau?.neu ? 'Abbrechen' : 'Schließen'}
            </button>
            {#if vorschau?.neu}
                <button type="button" onclick={anlegen} disabled={laeuft}
                    class="px-3 py-1.5 text-sm rounded-md bg-primary dark:bg-primary-dark text-on-fill font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed">
                    {laeuft ? 'Wird angelegt …' : anlegenKnopf(vorschau)}
                </button>
            {/if}
        </div>
    </Dialog>
{/if}
