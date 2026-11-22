<script>
    /**
     * Schulweite Übersicht einer Leitlinie oder Leitperspektive (0.53, Päckchen AU).
     *
     * Raster Fach × Aspekt mit der Zahl der Fundstellen, darunter je Aspekt die Fundstellen.
     * Umschalter in der Adresse, damit die Ansicht als Link weitergeht:
     *   `?faecher=alle`         — alle Fächer der Schule statt nur der mit Eintragungen (F7)
     *   `?nur_veroeffentlicht=1` — ohne Entwürfe (F3)
     */
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import { getLeitlinienUebersicht } from '$lib/api.js'
    import { stufe, stufenBereiche, bereichText } from '$lib/heatmap_stufen.js'
    import { fundstelleHref, hoechstwert, spalten, zeilen, zellenText } from '$lib/leitlinien_uebersicht.js'
    import ZurueckLink from '$lib/components/ZurueckLink.svelte'
    import PageBody from '$lib/components/PageBody.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import WarningBanner from '$lib/components/WarningBanner.svelte'
    import { ChevronDown, ChevronRight } from 'lucide-svelte'

    $effect(() => {
        if ($user && !userHasAnyRole($user, ['teacher', 'admin'])) goto('/chat')
    })

    const alleFaecher = $derived($page.url.searchParams.get('faecher') === 'alle')
    const nurVeroeffentlicht = $derived($page.url.searchParams.get('nur_veroeffentlicht') === '1')

    let u = $state(null)
    let loading = $state(true)
    let error = $state(null)

    $effect(() => {
        const id = $page.params.id
        const nur = nurVeroeffentlicht
        let abgebrochen = false
        loading = true
        error = null
        getLeitlinienUebersicht(id, nur)
            .then((d) => { if (!abgebrochen) u = d })
            .catch((e) => { if (!abgebrochen) error = e.message })
            .finally(() => { if (!abgebrochen) loading = false })
        return () => { abgebrochen = true }
    })

    function umschalten(name, wert) {
        const url = new URL($page.url)
        if (wert) url.searchParams.set(name, name === 'faecher' ? 'alle' : '1')
        else url.searchParams.delete(name)
        goto(url, { replaceState: true, keepFocus: true, noScroll: true })
    }

    const sp = $derived(u ? spalten(u) : [])
    const reihen = $derived(u ? zeilen(u, alleFaecher) : [])
    const max = $derived(hoechstwert(reihen))
    const hier = $derived($page.url.pathname + $page.url.search)
    const art = $derived(u?.art === 'leitperspektive' ? 'Leitperspektive' : 'Leitlinie')

    // Tooltip der Spaltenköpfe — `fixed`, damit der scrollbare Tabellenrahmen ihn nicht abschneidet
    let tipp = $state(null)
    function zeigen(e, s) {
        const r = e.currentTarget.getBoundingClientRect()
        const breite = 256
        const x = Math.min(Math.max(8, r.left + r.width / 2 - breite / 2), window.innerWidth - breite - 8)
        tipp = { schluessel: s.schluessel, kuerzel: s.kuerzel, text: s.titel, x, y: r.bottom + 6 }
    }
    const verbergen = () => (tipp = null)

    let offen = $state({})
    const aufklappen = (k) => (offen = { ...offen, [k]: !offen[k] })
</script>

<svelte:window onscroll={verbergen} />

