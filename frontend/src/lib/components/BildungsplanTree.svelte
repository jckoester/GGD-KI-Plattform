<script>
    import { goto } from "$app/navigation";
    import { page } from "$app/stores";
    import { getFachplanBySubject } from "$lib/api.js";
    import NodeTypeIcon from "./NodeTypeIcon.svelte";
    import LoadingBanner from "./LoadingBanner.svelte";
    import ErrorBanner from "./ErrorBanner.svelte";
    import { ChevronDown, ChevronRight } from "lucide-svelte";

    let { subjectId, subjectSlug, initialGrade = null } = $props();

    // Lade-States
    let data = $state(null);
    let loading = $state(false);
    let error = $state(null);

    // Ausgewählte Stufe — Voreinstellung aus Prop oder aus Daten
    const allGrades = JSON.parse(import.meta.env.PUBLIC_STUDENT_GRADES || "[5,6,7,8,9,10,11,12]");
    let selectedGrade = $state(initialGrade);

    // Accordion-Zustände
    let expandedLeitideen = $state({});
    let expandedPkGruppen = $state({});

    // Funktion zum Toggle von Accordion
    function toggleLeitidee(leitideeId) {
        expandedLeitideen = {
            ...expandedLeitideen,
            [leitideeId]: !expandedLeitideen[leitideeId]
        };
    }

    function togglePkGruppe(pkGruppeId) {
        expandedPkGruppen = {
            ...expandedPkGruppen,
            [pkGruppeId]: !expandedPkGruppen[pkGruppeId]
        };
    }

    // Ladefunktion
    async function load(grade = null) {
        loading = true;
        error = null;
        try {
            data = await getFachplanBySubject(subjectId, grade);
            
            // Setze Standard-Stufe: erste verfügbare aus den IK-Kompetenz-grade_bands
            if (!selectedGrade && data && data.leitideen && data.leitideen.length > 0) {
                const firstIk = data.leitideen[0]?.ik_kompetenzen[0];
                const gradeBand = firstIk?.metadata?.grade_band;
                if (gradeBand) {
                    // Extrahiere erste Zahl aus z.B. "5-6"
                    const match = String(gradeBand).match(/(\d+)/);
                    if (match) {
                        selectedGrade = parseInt(match[1]);
                    }
                }
                // Fallback: erste Stufe aus PUBLIC_STUDENT_GRADES
                if (!selectedGrade && allGrades.length > 0) {
                    selectedGrade = allGrades[0];
                }
            }
        } catch (e) {
            error = e.message || "Fehler beim Laden des Bildungsplans";
            data = null;
        } finally {
            loading = false;
        }
    }

    // Lade bei Mount und bei Änderung von subjectId
    $effect(() => {
        if (subjectId) {
            load();
        }
    });

    // Grade-Änderung triggert Neu-Laden
    $effect(() => {
        if (subjectId && selectedGrade !== null) {
            load(selectedGrade);
        }
    });

    // Navigationsfunktion für Knoten-Klicks
    function navigateToNode(nodeId) {
        goto(`/knowledge/${nodeId}?back=${encodeURIComponent($page.url.pathname)}`);
    }
</script>

