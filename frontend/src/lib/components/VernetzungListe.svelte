<script>
    /**
     * Die Vernetzung als Liste (BE, Teil A, Schritt 5, F9): je Stufe die Kapitel des Fachs in der
     * Mitte mit ihren Bezügen als Text — ohne Grafik, zum Lesen und für den Screenreader. Die Sätze
     * baut `liste()` in `$lib/zeitachse.js`; dieselben stehen im PDF (Schritt 7).
     *
     * Props: daten, bezuege (aktive), onwaehle(id)
     */
    import { fassungKurz, lageQuelleText, liste } from '$lib/zeitachse.js'

    let { daten, bezuege, onwaehle = () => {} } = $props()

    const l = $derived(liste(daten, bezuege))
</script>

<div class="space-y-6 text-sm">
    {#each l.stufen as { stufe: s, kapitel } (s.stufe)}
        <section aria-labelledby="liste-stufe-{s.stufe}">
            <h2 id="liste-stufe-{s.stufe}" class="font-semibold text-light-tx dark:text-dark-tx">
                Klasse {s.stufe}
                <span class="font-normal text-xs text-light-tx-2 dark:text-dark-tx-2">
                    {s.schuljahr}{#if s.fassung} · Bildungsplan {fassungKurz(s.fassung)}{/if} · {lageQuelleText(s)}
                </span>
            </h2>
            <ol class="mt-2 space-y-2">
                {#each kapitel as k (k.id)}
                    <li class="rounded border border-light-ui-3 dark:border-dark-ui-3 px-3 py-2">
                        <button type="button" class="font-medium text-light-tx dark:text-dark-tx hover:underline text-left"
                                onclick={() => onwaehle(k.id)}>{k.titel}</button>
                        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2"> · {k.lage}</span>
                        {#if k.zeilen.length}
                            <ul class="mt-1 space-y-0.5 text-xs text-light-tx-2 dark:text-dark-tx-2 list-disc pl-4">
                                {#each k.zeilen as zeile, i (i)}<li>{zeile}</li>{/each}
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
    {#if l.ohne_lage.length}
        <section>
            <h2 class="font-semibold text-light-tx dark:text-dark-tx">Nicht im Jahresverlaufsplan</h2>
            <ul class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2 list-disc pl-4">
                {#each l.ohne_lage as t, i (i)}<li>{t}</li>{/each}
            </ul>
        </section>
    {/if}
</div>
