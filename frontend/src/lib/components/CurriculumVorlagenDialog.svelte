<script>
    /**
     * Curriculum-Vorlagen gesammelt einspielen (0.62, Päckchen BH) — nur Admins.
     *
     * Dateien wählen → *Prüfen* → Tabelle je Datei (Curriculum, Umfang, was entsteht, Fehler und
     * Warnungen) → *n Entwürfe anlegen* → Liste der Entwürfe mit Links. Immer Entwürfe; die
     * Fachschaften prüfen und veröffentlichen. Regeln in `$lib/curriculum_vorlagen.js`.
     *
     * Props: `onClose(angelegt)` — `angelegt` = Zahl der angelegten Entwürfe (zum Neuladen).
     */
    import { FilePlus, FileUp, Loader2 } from "@lucide/svelte";
    import { importiereCurriculumVorlagen, pruefeCurriculumVorlagen } from "$lib/api.js";
    import { summenText } from "$lib/curriculum_yaml_import.js";
    import { anlegenText, anzulegen, artText, dateienLesen, ergebnisText, MAX_DATEIEN } from "$lib/curriculum_vorlagen.js";
    import Dialog from "$lib/components/Dialog.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";

    let { onClose } = $props();

    let dateien = $state([]);
    let lesefehler = $state([]);
    let vorschau = $state(null);
    let ergebnis = $state(null);
    let fehler = $state(null);
    /** `null`, `"pruefen"` oder `"anlegen"`. */
    let vorgang = $state(null);
    const laeuft = $derived(vorgang !== null);

    const knopfText = $derived(anlegenText(vorschau?.zahlen));
    const angelegt = $derived(ergebnis?.zahlen?.ok ?? 0);

    async function gewaehlt(e) {
        const gelesen = await dateienLesen(e.target.files);
        dateien = gelesen.dateien;
        lesefehler = gelesen.fehler;
        vorschau = null;
        ergebnis = null;
        fehler = null;
        if (dateien.length) await pruefen();
    }

    async function pruefen() {
        vorgang = "pruefen";
        fehler = null;
        try {
            vorschau = await pruefeCurriculumVorlagen(dateien);
        } catch (e) {
            fehler = e.message;
        } finally {
            vorgang = null;
        }
    }

    async function anlegen() {
        vorgang = "anlegen";
        fehler = null;
        try {
            ergebnis = await importiereCurriculumVorlagen(anzulegen(dateien, vorschau));
        } catch (e) {
            fehler = e.message;
        } finally {
            vorgang = null;
        }
    }

    function schliessen() {
        onClose?.(angelegt);
    }

    const knopf = "px-3 py-1.5 rounded text-sm font-medium transition-colors disabled:opacity-50";
    const zelle = "px-2 py-1.5 align-top";
</script>

