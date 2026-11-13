<script>
    /**
     * Archiv der Planung, Ebenen 2 und 3: Einheiten einer Gruppe, Stunden einer Einheit
     * (0.42, Päckchen AO, F3). Die Einheit steht in der Adresse (`?einheit=`), „Stunden ohne
     * Einheit“ unter `?einheit=ohne`. Eine Stunde öffnet sich im Stundenentwurf, dort im
     * Lesezustand.
     */
    import { page } from '$app/stores'
    import { getPlanungsArchivGruppe } from '$lib/api.js'
    import {
        anzahl, archivPfad, datumKurz, einheitenMitOhne, gewaehlteEinheit, stundenPfad,
    } from '$lib/planung_archiv.js'
    import { ueColorIndex } from '$lib/planner.js'
    import ArchivAnsicht from '$lib/components/planner/ArchivAnsicht.svelte'
    import FachBadge from '$lib/components/FachBadge.svelte'
    import InfoBanner from '$lib/components/InfoBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'

    const groupId = $derived(Number($page.params.id))
    const schluessel = $derived($page.url.searchParams.get('einheit'))

    let inhalt = $state(null)
    let laedt = $state(true)
    let fehler = $state(null)
    let ansicht = $state('kacheln')

    $effect(() => {
        const id = groupId
        laedt = true
        fehler = null
        getPlanungsArchivGruppe(id)
            .then((d) => (inhalt = d))
            .catch((e) => (fehler = e.message))
            .finally(() => (laedt = false))
    })

    const einheiten = $derived(inhalt ? einheitenMitOhne(inhalt) : [])
    const einheit = $derived(inhalt ? gewaehlteEinheit(inhalt, schluessel) : null)

    function farbe(e) {
        return e.farbe == null ? 'transparent' : ueColorIndex(e.farbe)
    }

    function stundeUnterzeile(s) {
        return [datumKurz(s.datum), s.nachbereitet ? 'nachbereitet' : ''].filter(Boolean).join(' · ')
    }

    const karte = 'block rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-4 bg-light-bg dark:bg-dark-bg ' +
        'hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors'
    const zeile = 'flex items-center gap-3 px-4 py-3 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors'
    const liste = 'divide-y divide-light-ui-2 dark:divide-dark-ui-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3'
</script>

<svelte:head><title>Archiv der Planung{inhalt ? ` – ${inhalt.gruppe.name}` : ''}</title></svelte:head>

