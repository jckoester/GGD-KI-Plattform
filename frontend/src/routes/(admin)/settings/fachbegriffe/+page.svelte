<script>
    /**
     * Fachbegriffe in **jedes** Fach einspielen (Admin, 0.15.2).
     *
     * Auf der Fachseite importiert nur die Fachschaft, und nur in ihr Fach — ein
     * Bezugsfach soll dem Leitfach nicht in die Definitionen schreiben. Diese Seite ist
     * der Weg für alles andere: ein Fach, in dessen Fachschaft niemand ist, oder eines
     * ganz ohne Fachschaftsgruppe. Dann ändern die Einträge vorerst nur Admins; ein
     * erneuter Import hängt sie an die Fachschaft, sobald es eine gibt.
     *
     * **Das Fach kommt aus der Datei** (`ausDatei`): Ein Lauf darf Dateien mehrerer Fächer
     * enthalten, und die Vorschau nennt je Datei, wohin sie geht. Die Fachauswahl ist nur
     * die Vorgabe für Dateien ohne `fach:` — ohne sie werden die übersprungen; fachlose
     * Begriffe entstehen nicht. Daneben wählt sie, welches Fach die Liste und „Als Zip"
     * zeigen.
     */
    import { onMount } from "svelte";
    import { ArrowLeft, BookOpen, Download, Upload } from "lucide-svelte";
    import KnowledgeNodeList from "$lib/components/KnowledgeNodeList.svelte";
    import FachbegriffImportDialog from "$lib/components/FachbegriffImportDialog.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import { subjects, refreshSubjects } from "$lib/stores/subjects.js";
    import { exportiereFachbegriffe } from "$lib/api.js";
    import { BP_CURRICULUM_CONTENT_TYPES } from "$lib/taxonomy.js";

    let slug = $state("");
    const fach = $derived($subjects.find((s) => s.slug === slug) ?? null);

    let importDialog = $state(false);
    let exportLaeuft = $state(false);
    let fehler = $state(null);
    // Nach einem Import neu laden — die Liste lädt beim Einhängen.
    let stand = $state(0);

    onMount(() => {
        if ($subjects.length === 0) refreshSubjects();
    });

    async function exportieren() {
        exportLaeuft = true;
        fehler = null;
        try {
            await exportiereFachbegriffe(fach.slug);
        } catch (e) {
            fehler = e.message;
        } finally {
            exportLaeuft = false;
        }
    }
</script>

<div class="max-w-5xl mx-auto p-6">
    <a
        href="/settings"
        class="inline-flex items-center gap-2 text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4"
    >
        <ArrowLeft class="w-4 h-4" /> Einstellungen
    </a>

    <h1 class="text-xl font-semibold text-light-tx dark:text-dark-tx mb-2 flex items-center gap-2">
        <BookOpen class="w-5 h-5" /> Fachbegriffe
    </h1>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-6 max-w-prose">
        Fachbegriffe und Stoffsteckbriefe in jedes Fach einspielen und wieder herausholen —
        auch in eines, in dessen Fachschaft du nicht bist. Jede Datei geht in das Fach, das
        sie unter <code>fach:</code> nennt; die Vorschau zeigt es je Datei. Dateien ohne
        Angabe gehen in das gewählte Fach, ist keines gewählt, werden sie übersprungen. Hat
        ein Fach keine Fachschaftsgruppe, ändern die Einträge vorerst nur Admins; gibt es
        eine, hängt ein erneuter Import sie an die Fachschaft.
    </p>

    <div class="flex flex-wrap items-end gap-3">
        <div>
            <label
                for="fachbegriffe-fach"
                class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-2"
            >
                Fach (für Liste und Export, Vorgabe beim Einspielen)
            </label>
            <select
                id="fachbegriffe-fach"
                bind:value={slug}
                class="w-full max-w-sm px-3 py-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx
                       focus:outline-none focus:ring-2 focus:ring-primary"
            >
                <option value="">— kein Fach —</option>
                {#each $subjects as s (s.slug)}
                    <option value={s.slug}>{s.name}</option>
                {/each}
            </select>
        </div>
        <button
            onclick={() => (importDialog = true)}
            class="px-3 py-2 text-sm rounded-md border border-light-ui-3
                   dark:border-dark-ui-3 text-light-tx dark:text-dark-tx
                   whitespace-nowrap inline-flex items-center gap-1.5"
        >
            <Upload size="16" /> Aus Dateien
        </button>
        <button
            onclick={exportieren}
            disabled={!fach || exportLaeuft}
            title={fach
                ? `Alle Fachbegriffe und Stoffsteckbriefe aus ${fach.name} als Zip`
                : "Erst ein Fach wählen"}
            class="px-3 py-2 text-sm rounded-md border border-light-ui-3
                   dark:border-dark-ui-3 text-light-tx dark:text-dark-tx
                   whitespace-nowrap inline-flex items-center gap-1.5 disabled:opacity-50"
        >
            <Download size="16" /> Als Zip
        </button>
    </div>

    {#if fehler}
        <div class="mt-4"><ErrorBanner message={fehler} /></div>
    {/if}

    {#if fach}
        <!-- Neu je Fach und nach jedem Import: Die Liste lädt beim Einhängen. -->
        {#key `${fach.slug}-${stand}`}
            <div class="mt-6">
                <KnowledgeNodeList
                    fixedSubjectSlug={fach.slug}
                    showSubjectFilter={false}
                    showNewButton={false}
                    excludeContentTypes={BP_CURRICULUM_CONTENT_TYPES}
                />
            </div>
        {/key}
    {/if}
</div>

{#if importDialog}
    <FachbegriffImportDialog
        ausDatei={true}
        fach={fach?.slug ?? null}
        fachname={fach?.name ?? null}
        onclose={() => (importDialog = false)}
        onfertig={() => (stand += 1)}
    />
{/if}