<div class="space-y-6">
    <!-- Lade-Indikator -->
    {#if loading && !data}
        <LoadingBanner message="Bildungsplan wird geladen…" />
    {/if}

    <!-- Fehler -->
    {#if error}
        <ErrorBanner message={error} />
    {/if}

    <!-- Kein Fachplan verfügbar -->
    {#if data && !data.fachplan}
        <div class="p-4 bg-light-bg-2 dark:bg-dark-bg-2 rounded border 
                    border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2">
            <p>Kein Bildungsplan für dieses Fach verfügbar.</p>
        </div>
    {:else if data}
        <!-- Stufen-Selektor -->
        {#if allGrades.length > 0 && data.leitideen && data.leitideen.length > 0}
            <div class="flex flex-wrap gap-2">
                {#each allGrades as grade}
                    <button
                        onclick={() => selectedGrade = grade}
                        class="px-3 py-1.5 text-sm rounded-md border transition-colors
                               {selectedGrade === grade
                                   ? 'border-primary dark:border-primary-dark bg-primary/10 dark:bg-primary-dark/10 text-primary dark:text-primary-dark font-medium'
                                   : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:border-primary dark:hover:border-primary-dark'}"
                    >
                        Kl. {grade}
                    </button>
                {/each}
            </div>
        {/if}

        <!-- Fachplan-Titel -->
        {#if data.fachplan}
            <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx">
                {data.fachplan.title}
            </h2>
        {/if}

        <!-- Leitideen mit IK-Kompetenz (Accordion) -->
        {#if data.leitideen && data.leitideen.length > 0}
            <div class="space-y-2">
                <h3 class="text-sm font-semibold uppercase tracking-wide 
                       text-light-tx-2 dark:text-dark-tx-2 mb-2">
                    Inhaltsbezogene Kompetenzen
                </h3>
                
                {#each data.leitideen as leitidee (leitidee.id)}
                    <div class="border border-light-ui-3 dark:border-dark-ui-3 rounded-md overflow-hidden">
                        <!-- Leitidee-Header (klickbar für Accordion) -->
                        <button
                            onclick={() => toggleLeitidee(leitidee.id)}
                            class="w-full flex items-center justify-between p-3 gap-3 
                                   bg-light-bg-2 dark:bg-dark-bg-2 
                                   text-light-tx dark:text-dark-tx hover:bg-light-bg-3 dark:hover:bg-dark-bg-3
                                   transition-colors"
                        >
                            <div class="flex items-center gap-3">
                                <NodeTypeIcon contentType="leitidee" size={18} />
                                <span class="font-medium">{leitidee.title}</span>
                            </div>
                            <div class="flex items-center gap-2">
                                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    {leitidee.ik_kompetenzen?.length || 0} Kompetenzen
                                </span>
                                {#if expandedLeitideen[leitidee.id]}
                                    <ChevronDown class="w-4 h-4 shrink-0" />
                                {:else}
                                    <ChevronRight class="w-4 h-4 shrink-0" />
                                {/if}
                            </div>
                        </button>

                        <!-- IK-Kompetenz-Liste (ausgeklappt) -->
                        {#if expandedLeitideen[leitidee.id] && leitidee.ik_kompetenzen && leitidee.ik_kompetenzen.length > 0}
                            <div class="p-3 space-y-1">
                                {#each leitidee.ik_kompetenzen as ik (ik.id)}
                                    <button
                                        onclick={() => navigateToNode(ik.id)}
                                        class="w-full flex items-center gap-3 p-2 rounded hover:bg-light-bg-2 dark:hover:bg-dark-bg-2
                                               text-light-tx dark:text-dark-tx text-sm transition-colors"
                                    >
                                        <NodeTypeIcon contentType="ik_kompetenz" size={16} />
                                        <span class="flex-1 text-left">{ik.title}</span>
                                    </button>
                                {/each}
                            </div>
                        {/if}
                    </div>
                {/each}
            </div>
        {/if}

        <!-- PK-Gruppen mit PK-Kompetenz (Accordion) -->
        {#if data.pk_gruppen && data.pk_gruppen.length > 0}
            <div class="space-y-2">
                <h3 class="text-sm font-semibold uppercase tracking-wide 
                       text-light-tx-2 dark:text-dark-tx-2 mb-2">
                    Prozessbezogene Kompetenzen
                </h3>
                
                {#each data.pk_gruppen as pkGruppe (pkGruppe.id)}
                    <div class="border border-light-ui-3 dark:border-dark-ui-3 rounded-md overflow-hidden">
                        <!-- PK-Gruppe-Header (klickbar für Accordion) -->
                        <button
                            onclick={() => togglePkGruppe(pkGruppe.id)}
                            class="w-full flex items-center justify-between p-3 gap-3 
                                   bg-light-bg-2 dark:bg-dark-bg-2 
                                   text-light-tx dark:text-dark-tx hover:bg-light-bg-3 dark:hover:bg-dark-bg-3
                                   transition-colors"
                        >
                            <div class="flex items-center gap-3">
                                <NodeTypeIcon contentType="pk_gruppe" size={18} />
                                <span class="font-medium">{pkGruppe.title}</span>
                            </div>
                            <div class="flex items-center gap-2">
                                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    {pkGruppe.pk_kompetenzen?.length || 0} Kompetenzen
                                </span>
                                {#if expandedPkGruppen[pkGruppe.id]}
                                    <ChevronDown class="w-4 h-4 shrink-0" />
                                {:else}
                                    <ChevronRight class="w-4 h-4 shrink-0" />
                                {/if}
                            </div>
                        </button>

                        <!-- PK-Kompetenz-Liste (ausgeklappt) -->
                        {#if expandedPkGruppen[pkGruppe.id] && pkGruppe.pk_kompetenzen && pkGruppe.pk_kompetenzen.length > 0}
                            <div class="p-3 space-y-1">
                                {#each pkGruppe.pk_kompetenzen as pk (pk.id)}
                                    <button
                                        onclick={() => navigateToNode(pk.id)}
                                        class="w-full flex items-center gap-3 p-2 rounded hover:bg-light-bg-2 dark:hover:bg-dark-bg-2
                                               text-light-tx dark:text-dark-tx text-sm transition-colors"
                                    >
                                        <NodeTypeIcon contentType="pk_kompetenz" size={16} />
                                        <span class="flex-1 text-left">{pk.title}</span>
                                    </button>
                                {/each}
                            </div>
                        {/if}
                    </div>
                {/each}
            </div>
        {/if}

        <!-- Leere Anzeige wenn keine Daten -->
        {#if data && (!data.leitideen || data.leitideen.length === 0) && (!data.pk_gruppen || data.pk_gruppen.length === 0)}
            <div class="p-4 bg-light-bg-2 dark:bg-dark-bg-2 rounded border 
                        border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2">
                <p>Keine Bildungsplan-Daten verfügbar.</p>
            </div>
        {/if}
    {/if}
</div>