{#snippet meldungen(d)}
    {#if d.fehler?.length}
        <ul class="list-disc pl-4 text-xs text-light-re dark:text-dark-re">
            {#each d.fehler as f, i (i)}<li>{f}</li>{/each}
        </ul>
    {/if}
    {#if d.warnungen?.length}
        <details class="text-xs text-light-tx-2 dark:text-dark-tx-2">
            <summary class="cursor-pointer">{d.warnungen.length} {d.warnungen.length === 1 ? "Warnung" : "Warnungen"}</summary>
            <ul class="list-disc pl-4 mt-1">
                {#each d.warnungen as w, i (i)}<li>{w}</li>{/each}
            </ul>
        </details>
    {/if}
{/snippet}

<Dialog open onClose={schliessen} titelId="vorlagen-titel" breite="max-w-5xl max-h-[90vh] overflow-y-auto mx-4">
    <div class="space-y-4">
        <h2 id="vorlagen-titel" class="text-lg font-semibold text-light-tx dark:text-dark-tx">
            Curriculum-Vorlagen einspielen
        </h2>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Aus jeder Datei entsteht ein <strong>Entwurf</strong> im Fach, das in der Datei steht. Die
            Fachschaften prüfen ihn, passen ihn an und veröffentlichen ihn. Vorhandene Curricula bleiben
            unverändert; gibt es zur Stufe schon einen Entwurf, kommt ein weiterer mit dem Importdatum im
            Titel dazu. Höchstens {MAX_DATEIEN} Dateien je Durchgang.
        </p>

        {#if !ergebnis && !laeuft}
            <label class="inline-flex items-center gap-2 text-sm text-light-bl dark:text-dark-bl cursor-pointer">
                <FileUp class="w-4 h-4" />
                <span>{dateien.length ? "Andere Dateien wählen" : "Dateien wählen (.yaml)"}</span>
                <input type="file" multiple accept=".yaml,.yml,text/yaml" class="sr-only" onchange={gewaehlt} />
            </label>
        {/if}

        {#if lesefehler.length}
            <div class="space-y-1">
                <ErrorBanner message="Diese Dateien bleiben außen vor:" />
                <ul class="list-disc pl-6 text-sm text-light-re dark:text-dark-re">
                    {#each lesefehler as f, i (i)}<li>{f.name}: {f.fehler}</li>{/each}
                </ul>
            </div>
        {/if}

        {#if fehler}
            <ErrorBanner message={fehler} />
        {/if}

        {#if laeuft}
            <p class="inline-flex items-center gap-2 text-sm text-light-tx-2 dark:text-dark-tx-2" role="status">
                <Loader2 class="w-4 h-4 animate-spin" />
                {vorgang === "anlegen" ? "Entwürfe werden angelegt …" : "Dateien werden geprüft …"}
                {#if dateien.length > 10}(bei {dateien.length} Dateien bis zu einer Minute){/if}
            </p>
        {/if}

        {#if ergebnis}
            <SuccessBanner message={ergebnisText(ergebnis.zahlen)} />
            <ul class="space-y-1 text-sm">
                {#each ergebnis.dateien as d (d.datei)}
                    <li>
                        {#if d.id}
                            <a href="/knowledge/curriculum/{d.id}" class="text-light-bl dark:text-dark-bl hover:underline">{d.curriculum.titel}</a>
                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">· {d.datei} · {artText(d)}</span>
                        {:else}
                            <span class="text-light-tx dark:text-dark-tx">{d.datei}</span>
                            {@render meldungen(d)}
                        {/if}
                    </li>
                {/each}
            </ul>
        {:else if vorschau}
            <div class="overflow-x-auto">
                <table class="w-full text-sm text-left">
                    <thead class="text-xs text-light-tx-2 dark:text-dark-tx-2 border-b border-light-ui-3 dark:border-dark-ui-3">
                        <tr>
                            <th class={zelle}>Datei</th>
                            <th class={zelle}>Curriculum</th>
                            <th class={zelle}>Umfang</th>
                            <th class={zelle}>Was entsteht</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each vorschau.dateien as d (d.datei)}
                            <tr class="border-b border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx">
                                <td class="{zelle} font-mono text-xs break-all">{d.datei}</td>
                                <td class={zelle}>
                                    {#if d.curriculum}
                                        {d.curriculum.titel}
                                        <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">
                                            {d.curriculum.fach} · Klasse {d.curriculum.jahrgangsstufe} · Fassung {d.curriculum.bp_version}
                                        </span>
                                        {#if d.curriculum.quelle}
                                            <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">Quelle: {d.curriculum.quelle}</span>
                                        {/if}
                                    {/if}
                                    {@render meldungen(d)}
                                </td>
                                <td class="{zelle} text-xs text-light-tx-2 dark:text-dark-tx-2">{summenText(d.summen)}</td>
                                <td class="{zelle} text-xs {d.ok ? '' : 'text-light-re dark:text-dark-re'}">{artText(d)}</td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
            {#if !knopfText}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Keine Datei ist fehlerfrei — es gibt nichts anzulegen.</p>
            {/if}
        {/if}

        <div class="flex justify-end gap-2 pt-2">
            {#if ergebnis}
                <button type="button" onclick={schliessen}
                        class="{knopf} bg-primary dark:bg-primary-dark text-on-fill hover:opacity-90">Schließen</button>
            {:else}
                <button type="button" onclick={schliessen}
                        class="{knopf} border border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2">
                    Abbrechen
                </button>
                {#if knopfText}
                    <button type="button" onclick={anlegen} disabled={laeuft}
                            class="{knopf} inline-flex items-center gap-1.5 bg-primary dark:bg-primary-dark text-on-fill hover:opacity-90">
                        <FilePlus class="w-4 h-4" /> {knopfText}
                    </button>
                {/if}
            {/if}
        </div>
    </div>
</Dialog>
