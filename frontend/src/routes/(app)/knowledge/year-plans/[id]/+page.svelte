<script>
    /**
     * Ein Jahresverlaufsplan (BD, Schritt 5): Zeitleiste, Abschnitte, Stundenbilanz; für die
     * Fachschaft mit Editor. Jede Änderung wird kurz verzögert gespeichert, der Server liefert die
     * Lage im Kalender zurück. Rückgängig nimmt den vorigen gespeicherten Stand und speichert ihn.
     */
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { onDestroy } from 'svelte'
    import { Undo2 } from 'lucide-svelte'
    import {
        beschliesseVerlaufsplan, deleteVerlaufsplan, getVerlaufsplan, saveVerlaufsplan, uebernehmeVerlaufsplan,
    } from '$lib/api.js'
    import {
        PLANUNGSARTEN, abschnittFarbe, bezugText, bilanzStand, einheiten, hinweise, uebernahmeZiele,
        wochenText, zeitraumText, zumSpeichern,
    } from '$lib/verlaufsplan.js'
    import { pageTitle } from '$lib/stores/pageTitle.js'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import PageBody from '$lib/components/PageBody.svelte'
    import ZurueckLink from '$lib/components/ZurueckLink.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import InfoBanner from '$lib/components/InfoBanner.svelte'
    import WarningBanner from '$lib/components/WarningBanner.svelte'
    import VerlaufsplanZeitleiste from '$lib/components/VerlaufsplanZeitleiste.svelte'
    import VerlaufsplanEditor from '$lib/components/VerlaufsplanEditor.svelte'

    $effect(() => {
        if ($user && !userHasAnyRole($user, ['teacher', 'admin'])) goto('/chat')
    })

    let plan = $state(null)
    let fehler = $state(null)
    let laedt = $state(true)
    let bearbeiten = $state(false)

    // Arbeitsstand des Editors und Speichern
    let abschnitte = $state([])
    let planungsart = $state('sequenz')
    let speichert = $state(false)
    let speicherFehler = $state(null)
    let verlauf = $state([])          // frühere gespeicherte Stände, für Rückgängig
    let zuletzt = null                // der zuletzt gespeicherte Stand
    let timer = null

    $effect(() => {
        const id = $page.params.id
        laedt = true
        fehler = null
        getVerlaufsplan(id)
            .then(uebernehmen)
            .catch((e) => (fehler = e.message))
            .finally(() => (laedt = false))
    })

    function uebernehmen(p) {
        plan = p
        abschnitte = p.abschnitte.map((a) => ({ ...a }))
        planungsart = p.planungsart
        zuletzt = zumSpeichern(abschnitte, planungsart)
        pageTitle.set(p.titel)
    }

    const e = $derived(einheiten(plan?.curricula))
    const band = $derived((plan?.curricula ?? []).some((c) => c.band))

    function geaendert() {
        speicherFehler = null
        clearTimeout(timer)
        timer = setTimeout(speichern, 700)
    }

    async function speichern({ zurueck = false, umrechnen = false } = {}) {
        clearTimeout(timer)
        const stand = zumSpeichern(abschnitte, planungsart)
        if (!umrechnen && JSON.stringify(stand) === JSON.stringify(zuletzt)) return
        speichert = true
        try {
            const p = await saveVerlaufsplan(plan.id, umrechnen ? { ...stand, umrechnen: true } : stand)
            if (!zurueck && zuletzt) verlauf = [...verlauf.slice(-19), zuletzt]
            zuletzt = stand
            if (umrechnen) {
                // Der Server hat die Abschnitte auf die neue Art umgerechnet — die gelten jetzt.
                abschnitte = p.abschnitte.map((a) => ({ ...a }))
                zuletzt = zumSpeichern(abschnitte, planungsart)
            }
            // Plan mit neuer Lage übernehmen; die Zeilen des Editors (`abschnitte`) bleiben, wie sie
            // sind — wer während des Speicherns weitertippt, verliert nichts.
            plan = p
        } catch (e) {
            speicherFehler = e.message
        } finally {
            speichert = false
        }
    }

    async function rueckgaengig() {
        const vorher = verlauf.at(-1)
        if (!vorher) return
        verlauf = verlauf.slice(0, -1)
        abschnitte = vorher.abschnitte.map((a) => ({ ...a }))
        planungsart = vorher.planungsart
        await speichern({ zurueck: true })
    }

    /** Planungsart wechseln (Schritt 7): Der Server rechnet die Abschnitte um; Rückgängig geht. */
    async function artWechseln(neu) {
        if (neu === planungsart) return
        const text = neu === 'kapitel'
            ? 'Auf kapitelgenau umstellen? Jede Sequenz wird zu ihrem Kapitel.'
            : 'Auf sequenzgenau umstellen? Jedes Kapitel wird zu allen seinen Sequenzen.'
        if (!confirm(text)) return
        await speichern()
        planungsart = neu
        await speichern({ umrechnen: true })
    }

    async function beschliessen() {
        if (!confirm('Den Plan als beschlossen kennzeichnen? Ändern geht danach weiterhin.')) return
        await speichern()
        try {
            uebernehmen(await beschliesseVerlaufsplan(plan.id))
        } catch (e) {
            speicherFehler = e.message
        }
    }

    async function loeschen() {
        if (!confirm(`„${plan.titel}“ löschen? Das lässt sich nicht rückgängig machen.`)) return
        try {
            await deleteVerlaufsplan(plan.id)
            goto(`/knowledge/year-plans?fach=${plan.subject_id}`)
        } catch (e) {
            speicherFehler = e.message
        }
    }

    // Übernehmen in ein anderes Schuljahr (Schritt 6)
    const ziele = $derived(plan ? uebernahmeZiele(plan.aktuelles_schuljahr, plan.schuljahr) : [])
    let ziel = $state('')
    $effect(() => { if (!ziele.includes(ziel)) ziel = ziele.at(-1) ?? '' })
    const entfallen = $derived(Number($page.url.searchParams.get('entfallen')) || 0)

    async function inSchuljahrUebernehmen() {
        await speichern()
        try {
            const neu = await uebernehmeVerlaufsplan(plan.id, ziel)
            goto(`/knowledge/year-plans/${neu.id}${neu.kapitel_entfallen ? `?entfallen=${neu.kapitel_entfallen}` : ''}`)
        } catch (e) {
            speicherFehler = e.message
        }
    }

    onDestroy(() => {
        if (timer) speichern()
    })

    const knopf = 'px-3 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-40'
    const stand = { 'passt': 'text-light-gr dark:text-dark-gr', 'zu wenig': 'text-light-or dark:text-dark-or', 'zu viel': 'text-light-or dark:text-dark-or' }
