<script>
    import { goto } from "$app/navigation";
    import { page } from "$app/stores";
    import { getFachplanBySubject } from "$lib/api.js";
    import NodeTypeIcon from "./NodeTypeIcon.svelte";
    import LoadingBanner from "./LoadingBanner.svelte";
    import ErrorBanner from "./ErrorBanner.svelte";
    import InfoBanner from "./InfoBanner.svelte";
    import { ChevronDown, ChevronRight } from "lucide-svelte";

    let { subjectId, subjectSlug, initialBpVersion = null } = $props();

    let data = $state(null);
    let loading = $state(false);
    let error = $state(null);

    // Ausgewähltes Band (Objekt mit min_grade/max_grade/niveau/label)
    let selectedBand = $state(null);
    // Ausgewählte BP-Version (null = aktuellste nehmen)
    let selectedVersion = $state(initialBpVersion);

    // Accordion-Zustände
    let expandedLeitideen = $state({});
    let expandedPkGruppen = $state({});

    function toggleLeitidee(id) {
        expandedLeitideen = { ...expandedLeitideen, [id]: !expandedLeitideen[id] };
    }
    function togglePkGruppe(id) {
        expandedPkGruppen = { ...expandedPkGruppen, [id]: !expandedPkGruppen[id] };
    }

    function isSameBand(a, b) {
        if (!a || !b) return false;
        return a.min_grade === b.min_grade && a.max_grade === b.max_grade && a.niveau === b.niveau;
    }

    // IK-Zähler über den gesamten Leitideen-Teilbaum
    function countIk(ld) {
        return (ld.ik_kompetenzen?.length ?? 0) +
            (ld.unter_leitideen ?? []).reduce((s, u) => s + countIk(u), 0);
    }

    async function load(band = null, bpVersion = null) {
        loading = true;
        error = null;
        try {
            data = await getFachplanBySubject(subjectId, band, bpVersion);
            // Band aus Response übernehmen falls noch keins gesetzt
            if (!selectedBand && data?.selected_band) {
                selectedBand = data.selected_band;
            }
            // BP-Version aus Response übernehmen
            if (!selectedVersion && data?.bp_version) {
                selectedVersion = data.bp_version;
            }
        } catch (e) {
            error = e.message || "Fehler beim Laden des Bildungsplans";
            data = null;
        } finally {
            loading = false;
        }
    }

    // Erstladen bei Mount / subjectId-Wechsel
    $effect(() => {
        if (subjectId) {
            selectedBand = null;
            load(null, selectedVersion);
        }
    });

    // Band-Wechsel → neu laden (nur wenn bereits Daten vorhanden)
    function selectBand(band) {
        selectedBand = band;
        load(band, selectedVersion);
    }

    // Versions-Wechsel → Band zurücksetzen + neu laden
    function selectVersion(version) {
        selectedVersion = version;
        selectedBand = null;
        load(null, version);
    }

    function navigateToNode(nodeId) {
        const back = $page.url.pathname + $page.url.search;
        goto(`/knowledge/${nodeId}?back=${encodeURIComponent(back)}`);
    }
</script>

