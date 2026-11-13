<script>
    /**
     * Einheiten einer Gruppe und die Stunden einer Einheit, als Liste oder Kacheln.
     *
     * Gemeinsam für das Archiv (`/planning/archive/[id]`, 0.42) und die Einheitenansicht des
     * Planers (0.42.3). Die Einheit steht in der Adresse; welche, sagt `schluessel`, wohin ein
     * Klick führt, `einheitPfad`. Daten: `ArchivInhaltRead` (`getPlanungsArchivGruppe`,
     * `getGruppenInhalt`).
     *
     * `termine`: Stunden ohne Termin kennzeichnen und je Einheit zählen — im Planer, wo man sie
     * noch einplanen will; im Archiv nicht.
     */
    import { anzahl, datumKurz, einheitenMitOhne, gewaehlteEinheit, ohneTermin, stundenPfad } from '$lib/planung_archiv.js'
    import { ueColorIndex } from '$lib/planner.js'
    import InfoBanner from '$lib/components/InfoBanner.svelte'

    const {
        inhalt,
        ansicht = 'kacheln',
        schluessel = null,
        einheitPfad,
        onKopiereEinheit,
        onKopiereStunde,
        termine = false,
        leerText = 'In dieser Gruppe liegt keine Planung.',
        fehltText = 'Diese Einheit gibt es nicht.',
    } = $props()

    const einheiten = $derived(einheitenMitOhne(inhalt))
    const einheit = $derived(gewaehlteEinheit(inhalt, schluessel))

    function farbe(e) {
        return e.farbe == null ? 'transparent' : ueColorIndex(e.farbe)
    }

    function stundeUnterzeile(s) {
        return [datumKurz(s.datum), s.nachbereitet ? 'nachbereitet' : ''].filter(Boolean).join(' · ')
    }

    function einheitUnterzeile(e) {
        const n = termine ? ohneTermin(e.stunden) : 0
        return anzahl(e.stunden.length, 'Stunde', 'Stunden') + (n ? ` · ${n} ohne Termin` : '')
    }

    const karte = 'block rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-4 bg-light-bg dark:bg-dark-bg ' +
        'hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors'
    const zeile = 'flex items-center gap-3 px-4 py-3 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors'
    const kopierKnopf = 'flex-shrink-0 px-2 py-1 text-xs rounded border border-light-ui-3 dark:border-dark-ui-3 ' +
        'text-light-tx-2 dark:text-dark-tx-2 bg-light-bg dark:bg-dark-bg hover:text-light-bl dark:hover:text-dark-bl transition-colors'
    const liste = 'divide-y divide-light-ui-2 dark:divide-dark-ui-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3'
    const ohneMarke = 'inline-block px-1.5 py-0.5 text-xs rounded border border-dashed border-light-ui-3 ' +
        'dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2'
</script>

{#snippet terminAngabe(s)}
    {#if termine && !s.slot_id}
        <span class={ohneMarke}>ohne Termin</span>
    {:else if stundeUnterzeile(s)}
        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">{stundeUnterzeile(s)}</span>
    {/if}
{/snippet}

{#if schluessel && !einheit}
    <InfoBanner message={fehltText} />
{:else if einheit}
    <!-- Stunden einer Einheit -->
    {#if einheit.stunden.length === 0}
        <InfoBanner message="In dieser Einheit liegen keine Stunden." />
    {:else if ansicht === 'liste'}
        <ol class={liste}>
            {#each einheit.stunden as s, i (s.id)}
                <li class="flex items-center pr-3">
                    <a href={stundenPfad(inhalt.gruppe, s.id)} class="{zeile} flex-1 min-w-0">
                        <span class="w-6 text-xs text-light-tx-2 dark:text-dark-tx-2">{i + 1}</span>
                        <span class="flex-1 min-w-0">
                            <span class="block font-medium text-light-tx dark:text-dark-tx truncate">{s.titel}</span>
                            {#if s.stundenziel}
                                <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2 truncate">{s.stundenziel}</span>
                            {/if}
                        </span>
                        {@render terminAngabe(s)}
                    </a>
                    <button type="button" class={kopierKnopf} onclick={() => onKopiereStunde(s, einheit)}
                            aria-label="Stunde „{s.titel}“ kopieren">Kopieren</button>
                </li>
            {/each}
        </ol>
    {:else}
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {#each einheit.stunden as s, i (s.id)}
                <div class="relative">
                    <a href={stundenPfad(inhalt.gruppe, s.id)} class="{karte} h-full pr-24">
                        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Stunde {i + 1}</span>
                        <p class="font-medium text-light-tx dark:text-dark-tx">{s.titel}</p>
                        {#if s.stundenziel}
                            <p class="mt-1 text-sm text-light-tx-2 dark:text-dark-tx-2 line-clamp-3">{s.stundenziel}</p>
                        {/if}
                        <p class="mt-2">{@render terminAngabe(s)}</p>
                    </a>
                    <button type="button" class="{kopierKnopf} absolute top-2 right-2" onclick={() => onKopiereStunde(s, einheit)}
                            aria-label="Stunde „{s.titel}“ kopieren">Kopieren</button>
                </div>
            {/each}
        </div>
    {/if}
{:else}
    <!-- Einheiten der Gruppe -->
    {#if einheiten.length === 0}
        <InfoBanner message={leerText} />
    {:else if ansicht === 'liste'}
        <ul class={liste}>
            {#each einheiten as e (e.schluessel)}
                <li class="flex items-center pr-3">
                    <a href={einheitPfad(e.schluessel)} class="{zeile} flex-1 min-w-0">
                        <span class="w-3 h-3 rounded-full flex-shrink-0" style="background-color: {farbe(e)}"></span>
                        <span class="flex-1 min-w-0 font-medium text-light-tx dark:text-dark-tx truncate
                                     {e.id ? '' : 'italic'}">{e.titel}</span>
                        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">{einheitUnterzeile(e)}</span>
                    </a>
                    {#if e.id}
                        <button type="button" class={kopierKnopf} onclick={() => onKopiereEinheit(e)}
                                aria-label="Einheit „{e.titel}“ kopieren">Kopieren</button>
                    {/if}
                </li>
            {/each}
        </ul>
    {:else}
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {#each einheiten as e (e.schluessel)}
                <div class="relative">
                    <a href={einheitPfad(e.schluessel)} class="{karte} h-full pr-24"
                       style={e.farbe != null ? `border-left: 4px solid ${farbe(e)}` : ''}>
                        <p class="font-medium text-light-tx dark:text-dark-tx {e.id ? '' : 'italic'}">{e.titel}</p>
                        <p class="mt-2 text-xs text-light-tx-2 dark:text-dark-tx-2">{einheitUnterzeile(e)}</p>
                    </a>
                    {#if e.id}
                        <button type="button" class="{kopierKnopf} absolute top-2 right-2" onclick={() => onKopiereEinheit(e)}
                                aria-label="Einheit „{e.titel}“ kopieren">Kopieren</button>
                    {/if}
                </div>
            {/each}
        </div>
    {/if}
{/if}
