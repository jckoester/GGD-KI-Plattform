<script>
    /**
     * Curriculum aus YAML importieren (0.56, Päckchen BA Schritt 4).
     *
     * Datei wählen oder Text einfügen → *Prüfen* → Vorschau (Fehler, Warnungen, Gliederung,
     * Ersatz) → *Als Entwurf anlegen* → Editor des Entwurfs. Die Vorschau ist der echte Import,
     * danach verworfen — was sie zeigt, legt *Anlegen* an. Ändert sich Text oder Wahl, muss neu
     * geprüft werden. Die Regeln stehen in `$lib/curriculum_yaml_import.js`.
     */
    import { goto } from "$app/navigation";
    import { FileUp, Loader2 } from "@lucide/svelte";
    import { importiereCurriculumYaml, pruefeCurriculumYaml } from "$lib/api.js";
    import { dateiLesen, ersetzbar, kannAnlegen, summenText, vorauswahl } from "$lib/curriculum_yaml_import.js";
    import Dialog from "$lib/components/Dialog.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";

    let { onClose } = $props();

    let text = $state("");
    let vorschau = $state(null);
    let ersetzen = $state(null);
    /** Text und Wahl, zu denen die Vorschau gehört. */
    let geprueft = $state(null);
    let fehler = $state(null);
    let laeuft = $state(false);

    const geaendert = $derived(geprueft === null || geprueft.text !== text || geprueft.ersetzen !== ersetzen);
    const anlegbar = $derived(kannAnlegen(vorschau, { geaendert }));
    const kandidaten = $derived(ersetzbar(vorschau));
    const blockiert = $derived((vorschau?.vorhanden ?? []).filter((v) => v.offener_entwurf));

    async function dateiGewaehlt(e) {
        const datei = e.target.files?.[0];
        const gelesen = await dateiLesen(datei);
        fehler = gelesen.fehler;
        if (!gelesen.fehler) text = gelesen.text;
    }

    async function pruefen({ ersteMal = false } = {}) {
        laeuft = true;
        fehler = null;
        try {
            let v = await pruefeCurriculumYaml(text, ersteMal ? null : ersetzen);
            let wahl = ersteMal ? null : ersetzen;
            // Beim ersten Prüfen kennt der Dialog die vorhandenen Curricula noch nicht. Gibt es
            // genau eins zum Ersetzen, ist es vorausgewählt (F2) — und die Vorschau dazu gilt.
            if (ersteMal && v.ok && (wahl = vorauswahl(v)) !== null) {
                v = await pruefeCurriculumYaml(text, wahl);
            }
            vorschau = v;
            ersetzen = wahl;
            geprueft = { text, ersetzen: wahl };
        } catch (e) {
            fehler = e.message;
        } finally {
            laeuft = false;
        }
    }

    async function anlegen() {
        laeuft = true;
        fehler = null;
        try {
            const ergebnis = await importiereCurriculumYaml(text, ersetzen);
            if (ergebnis.id) {
                goto(`/knowledge/curriculum/${ergebnis.id}/edit`);
                onClose?.();
                return;
            }
            vorschau = ergebnis;
        } catch (e) {
            fehler = e.message;
        } finally {
            laeuft = false;
        }
    }

    const knopf = "px-3 py-1.5 rounded text-sm font-medium transition-colors disabled:opacity-50";
</script>