<div class="max-w-5xl mx-auto p-6 space-y-4">
    <nav class="text-xs text-light-tx-2 dark:text-dark-tx-2 flex items-center gap-1.5 flex-wrap">
        <a href={archivPfad()} class="hover:text-light-bl dark:hover:text-dark-bl">Archiv</a>
        {#if inhalt}
            <span>›</span>
            {#if einheit}
                <a href={archivPfad(groupId)} class="hover:text-light-bl dark:hover:text-dark-bl">{inhalt.gruppe.name}</a>
                <span>›</span>
                <span>{einheit.titel}</span>
            {:else}
                <span>{inhalt.gruppe.name}</span>
            {/if}
        {/if}
    </nav>

    {#if laedt}
        <LoadingBanner message="Archiv wird geladen …" />
    {:else if fehler}
        <ErrorBanner message={fehler} />
    {:else if inhalt}
        <div class="flex items-center justify-between gap-3 flex-wrap">
            <div class="flex items-center gap-2 flex-wrap">
                {#if einheit}
                    {#if einheit.farbe != null}
                        <span class="w-3 h-3 rounded-full" style="background-color: {farbe(einheit)}"></span>
                    {/if}
                    <h1 class="text-xl font-semibold text-light-tx dark:text-dark-tx">{einheit.titel}</h1>
                {:else}
                    <h1 class="text-xl font-semibold text-light-tx dark:text-dark-tx">{inhalt.gruppe.name}</h1>
                    <FachBadge fach={inhalt.gruppe.fach} />
                    {#if inhalt.gruppe.schuljahr}
                        <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">{inhalt.gruppe.schuljahr}</span>
                    {/if}
                {/if}
            </div>
            <ArchivAnsicht bind:ansicht />
        </div>
        {#if inhalt.gruppe.zugang === 'eigentum'}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Du bist in dieser Gruppe nicht mehr eingetragen. Hier steht nur deine eigene Planung.
            </p>
        {/if}

        {#if schluessel && !einheit}
            <InfoBanner message="Diese Einheit gibt es im Archiv nicht." />
        {:else if einheit}
            <!-- Ebene 3: Stunden einer Einheit -->
            {#if einheit.stunden.length === 0}
                <InfoBanner message="In dieser Einheit liegen keine Stunden." />
            {:else if ansicht === 'liste'}
                <ol class={liste}>
                    {#each einheit.stunden as s, i (s.id)}
                        <li>
                            <a href={stundenPfad(inhalt.gruppe, s.id)} class={zeile}>
                                <span class="w-6 text-xs text-light-tx-2 dark:text-dark-tx-2">{i + 1}</span>
                                <span class="flex-1 min-w-0">
                                    <span class="block font-medium text-light-tx dark:text-dark-tx truncate">{s.titel}</span>
                                    {#if s.stundenziel}
                                        <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2 truncate">{s.stundenziel}</span>
                                    {/if}
                                </span>
                                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">{stundeUnterzeile(s)}</span>
                            </a>
                        </li>
                    {/each}
                </ol>
            {:else}
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {#each einheit.stunden as s, i (s.id)}
                        <a href={stundenPfad(inhalt.gruppe, s.id)} class={karte}>
                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Stunde {i + 1}</span>
                            <p class="font-medium text-light-tx dark:text-dark-tx">{s.titel}</p>
                            {#if s.stundenziel}
                                <p class="mt-1 text-sm text-light-tx-2 dark:text-dark-tx-2 line-clamp-3">{s.stundenziel}</p>
                            {/if}
                            {#if stundeUnterzeile(s)}
                                <p class="mt-2 text-xs text-light-tx-2 dark:text-dark-tx-2">{stundeUnterzeile(s)}</p>
                            {/if}
                        </a>
                    {/each}
                </div>
            {/if}
        {:else}
            <!-- Ebene 2: Einheiten der Gruppe -->
            {#if einheiten.length === 0}
                <InfoBanner message="In dieser Gruppe liegt keine Planung." />
            {:else if ansicht === 'liste'}
                <ul class={liste}>
                    {#each einheiten as e (e.schluessel)}
                        <li>
                            <a href={archivPfad(groupId, e.schluessel)} class={zeile}>
                                <span class="w-3 h-3 rounded-full flex-shrink-0" style="background-color: {farbe(e)}"></span>
                                <span class="flex-1 min-w-0 font-medium text-light-tx dark:text-dark-tx truncate
                                             {e.id ? '' : 'italic'}">{e.titel}</span>
                                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    {anzahl(e.stunden.length, 'Stunde', 'Stunden')}
                                </span>
                            </a>
                        </li>
                    {/each}
                </ul>
            {:else}
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {#each einheiten as e (e.schluessel)}
                        <a href={archivPfad(groupId, e.schluessel)} class={karte}
                           style={e.farbe != null ? `border-left: 4px solid ${farbe(e)}` : ''}>
                            <p class="font-medium text-light-tx dark:text-dark-tx {e.id ? '' : 'italic'}">{e.titel}</p>
                            <p class="mt-2 text-xs text-light-tx-2 dark:text-dark-tx-2">
                                {anzahl(e.stunden.length, 'Stunde', 'Stunden')}
                            </p>
                        </a>
                    {/each}
                </div>
            {/if}
        {/if}
    {/if}
</div>
