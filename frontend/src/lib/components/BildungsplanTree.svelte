<script>
    import { goto, beforeNavigate } from "$app/navigation";
    import { tick } from "svelte";
    import { page } from "$app/stores";
    import { getFachplanBySubject } from "$lib/api.js";
    import NodeTypeIcon from "./NodeTypeIcon.svelte";
    import LoadingBanner from "./LoadingBanner.svelte";
    import ErrorBanner from "./ErrorBanner.svelte";
    import InfoBanner from "./InfoBanner.svelte";
    import { ChevronDown, ChevronRight, ExternalLink } from "lucide-svelte";

    let { subjectId, subjectSlug, initialBpVersion = null } = $props();

    let data = $state(null);
    let loading = $state(false);
    let error = $state(null);
    let rootEl = $state(null);

    // Ausgewähltes Band (Objekt mit min_grade/max_grade/niveau/label)
    let selectedBand = $state(null);
    // Ausgewählte BP-Version (null = aktuellste nehmen)
    let selectedVersion = $state(initialBpVersion);

    // Ansicht: 'ik' = Inhaltsbezogene Kompetenzen, 'pk' = Prozessbezogene Kompetenzen
    let view = $state('ik');

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

    // ── UI-Zustand über die Knoten-Detailansicht hinweg erhalten ──────────────
    // Beim Öffnen einer Kompetenz (Detailseite) sichern wir Tab, Band, Version,
    // Aufklapp-Zustand und Scroll-Position in sessionStorage (pro Fach); bei der
    // Rückkehr (?back= → education-plans?subject=) wird der Zustand wiederher-
    // gestellt, statt auf den Default (IK, ganz oben) zu springen.
    const stateKey = (sid) => `bptree:${sid}`;

    function scrollContainer() {
        return rootEl?.closest(".overflow-y-auto") ?? null;
    }

    function saveTreeState() {
        if (typeof sessionStorage === "undefined" || !subjectId) return;
        try {
            sessionStorage.setItem(stateKey(subjectId), JSON.stringify({
                view, selectedBand, selectedVersion,
                expandedLeitideen, expandedPkGruppen,
                scrollTop: scrollContainer()?.scrollTop ?? 0,
            }));
        } catch { /* sessionStorage nicht verfügbar → ohne Wiederherstellung */ }
    }

    function readTreeState(sid) {
        if (typeof sessionStorage === "undefined" || !sid) return null;
        try {
            const raw = sessionStorage.getItem(stateKey(sid));
            return raw ? JSON.parse(raw) : null;
        } catch { return null; }
    }

    async function restoreScroll(top) {
        if (!top) return;
        await tick();
        const sc = scrollContainer();
        if (sc) sc.scrollTop = top;
    }

    // Vor dem Öffnen einer Knoten-Detailseite (/knowledge/<uuid>) Zustand sichern —
    // greift für Klick-Handler (goto) UND direkte <a href>-Links gleichermaßen.
    // Knoten-IDs sind UUIDs (nicht numerisch); benannte Unterseiten (archive,
    // education-plans …) matchen bewusst nicht.
    beforeNavigate((nav) => {
        const path = nav.to?.url.pathname ?? "";
        if (/^\/knowledge\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.test(path)) {
            saveTreeState();
        }
    });

    // Erstladen bei Mount / Fachwechsel — mit Wiederherstellung gesicherten Zustands.
    let lastLoadedSubject = null;
    $effect(() => {
        if (!subjectId || subjectId === lastLoadedSubject) return;
        lastLoadedSubject = subjectId;
        initForSubject(subjectId);
    });

    function initForSubject(sid) {
        const saved = readTreeState(sid);
        if (saved) {
            // Einmalig verbrauchen: nur die unmittelbare Rückkehr stellt wieder her;
            // ein späterer Fachwechsel startet wieder beim Default.
            try { sessionStorage.removeItem(stateKey(sid)); } catch { /* egal */ }
            view = saved.view ?? "ik";
            selectedBand = saved.selectedBand ?? null;
            selectedVersion = saved.selectedVersion ?? selectedVersion;
            expandedLeitideen = saved.expandedLeitideen ?? {};
            expandedPkGruppen = saved.expandedPkGruppen ?? {};
            load(selectedBand, selectedVersion).then(() => restoreScroll(saved.scrollTop));
        } else {
            selectedBand = null;
            view = "ik";
            load(null, selectedVersion);
        }
    }

    // Band-Wechsel → neu laden, IK-Ansicht aktivieren
    function selectBand(band) {
        selectedBand = band;
        view = 'ik';
        load(band, selectedVersion);
    }

    // Versions-Wechsel → Band + Ansicht zurücksetzen + neu laden
    function selectVersion(version) {
        selectedVersion = version;
        selectedBand = null;
        view = 'ik';
        load(null, version);
    }

    function selectPk() {
        view = 'pk';
    }

    function navigateToNode(nodeId) {
        goto(nodeHref(nodeId));
    }

    function nodeHref(nodeId) {
        const back = $page.url.pathname + $page.url.search;
        return `/knowledge/${nodeId}?back=${encodeURIComponent(back)}`;
    }
