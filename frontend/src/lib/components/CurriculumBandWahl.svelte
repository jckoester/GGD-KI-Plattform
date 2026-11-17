<script>
    /**
     * Band des Bildungsplans für Curricula der Oberstufe (0.46, Schritt 8).
     *
     * Erscheint nur, wenn die Stufen des Curriculums mehrere Bänder berühren (Basis- und
     * Leistungsfach, Physik zwei Basisfach-Schwerpunkte). Im Editor eine Auswahl, die
     * `metadata.band` setzt (gespeichert mit dem Curriculum); in der Ansicht das gewählte Band
     * oder der Hinweis, dass noch keines gewählt ist.
     */
    import { getCurriculumBand } from "$lib/api.js";

    let { curriculumId, wert = null, editMode = false, onchange = null } = $props();

    let wahl = $state([]);
    $effect(() => {
        if (!curriculumId) return;
        let abgebrochen = false;
        getCurriculumBand(curriculumId)
            .then((b) => { if (!abgebrochen) wahl = b.baender_zur_wahl ?? []; })
            .catch(() => { if (!abgebrochen) wahl = []; });
        return () => { abgebrochen = true; };
    });

    const gueltig = $derived(wahl.some((b) => b.schluessel === wert) ? wert : "");
</script>

{#if wahl.length > 1}
    <div class="mb-3 flex flex-wrap items-center gap-2 text-sm" data-abschnitt="band">
        <span class="text-light-tx-2 dark:text-dark-tx-2">Band im Bildungsplan:</span>
        {#if editMode}
            <select
                value={gueltig}
                onchange={(e) => onchange?.(e.currentTarget.value || null)}
                class="px-2 py-1 rounded-md border border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                       text-light-tx dark:text-dark-tx"
            >
                <option value="">– nicht gewählt –</option>
                {#each wahl as b (b.schluessel)}
                    <option value={b.schluessel}>{b.schluessel}</option>
                {/each}
            </select>
        {:else if gueltig}
            <span class="text-light-tx dark:text-dark-tx">{gueltig}</span>
        {:else}
            <span class="text-light-ye dark:text-dark-ye">nicht gewählt — die Abdeckung zählt alle Bänder dieser Stufen</span>
        {/if}
    </div>
{/if}