<Dialog open {onClose} titelId="yaml-import-titel" breite="max-w-2xl max-h-[90vh] overflow-y-auto mx-4">
    <div class="space-y-4">
        <h2 id="yaml-import-titel" class="text-lg font-semibold text-light-tx dark:text-dark-tx">
            Curriculum aus YAML importieren
        </h2>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Daraus entsteht ein <strong>Entwurf</strong>. Sichtbar für alle wird er erst, wenn deine
            Fachschaft ihn veröffentlicht. Vorhandene Curricula bleiben unverändert.
        </p>

        <div class="space-y-2">
            <label class="inline-flex items-center gap-2 text-sm text-light-bl dark:text-dark-bl cursor-pointer">
                <FileUp class="w-4 h-4" />
                <span>Datei wählen (.yaml)</span>
                <input type="file" accept=".yaml,.yml,text/yaml" class="sr-only" onchange={dateiGewaehlt} />
            </label>
            <textarea
                bind:value={text}
                rows="8"
                spellcheck="false"
                aria-label="YAML-Text"
                placeholder="… oder den YAML-Text hier einfügen"
                class="w-full font-mono text-xs p-2 rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
            ></textarea>
        </div>

        {#if fehler}
            <ErrorBanner message={fehler} />
        {/if}

        {#if vorschau}
            {#if vorschau.fehler?.length}
                <div class="space-y-1">
                    <ErrorBanner message="Die Datei lässt sich so nicht importieren:" />
                    <ul class="list-disc pl-6 text-sm text-light-re dark:text-dark-re">
                        {#each vorschau.fehler as f, i (i)}<li>{f}</li>{/each}
                    </ul>
                </div>
            {/if}
            {#if vorschau.ok}
                <div class="rounded border border-light-ui-3 dark:border-dark-ui-3 p-3 space-y-2">
                    <p class="text-sm font-medium text-light-tx dark:text-dark-tx">
                        {vorschau.curriculum.titel}
                        <span class="font-normal text-light-tx-2 dark:text-dark-tx-2">
                            · Klasse {vorschau.curriculum.jahrgangsstufe} · Fassung {vorschau.curriculum.bp_version}
                        </span>
                    </p>
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">{summenText(vorschau.summen)}</p>
                    <ol class="text-sm space-y-0.5 list-decimal pl-5 text-light-tx dark:text-dark-tx">
                        {#each vorschau.kapitel as k, i (i)}
                            <li>
                                {k.titel}
                                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    {#if k.std}· {k.std} Std.{/if}
                                    · {k.lernsequenzen} LS · {k.eintraege} Einträge
                                    {#if ersetzen && !k.ersetzt_kapitel}· neues Kapitel{/if}
                                </span>
                            </li>
                        {/each}
                    </ol>
                </div>
            {/if}

            {#if vorschau.vorhanden?.length}
                <fieldset class="space-y-1.5">
                    <legend class="text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
                        Zu Fach, Klasse und Fassung gibt es schon ein veröffentlichtes Curriculum
                    </legend>
                    {#each kandidaten as k (k.id)}
                        <label class="flex items-start gap-2 text-sm text-light-tx dark:text-dark-tx">
                            <input type="radio" name="ersetzen" value={k.id} bind:group={ersetzen} class="mt-1" />
                            <span>
                                Ersetzt beim Veröffentlichen „{k.titel}“{#if k.band} ({k.band}){/if}
                                <span class="block text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    Einheiten an gleichnamigen Kapiteln wandern mit.
                                </span>
                            </span>
                        </label>
                    {/each}
                    <label class="flex items-start gap-2 text-sm text-light-tx dark:text-dark-tx">
                        <input type="radio" name="ersetzen" value={null} bind:group={ersetzen} class="mt-1" />
                        <span>Neuer Entwurf, der nichts ersetzt</span>
                    </label>
                    {#each blockiert as b (b.id)}
                        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                            Zu „{b.titel}“ gibt es schon einen
                            <a href={`/knowledge/curriculum/${b.offener_entwurf}`} class="text-light-bl dark:text-dark-bl hover:underline">Entwurf</a>
                            — ersetzen kann nur einer.
                        </p>
                    {/each}
                </fieldset>
            {/if}

            {#if vorschau.warnungen?.length}
                <details class="text-sm">
                    <summary class="cursor-pointer text-light-ye dark:text-dark-ye">
                        {vorschau.warnungen.length} Hinweis{vorschau.warnungen.length === 1 ? "" : "e"} — der Import
                        geht trotzdem; was nicht aufgelöst wird, bleibt ohne Verknüpfung
                    </summary>
                    <ul class="list-disc pl-6 mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2 space-y-0.5">
                        {#each vorschau.warnungen as w, i (i)}<li>{w}</li>{/each}
                    </ul>
                </details>
            {/if}
        {/if}

        <div class="flex justify-end gap-2 pt-2">
            <button type="button" onclick={onClose}
                    class="{knopf} border border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2">
                Abbrechen
            </button>
            <button type="button" disabled={laeuft || !text.trim()}
                    onclick={() => pruefen({ ersteMal: geprueft === null || geprueft.text !== text })}
                    class="{knopf} border border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2">
                {#if laeuft}<Loader2 class="inline w-4 h-4 animate-spin" />{/if}
                {vorschau && geaendert ? "Neu prüfen" : "Prüfen"}
            </button>
            <button type="button" disabled={laeuft || !anlegbar} onclick={anlegen}
                    class="{knopf} bg-primary dark:bg-primary-dark text-on-fill hover:opacity-90">
                Als Entwurf anlegen
            </button>
        </div>
    </div>
</Dialog>
