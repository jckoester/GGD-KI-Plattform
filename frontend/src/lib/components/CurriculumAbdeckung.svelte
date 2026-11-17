<script>
    /**
     * Abdeckung der Kompetenzen des Bands (0.45, Päckchen AP Teil A) — aufklappbar über der
     * Curriculum-Tabelle, in Ansicht und Editor. Zeigt den gespeicherten Stand; `stand` ist das
     * geladene Curriculum, ein neues Objekt (nach dem Speichern) lädt neu.
     */
    import { getCurriculumAbdeckung } from "$lib/api.js";
    import WarningBanner from "$lib/components/WarningBanner.svelte";
    import { abdeckungUeberschrift, gefilterteGruppen, ZUSTAND } from "$lib/curriculum_abdeckung.js";
    import { abdeckungsPfad } from "$lib/curriculum_baender.js";

    let { curriculumId = null, stand = null, editMode = false, fachId = null } = $props();

    let abdeckung = $state(null);
    let fehler = $state(null);
    let nurLuecken = $state(true);

    $effect(() => {
        void stand;
        if (!curriculumId) return;
        let abgebrochen = false;
        getCurriculumAbdeckung(curriculumId)
            .then((a) => {
                if (!abgebrochen) {
                    abdeckung = a;
                    fehler = null;
                }
            })
            .catch((e) => {
                if (!abgebrochen) fehler = e.message;
            });
        return () => {
            abgebrochen = true;
        };
    });

    const ikGruppen = $derived(gefilterteGruppen(abdeckung?.ik.gruppen, nurLuecken));
</script>

{#if fehler}
    <p class="mb-3 text-xs text-light-re dark:text-dark-re">{fehler}</p>
{:else if abdeckung}
    <details
        class="mb-3 rounded-md border border-light-ui-3 dark:border-dark-ui-3 px-3 py-2 text-sm"
        data-uebersicht="abdeckung"
    >
        <summary class="cursor-pointer text-light-tx dark:text-dark-tx">
            {abdeckungUeberschrift(abdeckung)}
        </summary>
        <div class="mt-2 space-y-3">
            {#if abdeckung.hinweis}
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">{abdeckung.hinweis}</p>
            {/if}
            {#if abdeckung.band && fachId}
                <!-- Bandsicht (0.46, Schritt 8): ein Band verteilt sich oft auf mehrere Curricula. -->
                <a
                    href={abdeckungsPfad({ fachId, fassung: abdeckung.bp_version, band: abdeckung.band.schluessel })}
                    class="inline-block text-xs text-light-bl dark:text-dark-bl hover:underline"
                >
                    {abdeckung.band.schluessel}: Abdeckung über alle Curricula des Bands
                </a>
            {/if}
            {#if abdeckung.ik.gesamt}
                <div class="flex flex-wrap items-center gap-3 text-xs text-light-tx-2 dark:text-dark-tx-2">
                    <span>
                        Inhaltsbezogene Kompetenzen, BP {abdeckung.bp_version}{abdeckung.min_grade
                            ? `, Klasse ${abdeckung.min_grade}${abdeckung.max_grade !== abdeckung.min_grade ? `–${abdeckung.max_grade}` : ""}`
                            : ""}
                    </span>
                    <label class="inline-flex items-center gap-1">
                        <input type="checkbox" bind:checked={nurLuecken} /> nur Lücken
                    </label>
                    {#if editMode}
                        <span>Zeigt den gespeicherten Stand.</span>
                    {/if}
                </div>
                {#each ikGruppen as g (g.titel)}
                    <div>
                        {#if g.titel}
                            <p class="text-xs font-medium text-light-tx dark:text-dark-tx">{g.titel}</p>
                        {/if}
                        <ul class="text-xs space-y-0.5">
                            {#each g.kompetenzen as k (k.node_id)}
                                <li class="text-light-tx dark:text-dark-tx" data-zustand={k.zustand}>
                                    <span class={ZUSTAND[k.zustand].klasse}>{ZUSTAND[k.zustand].text}</span>
                                    · <span class="font-medium">{k.nr}</span>
                                    {k.titel}
                                    {#if k.lernsequenzen.length}
                                        <span class="text-light-tx-2 dark:text-dark-tx-2">
                                            — {k.lernsequenzen.join("; ")}
                                        </span>
                                    {/if}
                                    {#if k.anderswo}
                                        <span class="text-light-tx-2 dark:text-dark-tx-2">
                                            — in {k.anderswo.join(", ")}
                                        </span>
                                    {/if}
                                </li>
                            {/each}
                        </ul>
                    </div>
                {:else}
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">Alle Kompetenzen des Bands sind verknüpft.</p>
                {/each}
            {/if}
            {#if abdeckung.fremdes_fach.length}
                <div data-abschnitt="fremdes-fach">
                    <WarningBanner
                        message="Diese Kompetenzen gehören zu einem anderen Fach — vermutlich beim Import falsch zugeordnet. Bitte im Editor ersetzen oder die Schul-IT um die Reparatur bitten."
                    />
                    <ul class="mt-1 text-xs space-y-0.5">
                        {#each abdeckung.fremdes_fach as k (k.node_id)}
                            <li class="text-light-tx dark:text-dark-tx">
                                {k.typ.toUpperCase()} <span class="font-medium">{k.nr}</span> {k.titel}
                                <span class="text-light-tx-2 dark:text-dark-tx-2">
                                    — {k.fach}, BP {k.bp_version} — {k.lernsequenzen.join("; ")}
                                </span>
                            </li>
                        {/each}
                    </ul>
                </div>
            {/if}
            {#if abdeckung.ausserhalb.length}
                <div>
                    <p class="text-xs font-medium text-light-tx dark:text-dark-tx">
                        Verknüpft, aber nicht aus diesem Band oder dieser Fassung
                    </p>
                    <ul class="text-xs space-y-0.5">
                        {#each abdeckung.ausserhalb as k (k.node_id)}
                            <li class="text-light-tx-2 dark:text-dark-tx-2">
                                {k.typ.toUpperCase()} <span class="font-medium">{k.nr}</span> {k.titel} (BP {k.bp_version})
                            </li>
                        {/each}
                    </ul>
                </div>
            {/if}
            {#if abdeckung.pk.gesamt}
                <div>
                    <p class="text-xs font-medium text-light-tx dark:text-dark-tx">
                        Prozessbezogene Kompetenzen — gefördert in wie vielen Lernsequenzen
                    </p>
                    {#if fachId && abdeckung.bp_version}
                        <!-- Schritt 9: Ein Curriculum fördert nie alle PK; zählen tut die Fassung. -->
                        <a
                            href={abdeckungsPfad({ fachId, fassung: abdeckung.bp_version })}
                            class="inline-block text-xs text-light-bl dark:text-dark-bl hover:underline"
                        >
                            Über alle Curricula der Fassung
                        </a>
                    {/if}
                    {#each abdeckung.pk.gruppen as g (g.titel)}
                        <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">{g.titel}</p>
                        <ul class="text-xs space-y-0.5">
                            {#each g.kompetenzen as k (k.node_id)}
                                <li class={k.anzahl ? "text-light-tx dark:text-dark-tx" : "text-light-tx-2 dark:text-dark-tx-2"}>
                                    <span class="font-medium">{k.nr}</span> {k.titel} — {k.anzahl}×
                                </li>
                            {/each}
                        </ul>
                    {/each}
                </div>
            {/if}
        </div>
    </details>
{/if}
