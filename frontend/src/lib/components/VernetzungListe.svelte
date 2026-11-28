<script>
    /**
     * Die Vernetzung als Liste (BE, Teil A, Schritt 5, F9): je Stufe die Kapitel des Fachs in der
     * Mitte mit ihren Bezügen als Text — ohne Grafik, zum Lesen, für den Screenreader und als
     * Vorlage der Liste im PDF (Schritt 7).
     *
     * Props: daten, bezuege (aktive), kapitelFach, vergleich(a, b), onwaehle(id)
     */
    import { ART_SATZ, pruefungText } from '$lib/absprachen.js'
    import { bezuegeDesKapitels, fassungKurz, lageQuelleText, lageText } from '$lib/zeitachse.js'

    let { daten, bezuege, kapitelFach, vergleich, onwaehle = () => {} } = $props()

    const faecherJe = $derived(Object.fromEntries([[daten.fach.id, daten.fach], ...daten.faecher.map((f) => [f.id, f])]))
    const faecherCode = $derived(Object.fromEntries(Object.values(faecherJe).map((f) => [f.code, f])))
    const kapitelJe = $derived(new Map(daten.kapitel.map((k) => [k.id, k])))
    const stufenJe = $derived(Object.fromEntries(daten.stufen.map((s) => [s.stufe, s])))
    const jeStufe = $derived(daten.stufen.map((s) => ({
        s,
        kapitel: daten.kapitel
            .filter((k) => k.fach_id === daten.fach.id && (k.lage[0]?.stufe ?? null) === s.stufe)
            .sort((x, y) => (x.lage[0]?.von_woche ?? 0) - (y.lage[0]?.von_woche ?? 0)),
    })))
    const ohneLage = $derived(daten.kapitel.filter((k) => k.fach_id === daten.fach.id && !k.lage.length))

    function anderes(id) {
        const k = kapitelJe.get(id)
        return `${faecherJe[k?.fach_id]?.name ?? ''}: ${k?.titel ?? '?'} (${lageText(k, stufenJe)})`
    }
    function zeilen(id) {
        const g = bezuegeDesKapitels({ ...daten, bezuege }, id, { kapitelFach, vergleich, bereiche: true })
        return [
            ...g.absprachen.map((b) => `Absprache — ${anderes(b.ander)} ${ART_SATZ[b.art_hier] ?? b.art_hier}`
                + `${b.texte.filter(Boolean).length ? `: ${b.texte.filter(Boolean).join(' / ')}` : ''}`
                + `${pruefungText(b.pruefung) ? ` ${pruefungText(b.pruefung)}` : ''}`),
            ...g.fach.map((f) => `Absprache — ${faecherCode[f.fach_code]?.name ?? f.fach_code}: ${f.kapitel_titel ?? 'ganzes Fach'}${f.text ? `: ${f.text}` : ''}`),
            ...g.fremd.map((b) => `Bildungsplan — ${anderes(b.ander)}${b.typ === 'bereich' ? ', über einen Bereich' : ''} (${b.beispiele.join(', ')})`),
            ...g.baut_auf.map((b) => `Baut auf — ${anderes(b.ander)}`),
            ...g.aufgegriffen.map((b) => `Wird aufgegriffen in — ${anderes(b.ander)}`),
            ...(daten.leitlinien?.[id] ?? []).map((l) => `${l.art === 'll' ? 'Leitlinie' : 'Leitperspektive'} — ${l.titel}${l.aspekte.length ? ` (${l.aspekte.join(', ')})` : ''}`),
        ]
    }
</script>

<div class="space-y-6 text-sm">
    {#each jeStufe as { s, kapitel } (s.stufe)}
        <section aria-labelledby="liste-stufe-{s.stufe}">
            <h2 id="liste-stufe-{s.stufe}" class="font-semibold text-light-tx dark:text-dark-tx">
                Klasse {s.stufe}
                <span class="font-normal text-xs text-light-tx-2 dark:text-dark-tx-2">
                    {s.schuljahr}{#if s.fassung} · Bildungsplan {fassungKurz(s.fassung)}{/if} · {lageQuelleText(s)}
                </span>
            </h2>
            <ol class="mt-2 space-y-2">
                {#each kapitel as k (k.id)}
                    {@const z = zeilen(k.id)}
                    <li class="rounded border border-light-ui-3 dark:border-dark-ui-3 px-3 py-2">
                        <button type="button" class="font-medium text-light-tx dark:text-dark-tx hover:underline text-left"
                                onclick={() => onwaehle(k.id)}>{k.titel}</button>
                        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2"> · {lageText(k, stufenJe)}</span>
                        {#if z.length}
                            <ul class="mt-1 space-y-0.5 text-xs text-light-tx-2 dark:text-dark-tx-2 list-disc pl-4">
                                {#each z as zeile, i (i)}<li>{zeile}</li>{/each}
                            </ul>
                        {:else}
                            <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">keine Bezüge</p>
                        {/if}
                    </li>
                {:else}
                    <li class="text-xs text-light-tx-2 dark:text-dark-tx-2">Keine Kapitel {daten.fach.name} in dieser Stufe.</li>
                {/each}
            </ol>
        </section>
    {/each}
    {#if ohneLage.length}
        <section>
            <h2 class="font-semibold text-light-tx dark:text-dark-tx">Nicht im Jahresverlaufsplan</h2>
            <ul class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2 list-disc pl-4">
                {#each ohneLage as k (k.id)}<li>{k.titel}</li>{/each}
            </ul>
        </section>
    {/if}
</div>
