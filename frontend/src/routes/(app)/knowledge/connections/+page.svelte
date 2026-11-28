<script>
    /**
     * Vernetzung der Fächer (BE, Teil A, Schritt 5): ein Fach in der Mitte einer Zeitachse über
     * die Stufen, die vernetzten Fächer als Spuren daneben (Plan `Vernetzung-Zeitachse-BE-Plan`).
     * Nur für Lehrkräfte. Zustand in der Adresse (`?fach=&kapitel=&schuljahr=&weg=&stufe=&entwuerfe=1`),
     * die gewählten Spuren je Fach in den Einstellungen (`vernetzung_spuren`).
     */
    import { goto } from '$app/navigation'
    import { page } from '$app/stores'
    import { tick } from 'svelte'
    import { Plus, X } from '@lucide/svelte'
    import { getPreferences, getVernetzung, patchPreferences } from '$lib/api.js'
    import { pageTitle } from '$lib/stores/pageTitle.js'
    import { subjects } from '$lib/stores/subjects.js'
    import { user, userHasAnyRole } from '$lib/stores/user.js'
    import { fachToenung } from '$lib/absprachen.js'
    import {
        SPUREN_SCHLUESSEL, STIL, achse, adresse, ausAdresse, bloecke, gemerkteSpuren, naechstesSchuljahr, spalten,
        spurenWaehlen,
    } from '$lib/zeitachse.js'
    import FachWahl from '$lib/components/FachWahl.svelte'
    import SubjectIcon from '$lib/components/SubjectIcon.svelte'
    import ZurueckLink from '$lib/components/ZurueckLink.svelte'
    import LoadingBanner from '$lib/components/LoadingBanner.svelte'
    import ErrorBanner from '$lib/components/ErrorBanner.svelte'
    import VernetzungZeitachse from '$lib/components/VernetzungZeitachse.svelte'
    import VernetzungTafel from '$lib/components/VernetzungTafel.svelte'
    import VernetzungListe from '$lib/components/VernetzungListe.svelte'

    pageTitle.set('Vernetzung der Fächer')

    $effect(() => {
        if ($user && !userHasAnyRole($user, ['teacher', 'admin'])) goto('/chat')
    })

    const start = ausAdresse($page.url.searchParams)
    let zustand = $state(start)
    let gewaehlt = $state(start.kapitel)
    let daten = $state(null)
    let fehler = $state(null)
    let laedt = $state(false)
    let einstellungen = $state({})
    let wahl = $state(null)          // gewählte Spuren (Kennungen); null = gemerkt oder Vorgabe
    let schalter = $state({ querverweise: true, bereiche: false, alle: false, leitlinien: true, liste: false })
    let breite = $state(1000)
    let kopfHoehe = $state(0)
    let scroller = $state(null)
    let tipp = $state(null)
    let sprungZiel = $state(start.kapitel ? { kapitel: start.kapitel } : start.stufe ? { stufe: start.stufe } : null)

    getPreferences().then((e) => (einstellungen = e ?? {}))

    // Laden, wenn Fach oder Zeitraum wechseln
    $effect(() => {
        const { fach, schuljahr, weg, entwuerfe } = zustand
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
    const lay = $derived(spalten(breite, kandidaten, { leitlinien: schalter.leitlinien }))
    const genutzt = $derived(lay.genutzt)
    const spurIds = $derived(new Set(genutzt.map((f) => f.id)))
    const weitere = $derived((daten?.faecher ?? []).filter((f) => !spurIds.has(f.id)))
    const bereicheAn = $derived(schalter.bereiche || genutzt.some((f) => f.nur_bereich))
    const a = $derived(achse(daten?.stufen ?? []))
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
        if (!code || code === fachCode) return
        zustand = { ...zustand, fach: code, weg: null }
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
    }
    function waehleUndZeige(id) {
        gewaehlt = id
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
        if (!e || !k) { tipp = null; return }
        const rect = e.currentTarget?.getBoundingClientRect?.()
        const x = e.clientX ?? (rect ? rect.right : 0)
        const y = e.clientY ?? (rect ? rect.top : 0)
        tipp = { x, y, k }
    }

    function taste(e) {
        if (e.key === 'Escape' && gewaehlt) gewaehlt = null
    }

    const knopf = 'inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium border border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'
    const feld = 'text-sm rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx px-2 py-1'
    const faecherJe = $derived(daten ? Object.fromEntries([[daten.fach.id, daten.fach], ...daten.faecher.map((f) => [f.id, f])]) : {})
    const stufenJe = $derived(Object.fromEntries((daten?.stufen ?? []).map((s) => [s.stufe, s])))
</script>

<svelte:window onkeydown={taste} />

{#snippet linie(s, rot = false)}
    <svg width="30" height="10" aria-hidden="true" class={rot ? 'text-light-re dark:text-dark-re' : s.strich ? 'text-light-tx-2 dark:text-dark-tx-2' : 'text-light-tx dark:text-dark-tx'}>
        <path d="M1,5 L29,5" stroke="currentColor" stroke-width={s.breite} stroke-dasharray={s.strich ?? undefined} />
    </svg>
{/snippet}

<div class="h-full overflow-y-auto bg-light-bg dark:bg-dark-bg" bind:this={scroller}>
    <!-- Kopf: rastet ein (Befund 5) -->
    <div class="sticky top-0 z-40 bg-light-bg dark:bg-dark-bg border-b border-light-ui-3 dark:border-dark-ui-3" bind:clientHeight={kopfHoehe}>
        <div class="px-4 pt-3 pb-2 space-y-2">
            <div class="flex flex-wrap items-end gap-x-5 gap-y-2">
                <div>
                    <ZurueckLink href="/knowledge" label="Bibliothek" />
                    <h1 class="text-xl font-bold text-light-tx dark:text-dark-tx">Vernetzung der Fächer</h1>
                </div>
                <div class="w-56 text-xs text-light-tx-2 dark:text-dark-tx-2">
                    <label for="vernetzung-fach">Fach in der Mitte</label>
                    <FachWahl id="vernetzung-fach" faecher={faecherAuswahl} wert={fachCode} onwahl={fachWaehlen} />
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
                                {#each daten.stufen as s (s.stufe)}<option value={s.stufe}>Kl. {s.stufe} ist</option>{/each}
                            </select>
                        </label>
                    {/if}
                    <div class="flex flex-wrap items-center gap-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
                        Springe zu
                        {#each daten.stufen as s (s.stufe)}
                            <button type="button" class={knopf} onclick={() => zuStufe(s.stufe)}>Kl. {s.stufe}</button>
                        {/each}
                    </div>
                {/if}
            </div>
            {#if daten}
                <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
                    <label class="inline-flex items-center gap-1"><input type="checkbox" bind:checked={schalter.querverweise} /> Querverweise des Bildungsplans</label>
                    <label class="inline-flex items-center gap-1"><input type="checkbox" bind:checked={schalter.bereiche} disabled={!schalter.querverweise} /> auch Bezüge auf ganze Bereiche</label>
                    <label class="inline-flex items-center gap-1"><input type="checkbox" bind:checked={schalter.alle} /> alle Linien zeigen</label>
                    <label class="inline-flex items-center gap-1"><input type="checkbox" bind:checked={schalter.leitlinien} /> Leitlinien und Leitperspektiven</label>
                    <label class="inline-flex items-center gap-1"><input type="checkbox" checked={zustand.entwuerfe}
                           onchange={(e) => (zustand = { ...zustand, entwuerfe: e.target.checked })} /> mit Entwürfen</label>
                    <label class="inline-flex items-center gap-1"><input type="checkbox" bind:checked={schalter.liste} /> als Liste</label>
                </div>
                <!-- Legende der Linienarten -->
                <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-light-tx-2 dark:text-dark-tx-2" aria-label="Legende der Linien">
                    <span class="inline-flex items-center gap-1">{@render linie(STIL.absprache)} Absprache</span>
                    <span class="inline-flex items-center gap-1">{@render linie(STIL.absprache, true)} nicht eingehalten</span>
                    <span class="inline-flex items-center gap-1">{@render linie(STIL.kompetenz)} Querverweis</span>
                    {#if bereicheAn}<span class="inline-flex items-center gap-1">{@render linie(STIL.bereich)} über einen Bereich</span>{/if}
                    <span class="inline-flex items-center gap-1">
                        <svg width="22" height="14" aria-hidden="true"><path d="M20,2 H8 Q4,2 4,6 V8 Q4,12 8,12 H20" fill="none" stroke={daten.fach.color ?? 'currentColor'} stroke-width="2" /></svg>
                        im eigenen Fach (Pfeil zum späteren Kapitel)
                    </span>
                    <span class="text-light-tx-2 dark:text-dark-tx-2">
                        {#if zustand.weg != null}
                            · Weg der Klasse, die {aktuelles} in Kl. {zustand.weg} ist — jede Stufe mit dem Plan ihres Schuljahrs.
                        {:else}
                            · Jede Stufe auf dem Jahresverlaufsplan {zustand.schuljahr ?? aktuelles}: die Ansicht zeigt den Aufbau der Curricula, nicht den Weg einer Klasse.
                        {/if}
                    </span>
                </div>
            {/if}
        </div>
        <!-- Spaltenköpfe, ausgerichtet wie die Zeitachse -->
        {#if daten && !schalter.liste && daten.stufen.length}
            <div class="flex gap-4 px-4 pb-1.5">
                <div class="relative flex-1 min-w-0 h-7">
                    {#if lay.spalten.leitlinien}
                        <span class="absolute top-1.5 text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 text-center"
                              style="left: {lay.spalten.leitlinien.x}px; width: {lay.spalten.leitlinien.b}px">Leitlinien</span>
                        <span class="absolute top-1.5 text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 text-center"
                              style="left: {lay.spalten.leitperspektiven.x}px; width: {lay.spalten.leitperspektiven.b}px">Leitperspektiven</span>
                    {/if}
                    <span class="absolute top-0.5 flex justify-center" style="left: {lay.spalten.mitte.x}px; width: {lay.spalten.mitte.b}px">
                        <span class="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-semibold text-light-tx dark:text-dark-tx"
                              style={fachToenung(daten.fach.color)}>
                            <SubjectIcon name={daten.fach.icon} size={13} color={daten.fach.color} />{daten.fach.name}
                        </span>
                    </span>
                    {#each genutzt as f (f.id)}
                        {@const s = lay.spalten[f.id]}
                        <span class="absolute top-0.5 flex justify-center" style="left: {s.x}px; width: {s.b}px">
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
                        <span class="absolute top-0.5" style="left: 0">
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
                <div class="hidden lg:block w-80 shrink-0"></div>
            </div>
        {/if}
    </div>

    <div class="flex gap-4 px-4 pt-3 pb-12">
        <div class="flex-1 min-w-0" bind:clientWidth={breite}>
            {#if fehler}
                <ErrorBanner message={fehler} />
            {:else if laedt && !daten}
                <LoadingBanner />
            {:else if !zustand.fach}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 max-w-xl">
                    Wähle ein Fach. Es steht dann in der Mitte, über alle Klassenstufen, für die es ein Curriculum hat; daneben
                    die Fächer, mit denen es über Absprachen oder den Bildungsplan verbunden ist.
                </p>
            {:else if daten && !daten.stufen.length}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                    Für {daten.fach.name} gibt es {zustand.entwuerfe ? 'kein Curriculum' : 'kein veröffentlichtes Curriculum'}.
                    {#if !zustand.entwuerfe}Mit „mit Entwürfen“ siehst du auch Curricula, die noch entstehen.{/if}
                </p>
            {:else if daten && schalter.liste}
                <VernetzungListe {daten} {bezuege} {kapitelFach} {vergleich} onwaehle={waehle} />
            {:else if daten}
                {#if lay.mobil}
                    <p class="mb-2 text-xs text-light-tx-2 dark:text-dark-tx-2">Auf diesem schmalen Bildschirm steht nur das Fach in der Mitte; die Bezüge stehen beim gewählten Kapitel.</p>
                {/if}
                <div class={laedt ? 'opacity-60' : ''}>
                    <VernetzungZeitachse {daten} {lay} {a} {je} {bezuege} {kapitelFach} {spurIds} {gewaehlt}
                                         alle={schalter.alle} onwaehle={waehle} ontipp={zeigeTipp} />
                </div>
                {#if ohneLage.length}
                    <p class="mt-3 text-xs text-light-tx-2 dark:text-dark-tx-2">
                        Nicht im Jahresverlaufsplan: {ohneLage.map((k) => k.titel).join(', ')}.
                    </p>
                {/if}
            {/if}
        </div>
        {#if daten && daten.stufen.length}
            <aside class="hidden lg:block w-80 shrink-0 sticky self-start overflow-y-auto rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                          bg-light-bg-2 dark:bg-dark-bg-2 p-3"
                   style="top: {kopfHoehe + 12}px; max-height: calc(100vh - {kopfHoehe + 100}px)" aria-label="Bezüge des Kapitels">
                <VernetzungTafel {daten} {gewaehlt} {bezuege} {kapitelFach} {vergleich} onwaehle={waehleUndZeige} onmitte={inDieMitte} />
            </aside>
        {/if}
    </div>

    {#if daten && gewaehlt}
        <aside class="lg:hidden fixed bottom-0 inset-x-0 z-50 max-h-[45vh] overflow-y-auto border-t border-light-ui-3 dark:border-dark-ui-3
                      bg-light-bg-2 dark:bg-dark-bg-2 p-3" aria-label="Bezüge des Kapitels">
            <button type="button" class="float-right {knopf}" onclick={() => (gewaehlt = null)} aria-label="Schließen"><X class="w-3 h-3" /></button>
            <VernetzungTafel {daten} {gewaehlt} {bezuege} {kapitelFach} {vergleich} onwaehle={waehleUndZeige} onmitte={inDieMitte} />
        </aside>
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
