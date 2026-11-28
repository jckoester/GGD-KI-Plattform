<script>
    /**
     * Vernetzung der Fächer (BE, Plan `Vernetzung-Zeitachse-BE-Plan`). Zwei Reiter:
     * - **Übersicht** (Teil B, 0.67): Fach × Fach einer Stufe; Einstieg, solange kein Fach gewählt ist.
     * - **Zeitachse** (Teil A, 0.66): ein Fach in der Mitte, die vernetzten Fächer als Spuren daneben.
     * Nur für Lehrkräfte. Zustand in der Adresse (`?ansicht=uebersicht&fach=&spur=&kapitel=&schuljahr=&weg=&stufe=&entwuerfe=1`;
     * `spur` gilt nur beim Laden), die gewählten Spuren je Fach in den Einstellungen (`vernetzung_spuren`).
     */
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { tick } from 'svelte'
    import { ArrowDownUp, ChartGantt, FileDown, Grid3x3, List, PanelRight, Plus, TriangleAlert, X } from '@lucide/svelte'
    import { getPreferences, getVernetzung, getVernetzungMatrix, ladeVernetzungPdf, patchPreferences } from '$lib/api.js'
    import { ohneBezug, tabelle } from '$lib/vernetzung_matrix.js'
    import { pdfAnfrage } from '$lib/zeitachse_svg.js'
    import { pageTitle } from '$lib/stores/pageTitle.js'
    import { subjects } from '$lib/stores/subjects.js'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import { fachToenung } from '$lib/absprachen.js'
    import { bereichText, stufenBereiche } from '$lib/heatmap_stufen.js'
    import {
        SPUREN_SCHLUESSEL, STIL, achse, adresse, ausAdresse, bloecke, gemerkteSpuren, naechstesSchuljahr, spalten,
        spurenWaehlen, vernetzungPfad,
    } from '$lib/zeitachse.js'
    import FachWahl from '$lib/components/FachWahl.svelte'
    import SubjectIcon from '$lib/components/SubjectIcon.svelte'
    import ZurueckLink from '$lib/components/ZurueckLink.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import VernetzungZeitachse from '$lib/components/VernetzungZeitachse.svelte'
    import VernetzungTafel from '$lib/components/VernetzungTafel.svelte'
    import VernetzungListe from '$lib/components/VernetzungListe.svelte'
    import VernetzungMatrix from '$lib/components/VernetzungMatrix.svelte'

    pageTitle.set('Vernetzung der Fächer')

    $effect(() => {
        if ($user && !userHasAnyRole($user, ['teacher', 'admin'])) goto('/chat')
    })

    const start = ausAdresse($page.url.searchParams)
    let zustand = $state({ ...start, spur: null })   // `spur` nur beim Laden (Einstieg aus der Übersicht)
    let gewaehlt = $state(start.kapitel)
    let daten = $state(null)
    let fehler = $state(null)
    let laedt = $state(false)
    let einstellungen = $state({})
    let wahl = $state(start.spur != null ? [start.spur] : null)   // gewählte Spuren (Kennungen); null = gemerkt oder Vorgabe
    const ansicht = $derived(zustand.ansicht === 'uebersicht' || !zustand.fach ? 'uebersicht' : 'zeitachse')
    let schalter = $state({ querverweise: true, bereiche: false, alle: false, leitlinien: true, liste: false })
    let zeileBreite = $state(1000)   // Platz für Zeitachse und Tafel (gemessen)
    let kopfHoehe = $state(0)        // Höhe der stehenbleibenden Spaltenköpfe
    let scroller = $state(null)
    let werkzeugEl = $state(null)
    let leisteUnten = $state(false)  // Werkzeugleiste unten, sobald die obere weggescrollt ist (wie im Curriculum)

    // Tafel rechts, wenn neben Mitte und einer Spur Platz ist; sonst unten (Befund Sichtprobe:
    // vorher an der Fensterbreite `lg` festgemacht, Tafel landete unten links)
    const TAFEL = 320
    let tafelZu = $state(false)      // Tafel geschlossen: die Tabelle bekommt die ganze Breite (Jan 28.11.2026)
    let hover = $state(null)         // Kapitel unter dem Zeiger: hebt schon vor dem Klick hervor
    const tafelRechts = $derived(!tafelZu && zeileBreite >= 900 + TAFEL)
    const breite = $derived(tafelRechts ? zeileBreite - TAFEL - 16 : zeileBreite)

    $effect(() => {
        if (!scroller || !werkzeugEl) return
        const obs = new IntersectionObserver(([e]) => (leisteUnten = !e.isIntersecting), { root: scroller, threshold: 0 })
        obs.observe(werkzeugEl)
        return () => obs.disconnect()
    })
    let tipp = $state(null)
    let sprungZiel = $state(start.kapitel ? { kapitel: start.kapitel } : start.stufe ? { stufe: start.stufe } : null)

    getPreferences().then((e) => (einstellungen = e ?? {}))

    // Laden, wenn Fach oder Zeitraum wechseln (nur im Reiter Zeitachse)
    $effect(() => {
        const { fach, schuljahr, weg, entwuerfe } = zustand
        if (ansicht !== 'zeitachse') return
        if (!fach) {
            daten = null
            return
        }
        laedt = true
        fehler = null
        getVernetzung({ fach, schuljahr, weg, entwuerfe })
            .then((d) => (daten = d))
            .catch((e) => { fehler = e.message; daten = null })
            .finally(() => (laedt = false))
    })

    // Übersicht (Teil B): je Stufe; die Stufe teilt sie mit dem Sprungziel der Zeitachse
    let matrixDaten = $state(null)
    let matrixFehler = $state(null)
    let matrixLaedt = $state(false)
    const matrixStufe = $derived(zustand.stufe ?? 7)
    $effect(() => {
        if (ansicht !== 'uebersicht') return
        const stufe = matrixStufe
        const { schuljahr, entwuerfe } = zustand
        matrixLaedt = true
        matrixFehler = null
        getVernetzungMatrix({ stufe, schuljahr, entwuerfe })
            .then((d) => {
                matrixDaten = d
                // Keine Curricula in dieser Stufe, aber in anderen: zur nächstgelegenen
                if (!d.faecher.length && d.stufen.length && !d.stufen.includes(stufe)) {
                    const naechste = d.stufen.reduce((x, y) => (Math.abs(y - stufe) < Math.abs(x - stufe) ? y : x))
                    zustand = { ...zustand, stufe: naechste }
                }
            })
            .catch((e) => { matrixFehler = e.message; matrixDaten = null })
            .finally(() => (matrixLaedt = false))
    })
    const tab = $derived(matrixDaten ? tabelle(matrixDaten, schalter) : null)
    const hervor = $derived(matrixDaten?.faecher.find((f) => f.code === zustand.fach || String(f.id) === zustand.fach)?.id ?? null)
    const matrixAktuelles = $derived(matrixDaten?.aktuelles_schuljahr ?? aktuelles)

    function zelleOeffnen(zeile, spalte) {
        zustand = { ...zustand, ansicht: null, fach: zeile.code, weg: null, stufe: matrixStufe }
        gewaehlt = null
        wahl = zeile.id === spalte.id ? [] : [spalte.id]
        sprungZiel = { stufe: matrixStufe }
    }
    function zellePfad(zeile, spalte) {
        return vernetzungPfad({ fach: zeile.code, stufe: matrixStufe, schuljahr: zustand.schuljahr, aktuelles: matrixAktuelles,
            entwuerfe: zustand.entwuerfe, spur: zeile.id === spalte.id ? null : spalte.id })
    }
    function reiter(wert) {
        zustand = { ...zustand, ansicht: wert === 'uebersicht' ? 'uebersicht' : null, weg: wert === 'uebersicht' ? null : zustand.weg }
    }

    // Adresse nachführen
    $effect(() => {
        const q = adresse({ ...zustand, kapitel: gewaehlt })
        if (q !== $page.url.searchParams.toString()) goto(`?${q}`, { replaceState: true, noScroll: true, keepFocus: true })
    })

    const faecherAuswahl = $derived(($subjects ?? []).filter((s) => s.fach_code))
    const fachCode = $derived(daten?.fach?.code ?? faecherAuswahl.find((s) => String(s.id) === zustand.fach)?.fach_code ?? zustand.fach)
    const aktuelles = $derived(daten?.zeitraum?.aktuelles_schuljahr ?? null)
    const kommendes = $derived(naechstesSchuljahr(aktuelles))
    const zeitraum = $derived(zustand.weg != null ? 'weg' : zustand.schuljahr && zustand.schuljahr !== aktuelles ? 'kommend' : 'laufend')

    // Spuren und Anordnung
    const gemerkt = $derived(daten ? gemerkteSpuren(einstellungen, daten.fach.id) : null)
    const kandidaten = $derived(daten ? spurenWaehlen(daten.faecher, { gewaehlt: wahl ?? gemerkt }).spuren : [])
    const lay = $derived(spalten(breite, kandidaten, { leitlinien: schalter.leitlinien, fuellen: true }))
    const genutzt = $derived(lay.genutzt)
    const spurIds = $derived(new Set(genutzt.map((f) => f.id)))
    const weitere = $derived((daten?.faecher ?? []).filter((f) => !spurIds.has(f.id)))
    const bereicheAn = $derived(schalter.bereiche || genutzt.some((f) => f.nur_bereich))
    const a = $derived(achse(daten?.stufen ?? [], { fachName: daten?.fach?.name ?? '' }))
    const je = $derived(daten ? bloecke(daten.kapitel, a, lay.spalten, daten.fach.id) : new Map())
    const kapitelFach = $derived(new Map((daten?.kapitel ?? []).map((k) => [k.id, k.fach_id])))
    const bezuege = $derived((daten?.bezuege ?? []).filter((b) => b.typ === 'absprache'
        || (schalter.querverweise && (b.typ !== 'bereich' || bereicheAn))))
    const kapitelJe = $derived(new Map((daten?.kapitel ?? []).map((k) => [k.id, k])))
    const ohneLage = $derived((daten?.kapitel ?? []).filter((k) => k.fach_id === daten.fach.id && !k.lage.length))

    function vergleich(x, y) {
        const lx = kapitelJe.get(x)?.lage?.[0]
        const ly = kapitelJe.get(y)?.lage?.[0]
        if (!lx || !ly) return 0
        return lx.stufe - ly.stufe || lx.von_woche - ly.von_woche
    }

    // ── Bedienung ───────────────────────────────────────────────────────────
    function fachWaehlen(code) {
        if (code && code === fachCode) return
        // Leeren (× an der Fachmarke) setzt die Ansicht zurück
        // Ein Fach öffnet die Zeitachse; ohne Fach zeigt die Seite die Übersicht
        zustand = { ...zustand, ansicht: null, fach: code ?? '', weg: null, schuljahr: code ? zustand.schuljahr : null }
        gewaehlt = null
        wahl = null
    }
    function zeitraumWaehlen(wert) {
        gewaehlt = null
        if (wert === 'weg') {
            zustand = { ...zustand, schuljahr: null, weg: zustand.stufe ?? daten?.stufen?.[0]?.stufe ?? 7 }
        } else {
            zustand = { ...zustand, weg: null, schuljahr: wert === 'kommend' ? kommendes : null }
        }
    }
    async function spurenSpeichern(ids) {
        wahl = ids
        const alle = { ...(einstellungen[SPUREN_SCHLUESSEL] ?? {}) }
        if (ids) alle[String(daten.fach.id)] = ids
        else delete alle[String(daten.fach.id)]
        einstellungen = { ...einstellungen, [SPUREN_SCHLUESSEL]: alle }
        try { await patchPreferences({ [SPUREN_SCHLUESSEL]: alle }) } catch { /* bleibt für diese Sitzung */ }
    }
    function spurEntfernen(id) {
        spurenSpeichern(genutzt.map((f) => f.id).filter((x) => x !== id))
    }
    function spurHinzu(id) {
        const ids = genutzt.map((f) => f.id)
        if (ids.length >= lay.passen && ids.length) ids.pop()
        spurenSpeichern([...ids, id])
        if (daten.faecher.find((f) => f.id === id)?.nur_bereich) schalter.bereiche = true
        weitereOffen = false
    }
    let weitereOffen = $state(false)

    function zuStufe(stufe) {
        const el = document.getElementById(`stufe-${stufe}`)
        if (!el || !scroller) return
        const top = scroller.scrollTop + el.getBoundingClientRect().top - scroller.getBoundingClientRect().top - kopfHoehe - 6
        scroller.scrollTo({ top, behavior: 'smooth' })
        zustand = { ...zustand, stufe }
    }
    async function zuKapitel(id) {
        await tick()
        const el = document.getElementById(`kap-${id}`)
        if (!el || !scroller) return
        const r = el.getBoundingClientRect()
        const top = scroller.scrollTop + r.top - scroller.getBoundingClientRect().top - kopfHoehe - 80
        scroller.scrollTo({ top, behavior: 'smooth' })
    }
    function waehle(id) {
        gewaehlt = id
        if (id) tafelZu = false      // ein gewähltes Kapitel öffnet die Tafel wieder
    }
    function waehleUndZeige(id) {
        waehle(id)
        zuKapitel(id)
    }
    function inDieMitte(fachId) {
        const f = daten.faecher.find((x) => x.id === fachId)
        if (!f) return
        sprungZiel = gewaehlt ? { kapitel: gewaehlt } : null
        zustand = { ...zustand, fach: f.code, weg: null }
        wahl = null
    }

    // Nach dem Laden: zum Kapitel oder zur Stufe aus der Adresse
    $effect(() => {
        if (!daten || !sprungZiel) return
        const ziel = sprungZiel
        sprungZiel = null
        tick().then(() => (ziel.kapitel ? zuKapitel(ziel.kapitel) : zuStufe(ziel.stufe)))
    })

    function zeigeTipp(e, k) {
        hover = k?.id ?? null
        if (!e || !k) { tipp = null; return }
        const rect = e.currentTarget?.getBoundingClientRect?.()
        const x = e.clientX ?? (rect ? rect.right : 0)
        const y = e.clientY ?? (rect ? rect.top : 0)
        tipp = { x, y, k }
    }

    // PDF (Schritt 7, F14 a): je Stufe eine Seite, dazu die Liste
    let pdfLaeuft = $state(false)
    let pdfFehler = $state(null)
    async function pdf() {
        pdfLaeuft = true
        pdfFehler = null
        const zeitraumText = zustand.weg != null
            ? `Weg der Klasse, die ${aktuelles} in Kl. ${zustand.weg} ist`
            : `Schuljahr ${zustand.schuljahr ?? aktuelles}`
        const zusatz = [zustand.entwuerfe && 'mit Entwürfen', !schalter.querverweise && 'ohne Querverweise des Bildungsplans',
            bereicheAn && 'mit Bezügen auf ganze Bereiche'].filter(Boolean)
        try {
            await ladeVernetzungPdf(pdfAnfrage(daten, {
                kandidaten, bezuege, leitlinien: schalter.leitlinien,
                zeitraum: [zeitraumText, ...zusatz].join(' · '),
            }))
        } catch (e) {
            pdfFehler = e.message
        } finally {
            pdfLaeuft = false
        }
    }

    function taste(e) {
        if (e.key === 'Escape' && gewaehlt) gewaehlt = null
    }

    const knopf = 'inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium border border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'
    const feld = 'text-sm rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx pl-2 pr-8 py-1'
    const faecherJe = $derived(daten ? Object.fromEntries([[daten.fach.id, daten.fach], ...daten.faecher.map((f) => [f.id, f])]) : {})
    const stufenJe = $derived(Object.fromEntries((daten?.stufen ?? []).map((s) => [s.stufe, s])))
