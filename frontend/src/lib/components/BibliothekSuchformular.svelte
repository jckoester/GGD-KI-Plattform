<script>
    /**
     * Suchformular der Bibliothek: Suchfeld und die drei Facetten (Bausteinart, Fach, Stufe).
     *
     * Steht auf der Suchseite (`/knowledge/search`) und seit 0.48 auf der Übersicht der
     * Bibliothek (`/knowledge`). Ein Formular, zwei Orte — damit Facetten und Beschriftung
     * nicht auseinanderlaufen. Was beim Absenden geschieht, entscheidet die Seite
     * (`onsuchen`); `onfacette` läuft bei jeder Änderung einer Facette.
     */
    import { Loader2, Search } from "lucide-svelte";
    import { bibliothekTypLabels } from "$lib/knotentypen.js";
    import { STUDENT_GRADES } from "$lib/grades.js";
    import { subjects } from "$lib/stores/subjects.js";

    let {
        frage = $bindable(""),
        typ = $bindable(""),
        fachId = $bindable(""),
        stufe = $bindable(""),
        laeuft = false,
        onsuchen,
        onfacette = () => {},
    } = $props();

    const AUSWAHL =
        "pl-3 pr-9 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3 " +
        "bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx";
</script>

<form onsubmit={(e) => { e.preventDefault(); onsuchen(); }} class="space-y-3">
    <div class="flex gap-2">
        <input
            type="search"
            bind:value={frage}
            placeholder="Suchbegriff oder ganze Frage"
            aria-label="Suchbegriff"
            class="flex-1 px-3 py-2 rounded-lg text-sm
                   bg-light-bg-2 dark:bg-dark-bg-2
                   text-light-tx dark:text-dark-tx
                   border border-light-ui-3 dark:border-dark-ui-3"
        />
        <button
            type="submit"
            disabled={laeuft || !frage.trim()}
            class="px-4 py-2 rounded-lg text-sm bg-primary dark:bg-primary-dark text-white
                   hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed
                   flex items-center gap-2"
        >
            {#if laeuft}
                <Loader2 class="w-4 h-4 animate-spin" />
            {:else}
                <Search class="w-4 h-4" />
            {/if}
            Suchen
        </button>
    </div>

    <!-- Facetten: Verfeinerung des Ergebnisses, nicht Vorbedingung. Sie sind
         deshalb optional und lösen zusätzlich die gezählte Aufzählung aus. -->
    <div class="flex flex-wrap gap-2 text-sm">
        <select bind:value={typ} onchange={onfacette} aria-label="Bausteinart" class={AUSWAHL}>
            <option value="">Alle Bausteinarten</option>
            {#each bibliothekTypLabels(typ) as [wert, label] (wert)}
                <option value={wert}>{label}</option>
            {/each}
        </select>

        <select bind:value={fachId} onchange={onfacette} aria-label="Fach" class={AUSWAHL}>
            <option value="">Alle Fächer</option>
            {#each $subjects as fach (fach.id)}
                <option value={fach.id}>{fach.name}</option>
            {/each}
        </select>

        <select bind:value={stufe} onchange={onfacette} aria-label="Jahrgangsstufe" class={AUSWAHL}>
            <option value="">Alle Stufen</option>
            {#each STUDENT_GRADES as k (k)}
                <option value={k}>Klasse {k}</option>
            {/each}
        </select>
    </div>
</form>
