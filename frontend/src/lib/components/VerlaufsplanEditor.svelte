<script>
    /**
     * Editor der Abschnitte eines Jahresverlaufsplans (BD, Schritt 5).
     *
     * Jede Zeile ist ein Abschnitt: Dauer in Unterrichtswochen, Thema, Kapitel, Notiz. Die Lage im
     * Kalender kommt vom Server nach dem Speichern (`lage`); die Seite speichert jede Änderung
     * kurz verzögert selbst. Umstellen per Ziehen oder mit den Pfeilknöpfen (Tastatur).
     *
     * Props:
     * - `abschnitte` (bindable): die Zeilen in Planreihenfolge
     * - `raster`: Blocklänge für neue Zeilen
     * - `lage`: Lage der zuletzt gespeicherten Fassung, oder null ohne Kalender
     * - `curricula`: Curricula der Stufe mit Kapiteln, zur Auswahl
     * - `onaenderung`: nach jeder Änderung
     */
    import { ArrowDown, ArrowUp, GripVertical, Trash2, Plus } from 'lucide-svelte'
    import {
        RICHTGROESSE, hinweise, neuerAbschnitt, umsetzen, verschieben, wochenBisZuDenFerien,
        wochenText, zeitraumText,
    } from '$lib/verlaufsplan.js'

    let { abschnitte = $bindable([]), raster = 1, lage = null, curricula = [], onaenderung = () => {} } = $props()

    const kapitelTitel = $derived(Object.fromEntries(
        curricula.flatMap((c) => c.kapitel.map((k) => [k.id, k.titel]))))

    function neueId() {
        return (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}${Math.random()}`).replace(/-/g, '').slice(0, 12)
    }

    function setzen(neu) {
        abschnitte = neu
        onaenderung()
    }

    function aendern(i, feld, wert) {
        setzen(abschnitte.map((a, k) => (k === i ? { ...a, [feld]: wert } : a)))
    }

    function kapitelUmschalten(i, id) {
        const ids = abschnitte[i].kapitel_ids ?? []
        aendern(i, 'kapitel_ids', ids.includes(id) ? ids.filter((k) => k !== id) : [...ids, id])
    }

    function hinzufuegen() {
        setzen([...abschnitte, { ...neuerAbschnitt(raster), id: neueId() }])
    }

    function bisZuDenFerien(i) {
        const l = lage?.abschnitte?.[i]
        const w = l && wochenBisZuDenFerien(l.von_woche, lage.ferienabschnitte)
        if (w) aendern(i, 'wochen', w)
    }

    // Ziehen
    let gezogen = $state(null)
    function fallenlassen(i) {
        if (gezogen != null) setzen(umsetzen(abschnitte, gezogen, i))
        gezogen = null
    }

    const feld = 'rounded border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg px-2 py-1 text-sm text-light-tx dark:text-dark-tx'
    const knopf = 'p-1 rounded text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-30'
</script>

<datalist id="verlaufsplan-wochen">
    {#each Array.from({ length: RICHTGROESSE }, (_, k) => k + 1) as w (w)}<option value={w}></option>{/each}
</datalist>

<ol class="space-y-2" aria-label="Abschnitte">
    {#each abschnitte as a, i (a.id ?? i)}
        {@const l = lage?.abschnitte?.[i]}
        <li
            class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2 p-2
                   {gezogen === i ? 'opacity-50' : ''}"
            draggable="true"
            ondragstart={() => (gezogen = i)}
            ondragend={() => (gezogen = null)}
            ondragover={(e) => e.preventDefault()}
            ondrop={(e) => { e.preventDefault(); fallenlassen(i) }}
        >
            <div class="flex flex-wrap items-center gap-2">
                <span class="cursor-grab text-light-tx-2 dark:text-dark-tx-2" aria-hidden="true"><GripVertical size={16} /></span>
                <span class="w-6 text-sm font-medium text-light-tx-2 dark:text-dark-tx-2">{i + 1}.</span>
                <label class="flex items-center gap-1 text-sm text-light-tx-2 dark:text-dark-tx-2">
                    <input
                        type="number" min="1" max="45" list="verlaufsplan-wochen"
                        class="{feld} w-16" value={a.wochen}
                        aria-label="Dauer von Abschnitt {i + 1} in Wochen"
                        onchange={(e) => aendern(i, 'wochen', Math.max(1, Math.min(45, Number(e.currentTarget.value) || 1)))}
                    />
                    Wo.
                </label>
                <input
                    type="text" maxlength="200" placeholder="Thema"
                    class="{feld} flex-1 min-w-[12rem]" value={a.titel}
                    aria-label="Thema von Abschnitt {i + 1}"
                    oninput={(e) => aendern(i, 'titel', e.currentTarget.value)}
                />
                <button type="button" class="{knopf} text-xs px-2 border border-light-ui-3 dark:border-dark-ui-3"
                    disabled={!lage || !l?.beginn}
                    title="Abschnitt an den nächsten Ferien enden lassen"
                    onclick={() => bisZuDenFerien(i)}>bis zu den Ferien</button>
                <button type="button" class={knopf} disabled={i === 0} aria-label="Abschnitt {i + 1} nach oben"
                    onclick={() => setzen(verschieben(abschnitte, i, -1))}><ArrowUp size={16} /></button>
                <button type="button" class={knopf} disabled={i === abschnitte.length - 1} aria-label="Abschnitt {i + 1} nach unten"
                    onclick={() => setzen(verschieben(abschnitte, i, 1))}><ArrowDown size={16} /></button>
                <button type="button" class={knopf} aria-label="Abschnitt {i + 1} entfernen"
                    onclick={() => setzen(abschnitte.filter((_, k) => k !== i))}><Trash2 size={16} /></button>
            </div>

            <div class="mt-1 ml-14 text-xs text-light-tx-2 dark:text-dark-tx-2">
                {#if l}
                    {wochenText(l)}{#if zeitraumText(l)} · {zeitraumText(l)}{/if}
                    {#each hinweise(l) as h (h)} · <span class={h.startsWith('länger') || h.includes('nach Schuljahresende') ? 'text-light-or dark:text-dark-or' : ''}>{h}</span>{/each}
                {/if}
            </div>

            <div class="mt-2 ml-14 flex flex-wrap gap-2 items-start">
                <details class="text-sm">
                    <summary class="cursor-pointer text-light-bl dark:text-dark-bl">
                        Kapitel{#if a.kapitel_ids?.length}: {a.kapitel_ids.map((k) => kapitelTitel[k] ?? 'nicht mehr im Curriculum').join(', ')}{:else} wählen{/if}
                    </summary>
                    {#if curricula.length === 0}
                        <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">Für diese Stufe gibt es kein veröffentlichtes Curriculum.</p>
                    {/if}
                    {#each curricula as c (c.id)}
                        <fieldset class="mt-1">
                            <legend class="text-xs font-medium text-light-tx-2 dark:text-dark-tx-2">{c.titel}</legend>
                            {#each c.kapitel as k (k.id)}
                                <label class="flex items-center gap-2 text-sm text-light-tx dark:text-dark-tx">
                                    <input type="checkbox" checked={a.kapitel_ids?.includes(k.id)}
                                        onchange={() => kapitelUmschalten(i, k.id)} />
                                    {k.titel}{#if k.std != null}<span class="text-xs text-light-tx-2 dark:text-dark-tx-2">({k.std} Std.)</span>{/if}
                                </label>
                            {/each}
                        </fieldset>
                    {/each}
                </details>
                <input
                    type="text" maxlength="2000" placeholder="Notiz"
                    class="{feld} flex-1 min-w-[12rem] text-xs" value={a.notiz}
                    aria-label="Notiz zu Abschnitt {i + 1}"
                    oninput={(e) => aendern(i, 'notiz', e.currentTarget.value)}
                />
            </div>
        </li>
    {/each}
</ol>

<button type="button" onclick={hinzufuegen}
    class="mt-3 inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
           text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2">
    <Plus size={16} /> Abschnitt
</button>