</script>

<svelte:window onkeydown={taste} />

{#snippet linie(st, rot = false)}
    <svg width="30" height="10" aria-hidden="true" class={rot ? 'text-light-re dark:text-dark-re' : st.strich ? 'text-light-tx-2 dark:text-dark-tx-2' : 'text-light-tx dark:text-dark-tx'}>
        <path d="M1,5 L29,5" stroke="currentColor" stroke-width={st.breite} stroke-dasharray={st.strich ?? undefined} />
    </svg>
{/snippet}

<!-- Block 2: Werkzeugleiste (oben und, weggescrollt, unten) -->
{#snippet werkzeugeMatrix()}
    <div class="flex flex-wrap items-end gap-x-4 gap-y-2">
        <label class="text-xs text-light-tx-2 dark:text-dark-tx-2 flex flex-col">
            Klassenstufe
            <select class={feld} value={matrixStufe} onchange={(e) => (zustand = { ...zustand, stufe: Number(e.target.value) })}>
                {#each matrixDaten?.stufen?.length ? matrixDaten.stufen : [matrixStufe] as st (st)}<option value={st}>Kl. {st}</option>{/each}
            </select>
        </label>
        {#if matrixAktuelles}
            <label class="text-xs text-light-tx-2 dark:text-dark-tx-2 flex flex-col">
                Zeitraum
                <select class={feld} value={zustand.schuljahr && zustand.schuljahr !== matrixAktuelles ? 'kommend' : 'laufend'}
                        onchange={(e) => (zustand = { ...zustand, schuljahr: e.target.value === 'kommend' ? naechstesSchuljahr(matrixAktuelles) : null })}>
                    <option value="laufend">Schuljahr {matrixAktuelles}</option>
                    <option value="kommend">Schuljahr {naechstesSchuljahr(matrixAktuelles)}</option>
                </select>
            </label>
        {/if}
        <div class="w-56 text-xs text-light-tx-2 dark:text-dark-tx-2">
            <label for="vernetzung-fach-matrix">Zeitachse eines Fachs</label>
            <FachWahl id="vernetzung-fach-matrix" faecher={faecherAuswahl} wert={null} onwahl={fachWaehlen} />
        </div>
    </div>
    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
        <span class="font-medium">Zählen:</span>
        <label class="inline-flex items-center gap-1"><input type="checkbox" bind:checked={schalter.querverweise} /> Querverweise des Bildungsplans</label>
        <label class="inline-flex items-center gap-1"><input type="checkbox" bind:checked={schalter.bereiche} disabled={!schalter.querverweise} /> auch Bezüge auf ganze Bereiche</label>
        <label class="inline-flex items-center gap-1"><input type="checkbox" checked={zustand.entwuerfe}
               onchange={(e) => (zustand = { ...zustand, entwuerfe: e.target.checked })} /> mit Entwürfen</label>
    </div>
{/snippet}

{#snippet werkzeuge(wo)}
    <div class="flex flex-wrap items-end gap-x-4 gap-y-2">
        <div class="w-56 text-xs text-light-tx-2 dark:text-dark-tx-2">
            <label for="vernetzung-fach-{wo}">Fach in der Mitte</label>
            <FachWahl id="vernetzung-fach-{wo}" faecher={faecherAuswahl} wert={fachCode} onwahl={fachWaehlen} />
        </div>
        {#if daten}
            <label class="text-xs text-light-tx-2 dark:text-dark-tx-2 flex flex-col">
                Zeitraum
                <select class={feld} value={zeitraum} onchange={(e) => zeitraumWaehlen(e.target.value)}>
                    <option value="laufend">Schuljahr {aktuelles}</option>
                    {#if kommendes}<option value="kommend">Schuljahr {kommendes}</option>{/if}
                    <option value="weg">Weg einer Klasse</option>
                </select>
            </label>
            {#if zustand.weg != null}
                <label class="text-xs text-light-tx-2 dark:text-dark-tx-2 flex flex-col">
                    Klasse, die {aktuelles} in
                    <select class={feld} value={zustand.weg}
                            onchange={(e) => (zustand = { ...zustand, weg: Number(e.target.value) })}>
                        {#each daten.stufen as st (st.stufe)}<option value={st.stufe}>Kl. {st.stufe} ist</option>{/each}
                    </select>
                </label>
            {/if}
            {#if !schalter.liste && daten.stufen.length}
                <div class="flex flex-wrap items-center gap-1 text-xs text-light-tx-2 dark:text-dark-tx-2 pb-1">
                    Springe zu
                    {#each daten.stufen as st (st.stufe)}
                        <button type="button" class={knopf} onclick={() => zuStufe(st.stufe)}>Kl. {st.stufe}</button>
                    {/each}
                </div>
            {/if}
            <div class="flex items-center gap-2 pb-1 ml-auto">
                {#if !schalter.liste}
                    <button type="button" class={knopf} aria-pressed={!tafelZu} onclick={() => (tafelZu = !tafelZu)}>
                        <PanelRight class="w-3.5 h-3.5" /> {tafelZu ? 'Tafel zeigen' : 'Tafel ausblenden'}
                    </button>
                {/if}
                <button type="button" class={knopf} aria-pressed={schalter.liste} onclick={() => (schalter.liste = !schalter.liste)}>
                    {#if schalter.liste}<ChartGantt class="w-3.5 h-3.5" /> Zeitachse{:else}<List class="w-3.5 h-3.5" /> Liste{/if}
                </button>
                <button type="button" class={knopf} onclick={pdf} disabled={pdfLaeuft || !daten.stufen.length}>
                    <FileDown class="w-3.5 h-3.5" /> {pdfLaeuft ? 'PDF wird erstellt…' : 'PDF'}
                </button>
            </div>
        {/if}
    </div>
    {#if pdfFehler}<p class="mt-1 text-xs text-light-re dark:text-dark-re">{pdfFehler}</p>{/if}
{/snippet}

<!-- Block 3: welche Vernetzungen angezeigt werden -->
{#snippet auswahl()}
    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
        <span class="font-medium">Anzeigen:</span>
        <label class="inline-flex items-center gap-1"><input type="checkbox" bind:checked={schalter.querverweise} /> Querverweise des Bildungsplans</label>
        <label class="inline-flex items-center gap-1"><input type="checkbox" bind:checked={schalter.bereiche} disabled={!schalter.querverweise} /> auch Bezüge auf ganze Bereiche</label>
        <label class="inline-flex items-center gap-1"><input type="checkbox" bind:checked={schalter.alle} /> alle Linien</label>
        <label class="inline-flex items-center gap-1"><input type="checkbox" bind:checked={schalter.leitlinien} /> Leitlinien und Leitperspektiven</label>
        <label class="inline-flex items-center gap-1"><input type="checkbox" checked={zustand.entwuerfe}
               onchange={(e) => (zustand = { ...zustand, entwuerfe: e.target.checked })} /> mit Entwürfen</label>
    </div>
{/snippet}

<div class="h-full flex flex-col relative bg-light-bg dark:bg-dark-bg">
    <div class="flex-1 overflow-y-auto px-6 pt-4 {leisteUnten ? 'pb-36' : 'pb-12'}" bind:this={scroller}>
        <!-- Block 1: Überschrift (scrollt weg) -->
        <ZurueckLink href="/knowledge" label="Bibliothek" />
        <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">Vernetzung der Fächer</h1>
        {#if ansicht === 'uebersicht'}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                Welche Fächer einer Klassenstufe miteinander vernetzt sind: je Fächerpaar die Zahl der verbundenen Kapitel.
                Ein Klick auf eine Zelle öffnet die Zeitachse der beiden Fächer.
            </p>
        {:else if daten}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                {#if zustand.weg != null}
                    Weg der Klasse, die {aktuelles} in Kl. {zustand.weg} ist — jede Stufe mit dem Plan ihres Schuljahrs.
                {:else}
                    Jede Stufe auf dem Jahresverlaufsplan {zustand.schuljahr ?? aktuelles}: die Ansicht zeigt den Aufbau der Curricula, nicht den Weg einer Klasse.
                {/if}
            </p>
        {/if}

        <div class="mt-4 flex gap-1 border-b border-light-ui-3 dark:border-dark-ui-3" role="tablist" aria-label="Ansicht">
            {#each [['uebersicht', 'Übersicht', Grid3x3], ['zeitachse', 'Zeitachse', ChartGantt]] as [wert, name, Icon] (wert)}
                <button type="button" role="tab" aria-selected={ansicht === wert} disabled={wert === 'zeitachse' && !zustand.fach}
                        title={wert === 'zeitachse' && !zustand.fach ? 'Erst ein Fach wählen' : undefined}
                        class="inline-flex items-center gap-1.5 -mb-px px-3 py-1.5 text-sm border-b-2 disabled:opacity-50
                               {ansicht === wert ? 'border-primary dark:border-primary-dark text-light-tx dark:text-dark-tx font-medium'
                                                 : 'border-transparent text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx'}"
                        onclick={() => reiter(wert)}>
                    <Icon class="w-4 h-4" /> {name}{wert === 'zeitachse' && fachCode ? ` ${faecherAuswahl.find((f) => f.fach_code === fachCode)?.name ?? fachCode}` : ''}
                </button>
            {/each}
        </div>

        {#if ansicht === 'uebersicht'}
            <div class="mt-3 space-y-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2 px-3 py-2">
                {@render werkzeugeMatrix()}
            </div>
            <div class="mt-5">
                {#if matrixFehler}
                    <ErrorBanner message={matrixFehler} />
                {:else if matrixLaedt && !matrixDaten}
                    <LoadingBanner />
                {:else if tab && !tab.faecher.length}
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                        Für Kl. {matrixStufe} gibt es {zustand.entwuerfe ? 'kein Curriculum' : 'kein veröffentlichtes Curriculum'}.
                        {#if !zustand.entwuerfe}Mit „mit Entwürfen“ siehst du auch Curricula, die noch entstehen.{/if}
                    </p>
                {:else if tab}
                    <div class={matrixLaedt ? 'opacity-60' : ''}>
                        {#if ohneBezug(tab)}
                            <p class="mb-2 text-sm text-light-tx-2 dark:text-dark-tx-2">In Kl. {matrixStufe} sind die Fächer noch nicht miteinander verbunden.</p>
                        {/if}
                        <VernetzungMatrix t={tab} {schalter} {hervor} pfad={zellePfad} onzelle={zelleOeffnen} />
                    </div>
                    <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-light-tx-2 dark:text-dark-tx-2" aria-label="Legende">
                        <span><b>A</b> Absprachen, <b>Q</b> Querverweise{#if schalter.bereiche}, <b>B</b> über ganze Bereiche{/if}</span>
                        <span class="inline-flex items-center gap-1"><TriangleAlert class="w-3.5 h-3.5 text-light-re dark:text-dark-re" /> Absprache nicht eingehalten</span>
                        <span class="inline-flex items-center gap-1"><ArrowDownUp class="w-3.5 h-3.5" /> im eigenen Fach (ohne Farbe)</span>
                        <span>(n) Kapitel in Kl. {matrixStufe}</span>
                    </div>
                    {#if tab.max}
                        <div class="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-light-tx-2 dark:text-dark-tx-2" aria-label="Legende der Farben">
                            <span>Bezüge je Zelle:</span>
                            {#each stufenBereiche(tab.max) as b (b.stufe)}
                                <span class="inline-flex items-center gap-1">
                                    <span class="inline-block w-3 h-3 rounded-sm" style="background-color: var(--diagramm-stufe-{b.stufe})"></span>
                                    {bereichText(b)}
                                </span>
                            {/each}
                        </div>
                    {/if}
                    <p class="mt-2 text-xs text-light-tx-2 dark:text-dark-tx-2 max-w-3xl">
                        Gezählt werden Kapitel, die laut Jahresverlaufsplan oder Schätzung in Kl. {matrixStufe} liegen. Bezüge in eine
                        andere Klassenstufe zeigt die Zeitachse. Leitlinien und Leitperspektiven stehen in der
                        <a href="/knowledge/cross-cutting-themes" class="text-light-bl dark:text-dark-bl hover:underline">Übersicht der Leitlinien und Leitperspektiven</a>.
                    </p>
                {/if}
            </div>
        {:else}
        <!-- Block 2 und 3 -->
        <div bind:this={werkzeugEl} class="mt-3 space-y-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2 px-3 py-2">
            {@render werkzeuge('oben')}
            {#if daten}{@render auswahl()}{/if}
        </div>

        <!-- Block 5: Tabelle -->
        <div class="mt-3" bind:clientWidth={zeileBreite}>
            {#if fehler}
                <ErrorBanner message={fehler} />
            {:else if laedt && !daten}
                <LoadingBanner />
            {:else if daten && !daten.stufen.length}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                    Für {daten.fach.name} gibt es {zustand.entwuerfe ? 'kein Curriculum' : 'kein veröffentlichtes Curriculum'}.
                    {#if !zustand.entwuerfe}Mit „mit Entwürfen“ siehst du auch Curricula, die noch entstehen.{/if}
                </p>
            {:else if daten && schalter.liste}
                <VernetzungListe {daten} {bezuege} onwaehle={waehle} />
            {:else if daten}
                <!-- Stehender Kopf: Linienlegende und Spaltenköpfe, bündig an der Oberkante (`top: -1rem`
                     gleicht den Innenabstand des Scrollbereichs aus, sonst scrollt darüber ein Streifen durch) -->
                <div class="sticky -top-4 z-40 -mx-6 px-6 pt-2 bg-light-bg dark:bg-dark-bg border-b border-light-ui-3 dark:border-dark-ui-3"
                     bind:clientHeight={kopfHoehe}>
                    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 mb-1 text-xs text-light-tx-2 dark:text-dark-tx-2" aria-label="Legende der Linien">
                        <span class="inline-flex items-center gap-1">{@render linie(STIL.absprache)} Absprache</span>
                        <span class="inline-flex items-center gap-1">{@render linie(STIL.absprache, true)} nicht eingehalten</span>
                        {#if schalter.querverweise}
                            <span class="inline-flex items-center gap-1">{@render linie(STIL.kompetenz)} Querverweis</span>
                            {#if bereicheAn}<span class="inline-flex items-center gap-1">{@render linie(STIL.bereich)} über einen Bereich</span>{/if}
                            <span class="inline-flex items-center gap-1">
                                <svg width="22" height="14" aria-hidden="true"><path d="M20,2 H8 Q4,2 4,6 V8 Q4,12 8,12 H20" fill="none" stroke={daten.fach.color ?? 'currentColor'} stroke-width="2" /></svg>
                                im eigenen Fach (Pfeil zum späteren Kapitel)
                            </span>
                        {/if}
                    </div>
                    <div class="relative h-8" style="width: {breite}px">
                        {#if lay.spalten.leitlinien}
                            <span class="absolute top-2 text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 text-center"
                                  style="left: {lay.spalten.leitlinien.x}px; width: {lay.spalten.leitlinien.b}px">Leitlinien</span>
                            <span class="absolute top-2 text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 text-center"
                                  style="left: {lay.spalten.leitperspektiven.x}px; width: {lay.spalten.leitperspektiven.b}px">Leitperspektiven</span>
                        {/if}
                        <span class="absolute top-1 flex justify-center" style="left: {lay.spalten.mitte.x}px; width: {lay.spalten.mitte.b}px">
                            <span class="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-semibold text-light-tx dark:text-dark-tx"
                                  style={fachToenung(daten.fach.color)}>
                                <SubjectIcon name={daten.fach.icon} size={13} color={daten.fach.color} />{daten.fach.name}
                            </span>
                        </span>
                        {#each genutzt as f (f.id)}
                            {@const sp = lay.spalten[f.id]}
                            <span class="absolute top-1 flex justify-center" style="left: {sp.x}px; width: {sp.b}px">
                                <span class="inline-flex items-center gap-0.5 rounded border px-1 py-0.5 text-[11px] text-light-tx-2 dark:text-dark-tx-2 max-w-full"
                                      style={fachToenung(f.color)} title="{f.name}{f.nur_bereich ? ' — nur über Bereiche' : ''}">
                                    <SubjectIcon name={f.icon} size={12} color={f.color} />
                                    {#if !lay.schmal}<span class="truncate">{f.name}</span>{/if}
                                    <button type="button" class="rounded hover:text-light-tx dark:hover:text-dark-tx focus:outline-none focus:ring-2 focus:ring-primary"
                                            aria-label="{f.name} ausblenden" onclick={() => spurEntfernen(f.id)}><X class="w-3 h-3" /></button>
                                </span>
                            </span>
                        {/each}
                        {#if weitere.length && !lay.mobil}
                            <span class="absolute top-1" style="left: 0">
                                <button type="button" class={knopf} aria-expanded={weitereOffen} onclick={() => (weitereOffen = !weitereOffen)}>
                                    <Plus class="w-3 h-3" />{weitere.length} {weitere.length === 1 ? 'Fach' : 'Fächer'}
                                </button>
                                {#if weitereOffen}
                                    <ul class="absolute z-50 mt-1 w-64 max-h-72 overflow-y-auto rounded border border-light-ui-3 dark:border-dark-ui-3
                                               bg-light-bg dark:bg-dark-bg shadow text-sm">
                                        {#each weitere as f (f.id)}
                                            <li>
                                                <button type="button" class="w-full flex items-center gap-2 px-3 py-1.5 text-left text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                                                        onclick={() => spurHinzu(f.id)}>
                                                    <SubjectIcon name={f.icon} size={14} color={f.color} />
                                                    <span class="flex-1">{f.name}</span>
                                                    <span class="text-[11px] text-light-tx-2 dark:text-dark-tx-2">
                                                        {f.nur_bereich ? 'nur über Bereiche' : [f.absprachen && `${f.absprachen} Abspr.`, f.kompetenz && `${f.kompetenz} Querv.`].filter(Boolean).join(', ')}
                                                    </span>
                                                </button>
                                            </li>
                                        {/each}
                                        {#if wahl ?? gemerkt}
                                            <li class="border-t border-light-ui-3 dark:border-dark-ui-3">
                                                <button type="button" class="w-full px-3 py-1.5 text-left text-xs text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                                                        onclick={() => { spurenSpeichern(null); weitereOffen = false }}>Spuren wie vorgeschlagen</button>
                                            </li>
                                        {/if}
                                    </ul>
                                {/if}
                            </span>
                        {/if}
                    </div>
                </div>

                <div class="flex gap-4 mt-2">
                    <div class="shrink-0 {laedt ? 'opacity-60' : ''}" style="width: {breite}px">
                        {#if lay.mobil}
                            <p class="mb-2 text-xs text-light-tx-2 dark:text-dark-tx-2">Auf diesem schmalen Bildschirm steht nur das Fach in der Mitte; die Bezüge stehen beim gewählten Kapitel.</p>
                        {/if}
                        <VernetzungZeitachse {daten} {lay} {a} {je} {bezuege} {kapitelFach} {spurIds} {gewaehlt} {hover}
                                             alle={schalter.alle} onwaehle={waehle} ontipp={zeigeTipp} />
                        {#if ohneLage.length}
                            <p class="mt-3 text-xs text-light-tx-2 dark:text-dark-tx-2">
                                Nicht im Jahresverlaufsplan: {ohneLage.map((k) => k.titel).join(', ')}.
                            </p>
                        {/if}
                    </div>
                    {#if tafelRechts}
                        <aside class="sticky self-start overflow-y-auto rounded-lg border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2 p-3"
                               style="width: {TAFEL}px; top: {kopfHoehe - 8}px; max-height: calc(100vh - {kopfHoehe + (leisteUnten ? 220 : 110)}px)"
                               aria-label="Bezüge des Kapitels">
                            <button type="button" class="float-right {knopf}" onclick={() => { tafelZu = true; gewaehlt = null }}
                                    aria-label="Tafel schließen" title="Tafel schließen"><X class="w-3 h-3" /></button>
                            <VernetzungTafel {daten} {gewaehlt} {bezuege} {kapitelFach} {vergleich} onwaehle={waehleUndZeige} onmitte={inDieMitte} />
                        </aside>
                    {/if}
                </div>
            {/if}
        </div>
        {/if}
    </div>

    <!-- Unten: Tafel (wenn rechts kein Platz) und die Werkzeugleiste, sobald die obere weggescrollt ist -->
    {#if ansicht === 'zeitachse' && ((daten && gewaehlt && !tafelRechts && !tafelZu && !schalter.liste) || (daten && leisteUnten))}
        <div class="absolute bottom-0 inset-x-0 z-50 border-t border-light-ui-3 dark:border-dark-ui-3 bg-light-bg/95 dark:bg-dark-bg/95 backdrop-blur">
            {#if daten && gewaehlt && !tafelRechts && !tafelZu && !schalter.liste}
                <div class="max-h-[40vh] overflow-y-auto px-6 py-3 border-b border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2" aria-label="Bezüge des Kapitels">
                    <button type="button" class="float-right {knopf}" onclick={() => { tafelZu = true; gewaehlt = null }} aria-label="Tafel schließen"><X class="w-3 h-3" /></button>
                    <VernetzungTafel {daten} {gewaehlt} {bezuege} {kapitelFach} {vergleich} onwaehle={waehleUndZeige} onmitte={inDieMitte} />
                </div>
            {/if}
            {#if leisteUnten}
                <div class="px-6 py-2 space-y-2">
                    {@render werkzeuge('unten')}
                    {@render auswahl()}
                </div>
            {/if}
        </div>
    {/if}
</div>

{#if tipp}
    {@const f = faecherJe[tipp.k.fach_id]}
    <div class="fixed z-[60] pointer-events-none max-w-xs rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                px-2 py-1 text-xs shadow text-light-tx dark:text-dark-tx"
         style="left: {Math.min(tipp.x + 14, window.innerWidth - 300)}px; top: {tipp.y + 14}px" role="tooltip">
        <div class="font-semibold">{tipp.k.titel}</div>
        <div class="text-light-tx-2 dark:text-dark-tx-2">{f?.name}</div>
        <div class="text-light-tx-2 dark:text-dark-tx-2">
            {#each tipp.k.lage as l, i (i)}
                {i ? ' und ' : ''}Kl. {l.stufe}{stufenJe[l.stufe]?.kalenderwochen ? `, KW ${stufenJe[l.stufe].kalenderwochen[l.von_woche - 1]}–${stufenJe[l.stufe].kalenderwochen[l.bis_woche - 1]}` : `, Woche ${l.von_woche}–${l.bis_woche}`}
            {/each}
            {#if tipp.k.lage.some((l) => l.quelle === 'geschaetzt')} (geschätzt){:else if tipp.k.lage.some((l) => l.quelle === 'entwurf')} (Plan-Entwurf){/if}
        </div>
    </div>
{/if}