</script>

<svelte:head><title>{plan?.titel ?? 'Jahresverlaufsplan'}</title></svelte:head>

<PageBody breit>
    <ZurueckLink href={plan ? `/knowledge/year-plans?fach=${plan.subject_id}` : '/knowledge/year-plans'} label="Jahresverlaufspläne" />

    {#if laedt}
        <LoadingBanner message="Plan wird geladen…" />
    {:else if fehler}
        <ErrorBanner message={fehler} />
    {:else if plan}
        <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
            <div>
                <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">{plan.titel}</h1>
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    {#if plan.status === 'draft'}
                        <span class="font-medium text-light-or dark:text-dark-or">Entwurf</span>
                    {:else}
                        beschlossen{#if plan.beschlossen_am} am {plan.beschlossen_am.split('-').reverse().join('.')}{/if}
                    {/if}
                    {#if plan.archiviert} · Archiv, nur lesbar{/if}
                    {#if plan.wochenstunden} · {plan.wochenstunden} Wochenstunden{/if}
                </p>
            </div>
            {#if plan.darf_bearbeiten}
                <div class="flex flex-wrap items-center gap-2">
                    {#if bearbeiten}
                        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2" aria-live="polite">
                            {speichert ? 'Speichert…' : 'Gespeichert'}
                        </span>
                        <button type="button" class={knopf} disabled={!verlauf.length || speichert} onclick={rueckgaengig}>
                            <span class="inline-flex items-center gap-1"><Undo2 size={14} /> Rückgängig</span>
                        </button>
                    {/if}
                    <button type="button" class={knopf} onclick={async () => { if (bearbeiten) await speichern(); bearbeiten = !bearbeiten }}>
                        {bearbeiten ? 'Fertig' : 'Bearbeiten'}
                    </button>
                    {#if plan.darf_beschliessen}
                        <button type="button" class={knopf} onclick={beschliessen}>Beschließen</button>
                    {/if}
                    <button type="button" class={knopf} onclick={loeschen}>Löschen</button>
                </div>
            {/if}
        </div>

        {#if speicherFehler}<div class="mb-3"><ErrorBanner message={speicherFehler} /></div>{/if}
        {#if entfallen}
            <div class="mb-3"><WarningBanner message="Übernommen. {entfallen} {entfallen === 1 ? 'Kapitelbezug fand' : 'Kapitelbezüge fanden'} sich im heutigen Curriculum nicht wieder und {entfallen === 1 ? 'ist' : 'sind'} entfallen." /></div>
        {/if}
        {#if plan.darf_uebernehmen && ziele.length}
            <div class="mb-4 flex flex-wrap items-center gap-2 text-sm text-light-tx dark:text-dark-tx" data-abschnitt="uebernehmen">
                <span>{plan.archiviert ? 'Als Ausgangspunkt für ein neues Schuljahr:' : 'Für ein anderes Schuljahr:'}</span>
                <select bind:value={ziel} aria-label="Schuljahr"
                    class="rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg px-2 py-1 text-sm">
                    {#each ziele as j (j)}<option value={j}>{j}</option>{/each}
                </select>
                <button type="button" class={knopf} onclick={inSchuljahrUebernehmen}>Als Entwurf übernehmen</button>
            </div>
        {/if}
        {#if plan.kalender_fehlt}
            <div class="mb-3"><InfoBanner message="Für {plan.schuljahr} liegt der Kalender der Schule noch nicht vor. Der Plan zählt deshalb nur Wochen, ohne Daten und Ferien." /></div>
        {/if}

        {#if plan.lage}
            <section class="mb-5">
                <VerlaufsplanZeitleiste abschnitte={bearbeiten ? abschnitte : plan.abschnitte} lage={plan.lage}
                    kapitelReihenfolge={e.kapitelReihenfolge} kapitelVon={e.kapitelVon} planungsart={bearbeiten ? planungsart : plan.planungsart} />
                <p class="mt-2 text-sm text-light-tx-2 dark:text-dark-tx-2">
                    {plan.lage.belegt} von {plan.lage.unterrichtswochen} Unterrichtswochen verplant{#if plan.lage.frei}, {plan.lage.frei} frei{/if}
                </p>
                {#if plan.lage.ueberhang}
                    <div class="mt-2"><WarningBanner message="Der Plan ist {plan.lage.ueberhang} {plan.lage.ueberhang === 1 ? 'Woche' : 'Wochen'} länger als das Schuljahr." /></div>
                {/if}
            </section>
        {/if}

        {#if bearbeiten}
            <section class="mb-6">
                <label class="flex items-center gap-2 text-sm text-light-tx dark:text-dark-tx mb-3">
                    Planung
                    <select value={planungsart} onchange={(ev) => { const neu = ev.currentTarget.value; ev.currentTarget.value = planungsart; artWechseln(neu) }}
                        class="rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg px-2 py-1 text-sm">
                        {#each PLANUNGSARTEN as p (p.wert)}<option value={p.wert}>{p.text}</option>{/each}
                    </select>
                </label>
                <VerlaufsplanEditor bind:abschnitte {planungsart} wochenstunden={plan.wochenstunden}
                    lage={plan.lage} curricula={plan.curricula} onaenderung={geaendert} />
            </section>
        {:else}
            <section class="mb-6">
                {#if plan.abschnitte.length === 0}
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Noch keine Abschnitte.</p>
                {:else}
                    <div class="overflow-x-auto">
                        <table class="w-full text-sm">
                            <thead>
                                <tr class="text-left text-light-tx-2 dark:text-dark-tx-2 border-b border-light-ui-3 dark:border-dark-ui-3">
                                    <th class="py-1 pr-2">Nr.</th><th class="py-1 pr-2">Wochen</th><th class="py-1 pr-2">Zeitraum</th>
                                    <th class="py-1 pr-2">Thema</th><th class="py-1 pr-2">{plan.planungsart === 'sequenz' ? 'Sequenzen' : 'Kapitel'}</th><th class="py-1">Notiz</th>
                                </tr>
                            </thead>
                            <tbody>
                                {#each plan.abschnitte as a, i (a.id ?? i)}
                                    {@const l = plan.lage?.abschnitte?.[i]}
                                    {@const farbe = abschnittFarbe(a, e.kapitelReihenfolge, { planungsart: plan.planungsart, kapitelVon: e.kapitelVon })}
                                    <tr class="border-b border-light-ui-2 dark:border-dark-ui-2 align-top text-light-tx dark:text-dark-tx">
                                        <td class="py-1 pr-2">
                                            <span class="inline-block w-2.5 h-2.5 rounded-full mr-1 {farbe ? '' : 'bg-light-ui-3 dark:bg-dark-ui-3'}"
                                                style={farbe ? `background-color: ${farbe}` : ''} aria-hidden="true"></span>{i + 1}
                                        </td>
                                        <td class="py-1 pr-2">{a.wochen}</td>
                                        <td class="py-1 pr-2 whitespace-nowrap">
                                            {#if l}{zeitraumText(l) || wochenText(l)}<div class="text-xs text-light-tx-2 dark:text-dark-tx-2">{wochenText(l)}</div>{/if}
                                        </td>
                                        <td class="py-1 pr-2">
                                            {a.titel || '–'}
                                            {#if l && hinweise(l).length}<div class="text-xs text-light-tx-2 dark:text-dark-tx-2">{hinweise(l).join(' · ')}</div>{/if}
                                        </td>
                                        <td class="py-1 pr-2">{bezugText(a, plan.planungsart, e.titel)}</td>
                                        <td class="py-1 text-light-tx-2 dark:text-dark-tx-2">{a.notiz}</td>
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    </div>
                {/if}
            </section>
        {/if}

        <!-- Stundenbilanz je Kapitel -->
        {#if plan.lage?.kapitel?.length}
            <section>
                <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-2">Stunden je Kapitel</h2>
                {#if band}
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-2">Das Curriculum gilt für mehrere Stufen; „Soll“ ist die Stundenzahl für das ganze Band.</p>
                {/if}
                {#if !plan.wochenstunden}
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-2">Ohne Wochenstunden im Curriculum zählt die Bilanz nur Wochen.</p>
                {/if}
                <table class="text-sm">
                    <thead>
                        <tr class="text-left text-light-tx-2 dark:text-dark-tx-2 border-b border-light-ui-3 dark:border-dark-ui-3">
                            <th class="py-1 pr-4">Kapitel</th><th class="py-1 pr-4">Soll</th><th class="py-1 pr-4">Geplant</th><th class="py-1 pr-4">Wochen</th><th class="py-1"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each plan.lage.kapitel as k (k.kapitel_id)}
                            {@const s = bilanzStand(k, plan.wochenstunden)}
                            <tr class="border-b border-light-ui-2 dark:border-dark-ui-2 text-light-tx dark:text-dark-tx">
                                <td class="py-1 pr-4">{k.titel ?? 'nicht mehr im Curriculum'}</td>
                                <td class="py-1 pr-4">{k.soll ?? '–'}</td>
                                <td class="py-1 pr-4">{k.geplant ?? '–'}</td>
                                <td class="py-1 pr-4">{k.wochen}</td>
                                <td class="py-1 {s ? stand[s] : ''}">{s ?? ''}</td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
                {#if plan.lage.kapitel_ohne_abschnitt.length}
                    <p class="mt-2 text-sm text-light-or dark:text-dark-or">
                        Ohne Abschnitt: {plan.lage.kapitel_ohne_abschnitt.map((k) => e.titel[k] ?? k).join(', ')}
                    </p>
                {/if}
            </section>
        {/if}
    {/if}
</PageBody>