<div class="space-y-6">
    {#if loading && !data}
        <LoadingBanner message="Bildungsplan wird geladen…" />
    {/if}
    {#if error}
        <ErrorBanner message={error} />
    {/if}

    {#if data && !data.fachplan}
        <InfoBanner message="Kein Bildungsplan für dieses Fach verfügbar." />
    {:else if data}
        <!-- BP-Versions-Auswahl (nur wenn mehrere Editionen vorhanden) -->
        {#if data.available_versions && data.available_versions.length > 1}
            <div class="flex flex-wrap gap-2">
                {#each data.available_versions as version}
                    <button
                        onclick={() => selectVersion(version)}
                        class="px-3 py-1 text-sm rounded-md border transition-colors
                               {selectedVersion === version
                                   ? 'border-primary dark:border-primary-dark bg-primary/10 dark:bg-primary-dark/10 text-primary dark:text-primary-dark font-medium'
                                   : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 hover:border-primary dark:hover:border-primary-dark'}"
                    >
                        BP {version}
                    </button>
                {/each}
            </div>
        {/if}

        <!-- Band-Leiste (ersetzt Klassen-Chips) -->
        {#if data.bands && data.bands.length > 0}
            <div class="flex flex-wrap gap-2">
                {#each data.bands as band}
                    <button
                        onclick={() => selectBand(band)}
                        class="px-3 py-1.5 text-sm rounded-md border transition-colors
                               {isSameBand(selectedBand, band)
                                   ? 'border-primary dark:border-primary-dark bg-primary/10 dark:bg-primary-dark/10 text-primary dark:text-primary-dark font-medium'
                                   : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:border-primary dark:hover:border-primary-dark'}"
                    >
                        {band.label}
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

        <!-- Ladeindikator bei Band-Wechsel (Daten bereits vorhanden) -->
        {#if loading && data}
            <LoadingBanner message="Wird geladen…" />
        {/if}

        <!-- Inhaltsbezogene Kompetenzen -->
        {#if !loading && data.leitideen && data.leitideen.length > 0}
            <div class="space-y-2">
                <h3 class="text-sm font-semibold uppercase tracking-wide
                           text-light-tx-2 dark:text-dark-tx-2 mb-2">
                    Inhaltsbezogene Kompetenzen
                </h3>
                {#each data.leitideen as leitidee (leitidee.id)}
                    {@render renderLeitidee(leitidee, 0)}
                {/each}
            </div>
        {/if}

        <!-- Prozessbezogene Kompetenzen -->
        {#if !loading && data.pk_gruppen && data.pk_gruppen.length > 0}
            <div class="space-y-2">
                <h3 class="text-sm font-semibold uppercase tracking-wide
                           text-light-tx-2 dark:text-dark-tx-2 mb-2">
                    Prozessbezogene Kompetenzen
                </h3>
                {#each data.pk_gruppen as pkGruppe (pkGruppe.id)}
                    <div class="border border-light-ui-3 dark:border-dark-ui-3 rounded-md overflow-hidden">
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
                        {#if expandedPkGruppen[pkGruppe.id] && pkGruppe.pk_kompetenzen?.length > 0}
                            <div class="p-3 space-y-1">
                                {#each pkGruppe.pk_kompetenzen as pk (pk.id)}
                                    <button
                                        onclick={() => navigateToNode(pk.id)}
                                        class="w-full flex items-center gap-3 p-2 rounded
                                               hover:bg-light-bg-2 dark:hover:bg-dark-bg-2
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

        {#if !loading && (!data.leitideen?.length) && (!data.pk_gruppen?.length)}
            <InfoBanner message={selectedBand
                ? `Für ${selectedBand.label} sind keine Kompetenzen hinterlegt.`
                : 'Keine Bildungsplan-Daten verfügbar.'
            } />
        {/if}
    {/if}
</div>

{#snippet renderLeitidee(ld, depth)}
    <div class="border border-light-ui-3 dark:border-dark-ui-3 rounded-md overflow-hidden"
         style="margin-left: {depth * 16}px">
        <button
            onclick={() => toggleLeitidee(ld.id)}
            class="w-full flex items-center justify-between p-3 gap-3
                   bg-light-bg-2 dark:bg-dark-bg-2
                   text-light-tx dark:text-dark-tx hover:bg-light-bg-3 dark:hover:bg-dark-bg-3
                   transition-colors"
        >
            <div class="flex items-center gap-3">
                <NodeTypeIcon contentType="leitidee" size={18} />
                <span class="font-medium">{ld.title}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                    {countIk(ld)} Kompetenzen
                </span>
                {#if expandedLeitideen[ld.id]}
                    <ChevronDown class="w-4 h-4 shrink-0" />
                {:else}
                    <ChevronRight class="w-4 h-4 shrink-0" />
                {/if}
            </div>
        </button>

        {#if expandedLeitideen[ld.id]}
            <!-- Direkte IK-Kompetenzen -->
            {#if ld.ik_kompetenzen?.length > 0}
                <div class="p-3 space-y-1">
                    {#each ld.ik_kompetenzen as ik (ik.id)}
                        <button
                            onclick={() => navigateToNode(ik.id)}
                            class="w-full flex items-center gap-3 p-2 rounded
                                   hover:bg-light-bg-2 dark:hover:bg-dark-bg-2
                                   text-light-tx dark:text-dark-tx text-sm transition-colors"
                        >
                            <NodeTypeIcon contentType="ik_kompetenz" size={16} />
                            <span class="flex-1 text-left">{ik.title}</span>
                        </button>
                    {/each}
                </div>
            {/if}
            <!-- Unter-Leitideen (rekursiv) -->
            {#if ld.unter_leitideen?.length > 0}
                <div class="p-2 space-y-2">
                    {#each ld.unter_leitideen as unter (unter.id)}
                        {@render renderLeitidee(unter, depth + 1)}
                    {/each}
                </div>
            {/if}
        {/if}
    </div>
{/snippet}
