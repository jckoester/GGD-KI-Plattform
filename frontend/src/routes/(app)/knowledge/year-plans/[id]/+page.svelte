<script>
    /**
     * Ein Jahresverlaufsplan (BD, Schritt 5): Zeitleiste, Abschnitte, Stundenbilanz; für die
     * Fachschaft mit Editor. Jede Änderung wird kurz verzögert gespeichert, der Server liefert die
     * Lage im Kalender zurück. Rückgängig nimmt den vorigen gespeicherten Stand und speichert ihn.
     */
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { onDestroy } from 'svelte'
    import { Check, CopyPlus, FileDown, Pencil, Stamp, Trash2, Undo2 } from '@lucide/svelte'
    import {
        beschliesseVerlaufsplan, deleteVerlaufsplan, exportVerlaufsplan, getVerlaufsplan, saveVerlaufsplan, uebernehmeVerlaufsplan,
    } from '$lib/api.js'
    import {
        PLANUNGSARTEN, abschnittFarbe, bezugText, einheiten, entwurfHinweis, hinweise, uebernahmeZiele,
        wochenText, zeitraumText, zumSpeichern,
    } from '$lib/verlaufsplan.js'
    import { pageTitle } from '$lib/stores/pageTitle.js'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import PageBody from '$lib/components/PageBody.svelte'
    import ZurueckLink from '$lib/components/ZurueckLink.svelte'
    import { rueckwegAus } from '$lib/rueckweg.js'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import InfoBanner from '$lib/components/InfoBanner.svelte'
    import WarningBanner from '$lib/components/WarningBanner.svelte'
    import VerlaufsplanZeitleiste from '$lib/components/VerlaufsplanZeitleiste.svelte'
    import VerlaufsplanEditor from '$lib/components/VerlaufsplanEditor.svelte'
    import VerlaufsplanBilanz from '$lib/components/VerlaufsplanBilanz.svelte'

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

    // Zeile unter dem Titel; „Entwurf“ steht nicht darin, das sagt das Banner (Jan 26.11.2026).
    const kopfzeile = $derived(plan ? [
        plan.status !== 'draft' && (plan.beschlossen_am ? `beschlossen am ${plan.beschlossen_am.split('-').reverse().join('.')}` : 'beschlossen'),
        plan.archiviert && 'Archiv, nur lesbar',
        plan.wochenstunden && `${plan.wochenstunden} Wochenstunden`,
    ].filter(Boolean).join(' · ') : '')
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

    // Ablaufleiste ↔ Tabelle/Editor (zweiter Durchgang): Hervorheben in beide Richtungen, Klick springt
    let hervor = $state(null)
    function zumAbschnitt(i) {
        document.getElementById(`abschnitt-${i}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        // Im Editor öffnet der Klick die Auswahl der Sequenzen bzw. Kapitel (Plan, Schritt 3)
        const auswahl = document.getElementById(`abschnitt-${i}-auswahl`)
        if (auswahl) auswahl.open = true
    }

    onDestroy(() => {
        if (timer) speichern()
    })

    // Knöpfe wie auf der Curriculum-Seite: Bearbeiten gefüllt, alles andere mit Rahmen.
    const knopfForm = 'inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed'
    const knopf = `${knopfForm} border border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2`
    const knopfRot = `${knopfForm} border border-light-ui-3 dark:border-dark-ui-3 text-light-re dark:text-dark-re hover:bg-light-ui-2 dark:hover:bg-dark-ui-2`
    const knopfPrimaer = `${knopfForm} bg-primary dark:bg-primary-dark text-on-fill hover:opacity-90`

    // Export (BD Teil B, Schritt 7) — wie auf der Curriculum-Seite eine eigene Zeile unter dem Kopf
    const WEITERBEARBEITEN = 'Zum Weiterbearbeiten in Word oder LibreOffice.'
    const EXPORTE = [
        { format: 'pdf', label: 'PDF' },
        { format: 'docx', label: 'DOCX', titel: WEITERBEARBEITEN },
        { format: 'odt', label: 'ODT', titel: WEITERBEARBEITEN },
    ]
    let exportiert = $state(false)
    let exportFehler = $state(null)
    async function exportieren(format) {
        if (exportiert) return
        exportiert = true
        exportFehler = null
        try {
            // Beim Bearbeiten zuerst speichern, sonst fehlte der letzte Stand — und scheitert das,
            // keine Datei mit dem alten Stand
            if (bearbeiten) {
                speicherFehler = null
                await speichern()
                if (speicherFehler) {
                    exportFehler = 'Nicht gespeichert, deshalb nicht exportiert.'
                    return
                }
            }
            await exportVerlaufsplan(plan.id, format)
        } catch (e) {
            exportFehler = e.message || 'Export fehlgeschlagen.'
        } finally {
            exportiert = false
        }
    }
</script>

<svelte:head><title>{plan?.titel ?? 'Jahresverlaufsplan'}</title></svelte:head>

<PageBody breit>
    <!-- Aus dem Planer einer Gruppe (BD Teil B) mit `?back=` zurück dorthin -->
    {@const zurueck = rueckwegAus($page.url.searchParams)}
    <ZurueckLink href={zurueck ?? (plan ? `/knowledge/year-plans?fach=${plan.subject_id}` : '/knowledge/year-plans')} label={zurueck ? 'Planung' : 'Jahresverlaufspläne'} />

    {#if laedt}
        <LoadingBanner message="Plan wird geladen…" />
    {:else if fehler}
        <ErrorBanner message={fehler} />
    {:else if plan}
        <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
            <div>
                <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">{plan.titel}</h1>
                {#if kopfzeile}
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">{kopfzeile}</p>
                {/if}
            </div>
            {#if plan.darf_bearbeiten}
                <div class="flex flex-wrap items-center gap-2">
                    {#if bearbeiten}
                        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2" aria-live="polite">
                            {speichert ? 'Speichert…' : 'Gespeichert'}
                        </span>
                        <button type="button" class={knopf} disabled={!verlauf.length || speichert} onclick={rueckgaengig}>
                            <Undo2 class="w-4 h-4" /> Rückgängig
                        </button>
                        <!-- Fertig bewusst nicht blau (Jan 25.11.2026): gespeichert wird ohnehin laufend. -->
                        <button type="button" class={knopf} onclick={async () => { await speichern(); bearbeiten = false }}>
                            <Check class="w-4 h-4" /> Fertig
                        </button>
                    {:else}
                        <button type="button" class={knopfPrimaer} onclick={() => (bearbeiten = true)}>
                            <Pencil class="w-4 h-4" /> Bearbeiten
                        </button>
                    {/if}
                    {#if plan.darf_beschliessen}
                        <button type="button" class={knopf} onclick={beschliessen}>
                            <Stamp class="w-4 h-4" /> Beschließen
                        </button>
                    {/if}
                    <button type="button" class={knopfRot} onclick={loeschen}>
                        <Trash2 class="w-4 h-4" /> Löschen
                    </button>
                </div>
            {/if}
        </div>

        <div class="flex flex-wrap items-center justify-end gap-2 -mt-3 mb-4">
            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Exportieren:</span>
            {#each EXPORTE as e (e.format)}
                <button type="button" onclick={() => exportieren(e.format)} disabled={exportiert} title={e.titel}
                    class="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border border-light-ui-3 dark:border-dark-ui-3
                           text-light-tx dark:text-dark-tx font-medium hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                           disabled:opacity-50 disabled:cursor-not-allowed">
                    <FileDown class="w-3.5 h-3.5" /> {e.label}
                </button>
            {/each}
        </div>
        {#if exportFehler}<div class="mb-3"><ErrorBanner message={exportFehler} /></div>{/if}

        {#if speicherFehler}<div class="mb-3"><ErrorBanner message={speicherFehler} /></div>{/if}
        {#if entfallen}
            <div class="mb-3"><WarningBanner message="Übernommen. {entfallen} {entfallen === 1 ? 'Kapitelbezug fand' : 'Kapitelbezüge fanden'} sich im heutigen Curriculum nicht wieder und {entfallen === 1 ? 'ist' : 'sind'} entfallen." /></div>
        {/if}
        {#if plan.status === 'draft'}
            <div class="mb-4"><InfoBanner message={entwurfHinweis(plan)} /></div>
        {/if}
        {#if plan.kalender_fehlt}
            <div class="mb-3"><InfoBanner message="Für {plan.schuljahr} liegt der Kalender der Schule noch nicht vor. Der Plan zählt deshalb nur Wochen, ohne Daten und Ferien." /></div>
        {/if}

        <!-- Aufteilung der Seite über Abstände (Jan 26.11.2026): Leiste und Bilanz mit mehr Luft
             nach oben, keine weiteren Rahmen. -->
        {#if plan.lage}
            <section class="mt-8 mb-8">
                <VerlaufsplanZeitleiste abschnitte={bearbeiten ? abschnitte : plan.abschnitte} lage={plan.lage}
                    kapitelReihenfolge={e.kapitelReihenfolge} kapitelVon={e.kapitelVon} planungsart={bearbeiten ? planungsart : plan.planungsart}
                    aktuell={plan.schuljahr === plan.aktuelles_schuljahr} bind:hervor onwahl={zumAbschnitt} />
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
                        class="rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg pl-2 pr-8 py-1 text-sm">
                        {#each PLANUNGSARTEN as p (p.wert)}<option value={p.wert}>{p.text}</option>{/each}
                    </select>
                </label>
                <VerlaufsplanEditor bind:abschnitte {planungsart} wochenstunden={plan.wochenstunden}
                    lage={plan.lage} curricula={plan.curricula} onaenderung={geaendert} bind:hervor />
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
                                    <tr id="abschnitt-{i}"
                                        class="border-b border-light-ui-2 dark:border-dark-ui-2 align-top text-light-tx dark:text-dark-tx scroll-mt-24 transition-colors
                                               {hervor === i ? 'bg-light-ui-2 dark:bg-dark-ui-2' : ''}"
                                        onmouseenter={() => (hervor = i)} onmouseleave={() => (hervor = null)}>
                                        <td class="py-1 pr-2">
                                            <span class="inline-block w-2.5 h-2.5 rounded-full mr-1 {a.puffer ? 'verlaufsplan-puffer border border-light-ui-3 dark:border-dark-ui-3' : farbe ? '' : 'bg-light-ui-3 dark:bg-dark-ui-3'}"
                                                style={farbe && !a.puffer ? `background-color: ${farbe}` : ''} aria-hidden="true"></span>{i + 1}
                                        </td>
                                        <td class="py-1 pr-2">{a.wochen}</td>
                                        <td class="py-1 pr-2 whitespace-nowrap">
                                            {#if l}{zeitraumText(l) || wochenText(l)}<div class="text-xs text-light-tx-2 dark:text-dark-tx-2">{wochenText(l)}</div>{/if}
                                        </td>
                                        <td class="py-1 pr-2">
                                            {a.titel || '–'}
                                            {#if l && hinweise(l).length}<div class="text-xs text-light-tx-2 dark:text-dark-tx-2">{hinweise(l).join(' · ')}</div>{/if}
                                        </td>
                                        <td class="py-1 pr-2 {a.puffer ? 'italic text-light-tx-2 dark:text-dark-tx-2' : ''}">{bezugText(a, plan.planungsart, e.titel)}</td>
                                        <td class="py-1 text-light-tx-2 dark:text-dark-tx-2">{a.notiz}</td>
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    </div>
                {/if}
            </section>
        {/if}

        <div class="mt-12">
            <VerlaufsplanBilanz lage={plan.lage} wochenstunden={plan.wochenstunden} {band}
                planungsart={plan.planungsart} />
        </div>

        <!-- Übernehmen (Schritt 6) als eigener Rahmen am Seitenende (zweiter Durchgang): Es betrifft
             das nächste Schuljahr, nicht die Arbeit am Plan. -->
        {#if plan.darf_uebernehmen && ziele.length}
            <section class="mt-8 rounded-md border border-light-ui-3 dark:border-dark-ui-3 p-4" data-abschnitt="uebernehmen">
                <h2 class="text-base font-semibold text-light-tx dark:text-dark-tx">
                    {plan.archiviert ? 'Als Ausgangspunkt für ein neues Schuljahr' : 'Für ein anderes Schuljahr übernehmen'}
                </h2>
                <p class="mt-1 mb-3 text-sm text-light-tx-2 dark:text-dark-tx-2">
                    Legt eine Kopie mit denselben Abschnitten als Entwurf an; Daten und Ferien kommen aus dem Kalender des Zielschuljahrs. Dieser Plan bleibt unverändert.
                </p>
                <div class="flex flex-wrap items-center gap-2">
                    <select bind:value={ziel} aria-label="Schuljahr"
                        class="rounded-md border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx pl-2 pr-8 py-1.5 text-sm">
                        {#each ziele as j (j)}<option value={j}>{j}</option>{/each}
                    </select>
                    <button type="button" class={knopf} onclick={inSchuljahrUebernehmen}>
                        <CopyPlus class="w-4 h-4" /> Als Entwurf übernehmen
                    </button>
                </div>
            </section>
        {/if}
    {/if}
</PageBody>