<PageBody>
    <div class="mb-6">
        <ZurueckLink href="/knowledge/cross-cutting-themes" label="Leitperspektiven" />
        <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
            {u ? `${u.leitlinie.titel}` : 'Übersicht'}
        </h1>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
            {art} im Unterricht: wo jeder Aspekt in den Curricula der Schule vorkommt.
        </p>
    </div>

    <div class="flex flex-wrap gap-x-6 gap-y-2 mb-4 text-sm text-light-tx dark:text-dark-tx">
        <label class="inline-flex items-center gap-2">
            <input type="checkbox" checked={alleFaecher} onchange={(e) => umschalten('faecher', e.currentTarget.checked)} />
            Alle Fächer zeigen, auch ohne Eintragung
        </label>
        <label class="inline-flex items-center gap-2">
            <input type="checkbox" checked={nurVeroeffentlicht}
                   disabled={u && u.nur_veroeffentlicht && !nurVeroeffentlicht}
                   onchange={(e) => umschalten('nur_veroeffentlicht', e.currentTarget.checked)} />
            Nur veröffentlichte Curricula
        </label>
    </div>

    {#if loading && !u}
        <LoadingBanner message="Übersicht wird geladen…" />
    {:else if error}
        <ErrorBanner message={error} />
    {:else if u}
        {#if !u.nur_veroeffentlicht}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
                Entwürfe zählen mit und sind gekennzeichnet. Ein Entwurf, der ein veröffentlichtes
                Curriculum ersetzen soll, steht an dessen Stelle.
            </p>
        {/if}

        {#if sp.length === 0}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Diese {art} hat keine Aspekte.</p>
        {:else}
            {#if u.ohne_fundstelle.length}
                <WarningBanner message="Ohne Fundstelle: {u.ohne_fundstelle.join(', ')}" />
            {/if}

            {#if reihen.length === 0}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-6">
                    Noch kein Curriculum verweist auf diese {art}.
                </p>
            {:else}
                <div class="overflow-x-auto mb-3">
                    <table class="text-sm border-collapse">
                        <caption class="sr-only">Fundstellen je Fach und Aspekt</caption>
                        <thead>
                            <tr>
                                <th scope="col" class="text-left font-medium p-2 text-light-tx-2 dark:text-dark-tx-2">Fach</th>
                                {#each sp as s (s.schluessel)}
                                    <th scope="col"
                                        class="p-2 font-medium text-center whitespace-nowrap
                                               {s.leer ? 'text-light-re dark:text-dark-re' : 'text-light-tx dark:text-dark-tx'}">
                                        <!-- Tooltip mit dem Text des Aspekts: sofort, auch per Tastatur -->
                                        <button
                                            type="button"
                                            onclick={(e) => zeigen(e, s)}
                                            aria-describedby={tipp?.schluessel === s.schluessel ? 'aspekt-tipp' : undefined}
                                            class="cursor-help underline decoration-dotted underline-offset-4"
                                            onmouseenter={(e) => zeigen(e, s)}
                                            onmouseleave={verbergen}
                                            onfocus={(e) => zeigen(e, s)}
                                            onblur={verbergen}
                                            onkeydown={(e) => e.key === 'Escape' && verbergen()}
                                        >{s.kuerzel}</button>
                                        <span class="sr-only">: {s.titel}</span>
                                    </th>
                                {/each}
                                <th scope="col" class="p-2 font-medium text-center text-light-tx-2 dark:text-dark-tx-2">Summe</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each reihen as r (r.id ?? 'ohne')}
                                <tr class="border-t border-light-ui-3 dark:border-dark-ui-3">
                                    <th scope="row" class="text-left font-normal p-2 whitespace-nowrap text-light-tx dark:text-dark-tx">{r.name}</th>
                                    {#each r.zellen as n, i (sp[i].schluessel)}
                                        {@const s = stufe(n, max)}
                                        <td class="p-2 text-center" title={zellenText(r.name, sp[i].kuerzel, n)}>
                                            {#if n > 0}
                                                <span class="inline-flex items-center gap-1 text-light-tx dark:text-dark-tx">
                                                    <span class="inline-block w-3 h-3 rounded-sm" aria-hidden="true"
                                                          style="background-color: var(--diagramm-stufe-{s})"></span>
                                                    {n}
                                                </span>
                                            {:else}
                                                <span class="text-light-tx-2 dark:text-dark-tx-2" aria-hidden="true">·</span>
                                            {/if}
                                            <span class="sr-only">{zellenText(r.name, sp[i].kuerzel, n)}</span>
                                        </td>
                                    {/each}
                                    <td class="p-2 text-center text-light-tx-2 dark:text-dark-tx-2">{r.summe}</td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
                <div class="flex flex-wrap items-center gap-x-4 gap-y-1 mb-8 text-xs text-light-tx-2 dark:text-dark-tx-2">
                    <span>Fundstellen je Zelle:</span>
                    {#each stufenBereiche(max) as b (b.stufe)}
                        <span class="flex items-center gap-1">
                            <span class="inline-block w-3 h-3 rounded-sm" style="background-color: var(--diagramm-stufe-{b.stufe})"></span>
                            {bereichText(b)}
                        </span>
                    {/each}
                </div>
            {/if}

            <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-3">Fundstellen je Aspekt</h2>
            <div class="space-y-2">
                {#each sp as s (s.schluessel)}
                    <div class="rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2">
                        <button onclick={() => aufklappen(s.schluessel)} aria-expanded={!!offen[s.schluessel]}
                                disabled={s.leer}
                                class="w-full flex items-center gap-3 p-3 text-left text-sm text-light-tx dark:text-dark-tx">
                            {#if s.leer}
                                <span class="w-4"></span>
                            {:else if offen[s.schluessel]}
                                <ChevronDown class="w-4 h-4 shrink-0" />
                            {:else}
                                <ChevronRight class="w-4 h-4 shrink-0" />
                            {/if}
                            <span class="w-16 shrink-0 text-xs text-light-tx-2 dark:text-dark-tx-2">{s.kuerzel}</span>
                            <span class="flex-1">{s.titel}</span>
                            <span class="text-xs {s.leer ? 'text-light-re dark:text-dark-re' : 'text-light-tx-2 dark:text-dark-tx-2'}">
                                {s.leer ? 'kommt nicht vor' : `${s.fundstellen.length} Fundstelle${s.fundstellen.length === 1 ? '' : 'n'}`}
                            </span>
                        </button>
                        {#if offen[s.schluessel] && !s.leer}
                            <ul class="border-t border-light-ui-3 dark:border-dark-ui-3 p-3 space-y-1 text-sm">
                                {#each s.fundstellen as f (f.lernsequenz_id + f.curriculum_id)}
                                    <li>
                                        <a href={fundstelleHref(f, hier)} class="text-light-bl dark:text-dark-bl hover:underline">
                                            {f.fach ?? 'ohne Fach'}{f.stufen ? ` ${f.stufen}` : ''} — {f.curriculum}
                                        </a>
                                        <span class="text-light-tx-2 dark:text-dark-tx-2">
                                            · {f.kapitel} · {f.lernsequenz}{f.bp_version ? ` · BP ${f.bp_version}` : ''}
                                        </span>
                                        {#if f.status === 'draft'}
                                            <span class="ml-1 px-1.5 py-0.5 rounded text-xs border border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2">Entwurf</span>
                                        {/if}
                                    </li>
                                {/each}
                            </ul>
                        {/if}
                    </div>
                {/each}
            </div>
        {/if}
    {/if}
    {#if tipp}
        <div id="aspekt-tipp" role="tooltip"
             class="fixed z-50 w-64 p-2 rounded shadow text-sm text-left
                    bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                    border border-light-ui-3 dark:border-dark-ui-3"
             style="left: {tipp.x}px; top: {tipp.y}px">
            <span class="font-medium">{tipp.kuerzel}</span> — {tipp.text}
        </div>
    {/if}
</PageBody>