</script>

<div class="space-y-6" bind:this={rootEl}>
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

        <!-- Band-Leiste + PK-Button -->
        {#if data.bands && data.bands.length > 0}
            <div class="flex flex-wrap gap-2 items-center">
                {#each data.bands as band}
                    <button
                        onclick={() => selectBand(band)}
                        class="px-3 py-1.5 text-sm rounded-md border transition-colors
                               {view === 'ik' && isSameBand(selectedBand, band)
                                   ? 'border-primary dark:border-primary-dark bg-primary/10 dark:bg-primary-dark/10 text-primary dark:text-primary-dark font-medium'
                                   : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:border-primary dark:hover:border-primary-dark'}"
                    >
                        {band.label}
                    </button>
                {/each}
                {#if data.pk_gruppen?.length > 0}
                    <span class="text-light-ui-3 dark:text-dark-ui-3 select-none">|</span>
                    <button
                        onclick={selectPk}
                        title="Prozessbezogene Kompetenzen"
                        class="px-3 py-1.5 text-sm rounded-md border transition-colors
                               {view === 'pk'
                                   ? 'border-primary dark:border-primary-dark bg-primary/10 dark:bg-primary-dark/10 text-primary dark:text-primary-dark font-medium'
                                   : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:border-primary dark:hover:border-primary-dark'}"
                    >
                        PK
                    </button>
                {/if}
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
        {#if !loading && view === 'ik'}
            {#if data.leitideen && data.leitideen.length > 0}
                <div class="space-y-2">
                    <h3 class="text-sm font-semibold uppercase tracking-wide
                               text-light-tx-2 dark:text-dark-tx-2 mb-2">
                        Inhaltsbezogene Kompetenzen
                    </h3>
                    {#each data.leitideen as leitidee (leitidee.id)}
                        {@render renderLeitidee(leitidee, 0)}
                    {/each}
                </div>
            {:else}
                <InfoBanner message={selectedBand
                    ? `Für ${selectedBand.label} sind keine Kompetenzen hinterlegt.`
                    : 'Keine Bildungsplan-Daten verfügbar.'
                } />
            {/if}
        {/if}

        <!-- Prozessbezogene Kompetenzen -->
        {#if !loading && view === 'pk'}
            {#if data.pk_gruppen && data.pk_gruppen.length > 0}
                <div class="space-y-2">
                    <h3 class="text-sm font-semibold uppercase tracking-wide
                               text-light-tx-2 dark:text-dark-tx-2 mb-2">
                        Prozessbezogene Kompetenzen
                    </h3>
                    {#each data.pk_gruppen as pkGruppe (pkGruppe.id)}
                        <div class="border border-light-ui-3 dark:border-dark-ui-3 rounded-md overflow-hidden">
                            <div
                                class="w-full flex items-center justify-between gap-3
                                       bg-light-bg-2 dark:bg-dark-bg-2
                                       hover:bg-light-bg-3 dark:hover:bg-dark-bg-3 transition-colors"
                            >
                                <div class="flex items-center gap-2 min-w-0 pl-3">
                                    <button
                                        onclick={() => togglePkGruppe(pkGruppe.id)}
                                        class="flex items-center gap-3 min-w-0 py-3 text-left
                                               text-light-tx dark:text-dark-tx"
                                    >
                                        <NodeTypeIcon contentType="pk_gruppe" size={18} />
                                        <span class="font-medium truncate">{pkGruppe.title}</span>
                                    </button>
                                    <a
                                        href={nodeHref(pkGruppe.id)}
                                        title="Knotenansicht öffnen"
                                        class="shrink-0 p-1 rounded text-light-tx-2 dark:text-dark-tx-2
                                               hover:text-primary dark:hover:text-dark-bl transition-colors"
                                    >
                                        <ExternalLink class="w-4 h-4" />
                                    </a>
                                </div>
                                <button
                                    onclick={() => togglePkGruppe(pkGruppe.id)}
                                    class="flex items-center gap-2 py-3 pr-3 pl-2 shrink-0
                                           text-light-tx dark:text-dark-tx"
                                >
                                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                        {pkGruppe.pk_kompetenzen?.length || 0} Kompetenzen
                                    </span>
                                    {#if expandedPkGruppen[pkGruppe.id]}
                                        <ChevronDown class="w-4 h-4 shrink-0" />
                                    {:else}
                                        <ChevronRight class="w-4 h-4 shrink-0" />
                                    {/if}
                                </button>
                            </div>
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
            {:else}
                <InfoBanner message="Keine prozessbezogenen Kompetenzen verfügbar." />
            {/if}
        {/if}
    {/if}
</div>

{#snippet renderLeitidee(ld, depth)}
    <div class="border border-light-ui-3 dark:border-dark-ui-3 rounded-md overflow-hidden"
         style="margin-left: {depth * 16}px">
        <div
            class="w-full flex items-center justify-between gap-3
                   bg-light-bg-2 dark:bg-dark-bg-2
                   hover:bg-light-bg-3 dark:hover:bg-dark-bg-3 transition-colors"
        >
            <div class="flex items-center gap-2 min-w-0 pl-3">
                <button
                    onclick={() => toggleLeitidee(ld.id)}
                    class="flex items-center gap-3 min-w-0 py-3 text-left
                           text-light-tx dark:text-dark-tx"
                >
                    <NodeTypeIcon contentType="leitidee" size={18} />
                    <span class="font-medium truncate">{ld.title}</span>
                </button>
                <a
                    href={nodeHref(ld.id)}
                    title="Knotenansicht öffnen"
                    class="shrink-0 p-1 rounded text-light-tx-2 dark:text-dark-tx-2
                           hover:text-primary dark:hover:text-dark-bl transition-colors"
                >
                    <ExternalLink class="w-4 h-4" />
                </a>
            </div>
            <button
                onclick={() => toggleLeitidee(ld.id)}
                class="flex items-center gap-2 py-3 pr-3 pl-2 shrink-0
                       text-light-tx dark:text-dark-tx"
            >
                <!-- Zähler nur anzeigen wenn Kompetenzen vorhanden; bei reinem Beschreibungstext weglassen -->
                {#if countIk(ld) > 0}
                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                        {countIk(ld)} Kompetenzen
                    </span>
                {/if}
                {#if expandedLeitideen[ld.id]}
                    <ChevronDown class="w-4 h-4 shrink-0" />
                {:else}
                    <ChevronRight class="w-4 h-4 shrink-0" />
                {/if}
            </button>
        </div>

        {#if expandedLeitideen[ld.id]}
            <!-- Beschreibungstext der Leitidee (oberhalb der Kompetenzen) -->
            {#if ld.content}
                <div class="px-3 pt-3 pb-1">
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 whitespace-pre-line leading-relaxed">
                        {ld.content}
                    </p>
                </div>
            {/if}
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
