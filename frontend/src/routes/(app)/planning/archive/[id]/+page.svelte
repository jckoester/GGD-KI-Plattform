<script>
    /**
     * Archiv der Planung, Ebenen 2 und 3: Einheiten einer Gruppe, Stunden einer Einheit
     * (0.42, Päckchen AO, F3). Die Einheit steht in der Adresse (`?einheit=`), „Stunden ohne
     * Einheit“ unter `?einheit=ohne`. Eine Stunde öffnet sich im Stundenentwurf, dort im
     * Lesezustand.
     */
    import { page } from '$app/stores'
    import { getPlanungsArchivGruppe } from '$lib/api.js'
    import { archivPfad, gewaehlteEinheit } from '$lib/planung_archiv.js'
    import { ueColorIndex } from '$lib/planner.js'
    import ArchivAnsicht from '$lib/components/planner/ArchivAnsicht.svelte'
    import EinheitenAnsicht from '$lib/components/planner/EinheitenAnsicht.svelte'
    import KopierenDialog from '$lib/components/planner/KopierenDialog.svelte'
    import FachBadge from '$lib/components/FachBadge.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'

    const groupId = $derived(Number($page.params.id))
    const schluessel = $derived($page.url.searchParams.get('einheit'))

    let inhalt = $state(null)
    let laedt = $state(true)
    let fehler = $state(null)
    let ansicht = $state('kacheln')
    // Kopieren als Vorlage (0.42): {art, quelle} oder null.
    let kopieren = $state(null)

    function kopiereStunde(s, einheit) {
        kopieren = { art: 'stunde', quelle: { id: s.id, titel: s.titel, einheitTitel: einheit?.id ? einheit.titel : '' } }
    }

    function kopiereEinheit(e) {
        kopieren = { art: 'einheit', quelle: { id: e.id, titel: e.titel } }
    }

    $effect(() => {
        const id = groupId
        laedt = true
        fehler = null
        getPlanungsArchivGruppe(id)
            .then((d) => (inhalt = d))
            .catch((e) => (fehler = e.message))
            .finally(() => (laedt = false))
    })

    const einheit = $derived(inhalt ? gewaehlteEinheit(inhalt, schluessel) : null)

    function farbe(e) {
        return e.farbe == null ? 'transparent' : ueColorIndex(e.farbe)
    }
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

        <EinheitenAnsicht
            {inhalt}
            {ansicht}
            {schluessel}
            einheitPfad={(k) => archivPfad(groupId, k)}
            onKopiereEinheit={kopiereEinheit}
            onKopiereStunde={kopiereStunde}
            fehltText="Diese Einheit gibt es im Archiv nicht."
        />
    {/if}
</div>

<KopierenDialog
    open={kopieren != null}
    art={kopieren?.art ?? 'stunde'}
    quelle={kopieren?.quelle ?? null}
    fachId={inhalt?.gruppe?.fach?.id ?? null}
    onClose={() => (kopieren = null)}
/>
